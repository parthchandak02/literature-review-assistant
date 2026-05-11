"""Quality and manuscript-audit API routes."""

from __future__ import annotations

import json as _json
import pathlib
import sqlite3
from collections.abc import Awaitable, Callable
from typing import Any

import aiosqlite
from fastapi import APIRouter, HTTPException

from src.db.domain_repositories import AuditRepository
from src.db.repositories import WorkflowRepository as _WorkflowRepository
from src.models import ManuscriptAuditFinding, ManuscriptAuditResult


def register_quality_routes(
    router: APIRouter,
    *,
    resolve_db_path: Callable[[str], Awaitable[str]],
    is_missing_table_error: Callable[[Exception, set[str]], bool],
    format_audit_summary: Callable[[ManuscriptAuditResult | None], dict[str, Any] | None],
) -> None:
    @router.get("/api/workflow/{workflow_id}/manuscript-audit/summary")
    async def get_workflow_manuscript_audit_summary(workflow_id: str, limit: int = 20) -> dict[str, Any]:
        db_path = await resolve_db_path(workflow_id)
        try:
            async with aiosqlite.connect(db_path) as db:
                audit_repo = AuditRepository(_WorkflowRepository(db))
                latest = await audit_repo.get_latest_run(workflow_id)
                history = await audit_repo.get_history(workflow_id, limit=max(1, min(limit, 100)))
                return {
                    "workflow_id": workflow_id,
                    "latest_run": latest,
                    "history": history,
                    "audit_summary": format_audit_summary(latest),
                }
        except HTTPException:
            raise
        except Exception as exc:
            if is_missing_table_error(exc, {"manuscript_audit_runs"}):
                return {"workflow_id": workflow_id, "latest_run": None, "history": []}
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.get("/api/workflow/{workflow_id}/manuscript-audit/findings")
    async def get_workflow_manuscript_audit_findings(
        workflow_id: str,
        audit_run_id: str | None = None,
    ) -> dict[str, Any]:
        db_path = await resolve_db_path(workflow_id)
        try:
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
            if is_missing_table_error(exc, {"manuscript_audit_runs", "manuscript_audit_findings"}):
                return {"workflow_id": workflow_id, "audit_run_id": None, "findings": []}
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.get("/api/run/{run_id}/manuscript-audit")
    async def get_run_manuscript_audit(run_id: str, history_limit: int = 20) -> dict[str, Any]:
        db_path = await resolve_db_path(run_id)
        workflow_id = run_id
        summary_payload: dict[str, Any] = {}
        summary_path = pathlib.Path(db_path).parent / "run_summary.json"
        if summary_path.exists():
            try:
                summary_payload = _json.loads(summary_path.read_text(encoding="utf-8"))
            except Exception:
                summary_payload = {}
        try:
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
                    "audit_summary": format_audit_summary(latest),
                }
        except HTTPException:
            raise
        except Exception as exc:
            if is_missing_table_error(exc, {"manuscript_audit_runs", "manuscript_audit_findings"}):
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
            if isinstance(exc, sqlite3.OperationalError):
                raise HTTPException(status_code=500, detail=str(exc)) from exc
            raise HTTPException(status_code=500, detail=str(exc)) from exc
