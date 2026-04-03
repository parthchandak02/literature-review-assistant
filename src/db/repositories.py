"""Typed repositories for core persistence operations."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

import aiosqlite
from pydantic import ValidationError

from src.models import (
    CandidatePaper,
    CitationEntryRecord,
    ClaimRecord,
    CohortMembershipRecord,
    CostRecord,
    DecisionLogEntry,
    EvidenceLinkRecord,
    ExtractionRecord,
    GateResult,
    GRADEOutcomeAssessment,
    ManuscriptAssembly,
    ManuscriptAsset,
    ManuscriptAuditFinding,
    ManuscriptAuditResult,
    ManuscriptBlock,
    ManuscriptSection,
    RagRetrievalDiagnostic,
    RoB2Assessment,
    RobinsIAssessment,
    ScreeningDecision,
    ScreeningDecisionType,
    SearchResult,
    SectionDraft,
    ValidationArtifactRecord,
    ValidationCheckRecord,
    ValidationRunRecord,
)
from src.models.enums import SourceCategory
from src.models.papers import compute_display_label
from src.synthesis.feasibility import SynthesisFeasibility
from src.synthesis.narrative import NarrativeSynthesis

_logger = logging.getLogger(__name__)
_HEADING_RE = re.compile(r"^(#{2,6})\s+(.+)$")
_MARKER_RE = re.compile(r"^<!--\s*SECTION_BLOCK:([a-zA-Z0-9_.-]+)\s*-->$")
_CITE_RE = re.compile(r"\[(\d+|[A-Za-z][A-Za-z0-9_:-]*)\]")


def _row_to_candidate_paper(row: tuple[Any, ...]) -> CandidatePaper:
    """Convert a papers table row to CandidatePaper.

    Expected column order (matches all SELECT queries in this module):
      0 paper_id, 1 title, 2 authors, 3 year, 4 source_database, 5 doi,
      6 abstract, 7 url, 8 keywords, 9 source_category, 10 openalex_id,
      11 country, 12 display_label
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
    display_label = str(row[12]) if len(row) > 12 and row[12] else None
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
        display_label=display_label,
    )


class WorkflowRepository:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def save_screening_decision(
        self,
        workflow_id: str,
        stage: str,
        decision: ScreeningDecision,
    ) -> None:
        await self.db.execute(
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
            (
                workflow_id,
                decision.paper_id,
                stage,
                decision.decision.value,
                decision.reason,
                decision.exclusion_reason.value if decision.exclusion_reason else None,
                decision.reviewer_type.value,
                decision.confidence,
            ),
        )
        await self.db.commit()

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
                await self.save_paper(paper)

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

    async def save_dual_screening_result(
        self,
        workflow_id: str,
        paper_id: str,
        stage: str,
        agreement: bool,
        final_decision: ScreeningDecisionType,
        adjudication_needed: bool,
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO dual_screening_results (
                workflow_id, paper_id, stage, agreement, final_decision, adjudication_needed
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(workflow_id, paper_id, stage) DO UPDATE SET
                agreement=excluded.agreement,
                final_decision=excluded.final_decision,
                adjudication_needed=excluded.adjudication_needed
            """,
            (
                workflow_id,
                paper_id,
                stage,
                1 if agreement else 0,
                final_decision.value,
                1 if adjudication_needed else 0,
            ),
        )
        await self.db.commit()

    async def save_search_result(self, result: SearchResult) -> None:
        # Idempotency on resume/re-run: replace existing row for the same
        # workflow/database/source/query tuple instead of accumulating duplicates.
        await self.db.execute(
            """
            DELETE FROM search_results
            WHERE workflow_id = ?
              AND database_name = ?
              AND source_category = ?
              AND search_query = ?
            """,
            (
                result.workflow_id,
                result.database_name,
                result.source_category.value,
                result.search_query,
            ),
        )
        await self.db.execute(
            """
            INSERT INTO search_results (
                database_name, source_category, search_date, search_query,
                limits_applied, records_retrieved, workflow_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.database_name,
                result.source_category.value,
                result.search_date,
                result.search_query,
                result.limits_applied,
                result.records_retrieved,
                result.workflow_id,
            ),
        )
        for paper in result.papers:
            await self.save_paper(paper)
        await self.db.commit()

    async def save_paper(self, paper: CandidatePaper) -> None:
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
            label,
        )
        upsert_sql = """
            INSERT INTO papers (
                paper_id, title, authors, year, source_database, doi, abstract, url,
                keywords, source_category, openalex_id, country, display_label
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                display_label = excluded.display_label
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
            # rationale format: "connector_name: ExceptionType: message"
            connector_name = str(rationale).split(":")[0].strip()
            if connector_name and connector_name not in seen:
                seen.add(connector_name)
                failed.append(connector_name)
        return failed

    async def get_prisma_screening_counts(self, workflow_id: str) -> tuple[int, int, int, int, int, dict[str, int]]:
        """Return (records_screened, records_excluded_screening, reports_sought,
        reports_not_retrieved, reports_assessed, reports_excluded_with_reasons).

        When skip_fulltext_if_no_pdf=true, papers whose full text could not be
        retrieved are excluded with ExclusionReason.NO_FULL_TEXT at the fulltext
        stage.  PRISMA 2020 item 17 requires these to appear in "Reports not
        retrieved", NOT in "Reports excluded with reasons" (they were never
        assessed for eligibility -- they were simply unreachable).

        ft_assessed and ft_excluded are adjusted to exclude the not-retrieved
        papers so the caller's PRISMA arithmetic remains consistent:
            reports_sought == reports_not_retrieved + reports_assessed
        """
        ta_screened = 0
        ta_excluded = 0
        ft_sought = 0
        ft_assessed = 0
        ft_excluded = 0
        exclusion_reasons: dict[str, int] = {}
        cohort_counts_available = False

        # Exclude batch_screened_low rows from the PRISMA counts. Those papers were
        # auto-excluded by the batch LLM pre-ranker and belong in PRISMA "automation_excluded"
        # (before screening), not in "records_screened". Including them inflated ta_screened
        # above records_after_dedup, causing arithmetic failures in the PRISMA flow diagram.
        cursor = await self.db.execute(
            """
            SELECT stage, final_decision, COUNT(*)
            FROM dual_screening_results
            WHERE workflow_id = ?
              AND final_decision != 'batch_screened_low'
            GROUP BY stage, final_decision
            """,
            (workflow_id,),
        )
        for stage, decision, cnt in await cursor.fetchall():
            c = int(cnt)
            if stage == "title_abstract":
                ta_screened += c
                if decision == "exclude":
                    ta_excluded += c
                elif decision == "include":
                    ft_sought += c
            elif stage == "fulltext":
                ft_assessed += c
                if decision == "exclude":
                    ft_excluded += c

        # Query fulltext exclusion reasons from screening_decisions.
        # Do this unconditionally instead of gating on ft_excluded from
        # dual_screening_results because resume/interrupted runs may have
        # sparse dual rows while screening_decisions already contains final
        # fulltext exclusion reasons (including no_full_text).
        reason_cursor = await self.db.execute(
            """
            SELECT COALESCE(exclusion_reason, 'other'), COUNT(DISTINCT paper_id)
            FROM screening_decisions
            WHERE workflow_id = ? AND stage = 'fulltext' AND decision = 'exclude'
            GROUP BY exclusion_reason
            """,
            (workflow_id,),
        )
        for reason, cnt in await reason_cursor.fetchall():
            key = str(reason).strip().lower().replace(" ", "_") if reason else "other"
            exclusion_reasons[key] = exclusion_reasons.get(key, 0) + int(cnt)

        # Canonical source: study_cohort_membership fulltext_status semantics.
        # This table should encode fulltext outcome parity explicitly:
        # assessed vs not_retrieved.
        cohort_cursor = await self.db.execute(
            """
            SELECT
                COUNT(DISTINCT CASE
                    WHEN fulltext_status IN ('assessed', 'not_retrieved') THEN paper_id
                    ELSE NULL
                END) AS reports_sought,
                COUNT(DISTINCT CASE
                    WHEN fulltext_status = 'not_retrieved' THEN paper_id
                    ELSE NULL
                END) AS reports_not_retrieved,
                COUNT(DISTINCT CASE
                    WHEN fulltext_status = 'assessed' THEN paper_id
                    ELSE NULL
                END) AS reports_assessed
            FROM study_cohort_membership
            WHERE workflow_id = ?
            """,
            (workflow_id,),
        )
        cohort_row = await cohort_cursor.fetchone()
        if cohort_row and cohort_row[0] is not None and int(cohort_row[0]) > 0:
            cohort_counts_available = True
            ft_sought = int(cohort_row[0])
            reports_not_retrieved = int(cohort_row[1] or 0)
            ft_assessed = int(cohort_row[2] or 0)
        else:
            # Fallback for legacy runs with sparse/missing cohort rows.
            # Separate "not retrieved" from "assessed but excluded".
            # no_full_text papers were never read -- they belong in the PRISMA
            # "Reports not retrieved" box, not in "Reports excluded with reasons".
            reports_not_retrieved = exclusion_reasons.pop("no_full_text", 0)
            # Adjust ft_assessed and ft_excluded to exclude the not-retrieved papers.
            ft_assessed = max(0, ft_assessed - reports_not_retrieved)
            ft_excluded = max(0, ft_excluded - reports_not_retrieved)
        exclusion_reasons.pop("no_full_text", None)
        # Resume/partial-run edge case: full-text retrieval can be persisted in
        # extraction_records while fulltext-stage dual_screening_results rows are
        # sparse or absent. In that case, relying only on fulltext rows collapses
        # reports_assessed to 0, which breaks PRISMA arithmetic in writing/export.
        # Keep the invariant:
        #   reports_sought == reports_not_retrieved + reports_assessed
        expected_assessed = max(0, ft_sought - reports_not_retrieved)
        if not cohort_counts_available and expected_assessed > ft_assessed:
            ft_assessed = expected_assessed

        return ta_screened, ta_excluded, ft_sought, reports_not_retrieved, ft_assessed, exclusion_reasons

    async def get_processed_paper_ids(self, workflow_id: str, stage: str) -> set[str]:
        cursor = await self.db.execute(
            """
            SELECT DISTINCT paper_id
            FROM screening_decisions
            WHERE workflow_id = ? AND stage = ?
            """,
            (workflow_id, stage),
        )
        rows = await cursor.fetchall()
        return {str(row[0]) for row in rows}

    async def get_all_papers(self) -> list[CandidatePaper]:
        """Load all papers from the papers table (for resume state reconstruction)."""
        cursor = await self.db.execute(
            """
            SELECT paper_id, title, authors, year, source_database, doi, abstract, url,
                   keywords, source_category, openalex_id, country, display_label
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
                   keywords, source_category, openalex_id, country, display_label
            FROM papers
            WHERE paper_id IN ({placeholders})
            """,
            list(paper_ids),
        )
        rows = await cursor.fetchall()
        return [_row_to_candidate_paper(row) for row in rows]

    async def get_checkpoints(self, workflow_id: str) -> dict[str, str]:
        """Return phase -> status for all checkpoints of this workflow."""
        cursor = await self.db.execute(
            """
            SELECT phase, status FROM checkpoints WHERE workflow_id = ?
            """,
            (workflow_id,),
        )
        rows = await cursor.fetchall()
        return {str(row[0]): str(row[1]) for row in rows}

    async def get_included_paper_ids(self, workflow_id: str) -> set[str]:
        """Paper IDs in canonical synthesis cohort (fallback to fulltext includes)."""
        cursor = await self.db.execute(
            """
            SELECT paper_id
            FROM study_cohort_membership
            WHERE workflow_id = ? AND synthesis_eligibility = 'included_primary'
            """,
            (workflow_id,),
        )
        rows = await cursor.fetchall()
        if rows:
            return {str(row[0]) for row in rows}

        # Legacy fallback for runs created before cohort ledger rollout.
        cursor = await self.db.execute(
            """
            SELECT paper_id FROM dual_screening_results
            WHERE workflow_id = ? AND stage = 'fulltext' AND final_decision IN ('include', 'uncertain')
            """,
            (workflow_id,),
        )
        rows = await cursor.fetchall()
        return {str(row[0]) for row in rows}

    async def upsert_cohort_membership(self, record: CohortMembershipRecord) -> None:
        """Create or update one canonical cohort membership row."""
        await self.db.execute(
            """
            INSERT INTO study_cohort_membership (
                workflow_id,
                paper_id,
                screening_status,
                fulltext_status,
                synthesis_eligibility,
                exclusion_reason_code,
                source_phase
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workflow_id, paper_id) DO UPDATE SET
                screening_status = excluded.screening_status,
                fulltext_status = excluded.fulltext_status,
                synthesis_eligibility = excluded.synthesis_eligibility,
                exclusion_reason_code = excluded.exclusion_reason_code,
                source_phase = excluded.source_phase,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                record.workflow_id,
                record.paper_id,
                record.screening_status,
                record.fulltext_status,
                record.synthesis_eligibility,
                record.exclusion_reason_code,
                record.source_phase,
            ),
        )
        await self.db.commit()

    async def bulk_upsert_cohort_memberships(self, records: list[CohortMembershipRecord]) -> None:
        """Batch upsert canonical cohort rows in one transaction."""
        if not records:
            return
        await self.db.executemany(
            """
            INSERT INTO study_cohort_membership (
                workflow_id,
                paper_id,
                screening_status,
                fulltext_status,
                synthesis_eligibility,
                exclusion_reason_code,
                source_phase
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workflow_id, paper_id) DO UPDATE SET
                screening_status = excluded.screening_status,
                fulltext_status = excluded.fulltext_status,
                synthesis_eligibility = excluded.synthesis_eligibility,
                exclusion_reason_code = excluded.exclusion_reason_code,
                source_phase = excluded.source_phase,
                updated_at = CURRENT_TIMESTAMP
            """,
            [
                (
                    record.workflow_id,
                    record.paper_id,
                    record.screening_status,
                    record.fulltext_status,
                    record.synthesis_eligibility,
                    record.exclusion_reason_code,
                    record.source_phase,
                )
                for record in records
            ],
        )
        await self.db.commit()

    async def get_synthesis_included_paper_ids(self, workflow_id: str) -> set[str]:
        """Return paper_ids that are canonical synthesis-included."""
        cursor = await self.db.execute(
            """
            SELECT paper_id
            FROM study_cohort_membership
            WHERE workflow_id = ? AND synthesis_eligibility = 'included_primary'
            """,
            (workflow_id,),
        )
        rows = await cursor.fetchall()
        return {str(row[0]) for row in rows}

    async def get_title_abstract_include_ids(self, workflow_id: str) -> set[str]:
        """Paper IDs that passed title/abstract screening (include or uncertain).

        Used on resume to recover pre-crash screening decisions that were persisted
        but not returned by screen_batch (which skips already-processed papers).
        """
        cursor = await self.db.execute(
            """
            SELECT paper_id FROM dual_screening_results
            WHERE workflow_id = ? AND stage = 'title_abstract'
              AND final_decision IN ('include', 'uncertain')
            """,
            (workflow_id,),
        )
        rows = await cursor.fetchall()
        return {str(row[0]) for row in rows}

    async def get_fulltext_final_decisions(self, workflow_id: str) -> dict[str, str]:
        """Return paper_id -> final fulltext decision from dual screening results."""
        cursor = await self.db.execute(
            """
            SELECT paper_id, final_decision
            FROM dual_screening_results
            WHERE workflow_id = ? AND stage = 'fulltext'
            """,
            (workflow_id,),
        )
        rows = await cursor.fetchall()
        return {str(paper_id): str(decision) for paper_id, decision in rows}

    async def get_fulltext_not_retrieved_ids(self, workflow_id: str) -> set[str]:
        """Return paper_ids excluded at fulltext due to no_full_text."""
        cursor = await self.db.execute(
            """
            SELECT DISTINCT paper_id
            FROM screening_decisions
            WHERE workflow_id = ?
              AND stage = 'fulltext'
              AND decision = 'exclude'
              AND lower(COALESCE(exclusion_reason, '')) = 'no_full_text'
            """,
            (workflow_id,),
        )
        rows = await cursor.fetchall()
        return {str(row[0]) for row in rows}

    async def get_extraction_record_ids(self, workflow_id: str) -> set[str]:
        """Paper IDs already in extraction_records."""
        cursor = await self.db.execute(
            """
            SELECT paper_id FROM extraction_records WHERE workflow_id = ?
            """,
            (workflow_id,),
        )
        rows = await cursor.fetchall()
        return {str(row[0]) for row in rows}

    async def get_rob_assessment_ids(self, workflow_id: str) -> set[str]:
        """Paper IDs that already have a row in rob_assessments for this workflow."""
        cursor = await self.db.execute(
            """
            SELECT paper_id FROM rob_assessments WHERE workflow_id = ?
            """,
            (workflow_id,),
        )
        rows = await cursor.fetchall()
        return {str(row[0]) for row in rows}

    async def load_extraction_records(self, workflow_id: str) -> list[ExtractionRecord]:
        """Load all extraction records for a workflow.

        Skips malformed or legacy records (ValidationError) to allow resume of
        old runs with schema changes.
        """
        cursor = await self.db.execute(
            """
            SELECT paper_id, data FROM extraction_records WHERE workflow_id = ?
            """,
            (workflow_id,),
        )
        rows = await cursor.fetchall()
        records: list[ExtractionRecord] = []
        for row in rows:
            paper_id = str(row[0]) if row else "unknown"
            data_json = str(row[1]) if len(row) > 1 else str(row[0])
            try:
                records.append(ExtractionRecord.model_validate_json(data_json))
            except (ValidationError, Exception) as exc:
                _logger.warning(
                    "Skipping malformed extraction record for paper %s: %s",
                    paper_id,
                    exc,
                )
        return records

    async def get_completed_sections(self, workflow_id: str) -> set[str]:
        """Section names that have at least one draft (for writing phase resume)."""
        cursor = await self.db.execute(
            """
            SELECT DISTINCT section FROM section_drafts WHERE workflow_id = ?
            """,
            (workflow_id,),
        )
        rows = await cursor.fetchall()
        return {str(row[0]) for row in rows}

    async def save_section_draft(self, draft: SectionDraft) -> None:
        """Persist a section draft for checkpoint/resume."""
        await self.db.execute(
            """
            INSERT INTO section_drafts (workflow_id, section, version, content, claims_used, citations_used, word_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workflow_id, section, version) DO UPDATE SET
                content = excluded.content,
                claims_used = excluded.claims_used,
                citations_used = excluded.citations_used,
                word_count = excluded.word_count
            """,
            (
                draft.workflow_id,
                draft.section,
                draft.version,
                draft.content,
                json.dumps(draft.claims_used),
                json.dumps(draft.citations_used),
                draft.word_count,
            ),
        )
        await self.db.commit()

    def _to_manuscript_blocks(
        self,
        workflow_id: str,
        section_key: str,
        section_version: int,
        content: str,
    ) -> list[ManuscriptBlock]:
        """Parse section text into generic ordered blocks.

        Deterministic parser:
        1) explicit SECTION_BLOCK markers (highest priority),
        2) markdown heading boundaries,
        3) paragraph fallback.
        """
        blocks: list[ManuscriptBlock] = []
        order = 0
        lines = content.splitlines()
        para_buf: list[str] = []

        def _flush_para() -> None:
            nonlocal order, para_buf
            text = "\n".join(x for x in para_buf if x.strip()).strip()
            para_buf = []
            if not text:
                return
            blocks.append(
                ManuscriptBlock(
                    workflow_id=workflow_id,
                    section_key=section_key,
                    section_version=section_version,
                    block_order=order,
                    block_type="paragraph",
                    text=text,
                )
            )
            order += 1

        for raw in lines:
            line = raw.rstrip()
            if _MARKER_RE.match(line.strip()):
                _flush_para()
                blocks.append(
                    ManuscriptBlock(
                        workflow_id=workflow_id,
                        section_key=section_key,
                        section_version=section_version,
                        block_order=order,
                        block_type="marker",
                        text=line.strip(),
                    )
                )
                order += 1
                continue
            hm = _HEADING_RE.match(line.strip())
            if hm:
                _flush_para()
                blocks.append(
                    ManuscriptBlock(
                        workflow_id=workflow_id,
                        section_key=section_key,
                        section_version=section_version,
                        block_order=order,
                        block_type="heading",
                        text=line.strip(),
                        meta_json=json.dumps({"level": len(hm.group(1)), "title": hm.group(2).strip()}),
                    )
                )
                order += 1
                continue
            if not line.strip():
                _flush_para()
                continue
            para_buf.append(line)
        _flush_para()
        if not blocks:
            blocks.append(
                ManuscriptBlock(
                    workflow_id=workflow_id,
                    section_key=section_key,
                    section_version=section_version,
                    block_order=0,
                    block_type="paragraph",
                    text=content.strip(),
                )
            )
        return blocks

    async def save_manuscript_section_from_draft(self, draft: SectionDraft, section_order: int) -> None:
        """Dual-write section draft into DB-first manuscript section/block tables."""
        section = ManuscriptSection(
            workflow_id=draft.workflow_id,
            section_key=draft.section,
            section_order=section_order,
            version=draft.version,
            title=draft.section.replace("_", " ").title(),
            source="parser",
            boundary_confidence=1.0,
            content_hash=sha256(draft.content.encode("utf-8")).hexdigest(),
            content=draft.content,
        )
        blocks = self._to_manuscript_blocks(
            workflow_id=draft.workflow_id,
            section_key=draft.section,
            section_version=draft.version,
            content=draft.content,
        )
        await self.db.execute(
            """
            INSERT INTO manuscript_sections
                (workflow_id, section_key, section_order, version, title, status, source,
                 boundary_confidence, content_hash, content)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workflow_id, section_key, version) DO UPDATE SET
                section_order = excluded.section_order,
                title = excluded.title,
                status = excluded.status,
                source = excluded.source,
                boundary_confidence = excluded.boundary_confidence,
                content_hash = excluded.content_hash,
                content = excluded.content,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                section.workflow_id,
                section.section_key,
                section.section_order,
                section.version,
                section.title,
                section.status,
                section.source,
                section.boundary_confidence,
                section.content_hash,
                section.content,
            ),
        )
        await self.db.execute(
            """
            DELETE FROM manuscript_blocks
            WHERE workflow_id = ? AND section_key = ? AND section_version = ?
            """,
            (draft.workflow_id, draft.section, draft.version),
        )
        await self.db.executemany(
            """
            INSERT INTO manuscript_blocks
                (workflow_id, section_key, section_version, block_order, block_type, text, meta_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    b.workflow_id,
                    b.section_key,
                    b.section_version,
                    b.block_order,
                    b.block_type,
                    b.text,
                    b.meta_json,
                )
                for b in blocks
            ],
        )
        await self.db.commit()

    async def load_latest_manuscript_sections(self, workflow_id: str) -> list[ManuscriptSection]:
        cursor = await self.db.execute(
            """
            SELECT s.workflow_id, s.section_key, s.section_order, s.version, s.title, s.status,
                   s.source, s.boundary_confidence, s.content_hash, s.content
            FROM manuscript_sections s
            JOIN (
                SELECT workflow_id, section_key, MAX(version) AS max_version
                FROM manuscript_sections
                WHERE workflow_id = ?
                GROUP BY workflow_id, section_key
            ) lv
              ON s.workflow_id = lv.workflow_id
             AND s.section_key = lv.section_key
             AND s.version = lv.max_version
            WHERE s.workflow_id = ?
            ORDER BY s.section_order ASC
            """,
            (workflow_id, workflow_id),
        )
        rows = await cursor.fetchall()
        out: list[ManuscriptSection] = []
        for row in rows:
            out.append(
                ManuscriptSection(
                    workflow_id=str(row[0]),
                    section_key=str(row[1]),
                    section_order=int(row[2]),
                    version=int(row[3]),
                    title=str(row[4]),
                    status=str(row[5]),
                    source=str(row[6]),
                    boundary_confidence=float(row[7]),
                    content_hash=str(row[8]),
                    content=str(row[9]),
                )
            )
        return out

    async def load_latest_manuscript_assembly(self, workflow_id: str, target_format: str) -> ManuscriptAssembly | None:
        cursor = await self.db.execute(
            """
            SELECT workflow_id, assembly_id, target_format, content, manifest_json
            FROM manuscript_assemblies
            WHERE workflow_id = ? AND target_format = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (workflow_id, target_format),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return ManuscriptAssembly(
            workflow_id=str(row[0]),
            assembly_id=str(row[1]),
            target_format=str(row[2]),
            content=str(row[3]),
            manifest_json=str(row[4]),
        )

    async def save_manuscript_asset(self, asset: ManuscriptAsset) -> None:
        await self.db.execute(
            """
            INSERT INTO manuscript_assets
                (workflow_id, asset_key, asset_type, format, content, source_path, version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workflow_id, asset_key, version) DO UPDATE SET
                asset_type = excluded.asset_type,
                format = excluded.format,
                content = excluded.content,
                source_path = excluded.source_path
            """,
            (
                asset.workflow_id,
                asset.asset_key,
                asset.asset_type,
                asset.format,
                asset.content,
                asset.source_path,
                asset.version,
            ),
        )
        await self.db.commit()

    async def load_latest_manuscript_asset(self, workflow_id: str, asset_key: str) -> ManuscriptAsset | None:
        cursor = await self.db.execute(
            """
            SELECT workflow_id, asset_key, asset_type, format, content, source_path, version
            FROM manuscript_assets
            WHERE workflow_id = ? AND asset_key = ?
            ORDER BY version DESC
            LIMIT 1
            """,
            (workflow_id, asset_key),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return ManuscriptAsset(
            workflow_id=str(row[0]),
            asset_key=str(row[1]),
            asset_type=str(row[2]),
            format=str(row[3]),
            content=str(row[4]),
            source_path=str(row[5]) if row[5] is not None else None,
            version=int(row[6]),
        )

    async def _validate_assembly_manifest(self, workflow_id: str, manifest_json: str) -> None:
        try:
            manifest = json.loads(manifest_json or "{}")
        except Exception as exc:
            raise RuntimeError("Invalid manuscript assembly manifest JSON") from exc
        sections = manifest.get("sections", [])
        if sections:
            declared_orders = [int(s.get("order", i)) for i, s in enumerate(sections)]
            if sorted(declared_orders) != list(
                range(min(declared_orders), min(declared_orders) + len(declared_orders))
            ):
                raise RuntimeError("Assembly manifest section order is not contiguous")
            for s in sections:
                key = str(s.get("section_key", ""))
                ver = int(s.get("version", 0))
                if not key or ver <= 0:
                    raise RuntimeError("Assembly manifest section reference is invalid")
                cur = await self.db.execute(
                    """
                    SELECT 1 FROM manuscript_sections
                    WHERE workflow_id = ? AND section_key = ? AND version = ?
                    LIMIT 1
                    """,
                    (workflow_id, key, ver),
                )
                row = await cur.fetchone()
                if row is None:
                    raise RuntimeError(f"Assembly manifest references missing section: {key}@v{ver}")
        assets = manifest.get("assets", [])
        for a in assets:
            key = str(a.get("asset_key", ""))
            ver = int(a.get("version", 0))
            if not key or ver <= 0:
                raise RuntimeError("Assembly manifest asset reference is invalid")
            cur = await self.db.execute(
                """
                SELECT 1 FROM manuscript_assets
                WHERE workflow_id = ? AND asset_key = ? AND version = ?
                LIMIT 1
                """,
                (workflow_id, key, ver),
            )
            row = await cur.fetchone()
            if row is None:
                raise RuntimeError(f"Assembly manifest references missing asset: {key}@v{ver}")

    async def save_manuscript_assembly(self, assembly: ManuscriptAssembly) -> None:
        if assembly.target_format not in {"md", "tex"}:
            raise RuntimeError(f"Unsupported manuscript assembly format: {assembly.target_format}")
        await self._validate_assembly_manifest(assembly.workflow_id, assembly.manifest_json)
        await self.db.execute(
            """
            INSERT INTO manuscript_assemblies
                (workflow_id, assembly_id, target_format, content, manifest_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(workflow_id, assembly_id, target_format) DO UPDATE SET
                content = excluded.content,
                manifest_json = excluded.manifest_json
            """,
            (
                assembly.workflow_id,
                assembly.assembly_id,
                assembly.target_format,
                assembly.content,
                assembly.manifest_json,
            ),
        )
        await self.db.commit()

    async def backfill_manuscript_sections_from_drafts(self, workflow_id: str) -> int:
        """Backfill DB-first section tables from latest section_drafts rows."""
        cursor = await self.db.execute(
            """
            SELECT sd.workflow_id, sd.section, sd.version, sd.content, sd.word_count
            FROM section_drafts sd
            JOIN (
                SELECT workflow_id, section, MAX(version) AS max_version
                FROM section_drafts
                WHERE workflow_id = ?
                GROUP BY workflow_id, section
            ) latest
              ON sd.workflow_id = latest.workflow_id
             AND sd.section = latest.section
             AND sd.version = latest.max_version
            WHERE sd.workflow_id = ?
            ORDER BY sd.section
            """,
            (workflow_id, workflow_id),
        )
        rows = await cursor.fetchall()
        if not rows:
            return 0
        count = 0
        for order, row in enumerate(rows):
            draft = SectionDraft(
                workflow_id=str(row[0]),
                section=str(row[1]),
                version=int(row[2]),
                content=str(row[3]),
                claims_used=[],
                citations_used=[],
                word_count=int(row[4]) if row[4] is not None else len(str(row[3]).split()),
            )
            await self.save_manuscript_section_from_draft(draft, section_order=order)
            count += 1
        return count

    async def validate_manuscript_md_parity(self, workflow_id: str, legacy_md: str) -> dict[str, Any]:
        """Compare legacy markdown and latest DB markdown assembly for migration safety."""
        assembly = await self.load_latest_manuscript_assembly(workflow_id, "md")
        if assembly is None:
            return {
                "has_assembly": False,
                "hash_match": False,
                "citation_set_match": False,
                "section_count_match": False,
            }

        legacy_hash = sha256(legacy_md.encode("utf-8")).hexdigest()
        assembly_hash = sha256(assembly.content.encode("utf-8")).hexdigest()
        legacy_cites = sorted(set(_CITE_RE.findall(legacy_md)))
        assembly_cites = sorted(set(_CITE_RE.findall(assembly.content)))
        legacy_sections = len(re.findall(r"^##\s+", legacy_md, flags=re.MULTILINE))
        assembly_sections = len(re.findall(r"^##\s+", assembly.content, flags=re.MULTILINE))
        return {
            "has_assembly": True,
            "hash_match": legacy_hash == assembly_hash,
            "citation_set_match": legacy_cites == assembly_cites,
            "section_count_match": legacy_sections == assembly_sections,
            "legacy_hash": legacy_hash,
            "assembly_hash": assembly_hash,
        }

    async def delete_section_drafts(self, workflow_id: str, sections: set[str] | None = None) -> int:
        """Delete saved section drafts for a workflow.

        Returns number of rows deleted. When sections is None, removes all drafts
        for the workflow; otherwise only the specified section names.
        """
        if sections:
            placeholders = ",".join("?" for _ in sections)
            params = [workflow_id, *sorted(sections)]
            cursor = await self.db.execute(
                f"""
                DELETE FROM section_drafts
                WHERE workflow_id = ?
                  AND section IN ({placeholders})
                """,
                params,
            )
        else:
            cursor = await self.db.execute(
                """
                DELETE FROM section_drafts
                WHERE workflow_id = ?
                """,
                (workflow_id,),
            )
        await self.db.commit()
        return int(cursor.rowcount or 0)

    async def save_gate_result(self, result: GateResult) -> None:
        await self.db.execute(
            """
            INSERT INTO gate_results (
                workflow_id, gate_name, phase, status, details, threshold, actual_value
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.workflow_id,
                result.gate_name,
                result.phase,
                result.status.value,
                result.details,
                result.threshold,
                result.actual_value,
            ),
        )
        await self.db.commit()

    async def get_latest_gate_result(self, workflow_id: str, phase: str, gate_name: str) -> GateResult | None:
        """Return the most recent gate result for the given workflow, phase, and gate."""
        cursor = await self.db.execute(
            """
            SELECT workflow_id, gate_name, phase, status, details, threshold, actual_value
            FROM gate_results
            WHERE workflow_id = ? AND phase = ? AND gate_name = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (workflow_id, phase, gate_name),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        from src.models.enums import GateStatus

        return GateResult(
            workflow_id=str(row[0]),
            gate_name=str(row[1]),
            phase=str(row[2]),
            status=GateStatus(str(row[3])),
            details=str(row[4]),
            threshold=str(row[5]) if row[5] is not None else None,
            actual_value=str(row[6]) if row[6] is not None else None,
        )

    async def save_manuscript_audit(
        self,
        result: ManuscriptAuditResult,
        findings: list[ManuscriptAuditFinding],
        contract_result: "ManuscriptContractResult | None" = None,
        gate_blocked: bool = False,
        gate_failure_reasons: list[str] | None = None,
    ) -> None:
        contract_payload = contract_result
        failure_reasons = gate_failure_reasons or []
        run_columns = await self._table_columns("manuscript_audit_runs")
        insert_columns = [
            "audit_run_id",
            "workflow_id",
            "mode",
            "verdict",
            "passed",
            "selected_profiles_json",
            "summary",
            "total_findings",
            "major_count",
            "minor_count",
            "note_count",
            "blocking_count",
        ]
        insert_values: list[object] = [
            result.audit_run_id,
            result.workflow_id,
            result.mode,
            result.verdict,
            1 if result.passed else 0,
            json.dumps(result.selected_profiles, ensure_ascii=True),
            result.summary,
            result.total_findings,
            result.major_count,
            result.minor_count,
            result.note_count,
            result.blocking_count,
        ]
        if "contract_mode" in run_columns:
            insert_columns.append("contract_mode")
            insert_values.append(str(contract_payload.mode) if contract_payload is not None else "observe")
        if "contract_passed" in run_columns:
            insert_columns.append("contract_passed")
            insert_values.append(1 if (contract_payload.passed if contract_payload is not None else True) else 0)
        if "contract_violation_count" in run_columns:
            insert_columns.append("contract_violation_count")
            insert_values.append(len(contract_payload.violations) if contract_payload is not None else 0)
        if "contract_violations_json" in run_columns:
            insert_columns.append("contract_violations_json")
            insert_values.append(
                json.dumps(
                    [v.model_dump() for v in contract_payload.violations] if contract_payload is not None else [],
                    ensure_ascii=True,
                )
            )
        if "gate_blocked" in run_columns:
            insert_columns.append("gate_blocked")
            insert_values.append(1 if gate_blocked else 0)
        if "gate_failure_reasons_json" in run_columns:
            insert_columns.append("gate_failure_reasons_json")
            insert_values.append(json.dumps(failure_reasons, ensure_ascii=True))
        insert_columns.append("total_cost_usd")
        insert_values.append(result.total_cost_usd)
        placeholders = ", ".join("?" for _ in insert_columns)
        await self.db.execute(
            f"""
            INSERT INTO manuscript_audit_runs (
                {", ".join(insert_columns)}
            ) VALUES ({placeholders})
            """,
            tuple(insert_values),
        )
        for finding in findings:
            await self.db.execute(
                """
                INSERT INTO manuscript_audit_findings (
                    audit_run_id, workflow_id, finding_id, profile, severity, category, section,
                    evidence, recommendation, owner_module, blocking
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.audit_run_id,
                    result.workflow_id,
                    finding.finding_id,
                    finding.profile,
                    finding.severity,
                    finding.category,
                    finding.section,
                    finding.evidence,
                    finding.recommendation,
                    finding.owner_module,
                    1 if finding.blocking else 0,
                ),
            )
        await self.db.commit()

    async def _table_columns(self, table: str) -> set[str]:
        try:
            async with self.db.execute(f"PRAGMA table_info({table})") as cur:
                rows = await cur.fetchall()
        except Exception:
            return set()
        return {str(row[1]) for row in rows}

    @staticmethod
    def _decode_json_list(raw: object) -> list[object]:
        try:
            value = json.loads(str(raw or "[]"))
        except Exception:
            return []
        return value if isinstance(value, list) else []

    def _manuscript_audit_select_sql(self, include_workflow_id: bool) -> str:
        base_columns = ["audit_run_id"]
        if include_workflow_id:
            base_columns.append("workflow_id")
        base_columns.extend(
            [
                "mode",
                "verdict",
                "passed",
                "selected_profiles_json",
                "summary",
                "total_findings",
                "major_count",
                "minor_count",
                "note_count",
                "blocking_count",
                "total_cost_usd",
                "created_at",
            ]
        )
        return ", ".join(base_columns)

    def _decode_manuscript_audit_row(self, row: tuple[Any, ...], include_workflow_id: bool) -> dict[str, Any]:
        idx = 0
        payload: dict[str, Any] = {"audit_run_id": str(row[idx])}
        idx += 1
        if include_workflow_id:
            payload["workflow_id"] = str(row[idx])
            idx += 1
        payload["mode"] = str(row[idx])
        idx += 1
        payload["verdict"] = str(row[idx])
        idx += 1
        payload["passed"] = bool(row[idx])
        idx += 1
        payload["selected_profiles"] = self._decode_json_list(row[idx])
        idx += 1
        payload["summary"] = str(row[idx] or "")
        idx += 1
        payload["total_findings"] = int(row[idx] or 0)
        idx += 1
        payload["major_count"] = int(row[idx] or 0)
        idx += 1
        payload["minor_count"] = int(row[idx] or 0)
        idx += 1
        payload["note_count"] = int(row[idx] or 0)
        idx += 1
        payload["blocking_count"] = int(row[idx] or 0)
        idx += 1
        payload["total_cost_usd"] = float(row[idx] or 0.0)
        idx += 1
        payload["created_at"] = str(row[idx] or "")
        idx += 1
        if len(row) > idx:
            payload["contract_mode"] = str(row[idx] or "observe")
            idx += 1
            payload["contract_passed"] = bool(row[idx])
            idx += 1
            payload["contract_violation_count"] = int(row[idx] or 0)
            idx += 1
            payload["contract_violations"] = self._decode_json_list(row[idx])
            idx += 1
            payload["gate_blocked"] = bool(row[idx])
            idx += 1
            payload["gate_failure_reasons"] = self._decode_json_list(row[idx])
            idx += 1
        else:
            payload["contract_mode"] = "observe"
            payload["contract_passed"] = True
            payload["contract_violation_count"] = 0
            payload["contract_violations"] = []
            payload["gate_blocked"] = False
            payload["gate_failure_reasons"] = []
        return payload

    async def _manuscript_audit_optional_select_columns(self) -> str:
        cols = await self._table_columns("manuscript_audit_runs")
        wanted = [
            "contract_mode",
            "contract_passed",
            "contract_violation_count",
            "contract_violations_json",
            "gate_blocked",
            "gate_failure_reasons_json",
        ]
        available = [name for name in wanted if name in cols]
        if not available:
            return ""
        return ", " + ", ".join(available)

    async def get_latest_manuscript_audit(self, workflow_id: str) -> dict[str, Any] | None:
        optional_columns = await self._manuscript_audit_optional_select_columns()
        row = await (
            await self.db.execute(
                f"""
                SELECT {self._manuscript_audit_select_sql(include_workflow_id=True)}{optional_columns}
                FROM manuscript_audit_runs
                WHERE workflow_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (workflow_id,),
            )
        ).fetchone()
        if row is None:
            return None
        return self._decode_manuscript_audit_row(row, include_workflow_id=True)

    async def get_manuscript_audit_run(self, workflow_id: str, audit_run_id: str) -> dict[str, Any] | None:
        optional_columns = await self._manuscript_audit_optional_select_columns()
        row = await (
            await self.db.execute(
                f"""
                SELECT {self._manuscript_audit_select_sql(include_workflow_id=True)}{optional_columns}
                FROM manuscript_audit_runs
                WHERE workflow_id = ? AND audit_run_id = ?
                LIMIT 1
                """,
                (workflow_id, audit_run_id),
            )
        ).fetchone()
        if row is None:
            return None
        return self._decode_manuscript_audit_row(row, include_workflow_id=True)

    async def get_manuscript_audit_history(self, workflow_id: str, limit: int = 20) -> list[dict[str, Any]]:
        optional_columns = await self._manuscript_audit_optional_select_columns()
        rows = await (
            await self.db.execute(
                f"""
                SELECT {self._manuscript_audit_select_sql(include_workflow_id=False)}{optional_columns}
                FROM manuscript_audit_runs
                WHERE workflow_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (workflow_id, limit),
            )
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(self._decode_manuscript_audit_row(row, include_workflow_id=False))
        return out

    async def get_manuscript_audit_findings(self, audit_run_id: str) -> list[dict[str, Any]]:
        rows = await (
            await self.db.execute(
                """
                SELECT finding_id, profile, severity, category, section, evidence, recommendation, owner_module, blocking, created_at
                FROM manuscript_audit_findings
                WHERE audit_run_id = ?
                ORDER BY id ASC
                """,
                (audit_run_id,),
            )
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "finding_id": str(row[0]),
                    "profile": str(row[1]),
                    "severity": str(row[2]),
                    "category": str(row[3]),
                    "section": str(row[4]) if row[4] else None,
                    "evidence": str(row[5]),
                    "recommendation": str(row[6]),
                    "owner_module": str(row[7]),
                    "blocking": bool(row[8]),
                    "created_at": str(row[9] or ""),
                }
            )
        return out

    async def get_screening_summary(self, workflow_id: str) -> list[tuple[str, str, str, str]]:
        """Return (paper_id, stage, final_decision, rationale) for screening summary table."""
        cursor = await self.db.execute(
            """
            SELECT dsr.paper_id, dsr.stage, dsr.final_decision,
                   (SELECT sd.reason FROM screening_decisions sd
                    WHERE sd.workflow_id = dsr.workflow_id
                      AND sd.paper_id = dsr.paper_id
                      AND sd.stage = dsr.stage
                      AND sd.decision = dsr.final_decision
                    LIMIT 1) as rationale
            FROM dual_screening_results dsr
            WHERE dsr.workflow_id = ?
            ORDER BY dsr.stage, dsr.paper_id
            """,
            (workflow_id,),
        )
        rows = await cursor.fetchall()
        return [(str(r[0]), str(r[1]), str(r[2]), (r[3] or "")[:80]) for r in rows]

    async def append_decision_log(self, entry: DecisionLogEntry) -> None:
        await self.db.execute(
            """
            INSERT INTO decision_log (workflow_id, decision_type, paper_id, decision, rationale, actor, phase)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.workflow_id,
                entry.decision_type,
                entry.paper_id,
                entry.decision,
                entry.rationale,
                entry.actor,
                entry.phase,
            ),
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
        payload = {"metric": metric_name, "value": metric_value}
        if details:
            payload["details"] = details
        await self.append_decision_log(
            DecisionLogEntry(
                workflow_id=workflow_id,
                decision_type="screening_metric",
                decision=str(metric_value),
                rationale=json.dumps(payload, sort_keys=True),
                actor="workflow_run",
                phase=phase,
            )
        )

    async def save_validation_run(self, record: ValidationRunRecord) -> None:
        """Insert or update a validation run metadata row."""
        await self.db.execute(
            """
            INSERT INTO validation_runs (
                validation_run_id, workflow_id, profile, status, tool_version, summary_json, started_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(validation_run_id) DO UPDATE SET
                status = excluded.status,
                summary_json = excluded.summary_json,
                completed_at = excluded.completed_at
            """,
            (
                record.validation_run_id,
                record.workflow_id,
                record.profile,
                record.status,
                record.tool_version,
                record.summary_json,
                record.started_at.isoformat(),
                record.completed_at.isoformat() if record.completed_at else None,
            ),
        )
        await self.db.commit()

    async def save_validation_check(self, record: ValidationCheckRecord) -> None:
        """Persist a single validation check row."""
        await self.db.execute(
            """
            INSERT INTO validation_checks (
                validation_run_id, workflow_id, phase, check_name, status, severity,
                metric_value, details_json, source_module, paper_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.validation_run_id,
                record.workflow_id,
                record.phase,
                record.check_name,
                record.status,
                record.severity,
                record.metric_value,
                record.details_json,
                record.source_module,
                record.paper_id,
                record.created_at.isoformat(),
            ),
        )
        await self.db.commit()

    async def save_validation_artifact(self, record: ValidationArtifactRecord) -> None:
        """Persist validation artifact metadata/content pointers."""
        await self.db.execute(
            """
            INSERT INTO validation_artifacts (
                validation_run_id, workflow_id, artifact_key, artifact_type,
                content_path, content_text, meta_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.validation_run_id,
                record.workflow_id,
                record.artifact_key,
                record.artifact_type,
                record.content_path,
                record.content_text,
                record.meta_json,
                record.created_at.isoformat(),
            ),
        )
        await self.db.commit()

    async def get_latest_validation_run(self, workflow_id: str) -> ValidationRunRecord | None:
        """Return latest validation run for a workflow, if present."""
        cursor = await self.db.execute(
            """
            SELECT validation_run_id, workflow_id, profile, status, tool_version, summary_json, started_at, completed_at
            FROM validation_runs
            WHERE workflow_id = ?
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (workflow_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        started = datetime.fromisoformat(str(row[6])) if row[6] else datetime.now(UTC)
        completed = datetime.fromisoformat(str(row[7])) if row[7] else None
        return ValidationRunRecord(
            validation_run_id=str(row[0]),
            workflow_id=str(row[1]),
            profile=str(row[2]),
            status=str(row[3]),
            tool_version=str(row[4]),
            summary_json=str(row[5] or "{}"),
            started_at=started,
            completed_at=completed,
        )

    async def get_validation_checks(self, validation_run_id: str) -> list[ValidationCheckRecord]:
        """Return ordered validation checks for a given validation run."""
        cursor = await self.db.execute(
            """
            SELECT validation_run_id, workflow_id, phase, check_name, status, severity,
                   metric_value, details_json, source_module, paper_id, created_at
            FROM validation_checks
            WHERE validation_run_id = ?
            ORDER BY id ASC
            """,
            (validation_run_id,),
        )
        rows = await cursor.fetchall()
        checks: list[ValidationCheckRecord] = []
        for row in rows:
            created_at = datetime.fromisoformat(str(row[10])) if row[10] else datetime.now(UTC)
            checks.append(
                ValidationCheckRecord(
                    validation_run_id=str(row[0]),
                    workflow_id=str(row[1]),
                    phase=str(row[2]),
                    check_name=str(row[3]),
                    status=str(row[4]),
                    severity=str(row[5]),
                    metric_value=float(row[6]) if row[6] is not None else None,
                    details_json=str(row[7] or "{}"),
                    source_module=str(row[8]) if row[8] else None,
                    paper_id=str(row[9]) if row[9] else None,
                    created_at=created_at,
                )
            )
        return checks

    async def save_cost_record(self, record: CostRecord) -> None:
        await self.db.execute(
            """
            INSERT INTO cost_records
                (workflow_id, model, tokens_in, tokens_out, cost_usd, latency_ms, phase,
                 cache_read_tokens, cache_write_tokens)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.workflow_id,
                record.model,
                record.tokens_in,
                record.tokens_out,
                record.cost_usd,
                record.latency_ms,
                record.phase,
                record.cache_read_tokens,
                record.cache_write_tokens,
            ),
        )
        await self.db.commit()

    async def save_rag_retrieval_diagnostic(self, record: RagRetrievalDiagnostic) -> None:
        """Persist per-section RAG retrieval diagnostics for auditability."""
        await self.db.execute(
            """
            INSERT INTO rag_retrieval_diagnostics (
                workflow_id, section, query_type, rerank_enabled, candidate_k, final_k,
                retrieved_count, status, selected_chunks_json, error_message, latency_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.workflow_id,
                record.section,
                record.query_type,
                1 if record.rerank_enabled else 0,
                record.candidate_k,
                record.final_k,
                record.retrieved_count,
                record.status,
                record.selected_chunks_json,
                record.error_message,
                record.latency_ms,
            ),
        )
        await self.db.commit()

    async def get_rag_retrieval_diagnostics(self, workflow_id: str) -> list[dict[str, Any]]:
        """Load per-section RAG diagnostics ordered by creation time."""
        cursor = await self.db.execute(
            """
            SELECT section, query_type, rerank_enabled, candidate_k, final_k,
                   retrieved_count, status, selected_chunks_json, error_message,
                   latency_ms, created_at
            FROM rag_retrieval_diagnostics
            WHERE workflow_id = ?
            ORDER BY created_at ASC
            """,
            (workflow_id,),
        )
        rows = await cursor.fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "section": str(row[0]),
                    "query_type": str(row[1]),
                    "rerank_enabled": bool(row[2]),
                    "candidate_k": int(row[3]),
                    "final_k": int(row[4]),
                    "retrieved_count": int(row[5]),
                    "status": str(row[6]),
                    "selected_chunks_json": str(row[7] or "[]"),
                    "error_message": str(row[8]) if row[8] else None,
                    "latency_ms": int(row[9]) if row[9] is not None else None,
                    "created_at": str(row[10]),
                }
            )
        return out

    async def get_total_cost(self) -> float:
        cursor = await self.db.execute("SELECT COALESCE(SUM(cost_usd), 0.0) FROM cost_records")
        row = await cursor.fetchone()
        return float(row[0]) if row is not None else 0.0

    async def save_extraction_record(self, workflow_id: str, record: ExtractionRecord) -> None:
        await self.db.execute(
            """
            INSERT INTO extraction_records (
                workflow_id, paper_id, study_design, primary_study_status, extraction_source, data
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(workflow_id, paper_id) DO UPDATE SET
                study_design = excluded.study_design,
                primary_study_status = excluded.primary_study_status,
                extraction_source = excluded.extraction_source,
                data = excluded.data
            """,
            (
                workflow_id,
                record.paper_id,
                record.study_design.value,
                record.primary_study_status.value,
                (record.extraction_source or "text"),
                record.model_dump_json(),
            ),
        )
        await self.db.commit()

    async def save_rob2_assessment(self, workflow_id: str, assessment: RoB2Assessment) -> None:
        await self.db.execute(
            """
            INSERT INTO rob_assessments (workflow_id, paper_id, tool_used, assessment_data, overall_judgment)
            VALUES (?, ?, 'rob2', ?, ?)
            ON CONFLICT(workflow_id, paper_id) DO UPDATE SET
                tool_used = 'rob2',
                assessment_data = excluded.assessment_data,
                overall_judgment = excluded.overall_judgment
            """,
            (
                workflow_id,
                assessment.paper_id,
                assessment.model_dump_json(),
                assessment.overall_judgment.value,
            ),
        )
        await self.db.commit()

    async def save_robins_i_assessment(self, workflow_id: str, assessment: RobinsIAssessment) -> None:
        await self.db.execute(
            """
            INSERT INTO rob_assessments (workflow_id, paper_id, tool_used, assessment_data, overall_judgment)
            VALUES (?, ?, 'robins_i', ?, ?)
            ON CONFLICT(workflow_id, paper_id) DO UPDATE SET
                tool_used = 'robins_i',
                assessment_data = excluded.assessment_data,
                overall_judgment = excluded.overall_judgment
            """,
            (
                workflow_id,
                assessment.paper_id,
                assessment.model_dump_json(),
                assessment.overall_judgment.value,
            ),
        )
        await self.db.commit()

    async def load_rob_assessments(self, workflow_id: str) -> tuple[list[RoB2Assessment], list[RobinsIAssessment]]:
        """Load RoB2 and ROBINS-I assessments from rob_assessments table."""
        rob2_list: list[RoB2Assessment] = []
        robins_i_list: list[RobinsIAssessment] = []
        cursor = await self.db.execute(
            """
            SELECT tool_used, assessment_data
            FROM rob_assessments
            WHERE workflow_id = ?
            """,
            (workflow_id,),
        )
        for tool, data in await cursor.fetchall():
            if not data:
                continue
            try:
                parsed = json.loads(data)
                if tool == "rob2":
                    rob2_list.append(RoB2Assessment.model_validate(parsed))
                elif tool == "robins_i":
                    robins_i_list.append(RobinsIAssessment.model_validate(parsed))
            except (json.JSONDecodeError, Exception):
                continue
        return rob2_list, robins_i_list

    async def save_grade_assessment(self, workflow_id: str, assessment: GRADEOutcomeAssessment) -> None:
        from src.quality.grade import _PLACEHOLDER_OUTCOME_NAMES

        normalized_outcome = str(assessment.outcome_name or "").strip()
        if normalized_outcome.lower() in _PLACEHOLDER_OUTCOME_NAMES:
            _logger.warning(
                "Skipping grade_assessment persistence for placeholder outcome_name=%r (workflow_id=%s)",
                normalized_outcome,
                workflow_id,
            )
            return
        if normalized_outcome != assessment.outcome_name:
            assessment = assessment.model_copy(update={"outcome_name": normalized_outcome})
        cursor = await self.db.execute(
            "SELECT id FROM grade_assessments WHERE workflow_id = ? AND outcome_name = ?",
            (workflow_id, assessment.outcome_name),
        )
        existing = await cursor.fetchone()
        if existing:
            await self.db.execute(
                """
                UPDATE grade_assessments
                SET assessment_data = ?, final_certainty = ?
                WHERE id = ?
                """,
                (assessment.model_dump_json(), assessment.final_certainty.value, existing[0]),
            )
        else:
            await self.db.execute(
                """
                INSERT INTO grade_assessments (workflow_id, outcome_name, assessment_data, final_certainty)
                VALUES (?, ?, ?, ?)
                """,
                (
                    workflow_id,
                    assessment.outcome_name,
                    assessment.model_dump_json(),
                    assessment.final_certainty.value,
                ),
            )
        await self.db.commit()

    async def delete_placeholder_grade_assessments(self, workflow_id: str) -> int:
        """Delete placeholder-named GRADE rows for a workflow.

        Reruns on the same workflow_id can retain stale placeholder rows from
        earlier pipeline versions. This method removes them before writing fresh
        quality outputs so grade_assessments remains canonical.
        """
        from src.quality.grade import _PLACEHOLDER_OUTCOME_NAMES

        _placeholders = tuple(_PLACEHOLDER_OUTCOME_NAMES)
        if not _placeholders:
            return 0
        placeholders_q = ",".join("?" for _ in _placeholders)
        cursor = await self.db.execute(
            f"""
            DELETE FROM grade_assessments
            WHERE workflow_id = ?
              AND lower(trim(outcome_name)) IN ({placeholders_q})
            """,
            (workflow_id, *_placeholders),
        )
        await self.db.commit()
        return int(cursor.rowcount or 0)

    async def load_grade_assessments(self, workflow_id: str) -> list[GRADEOutcomeAssessment]:
        """Load all GRADE outcome assessments for a workflow."""
        from src.quality.grade import _PLACEHOLDER_OUTCOME_NAMES

        assessments: list[GRADEOutcomeAssessment] = []
        async with self.db.execute(
            "SELECT assessment_data FROM grade_assessments WHERE workflow_id = ?",
            (workflow_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        for (data,) in rows:
            try:
                parsed = GRADEOutcomeAssessment.model_validate_json(data)
                if str(parsed.outcome_name or "").strip().lower() in _PLACEHOLDER_OUTCOME_NAMES:
                    continue
                assessments.append(parsed)
            except Exception:
                continue
        return assessments

    async def save_casp_assessment(self, workflow_id: str, paper_id: str, assessment: Any) -> None:
        """Persist full structured CASP assessment for a paper (upsert on paper_id)."""
        await self.db.execute(
            """
            INSERT INTO casp_assessments (workflow_id, paper_id, assessment_data, overall_summary)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(workflow_id, paper_id) DO UPDATE SET
                assessment_data = excluded.assessment_data,
                overall_summary = excluded.overall_summary
            """,
            (workflow_id, paper_id, assessment.model_dump_json(), assessment.overall_summary),
        )
        await self.db.commit()

    async def save_mmat_assessment(self, workflow_id: str, paper_id: str, assessment: Any) -> None:
        """Persist full structured MMAT assessment for a paper (upsert on paper_id)."""
        await self.db.execute(
            """
            INSERT INTO mmat_assessments
                (workflow_id, paper_id, assessment_data, overall_summary, study_type, overall_score)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(workflow_id, paper_id) DO UPDATE SET
                assessment_data = excluded.assessment_data,
                overall_summary = excluded.overall_summary,
                study_type = excluded.study_type,
                overall_score = excluded.overall_score
            """,
            (
                workflow_id,
                paper_id,
                assessment.model_dump_json(),
                assessment.overall_summary,
                str(assessment.study_type),
                int(assessment.overall_score),
            ),
        )
        await self.db.commit()

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

    async def load_casp_assessments(self, workflow_id: str) -> list[Any]:
        """Load all CASP assessments for a workflow from casp_assessments table."""
        from src.quality.casp import CaspAssessment

        assessments: list[Any] = []
        cursor = await self.db.execute(
            "SELECT assessment_data FROM casp_assessments WHERE workflow_id = ?",
            (workflow_id,),
        )
        rows = await cursor.fetchall()
        for (data,) in rows:
            if not data:
                continue
            try:
                assessments.append(CaspAssessment.model_validate_json(data))
            except Exception:
                continue
        return assessments

    async def load_mmat_assessments(self, workflow_id: str) -> list[Any]:
        """Load all MMAT assessments for a workflow from mmat_assessments table."""
        from src.quality.mmat import MmatAssessment

        assessments: list[Any] = []
        cursor = await self.db.execute(
            "SELECT assessment_data FROM mmat_assessments WHERE workflow_id = ?",
            (workflow_id,),
        )
        rows = await cursor.fetchall()
        for (data,) in rows:
            if not data:
                continue
            try:
                assessments.append(MmatAssessment.model_validate_json(data))
            except Exception:
                continue
        return assessments

    async def save_checkpoint(
        self,
        workflow_id: str,
        phase: str,
        papers_processed: int = 0,
        status: str = "completed",
    ) -> None:
        _logger.debug(
            "save_checkpoint: workflow_id=%s, phase=%s, papers_processed=%s",
            workflow_id,
            phase,
            papers_processed,
        )
        await self.db.execute(
            """
            INSERT INTO checkpoints (workflow_id, phase, status, papers_processed)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(workflow_id, phase) DO UPDATE SET
                status = CASE
                    WHEN excluded.status = 'completed' THEN 'completed'
                    WHEN checkpoints.status = 'completed' THEN 'completed'
                    ELSE excluded.status
                END,
                papers_processed = CASE
                    WHEN excluded.status = 'completed' THEN excluded.papers_processed
                    ELSE MAX(checkpoints.papers_processed, excluded.papers_processed)
                END
            """,
            (workflow_id, phase, status, papers_processed),
        )
        await self.db.commit()

    async def delete_checkpoints_for_phases(self, workflow_id: str, phases: list[str]) -> None:
        """Delete checkpoints for the given phases. Used when resuming from a specific phase."""
        if not phases:
            return
        placeholders = ",".join("?" * len(phases))
        await self.db.execute(
            f"""
            DELETE FROM checkpoints
            WHERE workflow_id = ? AND phase IN ({placeholders})
            """,
            (workflow_id, *phases),
        )
        await self.db.commit()

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
            "phase_6_writing",
            "phase_7_audit",
            "finalize",
        ]
        if from_phase not in phase_order:
            return

        start_idx = phase_order.index(from_phase)

        async def _delete(table: str, has_workflow_id: bool = True) -> None:
            if has_workflow_id:
                await self.db.execute(f"DELETE FROM {table} WHERE workflow_id = ?", (workflow_id,))
            else:
                await self.db.execute(f"DELETE FROM {table}")

        # Writing/finalize artifacts and citation ledger
        if start_idx <= phase_order.index("phase_6_writing"):
            for table in (
                "manuscript_assemblies",
                "manuscript_assets",
                "manuscript_blocks",
                "manuscript_sections",
                "section_drafts",
            ):
                await _delete(table)
            # citations/claims/evidence_links are run-local in runtime.db
            for table in ("evidence_links", "claims", "citations"):
                await _delete(table, has_workflow_id=False)

        # Manuscript audit stage
        if start_idx <= phase_order.index("phase_7_audit"):
            for table in ("manuscript_audit_findings", "manuscript_audit_runs"):
                await _delete(table)

        # Knowledge graph stage
        if start_idx <= phase_order.index("phase_5b_knowledge_graph"):
            for table in ("paper_relationships", "graph_communities", "research_gaps"):
                await _delete(table)

        # Synthesis stage
        if start_idx <= phase_order.index("phase_5_synthesis"):
            await _delete("synthesis_results")

        # Embedding stage
        if start_idx <= phase_order.index("phase_4b_embedding"):
            await _delete("paper_chunks_meta")
            await _delete("rag_retrieval_diagnostics")

        # Extraction + quality stages
        if start_idx <= phase_order.index("phase_4_extraction_quality"):
            for table in (
                "extraction_records",
                "rob_assessments",
                "casp_assessments",
                "mmat_assessments",
                "grade_assessments",
            ):
                await _delete(table)

        # Screening stage
        if start_idx <= phase_order.index("phase_3_screening"):
            for table in ("dual_screening_results", "screening_decisions", "study_cohort_membership"):
                await _delete(table)

        # Search stage
        if start_idx <= phase_order.index("phase_2_search"):
            await _delete("search_results")
            # papers is run-local in runtime.db
            await _delete("papers", has_workflow_id=False)

        await self.db.commit()

    async def has_checkpoint_integrity(self, workflow_id: str) -> bool:
        cursor = await self.db.execute(
            "SELECT COUNT(*) FROM workflows WHERE workflow_id = ?",
            (workflow_id,),
        )
        workflow_row = await cursor.fetchone()
        if workflow_row is None or int(workflow_row[0]) == 0:
            return False
        return True

    async def save_synthesis_result(
        self,
        workflow_id: str,
        feasibility: SynthesisFeasibility,
        narrative: NarrativeSynthesis,
    ) -> None:
        """Persist synthesis results to DB as the canonical typed source of truth."""
        await self.db.execute(
            """
            INSERT INTO synthesis_results (
                workflow_id, outcome_name, feasibility_data, narrative_data
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(workflow_id, outcome_name) DO UPDATE SET
                feasibility_data = excluded.feasibility_data,
                narrative_data = excluded.narrative_data
            """,
            (
                workflow_id,
                narrative.outcome_name,
                json.dumps(feasibility.model_dump()),
                json.dumps(narrative.model_dump()),
            ),
        )
        await self.db.commit()

    async def load_synthesis_result(self, workflow_id: str) -> tuple[SynthesisFeasibility, NarrativeSynthesis] | None:
        """Load the most recent synthesis result for a workflow.

        Returns a typed (SynthesisFeasibility, NarrativeSynthesis) pair, or None
        if no result has been saved (e.g. older DB without synthesis_results table).
        """
        try:
            cursor = await self.db.execute(
                """
                SELECT feasibility_data, narrative_data
                FROM synthesis_results
                WHERE workflow_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (workflow_id,),
            )
            row = await cursor.fetchone()
        except Exception:
            return None
        if row is None:
            return None
        try:
            feasibility = SynthesisFeasibility.model_validate(json.loads(str(row[0])))
            narrative = NarrativeSynthesis.model_validate(json.loads(str(row[1])))
            return feasibility, narrative
        except Exception:
            return None

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

    async def get_last_event_of_type(self, workflow_id: str, event_type: str) -> dict | None:
        """Return the JSON payload of the most recent event_log row of a given type.

        Returns None if no such event exists for this workflow. Used to source
        structured counts (e.g. batch_screen_done.excluded) that are not
        reflected in row-count queries across dual_screening_results.
        """
        import json as _json

        cursor = await self.db.execute(
            """
            SELECT payload FROM event_log
            WHERE workflow_id = ? AND event_type = ?
            ORDER BY ts DESC
            LIMIT 1
            """,
            (workflow_id, event_type),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        try:
            return _json.loads(row[0]) if isinstance(row[0], str) else row[0]
        except Exception:
            return None

    async def create_workflow(self, workflow_id: str, topic: str, config_hash: str) -> None:
        await self.db.execute(
            """
            INSERT INTO workflows (workflow_id, topic, config_hash, status)
            VALUES (?, ?, ?, 'running')
            ON CONFLICT(workflow_id) DO UPDATE SET
                topic = excluded.topic,
                config_hash = excluded.config_hash,
                status = 'running',
                updated_at = CURRENT_TIMESTAMP
            """,
            (workflow_id, topic, config_hash),
        )
        await self.db.commit()

    async def update_workflow_status(self, workflow_id: str, status: str) -> None:
        """Update the status column in the local runtime.db workflows table."""
        await self.db.execute(
            "UPDATE workflows SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE workflow_id = ?",
            (status, workflow_id),
        )
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
                # Column already exists (or table does not exist yet -- schema.sql creates it).
                pass

        # Retroactively fix source_type for known methodology references that were
        # registered before the source_type column was added.  Without this UPDATE,
        # the ALTER TABLE default sets them all to 'included', causing them to be
        # treated as required included-study citations in coverage checks.
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
            # Background SR keys follow the pattern citekey LIKE '%SR' (e.g. Jones2021SR).
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
        # Guard: if a non-empty DOI already exists in the table (under any citekey),
        # skip registration.  This prevents the same paper from appearing twice in
        # the reference list when it is registered first as an included-study
        # citekey and later as a background-SR citekey (or vice-versa).
        # The unique partial index on doi (WHERE doi IS NOT NULL AND doi != '')
        # enforces this at the DB level for new databases; this pre-check handles
        # existing databases that pre-date the index.
        if citation.doi:
            _doi_cur = await self.db.execute("SELECT 1 FROM citations WHERE doi = ? LIMIT 1", (citation.doi,))
            if await _doi_cur.fetchone():
                return

        await self.db.execute(
            """
            INSERT INTO citations (citation_id, citekey, doi, url, title, authors, year, journal, bibtex, resolved, source_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(citation_id) DO UPDATE SET
                citekey=excluded.citekey,
                doi=excluded.doi,
                url=excluded.url,
                title=excluded.title,
                authors=excluded.authors,
                year=excluded.year,
                journal=excluded.journal,
                bibtex=excluded.bibtex,
                resolved=excluded.resolved,
                source_type=excluded.source_type
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

    async def get_unlinked_claim_ids(self) -> list[str]:
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
            # Only keep fallback behavior for the expected legacy schema gap.
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

            # Fetch all papers from parent using only columns guaranteed by the base schema.
            try:
                async with src_db.execute(
                    "SELECT paper_id, title, abstract, authors, year, doi, url, source_database, "
                    "       display_label, openalex_id FROM papers"
                ) as cur:
                    parent_papers = await cur.fetchall()
            except Exception:
                _logger.warning("merge_papers_from_parent: could not read papers from %s", parent_db_path)
                return 0

            # Fetch final screening decisions from dual_screening_results.
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
                    "merged_from_parent",  # mark as carrying over from a parent run
                    "database",  # source_category (required; merged papers are database-sourced)
                    row["display_label"],
                    row["openalex_id"],
                ),
            )
            merged += 1

            # Carry over the screening outcome so this paper is not re-screened.
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
