"""Run history, notes, resume, archive, and attach endpoints."""

from __future__ import annotations

import asyncio
import datetime
import json as _json
import logging
import pathlib
import shutil
from typing import Any, Literal

import aiosqlite
from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.db.database import open_runtime_db
from src.db.source_of_truth import RUN_STATS_PRECEDENCE
from src.db.workflow_registry import _open_registry as _open_registry_db
from src.db.workflow_registry import archive_workflow as _archive_registry_workflow
from src.db.workflow_registry import hide_completed_workflow as _hide_completed_registry_workflow
from src.db.workflow_registry import restore_completed_workflow as _restore_completed_registry_workflow
from src.db.workflow_registry import restore_workflow as _restore_registry_workflow
from src.db.workflow_registry import run_root_from_db_path
from src.db.workflow_registry import update_notes as _update_registry_notes
from src.orchestration.resume import USER_RESUMABLE_PHASE_ORDER
from src.web.shared import (
    AttachRequest,
    HistoryEntry,
    ResumeRequest,
    RunResponse,
    _normalize_status,
    _NoteBody,
)
from src.web.state import (
    _lifecycle_coordinator,
    _lifecycle_metrics,
    _notes_subscribers,
    _refresh_allowed_roots,
    _resume_wrapper,
    _run_resolver,
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
        ("papers_found", "INTEGER"),
        ("papers_included", "INTEGER"),
        ("total_cost", "REAL"),
        ("stats_updated_at", "TEXT"),
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


async def clear_registry_stats(registry_path: str, workflow_id: str) -> None:
    """Clear persisted registry stats when a workflow becomes active again."""
    invalidate_stats_cache(workflow_id)
    try:
        async with _open_registry_db(registry_path) as db:
            await _ensure_registry_columns(db, registry_path)
            await db.execute(
                """
                UPDATE workflows_registry
                SET papers_found = NULL,
                    papers_included = NULL,
                    total_cost = NULL,
                    stats_updated_at = NULL
                WHERE workflow_id = ?
                """,
                (workflow_id,),
            )
            await db.commit()
    except Exception:
        _logger.debug("Failed to clear registry stats for %s", workflow_id, exc_info=True)


def should_use_registry_stats(
    *,
    reg_status: str,
    stats_updated_at: str | None,
    live_run_id: str | None,
) -> bool:
    """Return True when persisted registry stats are fresh enough to skip runtime.db."""
    if live_run_id is not None:
        return False
    if not stats_updated_at:
        return False
    return _normalize_status(reg_status) in _TERMINAL_STATUSES


def stats_payload_from_registry_row(row: aiosqlite.Row) -> dict[str, Any]:
    """Build a list_history stats payload from registry-persisted columns."""
    return {
        "ok": True,
        "papers_found": row["papers_found"],
        "papers_included": row["papers_included"],
        "total_cost": row["total_cost"],
        "artifacts_count": None,
    }


async def _persist_registry_stats(
    registry_path: str,
    workflow_id: str,
    stats: dict[str, Any],
) -> None:
    """Write aggregate stats back to workflows_registry for future list_history calls."""
    if not stats.get("ok"):
        return
    try:
        async with _open_registry_db(registry_path) as db:
            await _ensure_registry_columns(db, registry_path)
            await db.execute(
                """
                UPDATE workflows_registry
                SET papers_found = ?,
                    papers_included = ?,
                    total_cost = ?,
                    stats_updated_at = datetime('now')
                WHERE workflow_id = ?
                """,
                (
                    stats.get("papers_found"),
                    stats.get("papers_included"),
                    stats.get("total_cost"),
                    workflow_id,
                ),
            )
            await db.commit()
    except Exception:
        _logger.debug("Failed to persist registry stats for %s", workflow_id, exc_info=True)


# ---------------------------------------------------------------------------
# Helpers local to this router
# ---------------------------------------------------------------------------


async def _fetch_run_stats(db_path: str, *, workflow_id: str | None = None) -> dict[str, Any]:
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

        payload = {
            "ok": True,
            **stats,
            "artifacts_count": artifacts_count,
        }
        if workflow_id is not None:
            run_root = run_root_from_db_path(db_path)
            registry_path = str(pathlib.Path(run_root) / "workflows_registry.db")
            await _persist_registry_stats(registry_path, workflow_id, payload)
        return payload
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


def parse_history_view(view: str) -> Literal["full", "rail"]:
    """Normalize and validate the history list view query param."""
    normalized = view.strip().lower()
    if normalized not in ("full", "rail"):
        raise HTTPException(status_code=422, detail=f"view must be 'full' or 'rail', got {view!r}")
    return normalized  # type: ignore[return-value]


def should_reconcile_history_status(*, view: Literal["full", "rail"], include_stats: bool) -> bool:
    """Full view always reconciles; rail view reconciles only when stats are requested."""
    if view == "full":
        return True
    # Rail + stats=false: registry status only (avoids runtime.db reads for reconcile).
    return include_stats


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/api/history")
async def list_history(
    response: Response,
    run_root: str = "runs",
    view: str = Query(default="full", description="full history row or sidebar rail"),
    stats: bool = Query(default=True, description="Include per-run stats from runtime.db"),
):
    """Return all past runs from the central workflows_registry.db."""
    history_view = parse_history_view(view)
    include_stats = stats
    reconcile_status = should_reconcile_history_status(view=history_view, include_stats=include_stats)
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
                          completed_hidden_at,
                          papers_found,
                          papers_included,
                          total_cost,
                          stats_updated_at
                   FROM workflows_registry
                   ORDER BY created_at DESC"""
            ) as cur:
                rows = await cur.fetchall()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not rows:
        return []

    active_run_id_by_workflow = _lifecycle_coordinator.active_run_id_by_workflow()

    # Separate rows into cached (terminal) and uncached (need fresh stats).
    # Terminal workflows whose stats are already cached skip DB access entirely.
    async def _get_stats_and_status(
        row: aiosqlite.Row,
    ) -> tuple[dict[str, Any], str, dict[str, Any]]:
        wf_id = str(row["workflow_id"])
        db_path = str(row["db_path"])
        live_run_id = active_run_id_by_workflow.get(wf_id)
        reg_status = _normalize_status(str(row["status"]))
        # Completed rows may be misclassified parked PROSPERO runs; always reconcile them.
        is_terminal = reg_status in _TERMINAL_STATUSES and reg_status != "completed" and not live_run_id

        if not reconcile_status:
            # stats=false rail: registry status only; no runtime.db access.
            return {}, reg_status, {"registry_status": reg_status, "source": "registry_only"}

        # Stats: prefer registry persistence, then in-memory cache, then runtime.db.
        if include_stats:
            stats_updated_at = row["stats_updated_at"] if row["stats_updated_at"] is not None else None
            if should_use_registry_stats(
                reg_status=reg_status,
                stats_updated_at=stats_updated_at,
                live_run_id=live_run_id,
            ):
                stats_payload = stats_payload_from_registry_row(row)
            elif is_terminal and wf_id in _stats_cache:
                stats_payload = _stats_cache[wf_id]
            else:
                try:
                    stats_payload = await _fetch_run_stats(db_path, workflow_id=wf_id)
                except Exception as exc:
                    stats_payload = {"ok": False, "error": str(exc)}
                if is_terminal and stats_payload.get("ok"):
                    _stats_cache[wf_id] = stats_payload
        else:
            stats_payload = {}

        # Status: skip expensive evidence collection for known-terminal workflows
        if is_terminal:
            diag: dict[str, Any] = {"registry_status": reg_status, "source": "registry_cached"}
            return stats_payload, reg_status, diag
        else:
            effective_status, diag = await _run_resolver.reconcile_effective_status(
                wf_id,
                run_root,
                row=row,
                live_run_id=live_run_id,
            )
            return stats_payload, effective_status, diag

    results = await asyncio.gather(
        *[_get_stats_and_status(r) for r in rows],
        return_exceptions=True,
    )

    if history_view == "rail":
        rail_entries: list[HistoryRailEntry] = []
        for row, result in zip(rows, results):
            if isinstance(result, BaseException):
                s: dict[str, Any] = {}
                effective_status = _normalize_status(str(row["status"]))
            else:
                s, effective_status, _diag = result
            rail_entries.append(
                build_history_rail_entry(
                    row,
                    effective_status=effective_status,
                    live_run_id=active_run_id_by_workflow.get(row["workflow_id"]),
                    stats=s,
                    include_stats=include_stats,
                )
            )
        return rail_entries

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
                papers_found=s.get("papers_found") if include_stats else None,
                papers_included=s.get("papers_included") if include_stats else None,
                total_cost=s.get("total_cost") if include_stats else None,
                artifacts_count=s.get("artifacts_count") if include_stats else None,
                stats_ok=s.get("ok") if include_stats else False,
                stats_error=s.get("error") if include_stats else None,
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
    for run_id, record in _lifecycle_coordinator.items():
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
    db_path = await _run_resolver.resolve_registry_db_path(workflow_id, run_root)
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
    record = _lifecycle_coordinator.find_active_by_workflow(workflow_id)
    if record is not None:
        return RunResponse(run_id=record.run_id, topic=record.topic or "")
    raise HTTPException(status_code=404, detail="Workflow not actively running")


@router.post("/api/history/resume", response_model=RunResponse)
async def resume_run(req: ResumeRequest) -> RunResponse:
    """Resume an interrupted workflow from its last checkpoint."""
    if req.from_phase is not None and req.from_phase not in USER_RESUMABLE_PHASE_ORDER:
        raise HTTPException(
            status_code=400,
            detail=f"from_phase must be one of {USER_RESUMABLE_PHASE_ORDER}",
        )
    run_id, _record = await _lifecycle_coordinator.start_resume(req, resume_wrapper=_resume_wrapper)
    return RunResponse(run_id=run_id, topic=req.topic)


@router.delete("/api/history/{workflow_id}")
async def delete_run(workflow_id: str, run_root: str = "runs") -> dict[str, bool]:
    """Delete a run from the registry and remove its run directory."""
    _lifecycle_coordinator.ensure_not_running(
        workflow_id,
        detail="Cannot delete a run that is currently in progress",
    )

    db_path = await _run_resolver.resolve_registry_db_path(workflow_id, run_root)
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
    _lifecycle_coordinator.ensure_not_running(
        workflow_id,
        detail="Cannot archive a run that is currently in progress",
    )
    db_path = await _run_resolver.resolve_registry_db_path(workflow_id, run_root)
    if not db_path:
        raise HTTPException(status_code=404, detail="Workflow not found in registry")
    await _archive_registry_workflow(run_root, workflow_id)
    invalidate_stats_cache(workflow_id)
    return {"ok": True}


@router.post("/api/history/{workflow_id}/restore")
async def restore_history_run(workflow_id: str, run_root: str = "runs") -> dict[str, bool]:
    _lifecycle_coordinator.ensure_not_running(
        workflow_id,
        detail="Cannot restore a run that is currently in progress",
    )
    db_path = await _run_resolver.resolve_registry_db_path(workflow_id, run_root)
    if not db_path:
        raise HTTPException(status_code=404, detail="Workflow not found in registry")
    await _restore_registry_workflow(run_root, workflow_id)
    invalidate_stats_cache(workflow_id)
    return {"ok": True}


@router.post("/api/history/{workflow_id}/complete-hide")
async def hide_completed_history_run(workflow_id: str, run_root: str = "runs") -> dict[str, bool]:
    _lifecycle_coordinator.ensure_not_running(
        workflow_id,
        detail="Cannot move a run to completed while it is currently in progress",
    )
    db_path = await _run_resolver.resolve_registry_db_path(workflow_id, run_root)
    if not db_path:
        raise HTTPException(status_code=404, detail="Workflow not found in registry")
    await _hide_completed_registry_workflow(run_root, workflow_id)
    invalidate_stats_cache(workflow_id)
    return {"ok": True}


@router.post("/api/history/{workflow_id}/complete-restore")
async def restore_completed_history_run(workflow_id: str, run_root: str = "runs") -> dict[str, bool]:
    _lifecycle_coordinator.ensure_not_running(
        workflow_id,
        detail="Cannot restore a run that is currently in progress",
    )
    db_path = await _run_resolver.resolve_registry_db_path(workflow_id, run_root)
    if not db_path:
        raise HTTPException(status_code=404, detail="Workflow not found in registry")
    await _restore_completed_registry_workflow(run_root, workflow_id)
    invalidate_stats_cache(workflow_id)
    return {"ok": True}


@router.post("/api/history/attach", response_model=RunResponse)
async def attach_history(req: AttachRequest) -> RunResponse:
    """Create a read-only completed _RunRecord from a historical workflow."""
    run_id, record = await _lifecycle_coordinator.attach_history(req)
    await _refresh_allowed_roots()
    return RunResponse(run_id=run_id, topic=record.topic)


class HistoryRailEntry(BaseModel):
    """Slim history row for sidebar rail UI."""

    workflow_id: str
    topic: str
    status: str
    db_path: str
    created_at: str
    live_run_id: str | None = None
    is_archived: bool = False
    is_completed_hidden: bool = False
    notes: str | None = None
    papers_found: int | None = None
    papers_included: int | None = None
    total_cost: float | None = None
    stats_ok: bool | None = None


def build_history_rail_entry(
    row: aiosqlite.Row,
    *,
    effective_status: str,
    live_run_id: str | None,
    stats: dict[str, Any] | None,
    include_stats: bool,
) -> HistoryRailEntry:
    """Build a sidebar-rail history row from registry + optional stats."""
    entry = HistoryRailEntry(
        workflow_id=row["workflow_id"],
        topic=row["topic"],
        status=effective_status,
        db_path=str(row["db_path"] or ""),
        created_at=row["created_at"] or "",
        live_run_id=live_run_id,
        notes=row["notes"] if row["notes"] is not None else None,
        is_archived=bool(row["is_archived"]),
        is_completed_hidden=bool(row["is_completed_hidden"]),
    )
    if include_stats and stats is not None:
        entry.papers_found = stats.get("papers_found")
        entry.papers_included = stats.get("papers_included")
        entry.total_cost = stats.get("total_cost")
        if stats.get("ok") is not None:
            entry.stats_ok = stats.get("ok")
    return entry
