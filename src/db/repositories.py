"""Typed repositories for core persistence operations."""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

import aiosqlite
from pydantic import ValidationError

from src.models import (
    CandidatePaper,
    CitationEntryRecord,
    ClaimRecord,
    CostRecord,
    DecisionLogEntry,
    EvidenceLinkRecord,
    ExtractionRecord,
    GateResult,
    GRADEOutcomeAssessment,
    RoB2Assessment,
    RobinsIAssessment,
    ScreeningDecision,
    ScreeningDecisionType,
    SearchResult,
    SectionDraft,
)
from src.models.enums import SourceCategory
from src.models.papers import compute_display_label
from src.synthesis.feasibility import SynthesisFeasibility
from src.synthesis.narrative import NarrativeSynthesis

_logger = logging.getLogger(__name__)


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
            INSERT OR IGNORE INTO screening_decisions (
                workflow_id, paper_id, stage, decision, reason, exclusion_reason,
                reviewer_type, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
            WHERE workflow_id = ? AND decision_type = 'search_connector_error'
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

        # When full-text exclusions exist, query their reasons from screening_decisions.
        # The dual_screening_results table records counts but not per-paper exclusion reasons;
        # the screening_decisions table has the exclusion_reason column populated by the LLM.
        if ft_excluded > 0:
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

        # Separate "not retrieved" from "assessed but excluded".
        # no_full_text papers were never read -- they belong in the PRISMA
        # "Reports not retrieved" box, not in "Reports excluded with reasons".
        reports_not_retrieved = exclusion_reasons.pop("no_full_text", 0)
        # Adjust ft_assessed and ft_excluded to exclude the not-retrieved papers
        # so that: reports_sought == reports_not_retrieved + reports_assessed
        ft_assessed = max(0, ft_assessed - reports_not_retrieved)
        ft_excluded = max(0, ft_excluded - reports_not_retrieved)

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
        """Paper IDs that passed fulltext screening with include or uncertain decision."""
        cursor = await self.db.execute(
            """
            SELECT paper_id FROM dual_screening_results
            WHERE workflow_id = ? AND stage = 'fulltext' AND final_decision IN ('include', 'uncertain')
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
            INSERT INTO decision_log (decision_type, paper_id, decision, rationale, actor, phase)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                entry.decision_type,
                entry.paper_id,
                entry.decision,
                entry.rationale,
                entry.actor,
                entry.phase,
            ),
        )
        await self.db.commit()

    async def save_cost_record(self, record: CostRecord) -> None:
        await self.db.execute(
            """
            INSERT INTO cost_records
                (model, tokens_in, tokens_out, cost_usd, latency_ms, phase,
                 cache_read_tokens, cache_write_tokens)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
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

    async def get_total_cost(self) -> float:
        cursor = await self.db.execute("SELECT COALESCE(SUM(cost_usd), 0.0) FROM cost_records")
        row = await cursor.fetchone()
        return float(row[0]) if row is not None else 0.0

    async def save_extraction_record(self, workflow_id: str, record: ExtractionRecord) -> None:
        await self.db.execute(
            """
            INSERT INTO extraction_records (workflow_id, paper_id, study_design, data)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(workflow_id, paper_id) DO UPDATE SET
                study_design = excluded.study_design,
                data = excluded.data
            """,
            (
                workflow_id,
                record.paper_id,
                record.study_design.value,
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

    async def load_grade_assessments(self, workflow_id: str) -> list[GRADEOutcomeAssessment]:
        """Load all GRADE outcome assessments for a workflow."""
        assessments: list[GRADEOutcomeAssessment] = []
        async with self.db.execute(
            "SELECT assessment_data FROM grade_assessments WHERE workflow_id = ?",
            (workflow_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        for (data,) in rows:
            try:
                assessments.append(GRADEOutcomeAssessment.model_validate_json(data))
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
                status=excluded.status,
                papers_processed=excluded.papers_processed
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
        try:
            await self.db.execute("ALTER TABLE citations ADD COLUMN url TEXT")
            await self.db.commit()
        except Exception:
            # Column already exists (or table does not exist yet -- schema.sql will create it).
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
            INSERT INTO citations (citation_id, citekey, doi, url, title, authors, year, journal, bibtex, resolved)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(citation_id) DO UPDATE SET
                citekey=excluded.citekey,
                doi=excluded.doi,
                url=excluded.url,
                title=excluded.title,
                authors=excluded.authors,
                year=excluded.year,
                journal=excluded.journal,
                bibtex=excluded.bibtex,
                resolved=excluded.resolved
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
