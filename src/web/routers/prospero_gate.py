"""PROSPERO registration gate endpoints."""

from __future__ import annotations

import pathlib

import aiosqlite
import yaml
from fastapi import APIRouter, HTTPException

from src.db.workflow_registry import run_root_from_db_path
from src.db.workflow_registry import update_status as _update_status
from src.models.config import ReviewConfig
from src.orchestration.helpers.prospero_validation import validate_prospero_id
from src.web.run_resolver import resolve_registry_entry, resolve_runtime_db
from src.web.shared import ResumeRequest, SubmitProsperoRequest
from src.web.state import _lifecycle_coordinator, _resume_wrapper

router = APIRouter(tags=["prospero_gate"])


def _update_protocol_fields(path: pathlib.Path, *, registration_number: str, registration_date: str) -> None:
    if not path.exists():
        return
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    review = ReviewConfig.model_validate(raw)
    review.protocol.registered = True
    review.protocol.registration_number = registration_number
    review.protocol.registration_date = registration_date
    review.protocol.registry = review.protocol.registry or "PROSPERO"
    dumped = yaml.safe_dump(
        review.model_dump(mode="json"),
        sort_keys=False,
        allow_unicode=True,
    )
    path.write_text(dumped, encoding="utf-8")


@router.post("/api/run/{run_id}/submit-prospero")
async def submit_prospero(run_id: str, body: SubmitProsperoRequest) -> dict[str, str]:
    """Record PROSPERO registration details and resume the workflow."""
    db_path = await resolve_runtime_db(run_id)
    if not pathlib.Path(db_path).exists():
        raise HTTPException(status_code=404, detail="Run database not found")

    try:
        registration_number = validate_prospero_id(body.registration_number)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    registration_date = str(body.registration_date or "").strip()
    if not registration_date:
        raise HTTPException(status_code=400, detail="registration_date is required")

    async with aiosqlite.connect(db_path) as _raw_db:
        cursor = await _raw_db.execute("SELECT workflow_id FROM workflows LIMIT 1")
        row = await cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="No workflow found in run database")

    workflow_id = row[0]
    run_dir = pathlib.Path(db_path).parent
    run_root = run_root_from_db_path(db_path)

    _update_protocol_fields(run_dir / "review.yaml", registration_number=registration_number, registration_date=registration_date)
    _update_protocol_fields(
        run_dir / "config_snapshot.yaml",
        registration_number=registration_number,
        registration_date=registration_date,
    )

    entry = await resolve_registry_entry(workflow_id, run_root)

    active = _lifecycle_coordinator.find_active_by_workflow(workflow_id)
    if active is not None:
        await _update_status(run_root, workflow_id, "running")
        return {
            "status": "submitted",
            "workflow_id": workflow_id,
            "registration_number": registration_number,
            "message": "PROSPERO registration recorded. Search will resume shortly.",
        }

    topic = entry.topic or "Untitled review"
    req = ResumeRequest(
        workflow_id=workflow_id,
        db_path=db_path,
        topic=topic,
    )
    await _lifecycle_coordinator.start_resume(req, resume_wrapper=_resume_wrapper)
    return {
        "status": "submitted",
        "workflow_id": workflow_id,
        "registration_number": registration_number,
        "message": "PROSPERO registration recorded. Workflow resume started.",
    }
