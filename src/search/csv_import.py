"""Master list CSV importer for the search phase.

Parses CSV exports from Scopus, Embase, CINAHL, or RIS-derived formats into
typed SearchResult objects that SearchNode can consume identically to connector
output.

Two modes:
  - masterlist_csv_path: replaces all connectors (one file, one source)
  - supplementary_csv_paths: added to connector results (multiple files)

Column detection is flexible: the parser probes for known aliases across
Scopus, Embase, and CINAHL export formats.
"""

from __future__ import annotations

import csv
import logging
import re
import uuid
from datetime import date
from pathlib import Path

from src.models.enums import SourceCategory
from src.models.papers import CandidatePaper, SearchResult

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


def _resolve_col(fieldnames: list[str], canonical: str) -> str | None:
    """Return the first alias for *canonical* that is present in *fieldnames*."""
    aliases = _ALIASES.get(canonical, [])
    for alias in aliases:
        if alias in fieldnames:
            return alias
    return None


def _parse_authors(raw: str) -> list[str]:
    """Split author field using either '; ' or ', ' as delimiter.

    Handles:
    - Scopus: "Last, F.I.; Last2, F.I."
    - Embase: "Last F, Last2 F2" (comma-separated without initials separator)
    - CINAHL: "Last, Firstname; Last2, Firstname2"
    """
    if not raw or not raw.strip():
        return []
    # Prefer semicolon split when semicolons are present (Scopus / CINAHL style).
    if ";" in raw:
        return [a.strip() for a in raw.split(";") if a.strip()]
    # Fall back to comma split for Embase style (comma between authors).
    # Avoid over-splitting "Last, FirstName" which has a single comma.
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
    """Extract 4-digit year from string, returning None on failure.

    Handles plain integers ("2021") and date strings ("2021-03-15").
    """
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
    return cleaned if cleaned else None


def _detect_database(path: Path, fieldnames: list[str]) -> str:
    """Guess the source database from the filename or unique column signatures."""
    stem = path.stem.lower()
    if "embase" in stem:
        return "Embase"
    if "cinahl" in stem or "ebsco" in stem:
        return "CINAHL"
    if "pubmed" in stem or "medline" in stem:
        return "PubMed"
    if "wos" in stem or "web_of_science" in stem:
        return "Web of Science"
    if "scopus" in stem:
        return "Scopus"
    # Column-signature heuristics
    if "CINAHL AN" in fieldnames or "Accession Number" in fieldnames:
        return "CINAHL"
    if "Medline PMID" in fieldnames or "Embase EMID" in fieldnames:
        return "Embase"
    if "PMID" in fieldnames:
        return "PubMed"
    return "CSV Import"


def _parse_csv_file(
    path: Path,
    workflow_id: str,
    database_label: str | None = None,
) -> SearchResult:
    """Parse a single CSV file into a SearchResult.

    Column detection is flexible: title/authors/year/doi/abstract/url/keywords
    are resolved via _ALIASES so the same function handles Scopus, Embase,
    CINAHL, and PubMed CSV formats.

    Args:
        path: Path to the CSV file.
        workflow_id: Workflow ID to embed in the returned SearchResult.
        database_label: Override the detected database name.

    Returns:
        A SearchResult containing all parsed papers.

    Raises:
        FileNotFoundError: If path does not exist.
        ValueError: If no recognisable Title column is found.
    """
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")

    papers: list[CandidatePaper] = []
    skipped = 0

    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames: list[str] = list(reader.fieldnames or [])

        title_col = _resolve_col(fieldnames, "title")
        if title_col is None:
            raise ValueError(
                f"CSV has no recognisable Title column. Found: {fieldnames}"
            )

        authors_col = _resolve_col(fieldnames, "authors")
        year_col = _resolve_col(fieldnames, "year")
        source_col = _resolve_col(fieldnames, "source")
        doi_col = _resolve_col(fieldnames, "doi")
        url_col = _resolve_col(fieldnames, "url")
        abstract_col = _resolve_col(fieldnames, "abstract")
        keywords_col = _resolve_col(fieldnames, "keywords")

        db_name = database_label or _detect_database(path, fieldnames)

        for i, row in enumerate(reader, start=2):
            title = (row.get(title_col) or "").strip()
            if not title:
                skipped += 1
                _log.debug("Skipping row %d: empty title", i)
                continue

            raw_authors = (row.get(authors_col) if authors_col else "") or ""
            authors = _parse_authors(raw_authors) or ["Unknown"]

            source_database = (
                (row.get(source_col) if source_col else "") or ""
            ).strip() or db_name

            papers.append(
                CandidatePaper(
                    paper_id=str(uuid.uuid4())[:12],
                    title=title,
                    authors=authors,
                    year=_parse_year((row.get(year_col) if year_col else "") or ""),
                    source_database=source_database,
                    doi=_clean_doi((row.get(doi_col) if doi_col else "") or ""),
                    abstract=(
                        (row.get(abstract_col) if abstract_col else "") or ""
                    ).strip() or None,
                    url=(
                        (row.get(url_col) if url_col else "") or ""
                    ).strip() or None,
                    keywords=_parse_keywords(
                        (row.get(keywords_col) if keywords_col else "") or ""
                    ),
                    source_category=SourceCategory.OTHER_SOURCE,
                )
            )

    _log.info(
        "CSV import: parsed %d papers from '%s' as '%s' (skipped %d blank-title rows)",
        len(papers),
        path.name,
        db_name,
        skipped,
    )

    return SearchResult(
        workflow_id=workflow_id,
        database_name=db_name,
        source_category=SourceCategory.OTHER_SOURCE,
        search_date=date.today().isoformat(),
        search_query=f"Imported from {path.name}",
        limits_applied=None,
        records_retrieved=len(papers),
        papers=papers,
    )


def parse_masterlist_csv(csv_path: str, workflow_id: str) -> SearchResult:
    """Parse a master list CSV (any supported format) into a SearchResult.

    This is the single-file replacement mode: when masterlist_csv_path is set
    in ReviewConfig, this function is called and all connectors are bypassed.

    Args:
        csv_path: Absolute path to the CSV file.
        workflow_id: Workflow ID to embed in the returned SearchResult.

    Returns:
        A SearchResult with all parsed papers.

    Raises:
        FileNotFoundError: If csv_path does not exist.
        ValueError: If the file has no recognisable Title column.
    """
    return _parse_csv_file(Path(csv_path), workflow_id, database_label="CSV Import")


def parse_supplementary_csvs(
    csv_paths: list[str],
    workflow_id: str,
) -> list[SearchResult]:
    """Parse multiple supplementary CSV exports into a list of SearchResults.

    Used when supplementary_csv_paths is set in ReviewConfig. Unlike
    masterlist_csv_path, these files are ADDED to connector results rather than
    replacing them. Each file produces its own SearchResult so PRISMA counts
    remain accurate per-source.

    Filenames are used to auto-detect the source database name; include
    'embase', 'cinahl', 'pubmed', or 'wos' in the filename for automatic
    labelling (e.g. 'embase_export.csv', 'cinahl_results.csv').

    Args:
        csv_paths: List of absolute paths to CSV files.
        workflow_id: Workflow ID to embed in returned SearchResults.

    Returns:
        List of SearchResult objects, one per file, in input order.

    Raises:
        FileNotFoundError: If any path does not exist.
        ValueError: If any file has no recognisable Title column.
    """
    results: list[SearchResult] = []
    for p in csv_paths:
        result = _parse_csv_file(Path(p), workflow_id)
        results.append(result)
    return results
