"""Screening decisions and cohort membership repository."""

from __future__ import annotations

import logging

import aiosqlite

from src.models import (
    CohortMembershipRecord,
    ScreeningDecision,
    ScreeningDecisionType,
)

_logger = logging.getLogger(__name__)


class ScreeningRepo:
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

        reason_cursor = await self.db.execute(
            """
            WITH ranked_reasons AS (
                SELECT
                    paper_id,
                    COALESCE(NULLIF(TRIM(exclusion_reason), ''), 'other') AS exclusion_reason,
                    CASE reviewer_type
                        WHEN 'human_override' THEN 0
                        WHEN 'adjudicator' THEN 1
                        WHEN 'reviewer_a' THEN 2
                        WHEN 'reviewer_b' THEN 3
                        ELSE 4
                    END AS reviewer_priority,
                    created_at,
                    id
                FROM screening_decisions
                WHERE workflow_id = ? AND stage = 'fulltext' AND decision = 'exclude'
            ),
            primary_reasons AS (
                SELECT paper_id, exclusion_reason
                FROM (
                    SELECT
                        paper_id,
                        exclusion_reason,
                        ROW_NUMBER() OVER (
                            PARTITION BY paper_id
                            ORDER BY reviewer_priority ASC, datetime(created_at) DESC, id DESC
                        ) AS rn
                    FROM ranked_reasons
                )
                WHERE rn = 1
            )
            SELECT exclusion_reason, COUNT(*)
            FROM primary_reasons
            GROUP BY exclusion_reason
            """,
            (workflow_id,),
        )
        for reason, cnt in await reason_cursor.fetchall():
            key = str(reason).strip().lower().replace(" ", "_") if reason else "other"
            exclusion_reasons[key] = exclusion_reasons.get(key, 0) + int(cnt)

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
            reports_not_retrieved = exclusion_reasons.pop("no_full_text", 0)
            ft_assessed = max(0, ft_assessed - reports_not_retrieved)
            ft_excluded = max(0, ft_excluded - reports_not_retrieved)
        exclusion_reasons.pop("no_full_text", None)
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
