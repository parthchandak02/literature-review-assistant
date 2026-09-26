"""CLI resume prompt reports progress against the full PHASE_ORDER."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.orchestration import workflow as workflow_mod
from src.orchestration.phase_catalog import PHASE_ORDER


@pytest.mark.asyncio
async def test_resume_prompt_counts_completed_phases_against_phase_order(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-prompt", "topic", "hash")
        for phase in PHASE_ORDER[:3]:
            await repo.save_checkpoint("wf-prompt", phase)
        await repo.save_checkpoint("wf-prompt", PHASE_ORDER[3], status="partial")
        await repo.save_checkpoint("wf-prompt", "phase_3b_fulltext")
        await db.commit()

    entry = SimpleNamespace(workflow_id="wf-prompt", status="running", db_path=str(db_path))
    prompts: list[str] = []

    def _fake_input(prompt: str) -> str:
        prompts.append(prompt)
        return "n"

    review = SimpleNamespace(research_question="topic")
    with (
        patch.object(workflow_mod, "load_configs", return_value=(review, None)),
        patch.object(workflow_mod, "_hash_config", return_value="hash"),
        patch.object(workflow_mod, "find_by_topic", new=AsyncMock(return_value=[entry])),
        patch.object(workflow_mod, "run_graph_with_budget", new=AsyncMock(return_value="fresh")),
        patch("builtins.input", side_effect=_fake_input),
    ):
        result = await workflow_mod.run_workflow(review_path="unused.yaml", run_context=None)

    assert result == "fresh"
    assert prompts == [f"Found existing run for this topic (3/{len(PHASE_ORDER)} phases complete). Resume? [Y/n]: "]
