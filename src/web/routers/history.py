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
# Helpers local to this router
# ---------------------------------------------------------------------------


async def _fetch_run_stats(db_path: str) -> dict[str, Any]:
    """Open a run's runtime.db and return lightweight aggregate stats."""
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            papers_found = (await (await db.execute("SELECT COUNT(*) FROM papers")).fetchone())[0]

            _workflow_row = await (
                await db.execute("SELECT workflow_id FROM workflows ORDER BY rowid DESC LIMIT 1")
            ).fetchone()
            _workflow_id = str(_workflow_row[0]) if (_workflow_row and _workflow_row[0]) else ""

            included_from_cohort = await (
                await db.execute(
                    """
                    SELECT COUNT(DISTINCT scm.paper_id)
                    FROM study_cohort_membership scm
                    WHERE scm.workflow_id = ?
                      AND scm.synthesis_eligibility = 'included_primary'
                    """,
                    (_workflow_id,),
                )
            ).fetchone()
            included_from_dual = await (
                await db.execute(
                    """
                    SELECT COUNT(DISTINCT paper_id)
                    FROM dual_screening_results
                    WHERE stage = 'fulltext' AND final_decision IN ('include', 'uncertain')
                    """
                )
            ).fetchone()
            included_source = "study_cohort_membership_synthesis_included_primary"
            if included_from_cohort and included_from_cohort[0] is not None and int(included_from_cohort[0]) > 0:
                papers_included = int(included_from_cohort[0])
            elif included_from_dual and included_from_dual[0] is not None and int(included_from_dual[0]) > 0:
                papers_included = int(included_from_dual[0])
                included_source = "dual_screening_results_fulltext"
            else:
                included_from_event = await (
                    await db.execute(
                        """
                        SELECT json_extract(payload, '$.summary.included')
                        FROM event_log
                        WHERE event_type = 'phase_done'
                          AND json_extract(payload, '$.phase') = 'phase_3_screening'
                        ORDER BY id DESC
                        LIMIT 1
                        """
                    )
                ).fetchone()
                if included_from_event and included_from_event[0] is not None:
                    papers_included = int(included_from_event[0])
                    included_source = "event_log_phase_done_phase_3_screening"
                else:
                    fallback_row = await (await db.execute("SELECT COUNT(*) FROM extraction_records")).fetchone()
                    papers_included = int(fallback_row[0]) if fallback_row else 0
                    included_source = "extraction_records"

            try:
                _event_inc_row = await (
                    await db.execute(
                        """
                        SELECT json_extract(payload, '$.summary.included')
                        FROM event_log
                        WHERE event_type = 'phase_done'
                          AND json_extract(payload, '$.phase') = 'phase_3_screening'
                        ORDER BY id DESC
                        LIMIT 1
                        """
                    )
                ).fetchone()
                _event_inc = int(_event_inc_row[0]) if (_event_inc_row and _event_inc_row[0] is not None) else None
                _cohort_inc = (
                    int(included_from_cohort[0])
                    if (included_from_cohort and included_from_cohort[0] is not None)
                    else 0
                )
                _dual_inc = (
                    int(included_from_dual[0]) if (included_from_dual and included_from_dual[0] is not None) else 0
                )
                if (
                    included_source == "dual_screening_results_fulltext"
                    and _event_inc is not None
                    and _dual_inc > 0
                    and _event_inc != _dual_inc
                ):
                    _logger.warning(
                        "run-stats divergence: dual_screening_results=%s event_log=%s for db=%s",
                        _dual_inc,
                        _event_inc,
                        db_path,
                    )
                if (
                    included_source == "study_cohort_membership_synthesis_included_primary"
                    and _cohort_inc > _dual_inc
                    and _dual_inc > 0
                ):
                    _logger.warning(
                        "run-stats divergence: cohort=%s exceeds dual_screening_results=%s for db=%s",
                        _cohort_inc,
                        _dual_inc,
                        db_path,
                    )
            except Exception:
                pass

            total_cost = (await (await db.execute("SELECT COALESCE(SUM(cost_usd), 0.0) FROM cost_records")).fetchone())[
                0
            ]

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
            "papers_found": int(papers_found),
            "papers_included": int(papers_included),
            "total_cost": float(total_cost),
            "papers_included_source": included_source,
            "papers_included_precedence": list(RUN_STATS_PRECEDENCE.papers_included_order),
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
            try:
                await db.execute("ALTER TABLE workflows_registry ADD COLUMN is_archived INTEGER NOT NULL DEFAULT 0")
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE workflows_registry ADD COLUMN archived_at TEXT")
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE workflows_registry ADD COLUMN notes TEXT")
            except Exception:
                pass
            try:
                await db.execute(
                    "ALTER TABLE workflows_registry ADD COLUMN is_completed_hidden INTEGER NOT NULL DEFAULT 0"
                )
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE workflows_registry ADD COLUMN completed_hidden_at TEXT")
            except Exception:
                pass
            await db.commit()
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

    stat_results = await asyncio.gather(
        *[_fetch_run_stats(str(r["db_path"])) for r in rows],
        return_exceptions=True,
    )

    active_run_id_by_workflow: dict[str, str] = {
        r.workflow_id: r.run_id
        for r in _active_runs.values()
        if r.workflow_id and not r.done and (r.task is None or not r.task.done())
    }

    enriched: list[HistoryEntry] = []
    for row, stats in zip(rows, stat_results):
        s = stats if isinstance(stats, dict) else {}
        live_run_id = active_run_id_by_workflow.get(row["workflow_id"])
        effective_status, diag = await _resolve_effective_status(row, live_run_id, run_root)
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
                live_run_id=live_run_id,
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
