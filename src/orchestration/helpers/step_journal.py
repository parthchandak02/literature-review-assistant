from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

from src.models import FailureCategory, RecoveryAction, StepStatus, WorkflowStepRecord

_log = logging.getLogger(__name__)


async def journal_step_start(
    repo,
    workflow_id: str,
    phase: str,
    step_name: str,
    *,
    paper_id: str | None = None,
    parent_step_id: str | None = None,
    max_attempts: int = 1,
) -> WorkflowStepRecord:
    record = WorkflowStepRecord(
        step_id=str(uuid4()),
        workflow_id=workflow_id,
        phase=phase,
        step_name=step_name,
        status=StepStatus.RUNNING,
        max_attempts=max_attempts,
        paper_id=paper_id,
        parent_step_id=parent_step_id,
    )
    try:
        await repo.reconcile_stale_running_steps(
            workflow_id,
            phase,
            step_name,
            replacement_step_id=record.step_id,
        )
        await repo.save_workflow_step(record)
    except Exception:
        _log.debug("step journal write failed for %s/%s", phase, step_name, exc_info=True)
    return record


async def journal_step_complete(
    repo,
    record: WorkflowStepRecord,
    *,
    status: StepStatus = StepStatus.SUCCEEDED,
    error_message: str | None = None,
    failure_category: FailureCategory | None = None,
    recovery_action: RecoveryAction | None = None,
) -> None:
    if not isinstance(status, StepStatus):
        raise ValueError(f"Invalid StepStatus '{status}'. Valid values: {[m.value for m in StepStatus]}")
    if failure_category is not None and not isinstance(failure_category, FailureCategory):
        raise ValueError(
            f"Invalid FailureCategory '{failure_category}'. Valid values: {[m.value for m in FailureCategory]}"
        )
    if recovery_action is not None and not isinstance(recovery_action, RecoveryAction):
        raise ValueError(
            f"Invalid RecoveryAction '{recovery_action}'. Valid values: {[m.value for m in RecoveryAction]}"
        )

    now = datetime.now(UTC)
    record.status = status
    record.error_message = error_message
    record.failure_category = failure_category
    record.recovery_action = recovery_action
    record.completed_at = now
    if record.started_at:
        record.duration_ms = int((now - record.started_at).total_seconds() * 1000)
    try:
        await repo.save_workflow_step(record)
    except Exception:
        _log.warning("step journal complete failed for %s", record.step_id, exc_info=True)
