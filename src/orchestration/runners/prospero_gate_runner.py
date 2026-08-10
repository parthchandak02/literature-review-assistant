"""Runner for the PROSPERO registration gate phase."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import yaml

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.db.workflow_registry import find_by_workflow_id, update_status
from src.db.workflow_registry import register as register_workflow
from src.models.config import ReviewConfig
from src.orchestration.helpers.runtime import hash_config as helper_hash_config
from src.orchestration.state import ReviewState
from src.protocol.generator import ProtocolGenerator
from src.utils.logging_paths import default_run_artifacts

logger = logging.getLogger(__name__)


def _reload_review_from_run_dir(state: ReviewState) -> None:
    from pathlib import Path

    run_dir = Path(state.output_dir)
    for name in ("config_snapshot.yaml", "review.yaml"):
        snapshot = run_dir / name
        if not snapshot.exists():
            continue
        try:
            snapshot_data = yaml.safe_load(snapshot.read_text(encoding="utf-8")) or {}
            state.review = ReviewConfig.model_validate(snapshot_data)
            return
        except Exception as exc:
            logger.warning("ProsperoGateNode: could not reload review from %s: %s", snapshot, exc)


def _rc(state: ReviewState):
    return getattr(state, "run_context", None)


def _write_run_summary_stub(state: ReviewState) -> None:
    """Minimal run_summary so artifact download routes resolve output_dir before finalize."""
    summary_path = state.artifacts.get("run_summary")
    if not summary_path:
        return
    payload = {
        "workflow_id": state.workflow_id,
        "output_dir": state.output_dir,
        "topic": state.review.research_question if state.review else "",
        "status": "in_progress",
    }
    Path(summary_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _is_web_mode(state: ReviewState) -> bool:
    rc = _rc(state)
    return rc is not None and bool(getattr(rc, "web_mode", False))


async def run_prospero_gate(state: ReviewState) -> bool:
    """Generate pre-registration artifacts and wait for PROSPERO submission.

    Returns True when the workflow should park in ``awaiting_prospero`` (web/API).
    Returns False when the gate is complete and search may proceed.
    """
    rc = _rc(state)
    assert state.review is not None
    assert state.settings is not None

    if rc:
        rc.emit_phase_start(
            "phase_1_prospero_gate",
            "Awaiting PROSPERO registration. "
            "Submit via POST /api/run/{run_id}/submit-prospero to continue.",
            total=0,
        )

    config_hash = helper_hash_config(state.review_path)
    async with get_db(state.db_path) as db:
        repository = WorkflowRepository(db)
        await repository.create_workflow(state.workflow_id, state.review.research_question, config_hash)
        await register_workflow(
            run_root=state.run_root,
            workflow_id=state.workflow_id,
            topic=state.review.research_question,
            config_hash=config_hash,
            db_path=state.db_path,
        )
        if rc is not None and hasattr(rc, "notify_workflow_id"):
            rc.notify_workflow_id(state.workflow_id, state.run_root)

    protocol_path = state.artifacts.get("protocol", "")
    prospero_md_path = state.artifacts.get("prospero_form_md", "")
    if not protocol_path or not prospero_md_path:
        state.artifacts.update(default_run_artifacts(Path(state.output_dir)))

    generator = ProtocolGenerator(output_dir=state.output_dir)
    generator.generate_pre_registration_artifacts(state.workflow_id, state.review, state.settings)
    _write_run_summary_stub(state)

    protocol = state.review.protocol
    already_registered = bool(protocol.registered and protocol.registration_number.strip())
    if already_registered:
        _reload_review_from_run_dir(state)
        await update_status(state.run_root, state.workflow_id, "running")
        async with get_db(state.db_path) as db:
            repository = WorkflowRepository(db)
            await repository.save_checkpoint(state.workflow_id, "phase_1_prospero_gate", papers_processed=0)
        if rc:
            rc.emit_phase_done(
                "phase_1_prospero_gate",
                {
                    "registered": bool(state.review.protocol.registered),
                    "registration_number": state.review.protocol.registration_number or None,
                },
            )
        return False

    await update_status(state.run_root, state.workflow_id, "awaiting_prospero")

    if _is_web_mode(state):
        if rc:
            rc.emit_phase_done(
                "phase_1_prospero_gate",
                {
                    "paused": True,
                    "awaiting_prospero": True,
                    "workflow_id": state.workflow_id,
                },
            )
        return True

    hitl = state.settings.human_in_the_loop
    poll_interval = max(1, int(getattr(hitl, "poll_interval_seconds", 5)))
    while True:
        entry = await find_by_workflow_id(state.run_root, state.workflow_id)
        if entry and str(getattr(entry, "status", "awaiting_prospero")) == "running":
            break
        await asyncio.sleep(poll_interval)

    _reload_review_from_run_dir(state)
    await update_status(state.run_root, state.workflow_id, "running")

    async with get_db(state.db_path) as db:
        repository = WorkflowRepository(db)
        await repository.save_checkpoint(state.workflow_id, "phase_1_prospero_gate", papers_processed=0)

    if rc:
        rc.emit_phase_done(
            "phase_1_prospero_gate",
            {
                "registered": bool(state.review.protocol.registered),
                "registration_number": state.review.protocol.registration_number or None,
            },
        )
    return False
