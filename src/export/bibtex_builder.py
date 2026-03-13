"""Build references.bib from citations table in Zotero-compatible style."""

from __future__ import annotations

import json
import re
import unicodedata

# Words that BibTeX processors treat as lowercase in titles -- do NOT wrap these.
_LOWERCASE_TITLE_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "but",
        "or",
        "nor",
        "for",
        "so",
        "yet",
        "at",
        "by",
        "in",
        "of",
        "on",
        "to",
        "up",
        "as",
        "is",
        "via",
        "vs",
        "per",
    }
)

# Keywords that strongly suggest an institutional/organisation author name.
_INSTITUTIONAL_KEYWORDS = frozenset(
    {
        "university",
        "institute",
        "college",
        "department",
        "association",
        "society",
        "national",
        "international",
        "hospital",
        "clinic",
        "center",
        "centre",
        "corporation",
        "inc",
        "ltd",
        "llc",
        "group",
        "committee",
        "organization",
        "organisation",
        "ministry",
        "agency",
        "foundation",
        "consortium",
        "network",
        "authority",
        "office",
        "bureau",
        "division",
        "school",
        "faculty",
        "board",
        "council",
    }
)

# DOI URL prefixes to strip when normalising a DOI string.
_DOI_URL_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
)

# LaTeX special characters that need escaping (order matters: backslash first).
_LATEX_SPECIAL = [
    ("\\", "\\textbackslash{}"),
    ("{", "\\{"),
    ("}", "\\}"),
    ("&", "\\&"),
    ("%", "\\%"),
    ("#", "\\#"),
    ("_", "\\_"),
    ("^", "\\textasciicircum{}"),
    ("~", "\\textasciitilde{}"),
    ("|", "{\\textbar}"),
    ("<", "{\\textless}"),
    (">", "{\\textgreater}"),
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
        suffix = stripped[len(core) :]

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
            if "," not in name and " " in name:
                name_parts = name.split()
                if len(name_parts) == 2:
                    first_tok, second_tok = name_parts
                    # "LastName Initials" -> "LastName, Initials"   e.g. "Cohen J", "Page MJ"
                    if _looks_like_initials(second_tok):
                        parts.append(f"{_escape_bibtex(first_tok)}, {_escape_bibtex(second_tok)}")
                    # "Initials LastName" -> "LastName, Initials"   e.g. "MJ Page"
                    elif _looks_like_initials(first_tok):
                        parts.append(f"{_escape_bibtex(second_tok)}, {_escape_bibtex(first_tok)}")
                    # "FirstName LastName" -> flip   e.g. "John Smith"
                    else:
                        parts.append(f"{_escape_bibtex(second_tok)}, {_escape_bibtex(first_tok)}")
                elif len(name_parts) == 3 and _looks_like_initials(name_parts[1]):
                    # "FirstName Middle LastName" -> "LastName, FirstName Middle"
                    # e.g. "Stephanie R. Beldick" -> "Beldick, Stephanie R."
                    first, mid, last = name_parts
                    parts.append(f"{_escape_bibtex(last)}, {_escape_bibtex(first)} {_escape_bibtex(mid)}")
                elif _is_institutional_name(name_parts):
                    parts.append(_wrap_institutional(_escape_bibtex(name)))
                else:
                    # Best effort: last word is last name.
                    last = name_parts[-1]
                    rest = " ".join(name_parts[:-1])
                    parts.append(f"{_escape_bibtex(last)}, {_escape_bibtex(rest)}")
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


def _looks_like_initials(token: str) -> bool:
    """Return True if token looks like name initials (e.g. 'J', 'MJ', 'JAC', 'A.')."""
    stripped = token.rstrip(".")
    return len(stripped) <= 3 and stripped.isupper() and stripped.isalpha()


def _is_institutional_name(name_parts: list[str]) -> bool:
    """Heuristic: does this multi-word string look like an organisation?"""
    joined_lower = " ".join(p.lower().rstrip(".,;") for p in name_parts)
    for kw in _INSTITUTIONAL_KEYWORDS:
        if kw in joined_lower:
            return True
    # All-caps words (acronym-style org names) with no obvious initials
    if all(p.isupper() for p in name_parts if len(p) > 1):
        return True
    return False


def _normalize_doi(doi: str) -> str:
    """Return bare DOI, stripping any leading URL prefix."""
    for prefix in _DOI_URL_PREFIXES:
        if doi.startswith(prefix):
            return doi[len(prefix) :]
    return doi.lstrip("/")


def _month_int_to_abbr(month: int | None) -> str | None:
    """Convert a 1-12 integer to the lowercase BibTeX month abbreviation."""
    _ABBRS = {
        1: "jan",
        2: "feb",
        3: "mar",
        4: "apr",
        5: "may",
        6: "jun",
        7: "jul",
        8: "aug",
        9: "sep",
        10: "oct",
        11: "nov",
        12: "dec",
    }
    return _ABBRS.get(month) if month is not None else None


def _normalize_ascii_token(text: str) -> str:
    """Return ASCII alnum-only token candidate for citekey construction."""
    ascii_text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Za-z0-9]+", "", ascii_text)


def _fallback_citekey_from_metadata(
    title: str,
    authors_json: str,
    year: int | None,
    index: int,
) -> str:
    """Build a deterministic fallback key when stored citekey is malformed."""
    year_part = str(year) if year else "nd"
    surname = ""
    try:
        authors = json.loads(authors_json) if authors_json else []
    except (json.JSONDecodeError, TypeError):
        authors = []
    if isinstance(authors, list) and authors:
        first = authors[0]
        if isinstance(first, dict):
            surname = str(first.get("last") or first.get("family") or "")
        else:
            s = str(first).strip()
            if "," in s:
                surname = s.split(",")[0].strip()
            else:
                parts = s.split()
                if len(parts) == 2:
                    first_tok, second_tok = parts
                    first_is_initial = len(first_tok.rstrip(".")) <= 3 and first_tok.rstrip(".").isupper()
                    second_is_initial = len(second_tok.rstrip(".")) <= 3 and second_tok.rstrip(".").isupper()
                    if second_is_initial and not first_is_initial:
                        surname = first_tok
                    elif first_is_initial and not second_is_initial:
                        surname = second_tok
                    else:
                        surname = parts[-1]
                else:
                    surname = parts[-1] if parts else ""
    surname_token = _normalize_ascii_token(surname)
    if surname_token:
        return f"{surname_token[:18]}{year_part}"

    title_token = ""
    for word in str(title or "").split():
        cand = _normalize_ascii_token(word)
        if len(cand) >= 4:
            title_token = cand
            break
    if title_token:
        return f"{title_token[:18]}{year_part}"
    return f"Ref{index + 1}{year_part}"


def _sanitize_citekey(
    citekey: str,
    title: str,
    authors_json: str,
    year: int | None,
    index: int,
) -> str:
    """Normalize citekey and replace unsafe/internal fallback keys."""
    raw = "".join(c for c in unicodedata.normalize("NFD", str(citekey or "")) if unicodedata.category(c) != "Mn")
    raw = raw.strip()
    # Replace internal fallback keys with metadata-derived citekeys.
    if not raw or raw.startswith("Paper_") or re.fullmatch(r"Ref\d+", raw):
        return _fallback_citekey_from_metadata(title, authors_json, year, index)

    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", raw)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned or cleaned.startswith("Paper_") or re.fullmatch(r"Ref\d+", cleaned):
        return _fallback_citekey_from_metadata(title, authors_json, year, index)
    if cleaned[0].isdigit():
        cleaned = f"Ref_{cleaned}"
    return cleaned


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

    Always regenerates from structured fields using our Zotero formatter so
    that field order, title bracing, author format, and DOI normalisation are
    consistent regardless of what may be stored in the bibtex column.
    The entry type is still inferred from stored bibtex when available.
    """
    entry_type = _detect_entry_type(journal, doi, bibtex)
    author_str = _authors_to_bibtex(authors_json)
    protected_title = _bibtex_protect_title(title) if title else "(No title)"

    # Normalise the DOI to bare form (strip any https://doi.org/ prefix).
    clean_doi = _normalize_doi(doi) if doi else None

    # Build field list in Zotero order: title, journal, url, doi,
    # author, month, year.
    fields: list[str] = []

    fields.append(f"\ttitle = {{{protected_title}}},")

    if journal:
        fields.append(f"\tjournal = {{{_bibtex_protect_title(journal)}}},")

    if url:
        fields.append(f"\turl = {{{_escape_bibtex(url)}}},")
    elif clean_doi and entry_type == "misc":
        # Synthesise a doi.org URL so @misc entries still have a url field.
        doi_url = f"https://doi.org/{clean_doi}"
        fields.append(f"\turl = {{{_escape_bibtex(doi_url)}}},")

    if clean_doi:
        fields.append(f"\tdoi = {{{_escape_bibtex(clean_doi)}}},")

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
    cited_citekeys: set[str] | None = None,
) -> str:
    """Build full references.bib content from citation rows.

    Accepts both the legacy 8-tuple schema and the extended 9-tuple schema
    that includes a url column at position 8.

    Each row: (citation_id, citekey, doi, title, authors_json, year, journal,
               bibtex[, url]).
    """
    entries: list[str] = []
    used: set[str] = set()
    for idx, row in enumerate(citations):
        _cid, citekey, doi, title, authors_json, year, journal, bibtex = row[:8]
        if cited_citekeys is not None and str(citekey) not in cited_citekeys:
            continue
        url: str | None = row[8] if len(row) > 8 else None  # type: ignore[misc]
        safe_key = _sanitize_citekey(citekey, title, authors_json, year, idx)
        unique_key = safe_key
        suffix = 2
        while unique_key in used:
            unique_key = f"{safe_key}_{suffix}"
            suffix += 1
        used.add(unique_key)
        entry = _build_single_entry(unique_key, doi, title, authors_json, year, journal, bibtex, url=url)
        entries.append(entry)
    return "\n\n".join(entries) if entries else "% No citations\n"
