"""Risk of bias, GRADE, CASP, and MMAT quality assessment repository."""

from __future__ import annotations

import json
import logging

import aiosqlite

from src.models import (
    CaspAssessment,
    GRADEOutcomeAssessment,
    MmatAssessment,
    RoB2Assessment,
    RobinsIAssessment,
)

_logger = logging.getLogger(__name__)


class QualityRepo:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

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

    async def save_casp_assessment(self, workflow_id: str, paper_id: str, assessment: CaspAssessment) -> None:
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

    async def save_mmat_assessment(self, workflow_id: str, paper_id: str, assessment: MmatAssessment) -> None:
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

    async def load_casp_assessments(self, workflow_id: str) -> list[CaspAssessment]:
        """Load all CASP assessments for a workflow from casp_assessments table."""
        assessments: list[CaspAssessment] = []
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

    async def load_mmat_assessments(self, workflow_id: str) -> list[MmatAssessment]:
        """Load all MMAT assessments for a workflow from mmat_assessments table."""
        assessments: list[MmatAssessment] = []
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
