from __future__ import annotations

from pathlib import Path

import aiosqlite


async def test_real_workflow_screening_replay_surface(real_workflow_target: tuple[str, Path]) -> None:
    workflow_id, runtime_db = real_workflow_target
    async with aiosqlite.connect(str(runtime_db)) as db:
        dual_rows = await (
            await db.execute(
                """
                SELECT COUNT(*)
                FROM dual_screening_results
                WHERE workflow_id = ? AND stage = 'title_abstract'
                """,
                (workflow_id,),
            )
        ).fetchone()
        assert dual_rows is not None
        assert int(dual_rows[0]) > 0

        decision_rows = await (
            await db.execute(
                """
                SELECT COUNT(*)
                FROM screening_decisions
                WHERE workflow_id = ? AND stage = 'title_abstract'
                """,
                (workflow_id,),
            )
        ).fetchone()
        assert decision_rows is not None
        assert int(decision_rows[0]) >= int(dual_rows[0])
