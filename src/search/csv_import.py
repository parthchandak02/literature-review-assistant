"""Master list CSV importer for the search phase.

Parses a pre-assembled Scopus-format CSV export and converts it into a
typed SearchResult that SearchNode can consume identically to connector output.
"""

from __future__ import annotations

import csv
import logging
import uuid
from datetime import date
from pathlib import Path
from typing import List, Optional

from src.models.enums import SourceCategory
from src.models.papers import CandidatePaper, SearchResult

_log = logging.getLogger(__name__)

# Columns expected in a Scopus CSV export.
# The importer tolerates missing optional columns gracefully.
_COL_AUTHORS = "Authors"
_COL_TITLE = "Title"
_COL_YEAR = "Year"
_COL_SOURCE = "Source title"
_COL_DOI = "DOI"
_COL_LINK = "Link"
_COL_ABSTRACT = "Abstract"
_COL_KEYWORDS = "Author Keywords"


def _parse_authors(raw: str) -> List[str]:
    """Split Scopus author field on '; ' delimiter.

    Scopus format: "Last, F.I.; Last2, F.I.; ..."
    Empty or whitespace-only strings return an empty list.
    """
    if not raw or not raw.strip():
        return []
    return [a.strip() for a in raw.split(";") if a.strip()]


def _parse_keywords(raw: str) -> Optional[List[str]]:
    """Split Scopus keyword field on '; ' delimiter."""
    if not raw or not raw.strip():
        return None
    parts = [k.strip() for k in raw.split(";") if k.strip()]
    return parts if parts else None


def _parse_year(raw: str) -> Optional[int]:
    """Convert year string to int, returning None on failure."""
    if not raw or not raw.strip():
        return None
    try:
        return int(raw.strip())
    except ValueError:
        return None


def _clean_doi(raw: str) -> Optional[str]:
    """Strip whitespace from DOI; return None if empty."""
    cleaned = raw.strip() if raw else ""
    return cleaned if cleaned else None


def parse_masterlist_csv(csv_path: str, workflow_id: str) -> SearchResult:
    """Parse a Scopus-format CSV master list into a typed SearchResult.

    Each valid row (non-empty Title) becomes a CandidatePaper with
    source_category=OTHER_SOURCE so the PRISMA diagram places it in the
    "Other sources" box automatically.

    Args:
        csv_path: Absolute path to the CSV file.
        workflow_id: Workflow ID to embed in the returned SearchResult.

    Returns:
        A SearchResult with database_name="CSV Import" and all parsed papers.

    Raises:
        FileNotFoundError: If csv_path does not exist.
        ValueError: If the file has no recognisable Title column.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Master list CSV not found: {csv_path}")

    papers: List[CandidatePaper] = []
    skipped = 0

    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None or _COL_TITLE not in reader.fieldnames:
            raise ValueError(
                f"CSV has no '{_COL_TITLE}' column. "
                f"Found columns: {list(reader.fieldnames or [])}"
            )

        for i, row in enumerate(reader, start=2):  # row 1 is header
            title = (row.get(_COL_TITLE) or "").strip()
            if not title:
                skipped += 1
                _log.debug("Skipping row %d: empty title", i)
                continue

            raw_authors = row.get(_COL_AUTHORS, "") or ""
            authors = _parse_authors(raw_authors)
            if not authors:
                # Use a placeholder so CandidatePaper validation passes.
                authors = ["Unknown"]

            source_database = (row.get(_COL_SOURCE) or "").strip() or "Unknown"

            papers.append(
                CandidatePaper(
                    paper_id=str(uuid.uuid4())[:12],
                    title=title,
                    authors=authors,
                    year=_parse_year(row.get(_COL_YEAR, "") or ""),
                    source_database=source_database,
                    doi=_clean_doi(row.get(_COL_DOI, "") or ""),
                    abstract=(row.get(_COL_ABSTRACT) or "").strip() or None,
                    url=(row.get(_COL_LINK) or "").strip() or None,
                    keywords=_parse_keywords(row.get(_COL_KEYWORDS, "") or ""),
                    source_category=SourceCategory.OTHER_SOURCE,
                )
            )

    _log.info(
        "CSV import: parsed %d papers from '%s' (skipped %d blank-title rows)",
        len(papers),
        path.name,
        skipped,
    )

    return SearchResult(
        workflow_id=workflow_id,
        database_name="CSV Import",
        source_category=SourceCategory.OTHER_SOURCE,
        search_date=date.today().isoformat(),
        search_query=f"Imported from {path.name}",
        limits_applied=None,
        records_retrieved=len(papers),
        papers=papers,
    )
