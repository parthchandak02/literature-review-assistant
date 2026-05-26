"""Typed repositories for core persistence operations.

WorkflowRepository composes domain-specific sub-repositories under
``src.db.repos`` and delegates method calls to them.  All existing method
names remain available on WorkflowRepository so callers require no changes.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import aiosqlite

from src.db.repos.costs import CostsRepo
from src.db.repos.events import EventsRepo
from src.db.repos.extraction import ExtractionRepo
from src.db.repos.papers import PapersRepo
from src.db.repos.quality import QualityRepo
from src.db.repos.screening import ScreeningRepo
from src.db.repos.validation import ValidationRepo
from src.db.repos.workflow_state import WorkflowStateRepo
from src.db.repos.writing import WritingRepo
from src.models import (
    CandidatePaper,
    CitationEntryRecord,
    ClaimRecord,
    DecisionLogEntry,
    EvidenceLinkRecord,
    ScreeningDecision,
)

if TYPE_CHECKING:
    pass

_logger = logging.getLogger(__name__)


class WorkflowRepository:
    """Coordinator that composes domain-specific sub-repositories.

    Attribute access for any method not defined directly on this class is
    automatically delegated to the appropriate sub-repo via ``__getattr__``.
    """

    def __init__(self, db: aiosqlite.Connection):
        self.db = db
        self.papers = PapersRepo(db)
        self.screening = ScreeningRepo(db)
        self.extraction = ExtractionRepo(db)
        self.quality = QualityRepo(db)
        self.writing = WritingRepo(db)
        self.costs = CostsRepo(db)
        self.workflow_state = WorkflowStateRepo(db)
        self.events = EventsRepo(db)
        self.validation = ValidationRepo(db)

    # Ordered lookup list for __getattr__ delegation.
    _SUB_REPO_ATTRS = (
        "papers",
        "screening",
        "extraction",
        "quality",
        "writing",
        "costs",
        "workflow_state",
        "events",
        "validation",
    )

    def __getattr__(self, name: str) -> Any:
        # Only triggered when normal attribute lookup fails.
        # Skip private/dunder attributes to avoid recursion during pickling etc.
        if name.startswith("_"):
            raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")
        for attr_name in self._SUB_REPO_ATTRS:
            repo = object.__getattribute__(self, attr_name)
            try:
                return getattr(repo, name)
            except AttributeError:
                continue
        raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")

    # ------------------------------------------------------------------
    # Cross-domain orchestrated methods
    # ------------------------------------------------------------------

    async def bulk_save_screening_decisions(
        self,
        workflow_id: str,
        stage: str,
        papers: list[CandidatePaper],
        decisions: list[ScreeningDecision],
    ) -> None:
        """Batch-insert keyword pre-filter decisions into both screening tables.

        Writes one row per paper to screening_decisions (individual reviewer
        record) and one row to dual_screening_results (PRISMA aggregate), all
        in a single commit. Saves each paper to the papers table first to
        satisfy the foreign-key constraint, then filters decisions to only
        those whose paper_id actually exists in the DB.
        """
        paper_by_id = {p.paper_id: p for p in papers}
        for decision in decisions:
            paper = paper_by_id.get(decision.paper_id)
            if paper is not None:
                await self.papers.save_paper(paper)

        all_decision_ids = [d.paper_id for d in decisions]
        if all_decision_ids:
            placeholders = ",".join("?" * len(all_decision_ids))
            cursor = await self.db.execute(
                f"SELECT paper_id FROM papers WHERE paper_id IN ({placeholders})",
                all_decision_ids,
            )
            existing_ids = {str(row[0]) for row in await cursor.fetchall()}
        else:
            existing_ids = set()

        valid = [d for d in decisions if d.paper_id in existing_ids]
        skipped = len(decisions) - len(valid)
        if skipped:
            _logger.warning(
                "bulk_save_screening_decisions: skipped %d decisions for non-existent paper_ids",
                skipped,
            )

        if not valid:
            return

        await self.db.executemany(
            """
            INSERT INTO screening_decisions (
                workflow_id, paper_id, stage, decision, reason, exclusion_reason,
                reviewer_type, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workflow_id, paper_id, stage, reviewer_type) DO UPDATE SET
                decision = excluded.decision,
                reason = excluded.reason,
                exclusion_reason = excluded.exclusion_reason,
                confidence = excluded.confidence,
                created_at = CURRENT_TIMESTAMP
            """,
            [
                (
                    workflow_id,
                    d.paper_id,
                    stage,
                    d.decision.value,
                    d.reason,
                    d.exclusion_reason.value if d.exclusion_reason else None,
                    d.reviewer_type.value,
                    d.confidence,
                )
                for d in valid
            ],
        )
        await self.db.executemany(
            """
            INSERT OR IGNORE INTO dual_screening_results (
                workflow_id, paper_id, stage, agreement, final_decision, adjudication_needed
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [(workflow_id, d.paper_id, stage, 1, d.decision.value, 0) for d in valid],
        )
        await self.db.commit()

    async def save_screening_metric(
        self,
        workflow_id: str,
        metric_name: str,
        metric_value: int | float,
        *,
        phase: str = "phase_3_screening",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Persist numeric screening QA counters in decision_log."""
        payload: dict[str, Any] = {"metric": metric_name, "value": metric_value}
        if details:
            payload["details"] = details
        await self.events.append_decision_log(
            DecisionLogEntry(
                workflow_id=workflow_id,
                decision_type="screening_metric",
                decision=str(metric_value),
                rationale=json.dumps(payload, sort_keys=True),
                actor="workflow_run",
                phase=phase,
            )
        )

    async def rollback_phase_data(self, workflow_id: str, from_phase: str) -> None:
        """Delete phase-scoped data for explicit resume rewinds.

        This enforces idempotent re-runs when a user resumes from an earlier
        phase (especially `phase_2_search`) by clearing all downstream
        materialized state before replay.
        """
        phase_order = [
            "phase_2_search",
            "phase_3_screening",
            "phase_4_extraction_quality",
            "phase_4b_embedding",
            "phase_5_synthesis",
            "phase_5b_knowledge_graph",
            "phase_5c_pre_writing_gate",
            "phase_6_writing",
            "finalize",
        ]
        if from_phase not in phase_order:
            return

        start_idx = phase_order.index(from_phase)
        if start_idx <= phase_order.index("phase_6_writing"):
            await self.writing.bump_writing_generation(workflow_id)

        async def _delete(table: str, has_workflow_id: bool = True) -> None:
            if has_workflow_id:
                await self.db.execute(f"DELETE FROM {table} WHERE workflow_id = ?", (workflow_id,))
            else:
                await self.db.execute(f"DELETE FROM {table}")

        phases_to_clear = phase_order[start_idx:]
        for p in phases_to_clear:
            await self.db.execute(
                "DELETE FROM workflow_steps WHERE workflow_id = ? AND phase = ?",
                (workflow_id, p),
            )
            await self.db.execute(
                "DELETE FROM recovery_policies WHERE workflow_id = ? AND phase = ?",
                (workflow_id, p),
            )

        if start_idx <= phase_order.index("phase_6_writing"):
            await _delete("section_outlines")
            await _delete("writing_manifests")
            for table in (
                "fallback_events",
                "manuscript_assemblies",
                "manuscript_assets",
                "manuscript_blocks",
                "manuscript_sections",
                "section_drafts",
            ):
                await _delete(table)
            for table in ("evidence_links", "claims", "citations"):
                await _delete(table, has_workflow_id=False)

        if start_idx <= phase_order.index("phase_6_writing"):
            for table in ("manuscript_audit_findings", "manuscript_audit_runs"):
                await _delete(table)

        if start_idx <= phase_order.index("phase_5b_knowledge_graph"):
            for table in ("paper_relationships", "graph_communities", "research_gaps"):
                await _delete(table)

        if start_idx <= phase_order.index("phase_5_synthesis"):
            await _delete("synthesis_results")

        if start_idx <= phase_order.index("phase_4b_embedding"):
            await _delete("paper_chunks_meta")
            await _delete("rag_retrieval_diagnostics")

        if start_idx <= phase_order.index("phase_4_extraction_quality"):
            for table in (
                "extraction_records",
                "rob_assessments",
                "casp_assessments",
                "mmat_assessments",
                "grade_assessments",
            ):
                await _delete(table)
            await self.db.execute(
                """
                DELETE FROM study_cohort_membership
                WHERE workflow_id = ? AND source_phase = 'phase_4_extraction_quality'
                """,
                (workflow_id,),
            )

        if start_idx <= phase_order.index("phase_3_screening"):
            for table in ("dual_screening_results", "screening_decisions", "study_cohort_membership"):
                await _delete(table)

        if start_idx <= phase_order.index("phase_2_search"):
            await _delete("search_results")
            await _delete("papers", has_workflow_id=False)

        await self.db.commit()


class CitationRepository:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def ensure_schema(self) -> None:
        """Idempotent migration: add columns introduced after initial schema creation."""
        for _ddl in (
            "ALTER TABLE citations ADD COLUMN url TEXT",
            "ALTER TABLE citations ADD COLUMN source_type TEXT NOT NULL DEFAULT 'included'",
        ):
            try:
                await self.db.execute(_ddl)
                await self.db.commit()
            except Exception:
                pass

        _METHODOLOGY_KEYS = (
            "Page2021",
            "Sterne2019",
            "Sterne2016",
            "Guyatt2011",
            "Cohen1960",
        )
        try:
            placeholders = ",".join("?" * len(_METHODOLOGY_KEYS))
            await self.db.execute(
                f"UPDATE citations SET source_type='methodology'"
                f" WHERE citekey IN ({placeholders}) AND source_type='included'",
                _METHODOLOGY_KEYS,
            )
            await self.db.execute(
                "UPDATE citations SET source_type='background_sr' WHERE citekey LIKE '%SR' AND source_type='included'"
            )
            await self.db.commit()
        except Exception:
            pass

    async def register_claim(self, claim: ClaimRecord) -> None:
        await self.db.execute(
            """
            INSERT INTO claims (claim_id, paper_id, claim_text, section, confidence)
            VALUES (?, ?, ?, ?, ?)
            """,
            (claim.claim_id, claim.paper_id, claim.claim_text, claim.section, claim.confidence),
        )
        await self.db.commit()

    async def register_citation(self, citation: CitationEntryRecord) -> None:
        _citekey_cur = await self.db.execute(
            "SELECT citation_id FROM citations WHERE citekey = ? LIMIT 1", (citation.citekey,)
        )
        _citekey_row = await _citekey_cur.fetchone()
        if _citekey_row:
            await self.db.execute(
                """
                UPDATE citations
                SET doi = ?,
                    url = ?,
                    title = ?,
                    authors = ?,
                    year = ?,
                    journal = ?,
                    bibtex = ?,
                    resolved = ?,
                    source_type = ?
                WHERE citekey = ?
                """,
                (
                    citation.doi,
                    citation.url,
                    citation.title,
                    json.dumps(citation.authors),
                    citation.year,
                    citation.journal,
                    citation.bibtex,
                    1 if citation.resolved else 0,
                    citation.source_type,
                    citation.citekey,
                ),
            )
            await self.db.commit()
            return
        if citation.doi:
            _doi_cur = await self.db.execute("SELECT 1 FROM citations WHERE doi = ? LIMIT 1", (citation.doi,))
            if await _doi_cur.fetchone():
                return

        cursor = await self.db.execute(
            """
            INSERT OR IGNORE INTO citations (citation_id, citekey, doi, url, title, authors, year, journal, bibtex, resolved, source_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                citation.citation_id,
                citation.citekey,
                citation.doi,
                citation.url,
                citation.title,
                json.dumps(citation.authors),
                citation.year,
                citation.journal,
                citation.bibtex,
                1 if citation.resolved else 0,
                citation.source_type,
            ),
        )
        if cursor.rowcount == 0:
            await self.db.execute(
                """
                UPDATE citations
                SET doi = ?,
                    url = ?,
                    title = ?,
                    authors = ?,
                    year = ?,
                    journal = ?,
                    bibtex = ?,
                    resolved = ?,
                    source_type = ?
                WHERE citekey = ? OR citation_id = ?
                """,
                (
                    citation.doi,
                    citation.url,
                    citation.title,
                    json.dumps(citation.authors),
                    citation.year,
                    citation.journal,
                    citation.bibtex,
                    1 if citation.resolved else 0,
                    citation.source_type,
                    citation.citekey,
                    citation.citation_id,
                ),
            )
        await self.db.commit()

    async def link_evidence(self, link: EvidenceLinkRecord) -> None:
        await self.db.execute(
            """
            INSERT INTO evidence_links (claim_id, citation_id, evidence_span, evidence_score)
            VALUES (?, ?, ?, ?)
            """,
            (link.claim_id, link.citation_id, link.evidence_span, link.evidence_score),
        )
        await self.db.commit()

    async def get_unlinked_claim_ids(self, section: str | None = None) -> list[str]:
        if section:
            cursor = await self.db.execute(
                """
                SELECT c.claim_id
                FROM claims c
                LEFT JOIN evidence_links e ON c.claim_id = e.claim_id
                WHERE e.claim_id IS NULL
                  AND lower(COALESCE(c.section, '')) = lower(?)
                """,
                (section,),
            )
        else:
            cursor = await self.db.execute(
                """
                SELECT c.claim_id
                FROM claims c
                LEFT JOIN evidence_links e ON c.claim_id = e.claim_id
                WHERE e.claim_id IS NULL
                """
            )
        rows = await cursor.fetchall()
        return [str(row[0]) for row in rows]

    async def get_unresolved_citation_ids(self) -> list[str]:
        cursor = await self.db.execute("SELECT citation_id FROM citations WHERE resolved = 0")
        rows = await cursor.fetchall()
        return [str(row[0]) for row in rows]

    async def get_citekeys(self) -> list[str]:
        cursor = await self.db.execute("SELECT citekey FROM citations")
        rows = await cursor.fetchall()
        return [str(row[0]) for row in rows]

    async def get_included_citekeys(self) -> list[str]:
        """Return citekeys for included primary studies only (source_type='included').

        Excludes methodology references (Page2021, Cohen1960, etc.) and background
        SR citations so callers can enforce citation coverage only over actual
        included studies. For pre-migration DBs that truly lack source_type,
        falls back to all citekeys.
        """
        try:
            cursor = await self.db.execute(
                "SELECT citekey FROM citations WHERE source_type = 'included' ORDER BY citekey"
            )
        except aiosqlite.OperationalError as exc:
            if "no such column: source_type" not in str(exc).lower():
                raise
            cursor = await self.db.execute("SELECT citekey FROM citations ORDER BY citekey")
        rows = await cursor.fetchall()
        return [str(row[0]) for row in rows]

    async def get_citation_map(self) -> dict[str, str]:
        """Return mapping of citekey -> citation_id for all registered citations."""
        cursor = await self.db.execute("SELECT citekey, citation_id FROM citations")
        rows = await cursor.fetchall()
        return {str(row[0]): str(row[1]) for row in rows}

    async def get_claim_citation_pairs(self) -> list[tuple[str, str]]:
        cursor = await self.db.execute(
            """
            SELECT c.claim_id, cit.citekey
            FROM evidence_links e
            JOIN claims c ON c.claim_id = e.claim_id
            JOIN citations cit ON cit.citation_id = e.citation_id
            """
        )
        rows = await cursor.fetchall()
        return [(str(row[0]), str(row[1])) for row in rows]

    async def get_all_citations_for_export(
        self,
    ) -> list[tuple[str, str, str | None, str, str, int | None, str | None, str | None, str | None]]:
        """Return (citation_id, citekey, doi, title, authors_json, year, journal, bibtex, url) for BibTeX export."""
        cursor = await self.db.execute(
            """
            SELECT citation_id, citekey, doi, title, authors, year, journal, bibtex, url
            FROM citations
            ORDER BY citekey
            """
        )
        rows = await cursor.fetchall()
        return [
            (
                str(row[0]),
                str(row[1]),
                str(row[2]) if row[2] else None,
                str(row[3]),
                str(row[4]) if row[4] else "{}",
                int(row[5]) if row[5] is not None else None,
                str(row[6]) if row[6] else None,
                str(row[7]) if row[7] else None,
                str(row[8]) if row[8] else None,
            )
            for row in rows
        ]

    async def get_citekeys_by_source_types(self, source_types: set[str]) -> set[str]:
        """Return citekeys for source_type values.

        Falls back to empty set on legacy DBs that predate source_type.
        """
        if not source_types:
            return set()
        try:
            placeholders = ",".join("?" * len(source_types))
            cursor = await self.db.execute(
                f"""
                SELECT citekey
                FROM citations
                WHERE lower(COALESCE(source_type, '')) IN ({placeholders})
                """,
                tuple(t.lower() for t in sorted(source_types)),
            )
            rows = await cursor.fetchall()
        except Exception:
            return set()
        return {str(row[0]) for row in rows if row and row[0]}


async def merge_papers_from_parent(
    parent_db_path: str,
    dst_db: aiosqlite.Connection,
) -> int:
    """Copy included papers and their screening decisions from a parent run DB.

    Only copies papers that are not already present in dst_db (INSERT OR IGNORE).
    Marks merged papers with source='merged_from_parent' so downstream phases
    can skip re-screening and re-embedding them.

    Returns the number of papers merged.
    """
    import logging as _logging

    _logger = _logging.getLogger(__name__)

    merged = 0
    parent_papers = []
    parent_decisions: dict[str, str] = {}

    try:
        async with aiosqlite.connect(parent_db_path) as src_db:
            src_db.row_factory = aiosqlite.Row

            try:
                async with src_db.execute(
                    "SELECT paper_id, title, abstract, authors, year, doi, url, source_database, "
                    "       display_label, openalex_id FROM papers"
                ) as cur:
                    parent_papers = await cur.fetchall()
            except Exception:
                _logger.warning("merge_papers_from_parent: could not read papers from %s", parent_db_path)
                return 0

            try:
                async with src_db.execute("SELECT paper_id, final_decision FROM dual_screening_results") as cur:
                    for row in await cur.fetchall():
                        parent_decisions[row["paper_id"]] = row["final_decision"]
            except Exception:
                pass

    except Exception:
        _logger.warning("merge_papers_from_parent: cannot open parent DB at %s", parent_db_path)
        return 0

    for row in parent_papers:
        try:
            await dst_db.execute(
                """INSERT OR IGNORE INTO papers
                   (paper_id, title, abstract, authors, year, doi, url, source_database,
                    source_category, display_label, openalex_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    row["paper_id"],
                    row["title"],
                    row["abstract"],
                    row["authors"],
                    row["year"],
                    row["doi"],
                    row["url"],
                    "merged_from_parent",
                    "database",
                    row["display_label"],
                    row["openalex_id"],
                ),
            )
            merged += 1

            decision = parent_decisions.get(row["paper_id"])
            if decision:
                await dst_db.execute(
                    """INSERT OR IGNORE INTO dual_screening_results
                       (workflow_id, paper_id, stage, agreement, final_decision, adjudication_needed)
                       VALUES ('merged', ?, 'stage1', 1, ?, 0)""",
                    (row["paper_id"], decision),
                )
        except Exception as exc:
            _logger.debug("merge_papers_from_parent: skip %s: %s", row["paper_id"], exc)

    await dst_db.commit()
    _logger.info("merge_papers_from_parent: merged %d papers from %s", merged, parent_db_path)
    return merged
