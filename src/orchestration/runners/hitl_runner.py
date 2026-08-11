"""Runner helpers for human-in-the-loop checkpoints."""

from __future__ import annotations

import logging

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.db.workflow_registry import find_by_workflow_id, update_status
from src.orchestration.state import ReviewState


def _rc(state: ReviewState):
    return getattr(state, "run_context", None)


def _is_web_mode(state: ReviewState) -> bool:
    rc = _rc(state)
    return rc is not None and bool(getattr(rc, "web_mode", False))


logger = logging.getLogger(__name__)


async def run_human_review_checkpoint(state: ReviewState) -> bool:
    """Return True when HITL is enabled and the workflow should park in ``awaiting_review`` (web/API)."""
    rc = _rc(state)
    assert state.settings is not None
    hitl = state.settings.human_in_the_loop
    if not hitl.enabled:
        return False

    if rc:
        rc.emit_phase_start(
            "human_review_checkpoint",
            f"Awaiting human review of {len(state.included_papers)} screened papers. "
            "Approve via POST /api/run/{{run_id}}/approve-screening to continue.",
            total=0,
        )

    await update_status(state.run_root, state.workflow_id, "awaiting_review")

    if _is_web_mode(state):
        if rc:
            rc.emit_phase_done(
                "human_review_checkpoint",
                {
                    "paused": True,
                    "awaiting_review": True,
                    "workflow_id": state.workflow_id,
                },
            )
        return True

    import asyncio as _asyncio

    poll_interval = max(1, int(getattr(hitl, "poll_interval_seconds", 5)))
    max_wait = max(poll_interval, int(getattr(hitl, "max_wait_seconds", 7200)))
    waited = 0
    approved = False
    while waited < max_wait:
        await _asyncio.sleep(poll_interval)
        waited += poll_interval
        entry = await find_by_workflow_id(state.run_root, state.workflow_id)
        if entry and str(getattr(entry, "status", "awaiting_review")) == "running":
            approved = True
            break

    if not approved:
        logger.warning(
            "HumanReviewCheckpointNode: CLI wait timed out after %ds without registry status 'running'; "
            "remaining parked in awaiting_review. Approve via API to continue.",
            max_wait,
        )
        if rc:
            rc.emit_phase_done(
                "human_review_checkpoint",
                {
                    "paused": True,
                    "awaiting_review": True,
                    "timeout": True,
                    "workflow_id": state.workflow_id,
                },
            )
        return True

    await update_status(state.run_root, state.workflow_id, "running")

    try:
        async with get_db(state.db_path) as hitl_db:
            repo = WorkflowRepository(hitl_db)
            included_ids = await repo.get_included_paper_ids(state.workflow_id)
            if not included_ids:
                included_ids = await repo.get_title_abstract_include_ids(state.workflow_id)
            state.included_papers = [paper for paper in state.deduped_papers if paper.paper_id in included_ids]
    except Exception as reload_err:
        logger.warning("HumanReviewCheckpointNode: could not reload included_papers: %s", reload_err)

    if rc:
        rc.emit_phase_done("human_review_checkpoint", {"approved": True})
    return False
