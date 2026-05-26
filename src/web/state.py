"""State containers and lifecycle management for the web layer.

Houses mutable process state (active runs, subscribers, allowed roots) and
run lifecycle wrappers so that router modules can import them without creating
circular imports with ``app.py``.
"""

from __future__ import annotations

import asyncio
import datetime
import json as _json
import logging
import pathlib
import time
import uuid
from collections.abc import Iterator
from typing import Any

import aiosqlite
from fastapi import HTTPException

from src.config.loader import load_configs as _load_configs
from src.db.workflow_registry import _open_registry as _open_registry_db
from src.db.workflow_registry import update_heartbeat as _update_registry_heartbeat
from src.db.workflow_registry import update_status as _update_registry_status
from src.web.shared import (
    RunRequest,
    _normalize_status,
    _resolve_db_path,
)

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Web-tier config (loaded once at import time)
# ---------------------------------------------------------------------------
try:
    _web_cfg = _load_configs()[1].web
except Exception:
    from src.models.config import WebConfig as _WebConfig

    _web_cfg = _WebConfig()

# ---------------------------------------------------------------------------
# RunRegistry & NotesBroadcaster
# ---------------------------------------------------------------------------


class RunRegistry:
    """Thin wrapper around the in-memory active run map."""

    def __init__(self, backing: dict[str, Any] | None = None) -> None:
        self._runs: dict[str, Any] = backing if backing is not None else {}

    def get(self, run_id: str) -> Any | None:
        return self._runs.get(run_id)

    def set(self, run_id: str, record: Any) -> None:
        self._runs[run_id] = record

    def pop(self, run_id: str, default: Any = None) -> Any:
        return self._runs.pop(run_id, default)

    def values(self) -> Iterator[Any]:
        return self._runs.values()

    def items(self) -> Iterator[tuple[str, Any]]:
        return self._runs.items()

    def as_dict(self) -> dict[str, Any]:
        return self._runs


class NotesBroadcaster:
    """Broadcast notes update payloads to subscribed queues."""

    def __init__(self, subscribers: set[asyncio.Queue[dict[str, Any] | None]] | None = None) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any] | None]] = subscribers if subscribers is not None else set()

    def subscribe(self, queue: asyncio.Queue[dict[str, Any] | None]) -> None:
        self._subscribers.add(queue)

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any] | None]) -> None:
        self._subscribers.discard(queue)

    def subscribers(self) -> set[asyncio.Queue[dict[str, Any] | None]]:
        return self._subscribers


# ---------------------------------------------------------------------------
# _RunRecord – in-process record of a single workflow execution
# ---------------------------------------------------------------------------


class _RunRecord:
    def __init__(self, run_id: str, topic: str) -> None:
        self.run_id = run_id
        self.topic = topic
        self.task: asyncio.Task[Any] | None = None
        self.done = False
        self.error: str | None = None
        self.outputs: dict[str, Any] = {}
        self.db_path: str | None = None
        self.workflow_id: str | None = None
        self.run_root: str = "runs"
        self.created_at: float = time.monotonic()
        self.event_log: list[dict[str, Any]] = []
        self._flush_index: int = 0
        self._flush_lock: asyncio.Lock = asyncio.Lock()
        self._event_cond: asyncio.Condition = asyncio.Condition()
        self.review_yaml: str = ""


# ---------------------------------------------------------------------------
# Mutable process state
# ---------------------------------------------------------------------------

_active_runs: dict[str, _RunRecord] = {}
_run_registry = RunRegistry(_active_runs)

_notes_subscribers: set[asyncio.Queue[dict[str, Any] | None]] = set()
_notes_broadcaster = NotesBroadcaster(_notes_subscribers)

_RUN_TTL_SECONDS = _web_cfg.run_ttl_seconds
_STALE_THRESHOLD_SECONDS = 2 * 60
_STALE_GRACE_SECONDS = 2 * 60

_TERMINAL_REGISTRY_STATUSES = {"completed", "failed", "interrupted", "stale"}
_TERMINAL_EVENT_TO_STATUS = {
    "done": "completed",
    "error": "failed",
    "cancelled": "interrupted",
}

_lifecycle_metrics: dict[str, int] = {
    "stale_detections": 0,
    "stale_reversals": 0,
    "missing_heartbeat_with_terminal_evidence": 0,
}

_allowed_roots: set[str] = set()

_RESUME_PHASE_ORDER = [
    "phase_2_search",
    "phase_3_screening",
    "phase_4_extraction_quality",
    "phase_4b_embedding",
    "phase_5_synthesis",
    "phase_5b_knowledge_graph",
    "phase_5c_pre_writing_gate",
    "phase_6_writing",
    "finalize",
]


def _bump_lifecycle_metric(name: str) -> None:
    _lifecycle_metrics[name] = _lifecycle_metrics.get(name, 0) + 1


# ---------------------------------------------------------------------------
# State-dependent helpers
# ---------------------------------------------------------------------------


def _get_db_path(run_id: str) -> str:
    record = _active_runs.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if not record.db_path:
        raise HTTPException(
            status_code=503,
            detail="Database initializing -- retry in a moment",
            headers={"Retry-After": "2"},
        )
    return record.db_path


async def _resolve_db_path_from_run_or_workflow(identifier: str, run_root: str = "runs") -> str:
    """Resolve a db_path from either an active run_id or a workflow_id."""
    record = _active_runs.get(identifier)
    if record is not None:
        if not record.db_path:
            raise HTTPException(
                status_code=503,
                detail="Database initializing -- retry in a moment",
                headers={"Retry-After": "2"},
            )
        return record.db_path

    if not identifier.startswith("wf-"):
        raise HTTPException(status_code=404, detail="Run not found")

    from src.db.workflow_registry import candidate_run_roots, resolve_workflow_db_path

    roots = candidate_run_roots(run_root, anchor_file=__file__)
    db_path = await resolve_workflow_db_path(identifier, roots)
    if not db_path:
        raise HTTPException(status_code=404, detail="Run not found")
    return db_path


# ---------------------------------------------------------------------------
# Startup / eviction helpers
# ---------------------------------------------------------------------------


async def _refresh_allowed_roots() -> None:
    """Rebuild the set of allowed download root directories."""
    roots: set[str] = {str(pathlib.Path("runs").resolve())}
    registry = pathlib.Path("runs") / "workflows_registry.db"
    if registry.exists():
        try:
            async with _open_registry_db(str(registry)) as db:
                async with db.execute("SELECT db_path FROM workflows_registry") as cur:
                    rows = await cur.fetchall()
            for (db_path,) in rows:
                run_root = pathlib.Path(db_path).parent.parent.parent.parent.resolve()
                roots.add(str(run_root))
        except Exception:
            pass
    _allowed_roots.update(roots)


async def _eviction_loop() -> None:
    while True:
        await asyncio.sleep(_web_cfg.eviction_interval_seconds)
        cutoff = time.monotonic() - _RUN_TTL_SECONDS
        stale = [k for k, v in list(_active_runs.items()) if v.done and v.created_at < cutoff]
        for k in stale:
            _active_runs.pop(k, None)


async def _repair_registry_statuses_from_runtime(run_root: str = "runs") -> None:
    """Repair stale/running registry rows when runtime.db has durable terminal evidence."""

    registry = pathlib.Path(run_root) / "workflows_registry.db"
    if not registry.exists():
        return
    try:
        async with _open_registry_db(str(registry)) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT workflow_id, status, db_path
                FROM workflows_registry
                WHERE status IN ('running', 'stale', 'awaiting_review')
                """
            ) as cur:
                rows = await cur.fetchall()
    except Exception:
        return
    repaired = 0
    for row in rows:
        db_path = str(row["db_path"])
        status = _normalize_status(str(row["status"]))
        evidence = await _collect_terminal_evidence(db_path)
        terminal = evidence.get("terminal_status")
        if terminal in {"completed", "failed", "interrupted"} and status in {"running", "stale", "awaiting_review"}:
            try:
                await _update_registry_status(run_root, str(row["workflow_id"]), str(terminal))
                repaired += 1
            except Exception:
                continue
    if repaired > 0:
        _logger.info("Lifecycle startup repair: updated %d registry rows using durable terminal evidence", repaired)


# ---------------------------------------------------------------------------
# Event system
# ---------------------------------------------------------------------------

_DURABLE_EVENT_TYPES = frozenset(
    {
        "phase_start",
        "phase_done",
        "done",
        "error",
        "cancelled",
        "workflow_id_ready",
        "db_ready",
    }
)


async def _persist_event_log(db_path: str, workflow_id: str, events: list[dict[str, Any]]) -> None:
    """Write buffered SSE events to the run's SQLite database for historical replay."""
    if not events or not workflow_id:
        return
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.executemany(
                "INSERT INTO event_log (workflow_id, event_type, payload, ts) VALUES (?, ?, ?, ?)",
                [
                    (
                        workflow_id,
                        e.get("type", "unknown"),
                        _json.dumps(e, default=str),
                        str(e.get("ts", "")),
                    )
                    for e in events
                ],
            )
            await db.commit()
    except Exception:
        pass


async def _notify_new_event(record: _RunRecord) -> None:
    async with record._event_cond:
        record._event_cond.notify_all()


async def _flush_pending_events(record: _RunRecord) -> None:
    """Flush unpersisted tail events in record.event_log to SQLite."""
    if not (record.db_path and record.workflow_id):
        return
    async with record._flush_lock:
        new = record.event_log[record._flush_index :]
        if not new:
            return
        await _persist_event_log(record.db_path, record.workflow_id, new)
        record._flush_index += len(new)


def _append_event(record: _RunRecord, event: dict[str, Any]) -> None:
    """Append event to replay log and notify all live stream subscribers."""
    if not event.get("id"):
        event["id"] = f"evt-{uuid.uuid4().hex}"
    if not event.get("ts"):
        event["ts"] = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    _etype = str(event.get("type") or "")
    event["durability"] = "durable" if _etype in _DURABLE_EVENT_TYPES else "eventual"
    record.event_log.append(event)
    try:
        asyncio.create_task(_notify_new_event(record))
    except Exception:
        pass

    if _etype in _DURABLE_EVENT_TYPES:
        try:
            asyncio.create_task(_flush_pending_events(record))
        except Exception:
            pass


async def _load_event_log_from_db(db_path: str) -> list[dict[str, Any]]:
    """Load persisted SSE events from a run's SQLite event_log table only."""
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT id, payload, ts FROM event_log ORDER BY id ASC") as cur:
                rows = await cur.fetchall()
        events = []
        for row in rows:
            event = _json.loads(row["payload"])
            if not event.get("id"):
                event["id"] = f"db-{row['id']}"
            if not event.get("ts"):
                event["ts"] = str(row["ts"] or "")
            events.append(event)
    except Exception:
        events = []

    return events


# ---------------------------------------------------------------------------
# Terminal evidence collection (used by history lifecycle reconciliation)
# ---------------------------------------------------------------------------


def _running_heartbeat_stale(row: aiosqlite.Row) -> bool:
    """Return True if a running workflow heartbeat is stale with grace windows."""
    from src.web.shared import _age_seconds as _age_fn

    heartbeat_age = _age_fn(row["heartbeat_at"])
    updated_age = _age_fn(row["updated_at"])
    created_age = _age_fn(row["created_at"])
    fresh = (
        min(x for x in (heartbeat_age, updated_age, created_age) if x is not None)
        if any(x is not None for x in (heartbeat_age, updated_age, created_age))
        else None
    )
    if fresh is not None and fresh <= _STALE_GRACE_SECONDS:
        return False
    if heartbeat_age is not None:
        return heartbeat_age > _STALE_THRESHOLD_SECONDS
    if updated_age is not None:
        return updated_age > _STALE_THRESHOLD_SECONDS
    if created_age is not None:
        return created_age > _STALE_THRESHOLD_SECONDS
    return True


async def _collect_terminal_evidence(db_path: str) -> dict[str, Any]:
    """Collect durable terminal evidence from runtime.db and run_summary.json."""
    out: dict[str, Any] = {
        "terminal_status": None,
        "source": None,
        "event_type": None,
        "workflow_status": None,
        "summary_status": None,
        "finalize_checkpoint_status": None,
    }
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            try:
                async with db.execute(
                    "SELECT event_type FROM event_log WHERE event_type IN ('done','error','cancelled') ORDER BY id DESC LIMIT 1"
                ) as cur:
                    ev_row = await cur.fetchone()
                if ev_row and ev_row["event_type"]:
                    ev_type = str(ev_row["event_type"])
                    out["event_type"] = ev_type
                    ev_status = _TERMINAL_EVENT_TO_STATUS.get(ev_type)
                    if ev_status:
                        out["terminal_status"] = ev_status
                        out["source"] = "event_log"
            except Exception:
                pass
            if out["terminal_status"] is None:
                try:
                    async with db.execute(
                        "SELECT status FROM workflows ORDER BY updated_at DESC, rowid DESC LIMIT 1"
                    ) as cur:
                        wf_row = await cur.fetchone()
                    wf_status = _normalize_status(str(wf_row["status"])) if wf_row and wf_row["status"] else ""
                    out["workflow_status"] = wf_status
                    if wf_status in {"completed", "failed", "interrupted"}:
                        out["terminal_status"] = wf_status
                        out["source"] = "workflows_table"
                except Exception:
                    pass
            if out["terminal_status"] is None:
                try:
                    async with db.execute(
                        "SELECT status FROM checkpoints WHERE phase='finalize' ORDER BY rowid DESC LIMIT 1"
                    ) as cur:
                        cp_row = await cur.fetchone()
                    cp_status = _normalize_status(str(cp_row["status"])) if cp_row and cp_row["status"] else ""
                    out["finalize_checkpoint_status"] = cp_status
                    if cp_status == "completed":
                        out["terminal_status"] = "completed"
                        out["source"] = "finalize_checkpoint"
                except Exception:
                    pass
    except Exception:
        return out
    summary_path = pathlib.Path(db_path).parent / "run_summary.json"
    if summary_path.exists():
        try:
            summary = _json.loads(summary_path.read_text(encoding="utf-8"))
            summary_status = _normalize_status(str(summary.get("status", "")))
            out["summary_status"] = summary_status
            if out["terminal_status"] is None and summary_status in {"completed", "failed", "interrupted"}:
                out["terminal_status"] = summary_status
                out["source"] = "run_summary"
        except Exception:
            pass
    return out


async def _resolve_effective_status(
    row: aiosqlite.Row,
    live_run_id: str | None,
    run_root: str,
) -> tuple[str, dict[str, Any]]:
    """Resolve effective status from registry + live-memory + durable runtime evidence."""
    from src.web.shared import _age_seconds as _age_fn

    registry_status = _normalize_status(str(row["status"]))
    diagnostics: dict[str, Any] = {
        "registry_status": registry_status,
        "live_run_id": live_run_id,
        "source": "registry",
    }
    live_run_active = bool(live_run_id and registry_status in {"running", "awaiting_review"})
    if live_run_active and not _running_heartbeat_stale(row):
        diagnostics["source"] = "active_run"
        return registry_status, diagnostics
    if live_run_active:
        diagnostics["live_run_stale"] = True
    evidence = await _collect_terminal_evidence(str(row["db_path"]))
    diagnostics["evidence"] = evidence
    terminal = evidence.get("terminal_status")
    if terminal in {"completed", "failed", "interrupted"} and registry_status in {
        "running",
        "stale",
        "awaiting_review",
    }:
        diagnostics["source"] = str(evidence.get("source") or "runtime")
        diagnostics["override"] = f"{registry_status}->{terminal}"
        if registry_status == "stale":
            _bump_lifecycle_metric("stale_reversals")
        heartbeat_age = _age_fn(row["heartbeat_at"])
        updated_age = _age_fn(row["updated_at"])
        if heartbeat_age is None or heartbeat_age > _STALE_THRESHOLD_SECONDS:
            if updated_age is None or updated_age > _STALE_THRESHOLD_SECONDS:
                _bump_lifecycle_metric("missing_heartbeat_with_terminal_evidence")
        if registry_status != terminal:
            try:
                await _update_registry_status(run_root, str(row["workflow_id"]), terminal)
            except Exception:
                pass
            else:
                _logger.info(
                    "Lifecycle repair: workflow %s status running -> %s (%s)",
                    row["workflow_id"],
                    terminal,
                    evidence.get("source"),
                )
        return terminal, diagnostics
    if registry_status == "running" and not live_run_id:
        if _running_heartbeat_stale(row):
            _bump_lifecycle_metric("stale_detections")
            diagnostics["source"] = "heartbeat_timeout"
            _logger.info(
                "Lifecycle stale classification: workflow=%s heartbeat_at=%s updated_at=%s metrics=%s",
                row["workflow_id"],
                row["heartbeat_at"],
                row["updated_at"],
                _lifecycle_metrics,
            )
            return "stale", diagnostics
    return registry_status, diagnostics


# ---------------------------------------------------------------------------
# Lifecycle loops
# ---------------------------------------------------------------------------


async def _heartbeat_loop(run_root: str, workflow_id: str, interval: int = 60) -> None:
    """Background task: update heartbeat_at every `interval` seconds while a workflow runs."""
    try:
        while True:
            await asyncio.sleep(interval)
            try:
                await _update_registry_heartbeat(run_root, workflow_id)
            except Exception:
                pass
    except asyncio.CancelledError:
        pass


async def _event_flusher_loop(record: _RunRecord, interval: int = 5) -> None:
    """Background task: flush new SSE events to SQLite every `interval` seconds."""
    try:
        while True:
            await asyncio.sleep(interval)
            await _flush_pending_events(record)
    except asyncio.CancelledError:
        pass


# ---------------------------------------------------------------------------
# Run wrappers
# ---------------------------------------------------------------------------


async def _run_wrapper(record: _RunRecord, review_path: str, req: RunRequest) -> None:
    from src.orchestration.context import WebRunContext
    from src.web.orchestration_facade import start_workflow_run

    record.run_root = req.run_root
    heartbeat_task: asyncio.Task[Any] | None = None

    def _on_db_ready(path: str) -> None:
        record.db_path = path
        if record.review_yaml:
            try:
                yaml_dest = pathlib.Path(path).parent / "review.yaml"
                yaml_dest.write_text(record.review_yaml, encoding="utf-8")
            except Exception as exc:
                _logger.error("Failed to copy YAML config snapshot to run directory: %s", exc)

    def _on_workflow_id_ready(workflow_id: str, run_root: str) -> None:
        record.workflow_id = workflow_id
        record.run_root = run_root
        event: dict[str, Any] = {"type": "workflow_id_ready", "workflow_id": workflow_id}
        _append_event(record, event)
        nonlocal heartbeat_task
        if heartbeat_task is None or heartbeat_task.done():
            heartbeat_task = asyncio.create_task(
                _heartbeat_loop(run_root, workflow_id, interval=_web_cfg.heartbeat_interval_seconds)
            )

    ctx = WebRunContext(
        on_db_ready=_on_db_ready,
        on_event=lambda e: _append_event(record, e),
        on_workflow_id_ready=_on_workflow_id_ready,
    )
    flusher_task: asyncio.Task[Any] = asyncio.create_task(
        _event_flusher_loop(record, interval=_web_cfg.event_flush_interval_seconds)
    )
    try:
        outputs = await start_workflow_run(
            review_path=review_path,
            settings_path="config/settings.yaml",
            run_root=req.run_root,
            run_context=ctx,
            parent_db_path=req.parent_db_path,
        )
        record.outputs = outputs if isinstance(outputs, dict) else {}
        record.done = True

        wf_id = str(record.outputs.get("workflow_id", ""))
        if wf_id:
            record.workflow_id = wf_id
            record.db_path = await _resolve_db_path(req.run_root, wf_id)
            if record.db_path and record.review_yaml:
                try:
                    yaml_dest = pathlib.Path(record.db_path).parent / "review.yaml"
                    yaml_dest.write_text(record.review_yaml, encoding="utf-8")
                except Exception as exc:
                    _logger.error("Failed to copy YAML config snapshot to run directory: %s", exc)

        if record.workflow_id and record.run_root:
            terminal_status = _normalize_status(str(record.outputs.get("status", "")))
            if terminal_status == "failed":
                record.error = str(record.outputs.get("error", "Workflow failed"))
                try:
                    await _update_registry_status(record.run_root, record.workflow_id, "failed")
                except Exception as exc:
                    _logger.error("Failed to update registry status to failed: %s", exc)
            else:
                try:
                    await _update_registry_status(record.run_root, record.workflow_id, "completed")
                except Exception as exc:
                    _logger.error("Failed to update registry status to completed: %s", exc)

        _done_evt: dict[str, Any] = {"type": "done", "outputs": record.outputs}
        _append_event(record, _done_evt)
    except asyncio.CancelledError:
        record.done = True
        record.error = "Cancelled"
        _cancelled_evt: dict[str, Any] = {"type": "cancelled"}
        _append_event(record, _cancelled_evt)
        if record.workflow_id and record.run_root:
            try:
                await _update_registry_status(record.run_root, record.workflow_id, "interrupted")
            except Exception as exc:
                _logger.error("Failed to update registry status to interrupted: %s", exc)
    except Exception as exc:
        import traceback

        record.done = True
        record.error = str(exc)
        _tb = traceback.format_exc()
        _logger.exception("Run failed: %s", exc)
        _error_evt: dict[str, Any] = {
            "type": "error",
            "msg": str(exc),
            "traceback": _tb,
        }
        _append_event(record, _error_evt)
        if record.workflow_id and record.run_root:
            try:
                await _update_registry_status(record.run_root, record.workflow_id, "failed")
            except Exception as exc:
                _logger.error("Failed to update registry status to failed: %s", exc)
    finally:
        if heartbeat_task is not None:
            heartbeat_task.cancel()
        flusher_task.cancel()
        try:
            pathlib.Path(review_path).unlink(missing_ok=True)
        except Exception:
            pass
        await _flush_pending_events(record)


async def _resume_wrapper(
    record: _RunRecord,
    workflow_id: str,
    db_path: str,
    from_phase: str | None = None,
    verbose: bool = False,
    debug: bool = False,
) -> None:
    """Async task that resumes an interrupted workflow from its last checkpoint."""
    from src.orchestration.context import WebRunContext
    from src.web.orchestration_facade import resume_workflow_run

    run_root = str(pathlib.Path(db_path).parent.parent.parent.parent)
    record.run_root = run_root
    record.workflow_id = workflow_id

    try:
        await _update_registry_status(run_root, workflow_id, "running")
    except Exception:
        pass

    try:
        record.event_log = await _load_event_log_from_db(db_path)
    except Exception:
        pass

    try:
        from src.db.database import get_db as _get_db
        from src.db.repositories import WorkflowRepository as _WorkflowRepository
        from src.orchestration.resume import PHASE_ORDER as _PHASE_ORDER

        async with _get_db(db_path) as _chk_db:
            _checkpoints = await _WorkflowRepository(_chk_db).get_checkpoints(workflow_id)
        _phases_with_done = {
            e["phase"] for e in record.event_log if isinstance(e, dict) and e.get("type") == "phase_done"
        }
        _insert_index = len(record.event_log)
        for _i, _e in enumerate(record.event_log):
            if isinstance(_e, dict) and _e.get("type") in ("done", "error", "cancelled"):
                _insert_index = _i
                break
        _synthetic_ts = None
        if _insert_index > 0:
            _prev = record.event_log[_insert_index - 1]
            if isinstance(_prev, dict) and "ts" in _prev:
                _synthetic_ts = _prev["ts"]
        if _synthetic_ts is None:
            _synthetic_ts = datetime.datetime.now(tz=datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        _synthetic_events: list[dict[str, Any]] = []
        for _phase in _PHASE_ORDER:
            if _phase in _checkpoints and _phase not in _phases_with_done:
                _synthetic_events.append(
                    {
                        "type": "phase_done",
                        "phase": _phase,
                        "summary": {},
                        "total": None,
                        "completed": None,
                        "synthetic": True,
                        "ts": _synthetic_ts,
                    }
                )
        for _ev in reversed(_synthetic_events):
            record.event_log.insert(_insert_index, _ev)
    except Exception:
        pass

    record.event_log = [
        _e for _e in record.event_log if not (isinstance(_e, dict) and _e.get("type") in ("done", "error", "cancelled"))
    ]

    record._flush_index = len(record.event_log)

    heartbeat_task: asyncio.Task[Any] = asyncio.create_task(
        _heartbeat_loop(run_root, workflow_id, interval=_web_cfg.heartbeat_interval_seconds)
    )
    flusher_task: asyncio.Task[Any] = asyncio.create_task(
        _event_flusher_loop(record, interval=_web_cfg.event_flush_interval_seconds)
    )

    run_dir = pathlib.Path(db_path).parent
    stored_yaml = run_dir / "review.yaml"
    review_path = str(stored_yaml) if stored_yaml.exists() else "config/review.yaml"

    def _on_db_ready(path: str) -> None:
        record.db_path = path

    ctx = WebRunContext(
        on_db_ready=_on_db_ready,
        on_event=lambda e: _append_event(record, e),
        verbose=verbose,
        debug=debug,
    )
    try:
        outputs = await resume_workflow_run(
            workflow_id=workflow_id,
            review_path=review_path,
            settings_path="config/settings.yaml",
            run_root=run_root,
            run_context=ctx,
            from_phase=from_phase,
        )
        record.outputs = outputs if isinstance(outputs, dict) else {}
        record.workflow_id = workflow_id
        record.db_path = db_path
        record.done = True
        if record.outputs.get("status") == "failed":
            err_msg = record.outputs.get("error", "Workflow failed")
            record.error = err_msg
            _gate_err_evt: dict[str, Any] = {"type": "error", "msg": err_msg}
            _append_event(record, _gate_err_evt)
            try:
                await _update_registry_status(run_root, workflow_id, "failed")
            except Exception as exc:
                _logger.error("Failed to update registry status to failed: %s", exc)
        else:
            try:
                await _update_registry_status(run_root, workflow_id, "completed")
            except Exception as exc:
                _logger.error("Failed to update registry status to completed: %s", exc)
        _done_resume_evt: dict[str, Any] = {"type": "done", "outputs": record.outputs}
        _append_event(record, _done_resume_evt)
    except asyncio.CancelledError:
        record.done = True
        record.error = "Cancelled"
        _cancelled_resume_evt: dict[str, Any] = {"type": "cancelled"}
        _append_event(record, _cancelled_resume_evt)
        try:
            await _update_registry_status(run_root, workflow_id, "interrupted")
        except Exception as exc:
            _logger.error("Failed to update registry status to interrupted: %s", exc)
    except Exception as exc:
        import traceback

        _tb = traceback.format_exc()
        _logger.exception("Resume failed: %s", exc)
        _runtime_completed = False
        try:
            async with aiosqlite.connect(db_path) as _db:
                async with _db.execute(
                    "SELECT status FROM workflows WHERE workflow_id = ?",
                    (workflow_id,),
                ) as _cur:
                    _row = await _cur.fetchone()
                    _runtime_completed = bool(_row and str(_row[0]) == "completed")
        except Exception:
            _runtime_completed = False

        if _runtime_completed:
            record.done = True
            record.error = None
            try:
                _summary_path = pathlib.Path(db_path).parent / "run_summary.json"
                if _summary_path.exists():
                    record.outputs = _json.loads(_summary_path.read_text(encoding="utf-8"))
            except Exception:
                pass
            _done_resume_evt2: dict[str, Any] = {"type": "done", "outputs": record.outputs}
            _append_event(record, _done_resume_evt2)
            try:
                await _update_registry_status(run_root, workflow_id, "completed")
            except Exception as exc_reg:
                _logger.error("Failed to update registry status to completed: %s", exc_reg)
        else:
            record.done = True
            record.error = str(exc)
            _error_resume_evt: dict[str, Any] = {
                "type": "error",
                "msg": str(exc),
                "traceback": _tb,
            }
            _append_event(record, _error_resume_evt)
            try:
                await _update_registry_status(run_root, workflow_id, "failed")
            except Exception as exc_reg:
                _logger.error("Failed to update registry status to failed: %s", exc_reg)
    finally:
        heartbeat_task.cancel()
        flusher_task.cancel()
        await _flush_pending_events(record)
