"""Build references.bib from citations table in Zotero-compatible style."""

from __future__ import annotations

import json
import re
import unicodedata

# Words that BibTeX processors treat as lowercase in titles -- do NOT wrap these.
_LOWERCASE_TITLE_WORDS = frozenset({
    "a", "an", "the",
    "and", "but", "or", "nor", "for", "so", "yet",
    "at", "by", "in", "of", "on", "to", "up", "as", "is",
    "via", "vs", "per",
})

# LaTeX special characters that need escaping (order matters: backslash first).
_LATEX_SPECIAL = [
    ("\\", "\\textbackslash{}"),
    ("{",  "\\{"),
    ("}",  "\\}"),
    ("&",  "\\&"),
    ("%",  "\\%"),
    ("#",  "\\#"),
    ("_",  "\\_"),
    ("^",  "\\textasciicircum{}"),
    ("~",  "\\textasciitilde{}"),
    ("|",  "{\\textbar}"),
    ("<",  "{\\textless}"),
    (">",  "{\\textgreater}"),
]


def _escape_bibtex(s: str) -> str:
    """Escape special BibTeX/LaTeX characters in plain text fields."""
    # Normalise to composed form but keep printable ASCII structure intact.
    for char, replacement in _LATEX_SPECIAL:
        s = s.replace(char, replacement)
    return s


def _bibtex_protect_title(title: str) -> str:
    """Apply Zotero-style title case protection.

    Every word that begins with an uppercase letter (or is an acronym) is
    wrapped in {} so BibTeX processors preserve the case regardless of the
    bibliography style chosen by the journal.  Stop words and prepositions
    that appear in the middle of the title are left unwrapped.
    """
    if not title:
        return title

    # First escape LaTeX specials so we work on safe text.
    safe = _escape_bibtex(title)

    words = safe.split(" ")
    result: list[str] = []
    for i, word in enumerate(words):
        if not word:
            result.append(word)
            continue

        # Strip leading punctuation to get the core token.
        stripped = word.lstrip("({[\"'")
        prefix = word[: len(word) - len(stripped)]
        # Strip trailing punctuation.
        core = stripped.rstrip(")}]\"',.;:!?")
        suffix = stripped[len(core):]

        # Wrap if: first word, or core starts uppercase, or core looks like
        # an acronym (all-caps >= 2 letters), and it's not a stop word.
        word_lower = core.lower()
        is_stop = word_lower in _LOWERCASE_TITLE_WORDS and i > 0
        starts_upper = core and core[0].isupper()
        is_acronym = core.isupper() and len(core) >= 2

        if not is_stop and (starts_upper or is_acronym):
            result.append(f"{prefix}{{{core}}}{suffix}")
        else:
            result.append(word)

    return " ".join(result)


def _detect_entry_type(journal: str | None, doi: str | None, bibtex: str | None) -> str:
    """Infer the most appropriate BibTeX entry type from available metadata.

    Mirrors Zotero heuristics: if a journal name is present the source is an
    article; everything else falls back to misc.  When a pre-built bibtex
    string is stored we extract the type from it directly.
    """
    if bibtex and bibtex.strip():
        m = re.match(r"@(\w+)\s*\{", bibtex.strip(), re.IGNORECASE)
        if m:
            return m.group(1).lower()

    if journal:
        return "article"

    # DOI prefixes that suggest specific types.
    if doi:
        doi_lower = doi.lower()
        if "book" in doi_lower:
            return "book"
        if "report" in doi_lower or "techreport" in doi_lower:
            return "techreport"

    return "misc"


def _authors_to_bibtex(authors_json: str) -> str:
    """Convert authors JSON list to BibTeX 'Last, First and ...' format.

    Institutional authors (strings containing spaces that look like org names,
    or all-caps tokens) are double-braced per Zotero convention: {{Name}}.
    """
    try:
        authors = json.loads(authors_json)
    except (json.JSONDecodeError, TypeError):
        return "noauthor"

    if not authors or not isinstance(authors, list):
        return "noauthor"

    parts: list[str] = []
    for a in authors:
        if isinstance(a, dict):
            last = a.get("last", a.get("family", ""))
            first = a.get("first", a.get("given", ""))
            if last and first:
                # Escape each component separately; do not double-brace
                # structured name entries.
                parts.append(f"{_escape_bibtex(last)}, {_escape_bibtex(first)}")
            elif last:
                parts.append(_wrap_institutional(_escape_bibtex(str(last))))
            elif first:
                parts.append(_wrap_institutional(_escape_bibtex(str(first))))
        elif isinstance(a, str):
            name = a.strip()
            if not name:
                continue
            # Heuristic: if the token has no comma and contains spaces it may
            # be "First Last" format; try to flip it.
            if "," not in name and " " in name:
                name_parts = name.split()
                # Treat multi-word strings with only title-case words as
                # institutional names; flip plain "First Last" pairs.
                all_title = all(w[0].isupper() if w else True for w in name_parts)
                if len(name_parts) == 2 and all_title:
                    # "John Smith" -> "Smith, John"
                    parts.append(
                        f"{_escape_bibtex(name_parts[-1])}, {_escape_bibtex(name_parts[0])}"
                    )
                else:
                    # Institutional name -- double-brace.
                    parts.append(_wrap_institutional(_escape_bibtex(name)))
            else:
                escaped = _escape_bibtex(name)
                parts.append(escaped)
        else:
            parts.append(_escape_bibtex(str(a)))

    return " and ".join(parts) if parts else "noauthor"


def _wrap_institutional(name: str) -> str:
    """Wrap an institutional author name in double braces for BibTeX."""
    # Already wrapped?
    if name.startswith("{{") and name.endswith("}}"):
        return name
    return "{{" + name + "}}"


def _month_int_to_abbr(month: int | None) -> str | None:
    """Convert a 1-12 integer to the lowercase BibTeX month abbreviation."""
    _ABBRS = {
        1: "jan", 2: "feb", 3: "mar", 4: "apr",
        5: "may", 6: "jun", 7: "jul", 8: "aug",
        9: "sep", 10: "oct", 11: "nov", 12: "dec",
    }
    return _ABBRS.get(month) if month is not None else None


def _build_single_entry(
    citekey: str,
    doi: str | None,
    title: str,
    authors_json: str,
    year: int | None,
    journal: str | None,
    bibtex: str | None,
    url: str | None = None,
    month: int | None = None,
) -> str:
    """Build one BibTeX entry in Zotero style.

    Uses the stored bibtex verbatim when present (preserving Crossref/Semantic
    Scholar supplied records).  Otherwise generates a clean entry from fields.
    """
    if bibtex and bibtex.strip():
        return bibtex.strip()

    entry_type = _detect_entry_type(journal, doi, bibtex)
    author_str = _authors_to_bibtex(authors_json)
    protected_title = _bibtex_protect_title(title) if title else "(No title)"

    # Build field list in Zotero order: title, volume/issn, url, doi,
    # abstract, urldate, journal, author, month, year, pages.
    fields: list[str] = []

    fields.append(f"\ttitle = {{{protected_title}}},")

    if journal:
        fields.append(f"\tjournal = {{{_bibtex_protect_title(journal)}}},")

    if url:
        fields.append(f"\turl = {{{_escape_bibtex(url)}}},")
    elif doi and not url:
        # Synthesise a doi.org URL so @misc entries still have a url field.
        if entry_type == "misc":
            doi_url = f"https://doi.org/{doi.lstrip('/')}"
            fields.append(f"\turl = {{{_escape_bibtex(doi_url)}}},")

    if doi:
        fields.append(f"\tdoi = {{{_escape_bibtex(doi)}}},")

    fields.append(f"\tauthor = {{{author_str}}},")

    month_abbr = _month_int_to_abbr(month)
    if month_abbr:
        fields.append(f"\tmonth = {month_abbr},")

    if year is not None:
        fields.append(f"\tyear = {{{year}}},")
    # When year is None the field is omitted entirely (Zotero behaviour).

    body = "\n".join(fields)
    return f"@{entry_type}{{{citekey},\n{body}\n}}"


def build_bibtex(
    citations: list[
        tuple[str, str, str | None, str, str, int | None, str | None, str | None]
        | tuple[str, str, str | None, str, str, int | None, str | None, str | None, str | None]
    ],
) -> str:
    """Build full references.bib content from citation rows.

    Accepts both the legacy 8-tuple schema and the extended 9-tuple schema
    that includes a url column at position 8.

    Each row: (citation_id, citekey, doi, title, authors_json, year, journal,
               bibtex[, url]).
    """
    entries: list[str] = []
    for row in citations:
        _cid, citekey, doi, title, authors_json, year, journal, bibtex = row[:8]
        url: str | None = row[8] if len(row) > 8 else None  # type: ignore[misc]
        entry = _build_single_entry(
            citekey, doi, title, authors_json, year, journal, bibtex, url=url
        )
        entries.append(entry)
    return "\n\n".join(entries) if entries else "% No citations\n"
