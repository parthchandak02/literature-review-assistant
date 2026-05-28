"""Run history, notes, resume, archive, and attach endpoints."""

from __future__ import annotations

import asyncio
import datetime
import json as _json
import logging
import pathlib
import shutil
import uuid
from typing import Any

import aiosqlite
from fastapi import APIRouter, HTTPException, Request, Response
from sse_starlette.sse import EventSourceResponse

from src.db.database import open_runtime_db
from src.db.source_of_truth import RUN_STATS_PRECEDENCE
from src.db.workflow_registry import _open_registry as _open_registry_db
from src.db.workflow_registry import archive_workflow as _archive_registry_workflow
from src.db.workflow_registry import hide_completed_workflow as _hide_completed_registry_workflow
from src.db.workflow_registry import restore_completed_workflow as _restore_completed_registry_workflow
from src.db.workflow_registry import restore_workflow as _restore_registry_workflow
from src.db.workflow_registry import update_notes as _update_registry_notes
from src.web.shared import (
    AttachRequest,
    HistoryEntry,
    ResumeRequest,
    RunResponse,
    _ensure_runtime_db_migrated,
    _normalize_status,
    _NoteBody,
    _resolve_db_path,
    _validate_db_path,
)
from src.web.state import (
    _RESUME_PHASE_ORDER,
    _active_runs,
    _collect_terminal_evidence,
    _lifecycle_metrics,
    _load_event_log_from_db,
    _notes_subscribers,
    _refresh_allowed_roots,
    _resolve_effective_status,
    _resume_wrapper,
    _RunRecord,
)

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["history"])

# ---------------------------------------------------------------------------
# One-time registry migration flag + stats cache
# ---------------------------------------------------------------------------

_registry_migrated: set[str] = set()

_TERMINAL_STATUSES = frozenset({"completed", "failed", "interrupted"})
_stats_cache: dict[str, dict[str, Any]] = {}


async def _ensure_registry_columns(db: aiosqlite.Connection, registry_key: str) -> None:
    """Run ALTER TABLE migrations once per registry DB per process lifetime."""
    if registry_key in _registry_migrated:
        return
    _columns = [
        ("is_archived", "INTEGER NOT NULL DEFAULT 0"),
        ("archived_at", "TEXT"),
        ("notes", "TEXT"),
        ("is_completed_hidden", "INTEGER NOT NULL DEFAULT 0"),
        ("completed_hidden_at", "TEXT"),
    ]
    for col_name, col_type in _columns:
        try:
            await db.execute(f"ALTER TABLE workflows_registry ADD COLUMN {col_name} {col_type}")
        except Exception:
            pass
    await db.commit()
    _registry_migrated.add(registry_key)


def invalidate_stats_cache(workflow_id: str) -> None:
    """Remove cached stats so the next list_history re-fetches them."""
    _stats_cache.pop(workflow_id, None)


# ---------------------------------------------------------------------------
# Helpers local to this router
# ---------------------------------------------------------------------------


async def _fetch_run_stats(db_path: str) -> dict[str, Any]:
    """Open a run's runtime.db and return lightweight aggregate stats."""
    from src.db.stats import RunStatsResolver

    resolver = RunStatsResolver()
    try:
        async with open_runtime_db(db_path, readonly=True) as db:
            stats = await resolver.aggregate(db)

        artifacts_count: int | None = None
        summary_path = pathlib.Path(db_path).parent / "run_summary.json"
        if summary_path.exists():
            try:
                summary = _json.loads(summary_path.read_text(encoding="utf-8"))
                artifacts_count = len(summary.get("artifacts", {}))
            except Exception:
                pass

        return {
            "ok": True,
            **stats,
            "artifacts_count": artifacts_count,
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "papers_found": 0,
            "papers_included": 0,
            "total_cost": 0.0,
            "papers_included_source": "error",
            "papers_included_precedence": list(RUN_STATS_PRECEDENCE.papers_included_order),
            "artifacts_count": None,
        }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/api/history")
async def list_history(response: Response, run_root: str = "runs") -> list[HistoryEntry]:
    """Return all past runs from the central workflows_registry.db."""
    registry = pathlib.Path(run_root) / "workflows_registry.db"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    if not registry.exists():
        return []
    try:
        async with _open_registry_db(str(registry)) as db:
            db.row_factory = aiosqlite.Row
            await _ensure_registry_columns(db, str(registry))
            async with db.execute(
                """SELECT workflow_id, topic, status, db_path,
                          COALESCE(created_at, '') AS created_at,
                          updated_at,
                          heartbeat_at,
                          notes,
                          COALESCE(is_archived, 0) AS is_archived,
                          archived_at,
                          COALESCE(is_completed_hidden, 0) AS is_completed_hidden,
                          completed_hidden_at
                   FROM workflows_registry
                   ORDER BY created_at DESC"""
            ) as cur:
                rows = await cur.fetchall()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not rows:
        return []

    active_run_id_by_workflow: dict[str, str] = {
        r.workflow_id: r.run_id
        for r in _active_runs.values()
        if r.workflow_id and not r.done and (r.task is None or not r.task.done())
    }

    # Separate rows into cached (terminal) and uncached (need fresh stats).
    # Terminal workflows whose stats are already cached skip DB access entirely.
    async def _get_stats_and_status(
        row: aiosqlite.Row,
    ) -> tuple[dict[str, Any], str, dict[str, Any]]:
        wf_id = str(row["workflow_id"])
        db_path = str(row["db_path"])
        live_run_id = active_run_id_by_workflow.get(wf_id)
        reg_status = _normalize_status(str(row["status"]))
        is_terminal = reg_status in _TERMINAL_STATUSES and not live_run_id

        # Stats: use cache for terminal workflows
        if is_terminal and wf_id in _stats_cache:
            stats = _stats_cache[wf_id]
        else:
            try:
                stats = await _fetch_run_stats(db_path)
            except Exception as exc:
                stats = {"ok": False, "error": str(exc)}
            if is_terminal and stats.get("ok"):
                _stats_cache[wf_id] = stats

        # Status: skip expensive evidence collection for known-terminal workflows
        if is_terminal:
            diag: dict[str, Any] = {"registry_status": reg_status, "source": "registry_cached"}
            return stats, reg_status, diag
        else:
            effective_status, diag = await _resolve_effective_status(row, live_run_id, run_root)
            return stats, effective_status, diag

    results = await asyncio.gather(
        *[_get_stats_and_status(r) for r in rows],
        return_exceptions=True,
    )

    enriched: list[HistoryEntry] = []
    for row, result in zip(rows, results):
        if isinstance(result, BaseException):
            s: dict[str, Any] = {}
            effective_status = _normalize_status(str(row["status"]))
            diag = {}
        else:
            s, effective_status, diag = result
        if diag.get("override"):
            _logger.info(
                "Lifecycle reconcile override workflow=%s override=%s source=%s metrics=%s",
                row["workflow_id"],
                diag.get("override"),
                diag.get("source"),
                _lifecycle_metrics,
            )
        enriched.append(
            HistoryEntry(
                workflow_id=row["workflow_id"],
                topic=row["topic"],
                status=effective_status,
                db_path=row["db_path"],
                created_at=row["created_at"] or "",
                updated_at=row["updated_at"],
                papers_found=s.get("papers_found"),
                papers_included=s.get("papers_included"),
                total_cost=s.get("total_cost"),
                artifacts_count=s.get("artifacts_count"),
                stats_ok=s.get("ok"),
                stats_error=s.get("error"),
                live_run_id=active_run_id_by_workflow.get(row["workflow_id"]),
                notes=row["notes"] if row["notes"] is not None else None,
                is_archived=bool(row["is_archived"]),
                archived_at=row["archived_at"] if row["archived_at"] is not None else None,
                is_completed_hidden=bool(row["is_completed_hidden"]),
                completed_hidden_at=(row["completed_hidden_at"] if row["completed_hidden_at"] is not None else None),
            )
        )
    return enriched


@router.get("/api/runs", include_in_schema=False)
async def list_runs_legacy() -> list[dict[str, Any]]:
    """Legacy compatibility endpoint for older clients and integration tests."""
    rows: list[dict[str, Any]] = []
    for run_id, record in _active_runs.items():
        rows.append(
            {
                "run_id": run_id,
                "topic": record.topic,
                "done": bool(record.done),
                "workflow_id": record.workflow_id,
            }
        )
    return rows


@router.patch("/api/notes/{workflow_id}")
async def save_note(workflow_id: str, body: _NoteBody) -> dict[str, bool]:
    """Persist a user note for a workflow and broadcast it to all connected note-stream clients."""
    await _update_registry_notes(body.run_root, workflow_id, body.note)
    event: dict[str, Any] = {
        "workflow_id": workflow_id,
        "note": body.note,
        "ts": datetime.datetime.utcnow().isoformat(),
    }
    dead: set[asyncio.Queue[dict[str, Any] | None]] = set()
    for q in list(_notes_subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            dead.add(q)
    _notes_subscribers.difference_update(dead)
    return {"ok": True}


@router.get("/api/notes/stream")
async def notes_stream(request: Request) -> EventSourceResponse:
    """SSE stream that broadcasts note-save events to all connected clients."""
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=64)
    _notes_subscribers.add(queue)

    async def _generator() -> Any:
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                except TimeoutError:
                    yield {"comment": "ka"}
                    continue
                if event is None:
                    break
                yield {"data": _json.dumps(event)}
        finally:
            _notes_subscribers.discard(queue)

    return EventSourceResponse(_generator())


@router.get("/api/history/{workflow_id}/config")
async def get_run_config(workflow_id: str, run_root: str = "runs") -> dict[str, str]:
    """Return the original review.yaml for a past run."""
    registry = pathlib.Path(run_root) / "workflows_registry.db"
    db_path: str | None = None
    if registry.exists():
        try:
            async with _open_registry_db(str(registry)) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT db_path FROM workflows_registry WHERE workflow_id = ?",
                    (workflow_id,),
                ) as cur:
                    row = await cur.fetchone()
                    if row:
                        db_path = row["db_path"]
        except Exception:
            pass

    if not db_path:
        candidate = pathlib.Path(run_root) / workflow_id / "runtime.db"
        if candidate.exists():
            db_path = str(candidate)

    if not db_path:
        raise HTTPException(status_code=404, detail="Workflow not found")

    yaml_path = pathlib.Path(db_path).parent / "review.yaml"
    if not yaml_path.exists():
        raise HTTPException(status_code=404, detail="Config not saved for this run")

    try:
        content = yaml_path.read_text(encoding="utf-8")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"content": content}


@router.get("/api/history/active-run")
async def get_active_run(workflow_id: str) -> RunResponse:
    """Return the run_id for a workflow that is currently being actively resumed."""
    for record in _active_runs.values():
        if record.workflow_id == workflow_id and not record.done:
            return RunResponse(run_id=record.run_id, topic=record.topic or "")
    raise HTTPException(status_code=404, detail="Workflow not actively running")


@router.post("/api/history/resume", response_model=RunResponse)
async def resume_run(req: ResumeRequest) -> RunResponse:
    """Resume an interrupted workflow from its last checkpoint."""
    if req.from_phase is not None and req.from_phase not in _RESUME_PHASE_ORDER:
        raise HTTPException(
            status_code=400,
            detail=f"from_phase must be one of {_RESUME_PHASE_ORDER}",
        )
    for existing in _active_runs.values():
        if existing.workflow_id == req.workflow_id and not existing.done:
            raise HTTPException(
                status_code=409,
                detail="Workflow is already running. Stop the active run before resuming.",
            )

    try:
        run_root = str(pathlib.Path(req.db_path).parent.parent.parent.parent)
        registry = pathlib.Path(run_root) / "workflows_registry.db"
        if registry.exists():
            async with _open_registry_db(str(registry)) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT status FROM workflows_registry WHERE workflow_id = ?",
                    (req.workflow_id,),
                ) as cur:
                    row = await cur.fetchone()
            registry_status = _normalize_status(str(row["status"])) if row else ""
            if registry_status in {"running", "awaiting_review"}:
                raise HTTPException(
                    status_code=409,
                    detail="Workflow is already running. Stop the active run before resuming.",
                )
    except HTTPException:
        raise
    except Exception:
        pass

    run_id = str(uuid.uuid4())[:8]
    record = _RunRecord(run_id=run_id, topic=req.topic)
    record.db_path = req.db_path
    record.workflow_id = req.workflow_id
    _active_runs[run_id] = record
    task = asyncio.create_task(
        _resume_wrapper(record, req.workflow_id, req.db_path, req.from_phase, req.verbose, req.debug)
    )
    record.task = task
    return RunResponse(run_id=run_id, topic=req.topic)


@router.delete("/api/history/{workflow_id}")
async def delete_run(workflow_id: str, run_root: str = "runs") -> dict[str, bool]:
    """Delete a run from the registry and remove its run directory."""
    for record in _active_runs.values():
        if record.workflow_id == workflow_id and not record.done:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete a run that is currently in progress",
            )

    db_path = await _resolve_db_path(run_root, workflow_id)
    if not db_path:
        raise HTTPException(status_code=404, detail="Workflow not found in registry")

    run_dir = pathlib.Path(db_path).parent
    registry = pathlib.Path(run_root) / "workflows_registry.db"

    try:
        async with _open_registry_db(str(registry)) as db:
            await db.execute(
                "DELETE FROM workflows_registry WHERE workflow_id = ?",
                (workflow_id,),
            )
            await db.commit()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    invalidate_stats_cache(workflow_id)

    try:
        if run_dir.exists():
            shutil.rmtree(run_dir)
    except OSError:
        pass

    return {"ok": True}


@router.post("/api/history/{workflow_id}/archive")
async def archive_history_run(workflow_id: str, run_root: str = "runs") -> dict[str, bool]:
    for record in _active_runs.values():
        if record.workflow_id == workflow_id and not record.done:
            raise HTTPException(status_code=409, detail="Cannot archive a run that is currently in progress")
    db_path = await _resolve_db_path(run_root, workflow_id)
    if not db_path:
        raise HTTPException(status_code=404, detail="Workflow not found in registry")
    await _archive_registry_workflow(run_root, workflow_id)
    invalidate_stats_cache(workflow_id)
    return {"ok": True}


@router.post("/api/history/{workflow_id}/restore")
async def restore_history_run(workflow_id: str, run_root: str = "runs") -> dict[str, bool]:
    for record in _active_runs.values():
        if record.workflow_id == workflow_id and not record.done:
            raise HTTPException(status_code=409, detail="Cannot restore a run that is currently in progress")
    db_path = await _resolve_db_path(run_root, workflow_id)
    if not db_path:
        raise HTTPException(status_code=404, detail="Workflow not found in registry")
    await _restore_registry_workflow(run_root, workflow_id)
    invalidate_stats_cache(workflow_id)
    return {"ok": True}


@router.post("/api/history/{workflow_id}/complete-hide")
async def hide_completed_history_run(workflow_id: str, run_root: str = "runs") -> dict[str, bool]:
    for record in _active_runs.values():
        if record.workflow_id == workflow_id and not record.done:
            raise HTTPException(
                status_code=409, detail="Cannot move a run to completed while it is currently in progress"
            )
    db_path = await _resolve_db_path(run_root, workflow_id)
    if not db_path:
        raise HTTPException(status_code=404, detail="Workflow not found in registry")
    await _hide_completed_registry_workflow(run_root, workflow_id)
    invalidate_stats_cache(workflow_id)
    return {"ok": True}


@router.post("/api/history/{workflow_id}/complete-restore")
async def restore_completed_history_run(workflow_id: str, run_root: str = "runs") -> dict[str, bool]:
    for record in _active_runs.values():
        if record.workflow_id == workflow_id and not record.done:
            raise HTTPException(status_code=409, detail="Cannot restore a run that is currently in progress")
    db_path = await _resolve_db_path(run_root, workflow_id)
    if not db_path:
        raise HTTPException(status_code=404, detail="Workflow not found in registry")
    await _restore_completed_registry_workflow(run_root, workflow_id)
    invalidate_stats_cache(workflow_id)
    return {"ok": True}


@router.post("/api/history/attach", response_model=RunResponse)
async def attach_history(req: AttachRequest) -> RunResponse:
    """Create a read-only completed _RunRecord from a historical workflow."""
    _validate_db_path(req.db_path)
    run_id = str(uuid.uuid4())[:8]
    record = _RunRecord(run_id=run_id, topic=req.topic)
    record.done = True
    record.db_path = req.db_path
    record.workflow_id = req.workflow_id
    await _ensure_runtime_db_migrated(req.db_path)
    summary_path = pathlib.Path(req.db_path).parent / "run_summary.json"
    if summary_path.exists():
        try:
            record.outputs = _json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    record.event_log = await _load_event_log_from_db(req.db_path)
    try:
        evidence = await _collect_terminal_evidence(req.db_path)
    except Exception:
        evidence = {"terminal_status": None, "source": None}
    normalized_req_status = _normalize_status(req.status)
    effective_attach_status = normalized_req_status
    evidence_terminal = evidence.get("terminal_status")
    if evidence_terminal in {"completed", "failed", "interrupted"} and normalized_req_status in {
        "running",
        "stale",
        "awaiting_review",
    }:
        effective_attach_status = str(evidence_terminal)
        _logger.info(
            "Attach status override for %s: %s -> %s (source=%s)",
            req.workflow_id,
            normalized_req_status,
            evidence_terminal,
            evidence.get("source"),
        )
    if effective_attach_status not in ("completed", "done"):
        record.error = f"Workflow {effective_attach_status}"
    if effective_attach_status not in ("completed", "done"):
        has_terminal = any(
            isinstance(e, dict) and e.get("type") in ("done", "error", "cancelled") for e in record.event_log
        )
        if not has_terminal:
            record.event_log.append(
                {
                    "type": "error",
                    "msg": (
                        "Workflow appears orphaned (no terminal event persisted)"
                        if effective_attach_status == "stale"
                        else f"Run ended with status: {effective_attach_status}"
                    ),
                    "ts": datetime.datetime.now(tz=datetime.UTC).isoformat(),
                }
            )
    _active_runs[run_id] = record
    await _refresh_allowed_roots()
    return RunResponse(run_id=run_id, topic=req.topic)
