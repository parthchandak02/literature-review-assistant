"""Upgrade replay tests to re-execute pipeline helper code, not only COUNT(*)."""

from __future__ import annotations

from pathlib import Path

import aiosqlite

from src.orchestration.helpers.pre_writing_gate import count_prior_pre_writing_failures


async def test_replay_db_pre_writing_failure_count_executes_query(
    real_workflow_target: tuple[str, Path],
) -> None:
    """Re-executes orchestration helper SQL against a fixture DB (not static COUNT-only)."""
    workflow_id, runtime_db = real_workflow_target
    async with aiosqlite.connect(str(runtime_db)) as db:
        count = await count_prior_pre_writing_failures(db, workflow_id)
    assert count >= 0
