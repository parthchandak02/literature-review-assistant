"""State containers and lifecycle management for the web layer.

Houses mutable process state (active runs, subscribers, allowed roots) and
run lifecycle wrappers so that router modules can import them without creating
circular imports with ``app.py``.
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import pathlib
import time
from collections.abc import Iterator
from typing import Any

import aiosqlite
from fastapi import HTTPException

from src.config.env_context import async_env_override_context
from src.config.loader import load_configs as _load_configs
from src.db.workflow_registry import _open_registry as _open_registry_db
from src.db.workflow_registry import update_heartbeat as _update_registry_heartbeat
from src.db.workflow_registry import update_status as _update_registry_status
from src.web.event_replay import load_replay_events
from src.web.event_store import EventStore
from src.web.lifecycle_coordinator import bind_active_runs
from src.web.lifecycle_reconciler import TERMINAL_EVENT_TO_STATUS, LifecycleReconciler
from src.web.run_resolver import RunResolver
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

_lifecycle_metrics: dict[str, int] = {
    "stale_detections": 0,
    "stale_reversals": 0,
    "missing_heartbeat_with_terminal_evidence": 0,
}

_allowed_roots: set[str] = set()


def _bump_lifecycle_metric(name: str) -> None:
    _lifecycle_metrics[name] = _lifecycle_metrics.get(name, 0) + 1


_TERMINAL_EVENT_TO_STATUS = TERMINAL_EVENT_TO_STATUS

_lifecycle_reconciler = LifecycleReconciler(
    stale_threshold_seconds=_STALE_THRESHOLD_SECONDS,
    stale_grace_seconds=_STALE_GRACE_SECONDS,
    bump_metric=_bump_lifecycle_metric,
)
_run_resolver = RunResolver(
    active_runs=_active_runs,
    lifecycle_reconciler=_lifecycle_reconciler,
    lifecycle_metrics=_lifecycle_metrics,
    anchor_file=__file__,
)
_lifecycle_coordinator = bind_active_runs(
    _active_runs,
    run_resolver=_run_resolver,
    lifecycle_reconciler=_lifecycle_reconciler,
)
_event_store = EventStore()

# ---------------------------------------------------------------------------
# State-dependent helpers
# ---------------------------------------------------------------------------


def _get_db_path(run_id: str) -> str:
    record = _lifecycle_coordinator.get(run_id)
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
    return await _run_resolver.resolve_db_path(identifier, run_root)


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
                from src.db.workflow_registry import run_root_from_db_path

                run_root = run_root_from_db_path(str(db_path))
                roots.add(str(pathlib.Path(run_root).resolve()))
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


async def _persist_event_log(db_path: str, workflow_id: str, events: list[dict[str, Any]]) -> None:
    await _event_store.persist(db_path, workflow_id, events)


async def _notify_new_event(record: _RunRecord) -> None:
    await _event_store.notify(record)


async def _flush_pending_events(record: _RunRecord) -> None:
    await _event_store.flush_pending(record)


def _append_event(record: _RunRecord, event: dict[str, Any]) -> None:
    _event_store.append(record, event)


async def _load_event_log_from_db(db_path: str, workflow_id: str | None = None) -> list[dict[str, Any]]:
    return await load_replay_events(db_path, workflow_id)


# ---------------------------------------------------------------------------
# Terminal evidence collection (used by history lifecycle reconciliation)
# ---------------------------------------------------------------------------


def _running_heartbeat_stale(row: aiosqlite.Row) -> bool:
    return _lifecycle_reconciler.running_heartbeat_stale(row)


async def _collect_terminal_evidence(db_path: str) -> dict[str, Any]:
    return await _lifecycle_reconciler.collect_terminal_evidence(db_path)


async def _resolve_effective_status(
    row: aiosqlite.Row,
    live_run_id: str | None,
    run_root: str,
) -> tuple[str, dict[str, Any]]:
    return await _run_resolver.reconcile_effective_status(
        str(row["workflow_id"]),
        run_root,
        row=row,
        live_run_id=live_run_id,
    )


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
    env_overrides = req.resolved_env_overrides()
    async with async_env_override_context(env_overrides):
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
            from src.web.run_concurrency import release_run_slot

            release_run_slot()


async def _resume_wrapper(
    record: _RunRecord,
    workflow_id: str,
    db_path: str,
    from_phase: str | None = None,
    verbose: bool = False,
    debug: bool = False,
) -> None:
    """Async task that resumes an interrupted workflow from its last checkpoint."""
    from src.db.workflow_registry import run_root_from_db_path
    from src.orchestration.context import WebRunContext
    from src.web.orchestration_facade import resume_workflow_run

    run_root = run_root_from_db_path(db_path)
    record.run_root = run_root
    record.workflow_id = workflow_id

    try:
        await _update_registry_status(run_root, workflow_id, "running")
    except Exception:
        pass

    try:
        record.event_log = await _load_event_log_from_db(db_path, workflow_id)
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
        from src.web.run_concurrency import release_run_slot

        release_run_slot()
