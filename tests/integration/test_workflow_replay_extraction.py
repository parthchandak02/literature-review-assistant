from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest


async def test_real_workflow_extraction_and_quality_coverage(real_workflow_target: tuple[str, Path]) -> None:
    workflow_id, runtime_db = real_workflow_target
    async with aiosqlite.connect(str(runtime_db)) as db:
        included_row = await (
            await db.execute(
                """
                SELECT COUNT(*)
                FROM study_cohort_membership
                WHERE workflow_id = ? AND synthesis_eligibility = 'included_primary'
                """,
                (workflow_id,),
            )
        ).fetchone()
        included_primary = int(included_row[0]) if included_row else 0
        if included_primary == 0:
            pytest.skip("Workflow has no included_primary records for extraction replay checks.")

        extracted_row = await (
            await db.execute(
                """
                SELECT COUNT(*)
                FROM extraction_records
                WHERE workflow_id = ?
                """,
                (workflow_id,),
            )
        ).fetchone()
        extracted_count = int(extracted_row[0]) if extracted_row else 0
        assert extracted_count > 0

        quality_row = await (
            await db.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM rob_assessments WHERE workflow_id = ?) +
                    (SELECT COUNT(*) FROM casp_assessments WHERE workflow_id = ?) +
                    (SELECT COUNT(*) FROM mmat_assessments WHERE workflow_id = ?)
                """,
                (workflow_id, workflow_id, workflow_id),
            )
        ).fetchone()
        quality_count = int(quality_row[0]) if quality_row else 0
        assert quality_count > 0
