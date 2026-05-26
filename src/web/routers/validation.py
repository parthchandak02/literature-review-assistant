"""Validation and manuscript-audit endpoints."""

from __future__ import annotations

import json as _json
from typing import Any

import aiosqlite
from fastapi import APIRouter, HTTPException

from src.db.domain_repositories import AuditRepository, ValidationRepository
from src.models import ManuscriptAuditFinding
from src.web.shared import _format_manuscript_audit_summary, _is_missing_table_error
from src.web.state import _resolve_db_path_from_run_or_workflow

router = APIRouter(tags=["validation"])


@router.get("/api/workflow/{workflow_id}/validation/summary")
async def get_workflow_validation_summary(workflow_id: str) -> dict[str, Any]:
    """Return latest validation-run summary for a workflow."""
    db_path = await _resolve_db_path_from_run_or_workflow(workflow_id)
    try:
        from src.db.repositories import WorkflowRepository as _WorkflowRepository

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            validation_repo = ValidationRepository(_WorkflowRepository(db))
            latest_run = await validation_repo.get_latest_run(workflow_id)
            if latest_run is None:
                return {"workflow_id": workflow_id, "latest_run": None}
            checks = await validation_repo.get_checks(str(latest_run.validation_run_id))
            error_count = len([c for c in checks if c.status == "fail" and c.severity == "error"])
            warn_count = len([c for c in checks if c.severity == "warn" and c.status in {"warn", "fail"}])
            try:
                summary_payload = _json.loads(str(latest_run.summary_json or "{}"))
            except Exception:
                summary_payload = {}
            return {
                "workflow_id": workflow_id,
                "latest_run": {
                    "validation_run_id": str(latest_run.validation_run_id),
                    "profile": str(latest_run.profile),
                    "status": str(latest_run.status),
                    "tool_version": str(latest_run.tool_version),
                    "summary": summary_payload if isinstance(summary_payload, dict) else {},
                    "started_at": str(latest_run.started_at or ""),
                    "completed_at": str(latest_run.completed_at or ""),
                    "error_count": error_count,
                    "warn_count": warn_count,
                    "total_checks": len(checks),
                },
            }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/workflow/{workflow_id}/validation/checks")
async def get_workflow_validation_checks(workflow_id: str, validation_run_id: str | None = None) -> dict[str, Any]:
    """Return ordered checks for a validation run (latest when omitted)."""
    db_path = await _resolve_db_path_from_run_or_workflow(workflow_id)
    try:
        from src.db.repositories import WorkflowRepository as _WorkflowRepository

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            validation_repo = ValidationRepository(_WorkflowRepository(db))
            run_id = validation_run_id
            if not run_id:
                latest_run = await validation_repo.get_latest_run(workflow_id)
                if latest_run is None:
                    return {"workflow_id": workflow_id, "validation_run_id": None, "checks": []}
                run_id = str(latest_run.validation_run_id)
            rows = await validation_repo.get_checks(str(run_id))
            checks: list[dict[str, Any]] = []
            for row in rows:
                try:
                    details = _json.loads(str(row.details_json or "{}"))
                except Exception:
                    details = {}
                checks.append(
                    {
                        "phase": str(row.phase),
                        "check_name": str(row.check_name),
                        "status": str(row.status),
                        "severity": str(row.severity),
                        "metric_value": float(row.metric_value) if row.metric_value is not None else None,
                        "details": details if isinstance(details, dict) else {},
                        "source_module": str(row.source_module) if row.source_module else None,
                        "paper_id": str(row.paper_id) if row.paper_id else None,
                        "created_at": str(row.created_at or ""),
                    }
                )
            return {"workflow_id": workflow_id, "validation_run_id": run_id, "checks": checks}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/workflow/{workflow_id}/manuscript-audit/summary")
async def get_workflow_manuscript_audit_summary(workflow_id: str, limit: int = 20) -> dict[str, Any]:
    """Return latest and historical manuscript-audit summaries for a workflow."""
    db_path = await _resolve_db_path_from_run_or_workflow(workflow_id)
    try:
        from src.db.repositories import WorkflowRepository as _WorkflowRepository

        async with aiosqlite.connect(db_path) as db:
            audit_repo = AuditRepository(_WorkflowRepository(db))
            latest = await audit_repo.get_latest_run(workflow_id)
            history = await audit_repo.get_history(workflow_id, limit=max(1, min(limit, 100)))
            return {
                "workflow_id": workflow_id,
                "latest_run": latest,
                "history": history,
                "audit_summary": _format_manuscript_audit_summary(latest),
            }
    except HTTPException:
        raise
    except Exception as exc:
        if _is_missing_table_error(exc, {"manuscript_audit_runs"}):
            return {"workflow_id": workflow_id, "latest_run": None, "history": []}
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/workflow/{workflow_id}/manuscript-audit/findings")
async def get_workflow_manuscript_audit_findings(
    workflow_id: str,
    audit_run_id: str | None = None,
) -> dict[str, Any]:
    """Return findings for a manuscript audit run (latest when omitted)."""
    db_path = await _resolve_db_path_from_run_or_workflow(workflow_id)
    try:
        from src.db.repositories import WorkflowRepository as _WorkflowRepository

        async with aiosqlite.connect(db_path) as db:
            audit_repo = AuditRepository(_WorkflowRepository(db))
            run_id = audit_run_id
            if not run_id:
                latest = await audit_repo.get_latest_run(workflow_id)
                if latest is None:
                    return {"workflow_id": workflow_id, "audit_run_id": None, "findings": []}
                run_id = str(latest.audit_run_id)
            else:
                scoped_run = await audit_repo.get_run(workflow_id, str(run_id))
                if scoped_run is None:
                    return {"workflow_id": workflow_id, "audit_run_id": None, "findings": []}
            findings = await audit_repo.get_findings(str(run_id))
            return {"workflow_id": workflow_id, "audit_run_id": run_id, "findings": findings}
    except HTTPException:
        raise
    except Exception as exc:
        if _is_missing_table_error(exc, {"manuscript_audit_runs", "manuscript_audit_findings"}):
            return {"workflow_id": workflow_id, "audit_run_id": None, "findings": []}
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/run/{run_id}/manuscript-audit")
async def get_run_manuscript_audit(run_id: str, history_limit: int = 20) -> dict[str, Any]:
    """Return manuscript audit payload for a run/workflow identifier."""
    db_path = await _resolve_db_path_from_run_or_workflow(run_id)
    workflow_id = run_id
    import pathlib

    summary_payload: dict[str, Any] = {}
    summary_path = pathlib.Path(db_path).parent / "run_summary.json"
    if summary_path.exists():
        try:
            summary_payload = _json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            summary_payload = {}
    try:
        from src.db.repositories import WorkflowRepository as _WorkflowRepository

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            audit_repo = AuditRepository(_WorkflowRepository(db))
            wf_row = await (
                await db.execute("SELECT workflow_id FROM workflows ORDER BY updated_at DESC, rowid DESC LIMIT 1")
            ).fetchone()
            workflow_id = str(wf_row["workflow_id"]) if wf_row and wf_row["workflow_id"] else run_id
            latest = await audit_repo.get_latest_run(workflow_id)
            history = await audit_repo.get_history(workflow_id, limit=max(1, min(history_limit, 100)))
            findings: list[ManuscriptAuditFinding] = []
            if latest is not None:
                findings = await audit_repo.get_findings(str(latest.audit_run_id))
            return {
                "run_id": run_id,
                "workflow_id": workflow_id,
                "run_summary_contract": summary_payload.get("manuscript_contract"),
                "citation_lineage_valid": summary_payload.get("citation_lineage_valid"),
                "citation_lineage": summary_payload.get("citation_lineage"),
                "latest_run": latest,
                "history": history,
                "findings": findings,
                "audit_summary": _format_manuscript_audit_summary(latest),
            }
    except HTTPException:
        raise
    except Exception as exc:
        if _is_missing_table_error(exc, {"manuscript_audit_runs", "manuscript_audit_findings"}):
            return {
                "run_id": run_id,
                "workflow_id": workflow_id,
                "run_summary_contract": summary_payload.get("manuscript_contract"),
                "citation_lineage_valid": summary_payload.get("citation_lineage_valid"),
                "citation_lineage": summary_payload.get("citation_lineage"),
                "latest_run": None,
                "history": [],
                "findings": [],
                "audit_summary": None,
            }
        raise HTTPException(status_code=500, detail=str(exc)) from exc
