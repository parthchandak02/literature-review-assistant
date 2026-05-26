"""Papers and search results repository."""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

import aiosqlite

from src.models import CandidatePaper, SearchResult
from src.models.enums import SourceCategory
from src.models.papers import compute_display_label
from src.search.source_quality import apply_source_quality_prior

_logger = logging.getLogger(__name__)


def _row_to_candidate_paper(row: tuple[Any, ...]) -> CandidatePaper:
    """Convert a papers table row to CandidatePaper.

    Expected column order (matches all SELECT queries in this module):
      0 paper_id, 1 title, 2 authors, 3 year, 4 source_database, 5 doi,
      6 abstract, 7 url, 8 keywords, 9 source_category, 10 openalex_id,
      11 country, 12 journal, 13 display_label, 14 source_quality_tier,
      15 source_peer_reviewed, 16 source_open_index
    """
    authors_raw = row[2]
    authors = json.loads(authors_raw) if isinstance(authors_raw, str) else (authors_raw or [])
    keywords_raw = row[8]
    keywords = json.loads(keywords_raw) if isinstance(keywords_raw, str) else (keywords_raw or [])
    try:
        source_cat = SourceCategory(str(row[9]))
    except ValueError:
        source_cat = SourceCategory.DATABASE
    country = str(row[11]) if len(row) > 11 and row[11] else None
    journal = str(row[12]) if len(row) > 12 and row[12] else None
    display_label = str(row[13]) if len(row) > 13 and row[13] else None
    source_quality_tier = str(row[14]) if len(row) > 14 and row[14] else None
    source_peer_reviewed = bool(row[15]) if len(row) > 15 and row[15] is not None else None
    source_open_index = bool(row[16]) if len(row) > 16 and row[16] is not None else None
    return CandidatePaper(
        paper_id=str(row[0]),
        title=str(row[1]),
        authors=authors,
        year=int(row[3]) if row[3] is not None else None,
        source_database=str(row[4]),
        doi=str(row[5]) if row[5] else None,
        abstract=str(row[6]) if row[6] else None,
        url=str(row[7]) if row[7] else None,
        keywords=keywords if keywords else None,
        source_category=source_cat,
        openalex_id=str(row[10]) if row[10] else None,
        country=country,
        journal=journal,
        display_label=display_label,
        source_quality_tier=source_quality_tier,
        source_peer_reviewed=source_peer_reviewed,
        source_open_index=source_open_index,
    )


class PapersRepo:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def save_paper(self, paper: CandidatePaper) -> None:
        paper = apply_source_quality_prior(paper)
        label = paper.display_label or compute_display_label(paper)
        params = (
            paper.paper_id,
            paper.title,
            json.dumps(paper.authors),
            paper.year,
            paper.source_database,
            paper.doi,
            paper.abstract,
            paper.url,
            json.dumps(paper.keywords or []),
            paper.source_category.value,
            paper.openalex_id,
            paper.country,
            paper.journal,
            label,
            paper.source_quality_tier,
            1 if paper.source_peer_reviewed else 0 if paper.source_peer_reviewed is not None else None,
            1 if paper.source_open_index else 0 if paper.source_open_index is not None else None,
        )
        upsert_sql = """
            INSERT INTO papers (
                paper_id, title, authors, year, source_database, doi, abstract, url,
                keywords, source_category, openalex_id, country, journal, display_label,
                source_quality_tier, source_peer_reviewed, source_open_index
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(paper_id) DO UPDATE SET
                title = excluded.title,
                authors = excluded.authors,
                year = excluded.year,
                source_database = excluded.source_database,
                doi = excluded.doi,
                abstract = excluded.abstract,
                url = excluded.url,
                keywords = excluded.keywords,
                source_category = excluded.source_category,
                openalex_id = excluded.openalex_id,
                country = excluded.country,
                journal = excluded.journal,
                display_label = excluded.display_label,
                source_quality_tier = excluded.source_quality_tier,
                source_peer_reviewed = excluded.source_peer_reviewed,
                source_open_index = excluded.source_open_index
            """
        try:
            await self.db.execute(upsert_sql, params)
        except (sqlite3.IntegrityError, Exception) as exc:
            if paper.doi is not None:
                _logger.debug(
                    "DOI conflict for paper %s (doi=%s), retrying with NULL DOI: %s",
                    paper.paper_id,
                    paper.doi,
                    exc,
                )
                params_no_doi = list(params)
                params_no_doi[5] = None
                try:
                    await self.db.execute(upsert_sql, tuple(params_no_doi))
                except Exception:
                    _logger.warning(
                        "Could not save paper %s even with NULL DOI",
                        paper.paper_id,
                    )
            else:
                _logger.warning("Could not save paper %s: %s", paper.paper_id, exc)

    async def save_search_result(self, result: SearchResult) -> None:
        await self.db.execute(
            """
            DELETE FROM search_results
            WHERE workflow_id = ?
              AND database_name = ?
              AND source_category = ?
            """,
            (
                result.workflow_id,
                result.database_name,
                result.source_category.value,
            ),
        )
        await self.db.execute(
            """
            INSERT INTO search_results (
                database_name, source_category, search_date, search_query,
                limits_applied, records_retrieved, diagnostic_cause, query_variant, workflow_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.database_name,
                result.source_category.value,
                result.search_date,
                result.search_query,
                result.limits_applied,
                result.records_retrieved,
                result.diagnostic_cause,
                result.query_variant or "primary",
                result.workflow_id,
            ),
        )
        for paper in result.papers:
            await self.save_paper(paper)
        await self.db.commit()

    async def get_search_counts(self, workflow_id: str) -> dict[str, int]:
        cursor = await self.db.execute(
            """
            SELECT database_name, COALESCE(SUM(records_retrieved), 0)
            FROM search_results
            WHERE workflow_id = ?
            GROUP BY database_name
            """,
            (workflow_id,),
        )
        rows = await cursor.fetchall()
        return {str(row[0]): int(row[1]) for row in rows}

    async def get_search_counts_by_category(self, workflow_id: str) -> tuple[dict[str, int], dict[str, int]]:
        """Return (databases_records, other_sources_records) for PRISMA two-column."""
        cursor = await self.db.execute(
            """
            SELECT database_name, source_category, COALESCE(SUM(records_retrieved), 0)
            FROM search_results
            WHERE workflow_id = ?
            GROUP BY database_name, source_category
            """,
            (workflow_id,),
        )
        rows = await cursor.fetchall()
        databases: dict[str, int] = {}
        other: dict[str, int] = {}
        for db_name, cat, count in rows:
            name = str(db_name)
            cnt = int(count)
            if str(cat).lower() == "other_source":
                other[name] = cnt
            else:
                databases[name] = cnt
        return databases, other

    async def get_failed_search_connectors(self, workflow_id: str) -> list[str]:
        """Return connector names that raised an error during the search phase.

        Failed connectors are logged to decision_log as search_connector_error
        and never receive a row in search_results.  PRISMA 2020 item 5 requires
        disclosing all attempted databases, including those that failed.
        The connector name is parsed from the rationale field which is formatted
        as "{connector_name}: {ExceptionType}: {message}".
        """
        cursor = await self.db.execute(
            """
            SELECT rationale FROM decision_log
            WHERE decision_type = 'search_connector_error' AND workflow_id = ?
            """,
            (workflow_id,),
        )
        rows = await cursor.fetchall()
        failed: list[str] = []
        seen: set[str] = set()
        for (rationale,) in rows:
            connector_name = str(rationale).split(":")[0].strip()
            if connector_name and connector_name not in seen:
                seen.add(connector_name)
                failed.append(connector_name)
        return failed

    async def get_all_papers(self) -> list[CandidatePaper]:
        """Load all papers from the papers table (for resume state reconstruction)."""
        cursor = await self.db.execute(
            """
            SELECT paper_id, title, authors, year, source_database, doi, abstract, url,
                   keywords, source_category, openalex_id, country, journal, display_label
            FROM papers
            """
        )
        rows = await cursor.fetchall()
        return [_row_to_candidate_paper(row) for row in rows]

    async def load_papers_by_ids(self, paper_ids: set[str]) -> list[CandidatePaper]:
        """Load papers by paper_id set."""
        if not paper_ids:
            return []
        placeholders = ",".join("?" * len(paper_ids))
        cursor = await self.db.execute(
            f"""
            SELECT paper_id, title, authors, year, source_database, doi, abstract, url,
                   keywords, source_category, openalex_id, country, journal, display_label
            FROM papers
            WHERE paper_id IN ({placeholders})
            """,
            list(paper_ids),
        )
        rows = await cursor.fetchall()
        return [_row_to_candidate_paper(row) for row in rows]

    async def save_dedup_count(self, workflow_id: str, count: int) -> None:
        """Persist the number of duplicate papers removed during deduplication.

        Note: `count` is duplicates-removed, NOT the post-dedup paper count.
        PRISMA diagram uses this value for the "duplicates removed" box.
        """
        await self.db.execute(
            "UPDATE workflows SET dedup_count = ? WHERE workflow_id = ?",
            (count, workflow_id),
        )
        await self.db.commit()

    async def get_dedup_count(self, workflow_id: str) -> int | None:
        """Return the number of duplicates removed, or None if not yet persisted."""
        cursor = await self.db.execute(
            "SELECT dedup_count FROM workflows WHERE workflow_id = ?",
            (workflow_id,),
        )
        row = await cursor.fetchone()
        if row is None or row[0] is None:
            return None
        return int(row[0])

    async def get_paper_id_to_citekey_map(self) -> dict[str, str]:
        """Build a paper_id -> citekey map by joining papers and citations on normalized DOI.

        Used to display human-readable citekeys in CASP/MMAT tables and other
        places that have paper_ids but need author-year labels for readability.
        """
        result: dict[str, str] = {}
        try:
            cursor = await self.db.execute(
                """
                SELECT p.paper_id, c.citekey
                FROM papers p
                JOIN citations c ON (
                    c.doi IS NOT NULL
                    AND p.doi IS NOT NULL
                    AND lower(trim(c.doi)) = lower(trim(p.doi))
                )
                WHERE c.citekey IS NOT NULL AND c.citekey != ''
                """
            )
            rows = await cursor.fetchall()
            for pid, citekey in rows:
                if pid and citekey:
                    result[str(pid)] = str(citekey)
        except Exception:
            pass
        return result
