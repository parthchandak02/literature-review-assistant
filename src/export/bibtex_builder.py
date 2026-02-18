"""Build references.bib from citations table."""

from __future__ import annotations

import json


def _escape_bibtex(s: str) -> str:
    """Escape special BibTeX characters."""
    s = s.replace("\\", "\\\\")
    s = s.replace("{", "\\{")
    s = s.replace("}", "\\}")
    s = s.replace("&", "\\&")
    return s


def _authors_to_bibtex(authors_json: str) -> str:
    """Convert authors JSON to BibTeX format (Last, First and Last, First)."""
    try:
        authors = json.loads(authors_json)
    except (json.JSONDecodeError, TypeError):
        return "Unknown"
    if not authors or not isinstance(authors, list):
        return "Unknown"
    parts = []
    for a in authors:
        if isinstance(a, str):
            parts.append(_escape_bibtex(a))
        elif isinstance(a, dict):
            last = a.get("last", a.get("family", ""))
            first = a.get("first", a.get("given", ""))
            if last and first:
                parts.append(f"{last}, {first}")
            elif last:
                parts.append(str(last))
            else:
                parts.append(str(first) if first else "Unknown")
        else:
            parts.append(str(a))
    return " and ".join(parts) if parts else "Unknown"


def _build_single_entry(
    citekey: str,
    doi: str | None,
    title: str,
    authors_json: str,
    year: int | None,
    journal: str | None,
    bibtex: str | None,
) -> str:
    """Build one BibTeX entry. Use stored bibtex if present; else generate from fields."""
    if bibtex and bibtex.strip():
        return bibtex.strip()
    author = _authors_to_bibtex(authors_json)
    year_str = str(year) if year else "n.d."
    lines = [
        f"@article{{{citekey},",
        f"  author = {{{_escape_bibtex(author)}}},",
        f"  title = {{{_escape_bibtex(title)}}},",
        f"  year = {{{year_str}}},",
    ]
    if journal:
        lines.append(f"  journal = {{{_escape_bibtex(journal)}}},")
    if doi:
        lines.append(f"  doi = {{{_escape_bibtex(doi)}}},")
    lines.append("}")
    return "\n".join(lines)


def build_bibtex(
    citations: list[tuple[str, str, str | None, str, str, int | None, str | None, str | None]],
) -> str:
    """Build full references.bib content from citation rows.

    Each row: (citation_id, citekey, doi, title, authors_json, year, journal, bibtex).
    """
    entries = []
    for row in citations:
        _cid, citekey, doi, title, authors_json, year, journal, bibtex = row
        entry = _build_single_entry(citekey, doi, title, authors_json, year, journal, bibtex)
        entries.append(entry)
    return "\n\n".join(entries) if entries else "% No citations\n"
