"""Tests for step journal persist-failure logging."""

from __future__ import annotations

import logging

import pytest

from src.models.enums import StepStatus
from src.models.workflow import WorkflowStepRecord
from src.orchestration.helpers import step_journal


class _FailingRepo:
    async def reconcile_stale_running_steps(self, *args, **kwargs) -> int:
        return 0

    async def save_workflow_step(self, record: WorkflowStepRecord) -> None:
        raise RuntimeError("db unavailable")


@pytest.mark.asyncio
async def test_journal_step_start_logs_warning_on_persist_failure(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.WARNING, logger=step_journal.__name__)
    repo = _FailingRepo()

    record = await step_journal.journal_step_start(
        repo,
        "wf-log",
        "phase_2_search",
        "search_phase",
    )

    assert record.workflow_id == "wf-log"
    assert any(
        "step journal start persist failed workflow_id=wf-log phase=phase_2_search" in rec.message
        for rec in caplog.records
        if rec.levelno == logging.WARNING
    )


@pytest.mark.asyncio
async def test_journal_step_complete_logs_warning_on_persist_failure(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.WARNING, logger=step_journal.__name__)
    record = WorkflowStepRecord(
        step_id="step-log",
        workflow_id="wf-log",
        phase="phase_3_screening",
        step_name="screen",
        status=StepStatus.RUNNING,
    )

    await step_journal.journal_step_complete(repo=_FailingRepo(), record=record)

    assert any(
        "step journal complete persist failed workflow_id=wf-log phase=phase_3_screening step_id=step-log"
        in rec.message
        for rec in caplog.records
        if rec.levelno == logging.WARNING
    )
