"""Unit tests for WorkflowStateRepo checkpoint and running-step helpers.

These methods power resume rewind and the resume_integrity gate, but were only
exercised indirectly (or not at all) before this file.
"""

from __future__ import annotations

import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.models.enums import StepStatus
from src.models.workflow import WorkflowStepRecord


@pytest.fixture
async def repo(tmp_path):
    db_path = str(tmp_path / "workflow_state_checkpoints.db")
    async with get_db(db_path) as db:
        repository = WorkflowRepository(db)
        await repository.create_workflow("wf-ckpt", "checkpoint topic", "hash-ckpt")
        yield repository


@pytest.mark.asyncio
async def test_get_checkpoints_returns_phase_status_map(repo: WorkflowRepository) -> None:
    await repo.save_checkpoint("wf-ckpt", "phase_2_search", papers_processed=10)
    await repo.save_checkpoint("wf-ckpt", "phase_3_screening", papers_processed=5, status="partial")

    checkpoints = await repo.get_checkpoints("wf-ckpt")

    assert checkpoints == {
        "phase_2_search": "completed",
        "phase_3_screening": "partial",
    }
    assert await repo.get_checkpoints("wf-missing") == {}


@pytest.mark.asyncio
async def test_delete_checkpoints_for_phases_removes_only_named_phases(
    repo: WorkflowRepository,
) -> None:
    await repo.save_checkpoint("wf-ckpt", "phase_2_search")
    await repo.save_checkpoint("wf-ckpt", "phase_3_screening")
    await repo.save_checkpoint("wf-ckpt", "phase_4_extraction_quality")

    await repo.delete_checkpoints_for_phases(
        "wf-ckpt",
        ["phase_3_screening", "phase_4_extraction_quality"],
    )

    assert await repo.get_checkpoints("wf-ckpt") == {"phase_2_search": "completed"}


@pytest.mark.asyncio
async def test_delete_checkpoints_for_phases_empty_list_is_noop(
    repo: WorkflowRepository,
) -> None:
    await repo.save_checkpoint("wf-ckpt", "phase_2_search")

    await repo.delete_checkpoints_for_phases("wf-ckpt", [])

    assert await repo.get_checkpoints("wf-ckpt") == {"phase_2_search": "completed"}


@pytest.mark.asyncio
async def test_has_checkpoint_integrity_requires_workflow_row(
    repo: WorkflowRepository,
) -> None:
    assert await repo.has_checkpoint_integrity("wf-ckpt") is True
    assert await repo.has_checkpoint_integrity("wf-absent") is False


@pytest.mark.asyncio
async def test_save_checkpoint_completed_status_is_sticky(repo: WorkflowRepository) -> None:
    await repo.save_checkpoint("wf-ckpt", "phase_6_writing", papers_processed=4, status="completed")
    await repo.save_checkpoint("wf-ckpt", "phase_6_writing", papers_processed=1, status="partial")

    cursor = await repo.db.execute(
        "SELECT status, papers_processed FROM checkpoints WHERE workflow_id = ? AND phase = ?",
        ("wf-ckpt", "phase_6_writing"),
    )
    row = await cursor.fetchone()
    assert row is not None
    assert str(row[0]) == "completed"
    assert int(row[1]) == 4


@pytest.mark.asyncio
async def test_update_workflow_status_persists(repo: WorkflowRepository) -> None:
    await repo.update_workflow_status("wf-ckpt", "interrupted")

    cursor = await repo.db.execute(
        "SELECT status FROM workflows WHERE workflow_id = ?",
        ("wf-ckpt",),
    )
    row = await cursor.fetchone()
    assert row is not None
    assert str(row[0]) == "interrupted"


@pytest.mark.asyncio
async def test_count_running_steps_filters_by_phase(repo: WorkflowRepository) -> None:
    await repo.save_workflow_step(
        WorkflowStepRecord(
            step_id="step-search-running",
            workflow_id="wf-ckpt",
            phase="phase_2_search",
            step_name="search_phase",
            status=StepStatus.RUNNING,
        )
    )
    await repo.save_workflow_step(
        WorkflowStepRecord(
            step_id="step-screen-running",
            workflow_id="wf-ckpt",
            phase="phase_3_screening",
            step_name="screening_phase",
            status=StepStatus.RUNNING,
        )
    )
    await repo.save_workflow_step(
        WorkflowStepRecord(
            step_id="step-screen-done",
            workflow_id="wf-ckpt",
            phase="phase_3_screening",
            step_name="screening_phase",
            status=StepStatus.SUCCEEDED,
        )
    )

    assert await repo.count_running_steps("wf-ckpt") == 2
    assert await repo.count_running_steps("wf-ckpt", "phase_3_screening") == 1
    assert await repo.count_running_steps("wf-ckpt", "phase_4_extraction_quality") == 0
    assert await repo.count_running_steps("wf-other") == 0
