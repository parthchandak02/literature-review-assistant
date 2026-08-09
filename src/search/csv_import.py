"""Master list CSV importer for the search phase.

Parses CSV exports from Scopus, Embase, CINAHL, or RIS-derived formats into
typed SearchResult objects that SearchNode can consume identically to connector
output.

Two modes:
  - masterlist_csv_path: replaces all connectors (one file, one source)
  - supplementary_csv_paths: added to connector results (multiple files)

Column detection is flexible: the parser probes for known aliases across
Scopus, Embase, and CINAHL export formats. Per-row source inference uses URL
patterns, ID columns, and file-format fingerprints before falling back to
``other``.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import uuid
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from src.models.enums import SourceCategory
from src.models.papers import CandidatePaper, SearchResult
from src.search.source_inference import (
    detect_csv_export_format,
    infer_csv_row_source,
    resolve_database_column,
)

_log = logging.getLogger(__name__)

# --- Column alias maps -------------------------------------------------------
# Each key is the canonical field; the value is an ordered list of column names
# tried in priority order across Scopus, Embase, CINAHL, and PubMed CSV formats.
# The first match in the actual CSV header wins.

_ALIASES: dict[str, list[str]] = {
    "title": ["Title", "TITLE", "Article Title", "Document Title"],
    "authors": [
        "Authors",
        "Author",
        "AUTHOR",
        "Author Names",
        "AU",
        "Authors (Last name, initials)",
    ],
    "year": [
        "Year",
        "YEAR",
        "Publication Year",
        "Source Year",
        "Pub Year",
        "PY",
        "Year of Publication",
    ],
    "source": [
        "Source title",
        "Source",
        "Journal",
        "Publication",
        "Journal Title",
        "SO",
        "Publication Name",
    ],
    "doi": ["DOI", "doi", "Digital Object Identifier"],
    "url": ["Link", "URL", "url", "Access URL", "Full Text Link"],
    "abstract": ["Abstract", "ABSTRACT", "AB", "Author Abstract"],
    "keywords": [
        "Author Keywords",
        "Author Keywords (DE)",
        "Keywords",
        "DE",
        "KW",
        "MeSH Terms",
        "MESH",
    ],
}


def _load_csv_text(path: Path) -> tuple[str, csv.Dialect]:
    """Read CSV bytes with resilient encoding and delimiter detection."""
    raw = path.read_bytes()
    if not raw:
        raise ValueError(f"CSV is empty: {path}")

    last_decode_error: Exception | None = None
    text: str | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError as exc:
            last_decode_error = exc
            continue

    if text is None:
        raise ValueError(f"CSV encoding is not supported for file: {path}") from last_decode_error

    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return text, dialect


def _resolve_col(fieldnames: list[str], canonical: str) -> str | None:
    """Return the first alias for *canonical* that is present in *fieldnames*."""
    aliases = _ALIASES.get(canonical, [])
    for alias in aliases:
        if alias in fieldnames:
            return alias
    return None


def _parse_authors(raw: str) -> list[str]:
    """Split author field using either '; ' or ', ' as delimiter."""
    if not raw or not raw.strip():
        return []
    if ";" in raw:
        return [a.strip() for a in raw.split(";") if a.strip()]
    parts = [a.strip() for a in raw.split(",") if a.strip()]
    return parts if parts else ["Unknown"]


def _parse_keywords(raw: str) -> list[str] | None:
    """Split keyword field on '; ' or ',' delimiter."""
    if not raw or not raw.strip():
        return None
    sep = ";" if ";" in raw else ","
    parts = [k.strip() for k in raw.split(sep) if k.strip()]
    return parts if parts else None


def _parse_year(raw: str) -> int | None:
    """Extract 4-digit year from string, returning None on failure."""
    if not raw or not raw.strip():
        return None
    match = re.search(r"\b(1[89]\d\d|20[0-2]\d)\b", raw)
    if match:
        return int(match.group(1))
    try:
        return int(raw.strip())
    except ValueError:
        return None


def _clean_doi(raw: str) -> str | None:
    """Strip whitespace and 'https://doi.org/' prefix from DOI."""
    cleaned = (raw or "").strip()
    cleaned = re.sub(r"^https?://doi\.org/", "", cleaned)
    cleaned = re.sub(r"^https?://dx\.doi\.org/", "", cleaned)
    return cleaned if cleaned else None


def _detect_database_from_filename(path: Path) -> str | None:
    """Guess source database from filename stem only."""
    stem = path.stem.lower()
    if "embase" in stem:
        return "embase"
    if "cinahl" in stem or "ebsco" in stem:
        return "cinahl"
    if "pubmed" in stem or "medline" in stem:
        return "pubmed"
    if "wos" in stem or "web_of_science" in stem:
        return "web_of_science"
    if "scopus" in stem:
        return "scopus"
    if "ieee" in stem:
        return "ieee_xplore"
    return None


def _group_papers_into_search_results(
    papers: list[CandidatePaper],
    *,
    workflow_id: str,
    path: Path,
) -> list[SearchResult]:
    """Split parsed papers into one SearchResult per (database, category) pair."""
    groups: dict[tuple[str, SourceCategory], list[CandidatePaper]] = defaultdict(list)
    for paper in papers:
        groups[(paper.source_database, paper.source_category)].append(paper)

    search_date = date.today().isoformat()
    results: list[SearchResult] = []
    for (db_name, category), group_papers in sorted(groups.items()):
        results.append(
            SearchResult(
                workflow_id=workflow_id,
                database_name=db_name,
                source_category=category,
                search_date=search_date,
                search_query=f"Imported from {path.name}",
                limits_applied=None,
                records_retrieved=len(group_papers),
                papers=group_papers,
            )
        )
    return results


def _parse_csv_file(
    path: Path,
    workflow_id: str,
    database_label: str | None = None,
) -> list[SearchResult]:
    """Parse a single CSV file into SearchResult(s) grouped by inferred source.

    Returns one SearchResult per distinct (source_database, source_category)
    so PRISMA identification counts consolidate with connector results.
    """
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")

    papers: list[CandidatePaper] = []
    skipped = 0
    url_samples: list[str] = []

    csv_text, dialect = _load_csv_text(path)
    reader = csv.DictReader(io.StringIO(csv_text), dialect=dialect)
    fieldnames: list[str] = list(reader.fieldnames or [])

    title_col = _resolve_col(fieldnames, "title")
    if title_col is None:
        raise ValueError(f"CSV has no recognisable Title column. Found: {fieldnames}")

    authors_col = _resolve_col(fieldnames, "authors")
    year_col = _resolve_col(fieldnames, "year")
    source_col = _resolve_col(fieldnames, "source")
    doi_col = _resolve_col(fieldnames, "doi")
    url_col = _resolve_col(fieldnames, "url")
    abstract_col = _resolve_col(fieldnames, "abstract")
    keywords_col = _resolve_col(fieldnames, "keywords")
    database_col = resolve_database_column(fieldnames)

    rows = list(reader)
    for row in rows:
        url = ((row.get(url_col) if url_col else "") or "").strip()
        if url:
            url_samples.append(url)
        if len(url_samples) >= 200:
            break

    file_hint = (
        database_label
        or _detect_database_from_filename(path)
        or detect_csv_export_format(fieldnames, url_samples)
    )

    for i, row in enumerate(rows, start=2):
        title = (row.get(title_col) or "").strip()
        if not title:
            skipped += 1
            _log.debug("Skipping row %d: empty title", i)
            continue

        raw_authors = (row.get(authors_col) if authors_col else "") or ""
        authors = _parse_authors(raw_authors) or ["Unknown"]
        journal = ((row.get(source_col) if source_col else "") or "").strip() or None
        doi = _clean_doi((row.get(doi_col) if doi_col else "") or "")
        url = ((row.get(url_col) if url_col else "") or "").strip() or None
        explicit_db = ((row.get(database_col) if database_col else "") or "").strip() or None

        source_database, source_category = infer_csv_row_source(
            url=url,
            doi=doi,
            explicit_database=explicit_db,
            row=row,
            fieldnames=fieldnames,
            file_hint=file_hint,
        )

        papers.append(
            CandidatePaper(
                paper_id=str(uuid.uuid4())[:12],
                title=title,
                authors=authors,
                year=_parse_year((row.get(year_col) if year_col else "") or ""),
                source_database=source_database,
                doi=doi,
                abstract=((row.get(abstract_col) if abstract_col else "") or "").strip() or None,
                url=url,
                keywords=_parse_keywords((row.get(keywords_col) if keywords_col else "") or ""),
                journal=journal,
                source_category=source_category,
            )
        )

    source_counts: dict[str, int] = defaultdict(int)
    for paper in papers:
        source_counts[paper.source_database] += 1

    _log.info(
        "CSV import: parsed %d papers from '%s' (skipped %d blank-title rows); sources=%s",
        len(papers),
        path.name,
        skipped,
        dict(source_counts),
    )

    if not papers:
        raise ValueError(f"CSV contains no data rows with a non-empty Title column: {path}")

    return _group_papers_into_search_results(papers, workflow_id=workflow_id, path=path)


def validate_csv_file(csv_path: str) -> dict[str, Any]:
    """Validate CSV parseability and required schema before launching workflow."""
    results = _parse_csv_file(Path(csv_path), workflow_id="validation")
    total = sum(r.records_retrieved for r in results)
    if total <= 0:
        raise ValueError("CSV contains no data rows with a non-empty Title column.")
    return {
        "records_retrieved": total,
        "database_name": ", ".join(f"{r.database_name} ({r.records_retrieved})" for r in results),
        "sources": {r.database_name: r.records_retrieved for r in results},
    }


def parse_masterlist_csv(csv_path: str, workflow_id: str) -> list[SearchResult]:
    """Parse a master list CSV into SearchResults grouped by inferred source."""
    return _parse_csv_file(Path(csv_path), workflow_id)


def parse_supplementary_csvs(
    csv_paths: list[str],
    workflow_id: str,
) -> list[SearchResult]:
    """Parse supplementary CSV exports; one or more SearchResults per file."""
    results: list[SearchResult] = []
    for p in csv_paths:
        results.extend(_parse_csv_file(Path(p), workflow_id))
    return results
