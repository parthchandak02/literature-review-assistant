"""Typed repositories for core persistence operations."""

from __future__ import annotations

import json
from typing import Any, List, Optional, Set, Tuple

import aiosqlite


def _row_to_candidate_paper(row: Tuple[Any, ...]) -> CandidatePaper:
    """Convert a papers table row to CandidatePaper."""
    authors_raw = row[2]
    authors = json.loads(authors_raw) if isinstance(authors_raw, str) else (authors_raw or [])
    keywords_raw = row[8]
    keywords = json.loads(keywords_raw) if isinstance(keywords_raw, str) else (keywords_raw or [])
    try:
        source_cat = SourceCategory(str(row[9]))
    except ValueError:
        source_cat = SourceCategory.DATABASE
    country = str(row[11]) if len(row) > 11 and row[11] else None
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
    )

from src.models import (
    CandidatePaper,
    CitationEntryRecord,
    ClaimRecord,
    CostRecord,
    DecisionLogEntry,
    EvidenceLinkRecord,
    ExtractionRecord,
    GRADEOutcomeAssessment,
    GateResult,
    RobinsIAssessment,
    RoB2Assessment,
    SearchResult,
    ScreeningDecision,
    ScreeningDecisionType,
    SectionDraft,
)
from src.models.enums import SourceCategory


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
        await self.db.execute(
            """
            INSERT OR REPLACE INTO papers (
                paper_id, title, authors, year, source_database, doi, abstract, url,
                keywords, source_category, openalex_id, country
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
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
            ),
        )

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

    async def get_search_counts_by_category(
        self, workflow_id: str
    ) -> tuple[dict[str, int], dict[str, int]]:
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

    async def get_prisma_screening_counts(
        self, workflow_id: str
    ) -> tuple[int, int, int, int, int, dict[str, int]]:
        """Return (records_screened, records_excluded_screening, reports_sought,
        reports_not_retrieved, reports_assessed, reports_excluded_with_reasons)."""
        ta_screened = 0
        ta_excluded = 0
        ft_sought = 0
        ft_assessed = 0
        ft_excluded = 0
        exclusion_reasons: dict[str, int] = {}

        cursor = await self.db.execute(
            """
            SELECT stage, final_decision, COUNT(*)
            FROM dual_screening_results
            WHERE workflow_id = ?
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

        cursor = await self.db.execute(
            """
            SELECT exclusion_reason, COUNT(DISTINCT paper_id)
            FROM screening_decisions
            WHERE workflow_id = ? AND stage = 'fulltext' AND decision = 'exclude'
                AND exclusion_reason IS NOT NULL
            GROUP BY exclusion_reason
            """,
            (workflow_id,),
        )
        for reason, cnt in await cursor.fetchall():
            exclusion_reasons[str(reason or "other")] = int(cnt)
        if ft_excluded > sum(exclusion_reasons.values()):
            exclusion_reasons["other"] = (
                exclusion_reasons.get("other", 0) + ft_excluded - sum(exclusion_reasons.values())
            )

        reports_not_retrieved = max(0, ft_sought - ft_assessed)
        return ta_screened, ta_excluded, ft_sought, reports_not_retrieved, ft_assessed, exclusion_reasons

    async def get_processed_paper_ids(self, workflow_id: str, stage: str) -> Set[str]:
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

    async def get_all_papers(self) -> List[CandidatePaper]:
        """Load all papers from the papers table (for resume state reconstruction)."""
        cursor = await self.db.execute(
            """
            SELECT paper_id, title, authors, year, source_database, doi, abstract, url,
                   keywords, source_category, openalex_id, country
            FROM papers
            """
        )
        rows = await cursor.fetchall()
        return [_row_to_candidate_paper(row) for row in rows]

    async def load_papers_by_ids(self, paper_ids: Set[str]) -> List[CandidatePaper]:
        """Load papers by paper_id set."""
        if not paper_ids:
            return []
        placeholders = ",".join("?" * len(paper_ids))
        cursor = await self.db.execute(
            f"""
            SELECT paper_id, title, authors, year, source_database, doi, abstract, url,
                   keywords, source_category, openalex_id, country
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

    async def get_included_paper_ids(self, workflow_id: str) -> Set[str]:
        """Paper IDs that passed fulltext screening with include decision."""
        cursor = await self.db.execute(
            """
            SELECT paper_id FROM dual_screening_results
            WHERE workflow_id = ? AND stage = 'fulltext' AND final_decision = 'include'
            """,
            (workflow_id,),
        )
        rows = await cursor.fetchall()
        return {str(row[0]) for row in rows}

    async def get_extraction_record_ids(self, workflow_id: str) -> Set[str]:
        """Paper IDs already in extraction_records."""
        cursor = await self.db.execute(
            """
            SELECT paper_id FROM extraction_records WHERE workflow_id = ?
            """,
            (workflow_id,),
        )
        rows = await cursor.fetchall()
        return {str(row[0]) for row in rows}

    async def load_extraction_records(self, workflow_id: str) -> List[ExtractionRecord]:
        """Load all extraction records for a workflow."""
        cursor = await self.db.execute(
            """
            SELECT data FROM extraction_records WHERE workflow_id = ?
            """,
            (workflow_id,),
        )
        rows = await cursor.fetchall()
        records: List[ExtractionRecord] = []
        for row in rows:
            data_json = str(row[0])
            records.append(ExtractionRecord.model_validate_json(data_json))
        return records

    async def get_completed_sections(self, workflow_id: str) -> Set[str]:
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

    async def get_screening_summary(
        self, workflow_id: str
    ) -> List[Tuple[str, str, str, str]]:
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
        return [
            (str(r[0]), str(r[1]), str(r[2]), (r[3] or "")[:80])
            for r in rows
        ]

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
            INSERT INTO cost_records (model, tokens_in, tokens_out, cost_usd, latency_ms, phase)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                record.model,
                record.tokens_in,
                record.tokens_out,
                record.cost_usd,
                record.latency_ms,
                record.phase,
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
            INSERT OR REPLACE INTO extraction_records (workflow_id, paper_id, study_design, data)
            VALUES (?, ?, ?, ?)
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
            INSERT OR REPLACE INTO rob_assessments (workflow_id, paper_id, tool_used, assessment_data, overall_judgment)
            VALUES (?, ?, 'rob2', ?, ?)
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
            INSERT OR REPLACE INTO rob_assessments (workflow_id, paper_id, tool_used, assessment_data, overall_judgment)
            VALUES (?, ?, 'robins_i', ?, ?)
            """,
            (
                workflow_id,
                assessment.paper_id,
                assessment.model_dump_json(),
                assessment.overall_judgment.value,
            ),
        )
        await self.db.commit()

    async def load_rob_assessments(
        self, workflow_id: str
    ) -> tuple[list[RoB2Assessment], list[RobinsIAssessment]]:
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

    async def save_checkpoint(
        self,
        workflow_id: str,
        phase: str,
        papers_processed: int = 0,
        status: str = "completed",
    ) -> None:
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

    async def has_checkpoint_integrity(self, workflow_id: str) -> bool:
        cursor = await self.db.execute(
            "SELECT COUNT(*) FROM workflows WHERE workflow_id = ?",
            (workflow_id,),
        )
        workflow_row = await cursor.fetchone()
        if workflow_row is None or int(workflow_row[0]) == 0:
            return False
        return True

    async def create_workflow(self, workflow_id: str, topic: str, config_hash: str) -> None:
        await self.db.execute(
            """
            INSERT OR REPLACE INTO workflows (workflow_id, topic, config_hash, status)
            VALUES (?, ?, ?, 'running')
            """,
            (workflow_id, topic, config_hash),
        )
        await self.db.commit()


class CitationRepository:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

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
        await self.db.execute(
            """
            INSERT INTO citations (citation_id, citekey, doi, title, authors, year, journal, bibtex, resolved)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(citation_id) DO UPDATE SET
                citekey=excluded.citekey,
                doi=excluded.doi,
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

    async def get_unlinked_claim_ids(self) -> List[str]:
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

    async def get_unresolved_citation_ids(self) -> List[str]:
        cursor = await self.db.execute("SELECT citation_id FROM citations WHERE resolved = 0")
        rows = await cursor.fetchall()
        return [str(row[0]) for row in rows]

    async def get_citekeys(self) -> List[str]:
        cursor = await self.db.execute("SELECT citekey FROM citations")
        rows = await cursor.fetchall()
        return [str(row[0]) for row in rows]

    async def get_claim_citation_pairs(self) -> List[Tuple[str, str]]:
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

    async def get_all_citations_for_export(self) -> List[Tuple[str, str, str | None, str, str, int | None, str | None, str | None]]:
        """Return (citation_id, citekey, doi, title, authors_json, year, journal, bibtex) for BibTeX export."""
        cursor = await self.db.execute(
            """
            SELECT citation_id, citekey, doi, title, authors, year, journal, bibtex
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
            )
            for row in rows
        ]
