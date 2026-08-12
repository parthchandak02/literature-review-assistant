"""PROSPERO registration gate endpoints."""

from __future__ import annotations

import pathlib

import aiosqlite
import yaml
from fastapi import APIRouter, HTTPException

from src.config.loader import load_configs
from src.db.workflow_registry import find_by_workflow_id, run_root_from_db_path
from src.db.workflow_registry import update_status as _update_status
from src.models.config import ReviewConfig
from src.orchestration.helpers.prospero_validation import validate_prospero_id
from src.protocol.generator import ProtocolGenerator
from src.web.run_resolver import resolve_registry_entry, resolve_runtime_db
from src.web.shared import ResumeRequest, SubmitProsperoRequest
from src.web.state import _lifecycle_coordinator, _resume_wrapper

router = APIRouter(tags=["prospero_gate"])


def _load_review_config(path: pathlib.Path) -> ReviewConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return ReviewConfig.model_validate(raw)


def _update_protocol_fields(path: pathlib.Path, *, registration_number: str, registration_date: str) -> None:
    if not path.exists():
        return
    review = _load_review_config(path)
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


def _regenerate_prospero_artifacts(run_dir: pathlib.Path, workflow_id: str) -> None:
    snapshot = run_dir / "config_snapshot.yaml"
    review_path = snapshot if snapshot.exists() else run_dir / "review.yaml"
    if not review_path.exists():
        raise FileNotFoundError(f"Review config not found in {run_dir}")

    review, settings = load_configs(review_path=str(review_path), settings_path="config/settings.yaml")
    generator = ProtocolGenerator(output_dir=str(run_dir))
    generator.generate_pre_registration_artifacts(workflow_id, review, settings)


async def _registry_status_for_workflow(workflow_id: str, run_root: str) -> str:
    entry = await find_by_workflow_id(run_root, workflow_id)
    if entry is None:
        return ""
    return str(entry.status or "").strip().lower()


@router.post("/api/run/{run_id}/submit-prospero")
async def submit_prospero(run_id: str, body: SubmitProsperoRequest) -> dict[str, str]:
    """Record PROSPERO registration details and optionally resume the workflow."""
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

    try:
        _regenerate_prospero_artifacts(run_dir, workflow_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to regenerate PROSPERO artifacts: {exc}") from exc

    registry_status = await _registry_status_for_workflow(workflow_id, run_root)
    should_resume = body.resume and registry_status == "awaiting_prospero"
    if not should_resume:
        return {
            "status": "updated",
            "workflow_id": workflow_id,
            "registration_number": registration_number,
            "message": "PROSPERO registration saved and documents regenerated.",
        }

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


@router.post("/api/run/{run_id}/regenerate-prospero")
async def regenerate_prospero(run_id: str) -> dict[str, str]:
    """Regenerate PROSPERO draft documents from the current run config."""
    db_path = await resolve_runtime_db(run_id)
    if not pathlib.Path(db_path).exists():
        raise HTTPException(status_code=404, detail="Run database not found")

    async with aiosqlite.connect(db_path) as _raw_db:
        cursor = await _raw_db.execute("SELECT workflow_id FROM workflows LIMIT 1")
        row = await cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="No workflow found in run database")

    workflow_id = row[0]
    run_dir = pathlib.Path(db_path).parent
    try:
        _regenerate_prospero_artifacts(run_dir, workflow_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to regenerate PROSPERO artifacts: {exc}") from exc

    return {
        "status": "regenerated",
        "workflow_id": workflow_id,
        "message": "PROSPERO documents regenerated from the current config.",
    }
