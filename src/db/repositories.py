"""Typed repositories for core persistence operations."""

from __future__ import annotations

import json
from typing import List, Optional, Set, Tuple

import aiosqlite

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
                keywords, source_category, openalex_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

    async def save_checkpoint(self, workflow_id: str, phase: str, papers_processed: int = 0) -> None:
        await self.db.execute(
            """
            INSERT INTO checkpoints (workflow_id, phase, status, papers_processed)
            VALUES (?, ?, 'completed', ?)
            ON CONFLICT(workflow_id, phase) DO UPDATE SET
                status=excluded.status,
                papers_processed=excluded.papers_processed
            """,
            (workflow_id, phase, papers_processed),
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
