"""FastAPI web backend for the systematic review tool.

Run with:
    uv run uvicorn src.web.app:app --reload --port ${PORT:-8001}

Or via Overmind (dev, runs API + Vite together):
    overmind start -f Procfile.dev

Or via Overmind (production, single process):
    overmind start
"""

from __future__ import annotations

import asyncio
import csv
import datetime
import io
import json as _json
import logging
import os
import pathlib
import shutil
import sqlite3
import tempfile
import time
import uuid
import zipfile
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import aiofiles
import aiosqlite
import pydantic
import yaml
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.config.loader import load_configs as _load_configs
from src.db.source_of_truth import RUN_STATS_PRECEDENCE
from src.db.workflow_registry import _open_registry as _open_registry_db
from src.db.workflow_registry import archive_workflow as _archive_registry_workflow
from src.db.workflow_registry import restore_workflow as _restore_registry_workflow
from src.db.workflow_registry import update_heartbeat as _update_registry_heartbeat
from src.db.workflow_registry import update_notes as _update_registry_notes
from src.db.workflow_registry import update_status as _update_registry_status
from src.export.submission_packager import package_submission
from src.manuscript.readiness import compute_readiness_scorecard
from src.orchestration.context import WebRunContext
from src.orchestration.workflow import run_workflow, run_workflow_resume
from src.search.csv_import import validate_csv_file

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Load web-tier config from settings.yaml at import time so the constants
# below reflect user configuration without requiring a code change.
# Falls back to safe defaults if settings.yaml is missing (e.g. in tests).
# ---------------------------------------------------------------------------
try:
    _web_cfg = _load_configs()[1].web
except Exception:
    from src.models.config import WebConfig as _WebConfig

    _web_cfg = _WebConfig()

# ---------------------------------------------------------------------------
# State: in-process registry of active runs
# ---------------------------------------------------------------------------


class _RunRecord:
    def __init__(self, run_id: str, topic: str) -> None:
        self.run_id = run_id
        self.topic = topic
        self.task: asyncio.Task[Any] | None = None
        self.done = False
        self.error: str | None = None
        self.outputs: dict[str, Any] = {}
        self.db_path: str | None = None  # set by on_db_ready callback when DB is created
        self.workflow_id: str | None = None  # set by on_workflow_id_ready callback early in SearchNode
        self.run_root: str = "runs"  # set immediately from req.run_root in _run_wrapper
        self.created_at: float = time.monotonic()  # for TTL eviction
        # Append-only log of every emitted event for replay on reconnect.
        self.event_log: list[dict[str, Any]] = []
        # Index into event_log up to which events have already been flushed to SQLite.
        # The flusher task advances this so the final flush only writes the tail.
        self._flush_index: int = 0
        self._flush_lock: asyncio.Lock = asyncio.Lock()
        self._event_cond: asyncio.Condition = asyncio.Condition()
        # Original review YAML submitted by the user -- saved to run dir after completion.
        self.review_yaml: str = ""


_active_runs: dict[str, _RunRecord] = {}

# ---------------------------------------------------------------------------
# Notes SSE: global broadcast channel for per-workflow note updates.
# Each connected client gets an asyncio.Queue; PATCH /api/notes/{id} pushes
# to all queues so every open browser tab sees the update in real time.
# ---------------------------------------------------------------------------
_notes_subscribers: set[asyncio.Queue[dict[str, Any] | None]] = set()

# Evict completed run records older than run_ttl_seconds (from settings.yaml web.run_ttl_seconds).
_RUN_TTL_SECONDS = _web_cfg.run_ttl_seconds
_STALE_THRESHOLD_SECONDS = 2 * 60  # 2 minutes
_STALE_GRACE_SECONDS = 2 * 60  # avoid startup/resume races

_TERMINAL_REGISTRY_STATUSES = {"completed", "failed", "interrupted", "stale"}
_TERMINAL_EVENT_TO_STATUS = {
    "done": "completed",
    "error": "failed",
    "cancelled": "interrupted",
}


def _is_missing_table_error(exc: Exception, table_names: set[str]) -> bool:
    """Return True when sqlite reports a missing table from a known set."""
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    text = str(exc).lower()
    if "no such table" not in text:
        return False
    return any(name.lower() in text for name in table_names)

_lifecycle_metrics: dict[str, int] = {
    "stale_detections": 0,
    "stale_reversals": 0,
    "missing_heartbeat_with_terminal_evidence": 0,
}

# ---------------------------------------------------------------------------
# Download security: set of allowed root directories (str of resolved paths).
# Populated at startup and refreshed whenever a new run root is discovered
# (e.g. after attaching a historical run from a different project location).
# ---------------------------------------------------------------------------
_allowed_roots: set[str] = set()


async def _refresh_allowed_roots() -> None:
    """Rebuild the set of allowed download root directories.

    Always includes the current project's runs/ directory.
    Also discovers run_roots recorded in the workflow registry so that runs
    created from a different on-disk project location remain accessible.
    """
    roots: set[str] = {str(pathlib.Path("runs").resolve())}
    registry = pathlib.Path("runs") / "workflows_registry.db"
    if registry.exists():
        try:
            async with _open_registry_db(str(registry)) as db:
                async with db.execute("SELECT db_path FROM workflows_registry") as cur:
                    rows = await cur.fetchall()
            for (db_path,) in rows:
                # db_path layout: <run_root>/YYYY-MM-DD/<slug>/run_<ts>/runtime.db
                # run_root is exactly 4 parent levels above runtime.db.
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


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    await _refresh_allowed_roots()
    # On startup, mark any registry entries still showing "running" as "interrupted".
    # Those workflows cannot be running in a fresh process -- they were orphaned by a
    # crash or SIGKILL during the previous process lifetime.
    try:
        _registry_path = pathlib.Path("runs") / "workflows_registry.db"
        if _registry_path.exists():
            async with _open_registry_db(str(_registry_path)) as _reg_db:
                await _reg_db.execute(
                    "UPDATE workflows_registry SET status='interrupted', updated_at=datetime('now')"
                    " WHERE status='running'"
                )
                await _reg_db.commit()
    except Exception:
        pass
    await _repair_registry_statuses_from_runtime("runs")
    eviction = asyncio.create_task(_eviction_loop())
    yield
    # Graceful shutdown: cancel active tasks and mark workflows as 'interrupted'.
    eviction.cancel()
    for record in list(_active_runs.values()):
        if not record.done and record.task and not record.task.done():
            record.task.cancel()
            if record.db_path and record.workflow_id:
                try:
                    async with aiosqlite.connect(record.db_path) as _db:
                        await _db.execute(
                            "UPDATE workflows SET status='interrupted' WHERE workflow_id=?",
                            (record.workflow_id,),
                        )
                        await _db.commit()
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="LitReview API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class RunRequest(BaseModel):
    review_yaml: str
    gemini_api_key: str
    openalex_api_key: str | None = None
    ieee_api_key: str | None = None
    pubmed_email: str | None = None
    pubmed_api_key: str | None = None
    perplexity_api_key: str | None = None
    semantic_scholar_api_key: str | None = None
    crossref_email: str | None = None
    wos_api_key: str | None = None
    scopus_api_key: str | None = None
    run_root: str = "runs"
    parent_db_path: str | None = None


class RunResponse(BaseModel):
    run_id: str
    topic: str


class RunInfo(BaseModel):
    run_id: str
    topic: str
    done: bool
    error: str | None


class HistoryEntry(BaseModel):
    workflow_id: str
    topic: str
    status: str
    db_path: str
    created_at: str
    updated_at: str | None = None
    papers_found: int | None = None
    papers_included: int | None = None
    total_cost: float | None = None
    artifacts_count: int | None = None
    stats_ok: bool | None = None
    stats_error: str | None = None
    # Populated when a workflow is actively running in-process.
    # The frontend uses this to connect a live SSE stream instead of replaying DB events.
    live_run_id: str | None = None
    # User-authored annotation stored in the central registry.
    notes: str | None = None
    # Sidebar archive state. Archive does not affect lifecycle status.
    is_archived: bool = False
    archived_at: str | None = None


class AttachRequest(BaseModel):
    workflow_id: str
    topic: str
    db_path: str
    status: str = "completed"


# ---------------------------------------------------------------------------
# Helper: inject API keys
# ---------------------------------------------------------------------------


def _inject_env(req: RunRequest) -> None:
    # Only overwrite GEMINI_API_KEY when the caller actually provides a value;
    # fall back to whatever load_dotenv() already set from .env.
    if req.gemini_api_key:
        os.environ["GEMINI_API_KEY"] = req.gemini_api_key
    if req.openalex_api_key:
        os.environ["OPENALEX_API_KEY"] = req.openalex_api_key
    if req.ieee_api_key:
        os.environ["IEEE_API_KEY"] = req.ieee_api_key
    if req.pubmed_email:
        os.environ["PUBMED_EMAIL"] = req.pubmed_email
        os.environ["NCBI_EMAIL"] = req.pubmed_email
    if req.pubmed_api_key:
        os.environ["PUBMED_API_KEY"] = req.pubmed_api_key
    if req.perplexity_api_key:
        os.environ["PERPLEXITY_SEARCH_API_KEY"] = req.perplexity_api_key
    if req.semantic_scholar_api_key:
        os.environ["SEMANTIC_SCHOLAR_API_KEY"] = req.semantic_scholar_api_key
    if req.crossref_email:
        os.environ["CROSSREF_EMAIL"] = req.crossref_email
    if req.wos_api_key:
        os.environ["WOS_API_KEY"] = req.wos_api_key
    if req.scopus_api_key:
        os.environ["SCOPUS_API_KEY"] = req.scopus_api_key


def _extract_topic(review_yaml: str) -> str:
    try:
        data = yaml.safe_load(review_yaml)
        return str(data.get("research_question", "Untitled review"))
    except Exception:
        return "Untitled review"


def _validate_csv_upload(csv_file: UploadFile, content: bytes) -> None:
    """Validate filename and payload basics before parsing."""
    filename = (csv_file.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="Uploaded CSV file must include a filename.")
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported for sheet upload.")
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded CSV file is empty.")


def _normalize_path(value: str) -> str:
    return str(pathlib.Path(value).expanduser().resolve(strict=False))


def _merge_supplementary_csv_paths(
    existing_paths: list[str],
    incoming_paths: list[str],
    *,
    run_root: str | None = None,
    replace_staged_existing: bool = False,
) -> list[str]:
    """Merge supplementary CSV paths with stable dedup semantics.

    When a user uploads a new supplementary CSV via the web endpoint, the request
    YAML may already contain older staged supplementary paths from prior runs.
    If replace_staged_existing is true, those stale staged paths are removed so
    each run uses only the newly uploaded staged file plus any user-managed paths.
    """

    staging_root: str | None = None
    if replace_staged_existing and run_root:
        staging_root = _normalize_path(str(pathlib.Path(run_root) / "staging"))

    merged: list[str] = []
    seen: set[str] = set()

    for raw in existing_paths:
        normalized = _normalize_path(str(raw))
        if staging_root and normalized.startswith(staging_root + os.sep):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        merged.append(normalized)

    for raw in incoming_paths:
        normalized = _normalize_path(str(raw))
        if normalized in seen:
            continue
        seen.add(normalized)
        merged.append(normalized)

    return merged


def _inject_csv_paths_into_yaml(
    review_yaml: str,
    *,
    masterlist_csv_path: str | None = None,
    supplementary_csv_paths: list[str] | None = None,
    run_root: str | None = None,
    replace_staged_supplementary_paths: bool = False,
) -> str:
    """Inject CSV paths into review YAML, preserving existing config values."""
    try:
        config_data = yaml.safe_load(review_yaml) or {}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid review YAML: {exc}") from exc

    if masterlist_csv_path is not None:
        config_data["masterlist_csv_path"] = masterlist_csv_path

    if supplementary_csv_paths is not None:
        existing = config_data.get("supplementary_csv_paths") or []
        if not isinstance(existing, list):
            raise HTTPException(status_code=400, detail="supplementary_csv_paths in YAML must be a list.")
        config_data["supplementary_csv_paths"] = _merge_supplementary_csv_paths(
            [str(p) for p in existing],
            [str(p) for p in supplementary_csv_paths],
            run_root=run_root,
            replace_staged_existing=replace_staged_supplementary_paths,
        )

    return yaml.dump(config_data, default_flow_style=False, allow_unicode=True)


async def _resolve_db_path(run_root: str, workflow_id: str) -> str | None:
    """Look up db_path in the central workflows_registry.db."""
    registry = pathlib.Path(run_root) / "workflows_registry.db"
    if not registry.exists():
        return None
    try:
        async with _open_registry_db(str(registry)) as db:
            async with db.execute(
                "SELECT db_path FROM workflows_registry WHERE workflow_id = ?",
                (workflow_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return str(row[0]) if row else None
    except Exception:
        return None


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

    # Persist transition-critical events immediately to reduce loss window on abrupt exits.
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


async def _ensure_runtime_db_migrated(db_path: str) -> None:
    """Run runtime.db migrations once before historical read endpoints use it."""
    try:
        from src.db.database import get_db as _get_db
        from src.db.repositories import WorkflowRepository as _WorkflowRepository

        async with _get_db(db_path) as _db:
            # Best-effort backfill: legacy runs with section_drafts but no
            # DB-first manuscript rows are upgraded on first attach/read.
            try:
                _repo = _WorkflowRepository(_db)
                async with _db.execute("SELECT workflow_id FROM workflows ORDER BY created_at DESC LIMIT 1") as _cur:
                    _row = await _cur.fetchone()
                if _row and _row[0]:
                    _wid = str(_row[0])
                    await _repo.backfill_manuscript_sections_from_drafts(_wid)
                    _legacy_md = pathlib.Path(db_path).parent / "doc_manuscript.md"
                    if _legacy_md.exists():
                        try:
                            parity = await _repo.validate_manuscript_md_parity(
                                _wid, _legacy_md.read_text(encoding="utf-8")
                            )
                            if parity.get("has_assembly") and not (
                                parity.get("citation_set_match") and parity.get("section_count_match")
                            ):
                                _logger.warning(
                                    "runtime.db manuscript parity warning for %s: %s",
                                    _wid,
                                    parity,
                                )
                        except Exception as _parity_exc:
                            _logger.debug("runtime.db manuscript parity check skipped: %s", _parity_exc)
            except Exception as _bf_exc:
                _logger.debug("runtime.db manuscript backfill skipped: %s", _bf_exc)
    except Exception as exc:
        # Historical runs may predate newer schema contracts. Keep attach/replay
        # available instead of hard-failing, and let endpoint-level queries
        # degrade gracefully if a specific table/column is truly unavailable.
        _logger.warning("Historical runtime.db migration skipped for %s: %s", db_path, exc)


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
    """Background task: flush new SSE events to SQLite every `interval` seconds.

    Advances record._flush_index so the final flush in the wrapper's finally block
    only writes the tail of events not yet persisted, preventing duplicates.
    """
    try:
        while True:
            await asyncio.sleep(interval)
            await _flush_pending_events(record)
    except asyncio.CancelledError:
        pass


async def _run_wrapper(record: _RunRecord, review_path: str, req: RunRequest) -> None:
    record.run_root = req.run_root
    heartbeat_task: asyncio.Task[Any] | None = None

    def _on_db_ready(path: str) -> None:
        record.db_path = path
        # Save review.yaml immediately so Config tab shows it while run is active.
        if record.review_yaml:
            try:
                yaml_dest = pathlib.Path(path).parent / "review.yaml"
                yaml_dest.write_text(record.review_yaml, encoding="utf-8")
            except Exception:
                pass

    def _on_workflow_id_ready(workflow_id: str, run_root: str) -> None:
        record.workflow_id = workflow_id
        record.run_root = run_root
        # Emit early so the frontend can deduplicate the sidebar before the run completes.
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
    # Flusher starts immediately; no-ops until db_path and workflow_id are set.
    flusher_task: asyncio.Task[Any] = asyncio.create_task(
        _event_flusher_loop(record, interval=_web_cfg.event_flush_interval_seconds)
    )
    try:
        outputs = await run_workflow(
            review_path=review_path,
            settings_path="config/settings.yaml",
            run_root=req.run_root,
            run_context=ctx,
            fresh=True,
            parent_db_path=req.parent_db_path,
        )
        record.outputs = outputs if isinstance(outputs, dict) else {}
        record.done = True

        # Resolve db_path for database explorer
        wf_id = str(record.outputs.get("workflow_id", ""))
        if wf_id:
            record.workflow_id = wf_id
            record.db_path = await _resolve_db_path(req.run_root, wf_id)
            # Save the original review YAML alongside runtime.db so it can be
            # retrieved later via GET /api/history/{workflow_id}/config.
            if record.db_path and record.review_yaml:
                try:
                    yaml_dest = pathlib.Path(record.db_path).parent / "review.yaml"
                    yaml_dest.write_text(record.review_yaml, encoding="utf-8")
                except Exception:
                    pass

        # Ensure registry terminal status is durable even if orchestration status
        # updates were skipped by an earlier exception path.
        if record.workflow_id and record.run_root:
            terminal_status = _normalize_status(str(record.outputs.get("status", "")))
            if terminal_status == "failed":
                record.error = str(record.outputs.get("error", "Workflow failed"))
                try:
                    await _update_registry_status(record.run_root, record.workflow_id, "failed")
                except Exception:
                    pass
            else:
                try:
                    await _update_registry_status(record.run_root, record.workflow_id, "completed")
                except Exception:
                    pass

        # Append "done" to event_log so final flush persists it (avoids Search stuck
        # as "running" when event_log is replayed for historical view).
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
            except Exception:
                pass
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
            except Exception:
                pass
    finally:
        if heartbeat_task is not None:
            heartbeat_task.cancel()
        flusher_task.cancel()
        try:
            pathlib.Path(review_path).unlink(missing_ok=True)
        except Exception:
            pass
        # Final flush: persist any events not yet written by the flusher loop,
        # including the terminal error/cancelled event appended above.
        await _flush_pending_events(record)


# ---------------------------------------------------------------------------
# Core endpoints
# ---------------------------------------------------------------------------


@app.post("/api/run", response_model=RunResponse)
async def start_run(req: RunRequest) -> RunResponse:
    _inject_env(req)
    topic = _extract_topic(req.review_yaml)
    run_id = str(uuid.uuid4())[:8]

    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        prefix=f"review_{run_id}_",
        delete=False,
    )
    tmp.write(req.review_yaml)
    tmp.flush()
    tmp.close()

    record = _RunRecord(run_id=run_id, topic=topic)
    record.review_yaml = req.review_yaml
    _active_runs[run_id] = record

    task = asyncio.create_task(_run_wrapper(record, tmp.name, req))
    record.task = task

    return RunResponse(run_id=run_id, topic=topic)


@app.post("/api/run-with-masterlist", response_model=RunResponse)
async def start_run_with_masterlist(
    csv_file: UploadFile = File(...),
    review_yaml: str = Form(...),
    gemini_api_key: str = Form(...),
    openalex_api_key: str | None = Form(default=None),
    ieee_api_key: str | None = Form(default=None),
    pubmed_email: str | None = Form(default=None),
    pubmed_api_key: str | None = Form(default=None),
    perplexity_api_key: str | None = Form(default=None),
    semantic_scholar_api_key: str | None = Form(default=None),
    crossref_email: str | None = Form(default=None),
    wos_api_key: str | None = Form(default=None),
    scopus_api_key: str | None = Form(default=None),
    run_root: str = Form(default="runs"),
) -> RunResponse:
    """Start a review run using a pre-assembled master list CSV instead of running connectors.

    The CSV is saved to a staging directory and its absolute path is injected into the
    review YAML as ``masterlist_csv_path``. SearchNode detects this field and loads
    papers from the file instead of querying databases. Every downstream phase
    (screening, extraction, synthesis, writing) runs identically to a normal run.
    """
    # Save the uploaded CSV to a stable staging path so SearchNode can read it.
    run_id = str(uuid.uuid4())[:8]
    staging_dir = pathlib.Path(run_root) / "staging" / run_id
    staging_dir.mkdir(parents=True, exist_ok=True)
    csv_path = staging_dir / "masterlist.csv"

    content = await csv_file.read()
    _validate_csv_upload(csv_file, content)
    csv_path.write_bytes(content)

    # Parse-validate before workflow launch so malformed files fail fast.
    try:
        validate_csv_file(str(csv_path.resolve()))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid master list CSV: {exc}") from exc

    modified_yaml = _inject_csv_paths_into_yaml(
        review_yaml,
        masterlist_csv_path=str(csv_path.resolve()),
    )

    # Build a RunRequest so _inject_env and _run_wrapper can be reused unchanged.
    req = RunRequest(
        review_yaml=modified_yaml,
        gemini_api_key=gemini_api_key,
        openalex_api_key=openalex_api_key,
        ieee_api_key=ieee_api_key,
        pubmed_email=pubmed_email,
        pubmed_api_key=pubmed_api_key,
        perplexity_api_key=perplexity_api_key,
        semantic_scholar_api_key=semantic_scholar_api_key,
        crossref_email=crossref_email,
        wos_api_key=wos_api_key,
        scopus_api_key=scopus_api_key,
        run_root=run_root,
    )
    _inject_env(req)

    topic = _extract_topic(modified_yaml)

    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        prefix=f"review_{run_id}_",
        delete=False,
    )
    tmp.write(modified_yaml)
    tmp.flush()
    tmp.close()

    record = _RunRecord(run_id=run_id, topic=topic)
    record.review_yaml = modified_yaml
    _active_runs[run_id] = record

    task = asyncio.create_task(_run_wrapper(record, tmp.name, req))
    record.task = task

    return RunResponse(run_id=run_id, topic=topic)


@app.post("/api/run-with-supplementary-csv", response_model=RunResponse)
async def start_run_with_supplementary_csv(
    csv_file: UploadFile = File(...),
    review_yaml: str = Form(...),
    gemini_api_key: str = Form(...),
    openalex_api_key: str | None = Form(default=None),
    ieee_api_key: str | None = Form(default=None),
    pubmed_email: str | None = Form(default=None),
    pubmed_api_key: str | None = Form(default=None),
    perplexity_api_key: str | None = Form(default=None),
    semantic_scholar_api_key: str | None = Form(default=None),
    crossref_email: str | None = Form(default=None),
    wos_api_key: str | None = Form(default=None),
    scopus_api_key: str | None = Form(default=None),
    run_root: str = Form(default="runs"),
) -> RunResponse:
    """Start a review run using connectors plus one supplementary CSV import."""
    run_id = str(uuid.uuid4())[:8]
    staging_dir = pathlib.Path(run_root) / "staging" / run_id
    staging_dir.mkdir(parents=True, exist_ok=True)
    csv_path = staging_dir / "supplementary.csv"

    content = await csv_file.read()
    _validate_csv_upload(csv_file, content)
    csv_path.write_bytes(content)

    try:
        validate_csv_file(str(csv_path.resolve()))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid supplementary CSV: {exc}") from exc

    modified_yaml = _inject_csv_paths_into_yaml(
        review_yaml,
        supplementary_csv_paths=[str(csv_path.resolve())],
        run_root=run_root,
        replace_staged_supplementary_paths=True,
    )

    req = RunRequest(
        review_yaml=modified_yaml,
        gemini_api_key=gemini_api_key,
        openalex_api_key=openalex_api_key,
        ieee_api_key=ieee_api_key,
        pubmed_email=pubmed_email,
        pubmed_api_key=pubmed_api_key,
        perplexity_api_key=perplexity_api_key,
        semantic_scholar_api_key=semantic_scholar_api_key,
        crossref_email=crossref_email,
        wos_api_key=wos_api_key,
        scopus_api_key=scopus_api_key,
        run_root=run_root,
    )
    _inject_env(req)

    topic = _extract_topic(modified_yaml)

    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        prefix=f"review_{run_id}_",
        delete=False,
    )
    tmp.write(modified_yaml)
    tmp.flush()
    tmp.close()

    record = _RunRecord(run_id=run_id, topic=topic)
    record.review_yaml = modified_yaml
    _active_runs[run_id] = record

    task = asyncio.create_task(_run_wrapper(record, tmp.name, req))
    record.task = task

    return RunResponse(run_id=run_id, topic=topic)


@app.get("/api/stream/{run_id}")
async def stream_run(run_id: str, request: Request) -> EventSourceResponse:
    record = _active_runs.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found")

    # If the client sends Last-Event-ID, only replay events after that index.
    # This avoids re-sending events the client already received on reconnect.
    last_event_id_header = request.headers.get("last-event-id", "")
    resume_from: int = 0
    if last_event_id_header:
        try:
            resume_from = int(last_event_id_header) + 1
        except ValueError:
            resume_from = 0

    async def _generator() -> AsyncGenerator[dict[str, Any], None]:
        replay_index = max(0, resume_from)
        # Replay buffered events first.
        while replay_index < len(record.event_log):
            yield {"id": str(replay_index), "data": _json_safe(record.event_log[replay_index])}
            replay_index += 1

        while True:
            # Emit newly appended events for this subscriber.
            while replay_index < len(record.event_log):
                event = record.event_log[replay_index]
                yield {"id": str(replay_index), "data": _json_safe(event)}
                replay_index += 1
                if event.get("type") in ("done", "error", "cancelled"):
                    return

            if record.done:
                return

            try:
                async with record._event_cond:
                    await asyncio.wait_for(record._event_cond.wait(), timeout=15.0)
            except TimeoutError:
                yield {"event": "heartbeat", "data": "{}"}

    return EventSourceResponse(_generator())


@app.post("/api/cancel/{run_id}")
async def cancel_run(run_id: str) -> dict[str, str]:
    record = _active_runs.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if record.task and not record.task.done():
        record.task.cancel()
    return {"status": "cancelled"}


@app.get("/api/runs")
async def list_runs() -> list[RunInfo]:
    return [RunInfo(run_id=r.run_id, topic=r.topic, done=r.done, error=r.error) for r in _active_runs.values()]


@app.get("/api/results/{run_id}")
async def get_results(run_id: str) -> dict[str, Any]:
    record = _active_runs.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if not record.done:
        raise HTTPException(status_code=409, detail="Run not complete")
    return {"run_id": run_id, "outputs": record.outputs}


@app.get("/api/download")
async def download_file(path: str) -> FileResponse:
    resolved = pathlib.Path(path).resolve()
    resolved_str = str(resolved)
    if not any(resolved_str.startswith(root) for root in _allowed_roots):
        raise HTTPException(status_code=403, detail="Access denied")
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=resolved_str, filename=resolved.name)


@app.get("/api/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config/review")
async def get_review_config() -> dict[str, str]:
    try:
        content = pathlib.Path("config/review.yaml").read_text()
    except Exception:
        content = ""
    return {"content": content}


@app.get("/api/config/env-keys")
async def get_env_keys() -> dict[str, str]:
    """Return API keys that are already set in the server environment (from .env).

    Empty string for any key that is not set.  This lets the frontend pre-fill
    the API-key form without the user having to retype values that are already
    configured on the server.
    """
    return {
        "gemini": os.environ.get("GEMINI_API_KEY", ""),
        "openalex": os.environ.get("OPENALEX_API_KEY", ""),
        "ieee": os.environ.get("IEEE_API_KEY", ""),
        "pubmedEmail": os.environ.get("PUBMED_EMAIL", "") or os.environ.get("NCBI_EMAIL", ""),
        "pubmedApiKey": os.environ.get("PUBMED_API_KEY", ""),
        "perplexity": os.environ.get("PERPLEXITY_SEARCH_API_KEY", ""),
        "semanticScholar": os.environ.get("SEMANTIC_SCHOLAR_API_KEY", ""),
        "crossrefEmail": os.environ.get("CROSSREF_EMAIL", ""),
        "wos": os.environ.get("WOS_API_KEY", ""),
        "scopus": os.environ.get("SCOPUS_API_KEY", ""),
    }


class _GenerateConfigRequest(BaseModel):
    research_question: str
    gemini_api_key: str = ""


@app.post("/api/config/generate")
async def generate_config(req: _GenerateConfigRequest) -> dict[str, str]:
    """Generate a complete review config YAML from a plain-English research question.

    Uses Gemini flash with native structured output to produce PICO, keywords,
    inclusion/exclusion criteria, domain, and scope. Structural fields
    (date range, databases, sections) are set to safe defaults.
    """
    from src.web.config_generator import generate_config_yaml

    if not req.research_question.strip():
        raise HTTPException(status_code=422, detail="research_question must not be empty")
    # Set the API key in the environment so PydanticAI can find it.
    # Falls back to whatever is already in the environment (e.g. set via .env).
    if req.gemini_api_key.strip():
        os.environ["GEMINI_API_KEY"] = req.gemini_api_key.strip()
    if not os.environ.get("GEMINI_API_KEY"):
        raise HTTPException(
            status_code=422, detail="Gemini API key is required to generate a config. Add it in the API Keys section."
        )
    try:
        yaml_content = await generate_config_yaml(req.research_question)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"yaml": yaml_content}


@app.post("/api/config/generate/stream")
async def generate_config_stream(req: _GenerateConfigRequest) -> StreamingResponse:
    """SSE streaming version of /api/config/generate.

    Emits progress events as each stage completes, then a final 'done' event
    containing the generated YAML. Events are JSON-encoded SSE data lines.

    Progress steps: start -> web_research -> web_research_done -> structuring -> finalizing -> done
    Error: {"type": "error", "detail": "..."}
    Done:  {"type": "done", "yaml": "...", "quality": {...}}
    """
    from src.web.config_generator import evaluate_config_quality_yaml, generate_config_yaml

    if not req.research_question.strip():
        raise HTTPException(status_code=422, detail="research_question must not be empty")
    if req.gemini_api_key.strip():
        os.environ["GEMINI_API_KEY"] = req.gemini_api_key.strip()
    if not os.environ.get("GEMINI_API_KEY"):
        raise HTTPException(
            status_code=422, detail="Gemini API key is required to generate a config. Add it in the API Keys section."
        )

    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    def progress_cb(progress: dict[str, Any]) -> None:
        step = str(progress.get("step", "unknown"))
        payload: dict[str, Any] = {"type": "progress", "step": step}
        for key, value in progress.items():
            if key != "step":
                payload[key] = value
        queue.put_nowait(payload)

    async def run_generation() -> None:
        try:
            yaml_content = await generate_config_yaml(req.research_question, progress_cb=progress_cb)
            quality = evaluate_config_quality_yaml(yaml_content)
            queue.put_nowait({"type": "done", "yaml": yaml_content, "quality": quality})
        except RuntimeError as exc:
            queue.put_nowait({"type": "error", "detail": str(exc)})
        except Exception as exc:
            queue.put_nowait({"type": "error", "detail": f"Unexpected error: {exc}"})
        finally:
            queue.put_nowait(None)

    async def event_stream() -> AsyncGenerator[str, None]:
        task = asyncio.create_task(run_generation())
        yield f"data: {_json.dumps({'type': 'progress', 'step': 'start'})}\n\n"
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=180.0)
                except TimeoutError:
                    yield f"data: {_json.dumps({'type': 'error', 'detail': 'Generation timed out after 3 minutes'})}\n\n"
                    break
                if msg is None:
                    break
                yield f"data: {_json.dumps(msg)}\n\n"
        finally:
            task.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Run history endpoints (reads workflows_registry.db from run_root)
# ---------------------------------------------------------------------------


async def _fetch_run_stats(db_path: str) -> dict[str, Any]:
    """Open a run's runtime.db and return lightweight aggregate stats.

    Uses WAL mode for safe concurrent reads (no exclusive lock needed).
    On failure returns ok=false with diagnostics instead of an empty dict.
    Also reads the sibling run_summary.json to count generated artifacts.
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            papers_found = (await (await db.execute("SELECT COUNT(*) FROM papers")).fetchone())[0]

            _workflow_row = await (
                await db.execute("SELECT workflow_id FROM workflows ORDER BY rowid DESC LIMIT 1")
            ).fetchone()
            _workflow_id = str(_workflow_row[0]) if (_workflow_row and _workflow_row[0]) else ""

            # Canonical source order is defined in src/db/source_of_truth.py:
            # 1) study_cohort_membership included_primary (canonical)
            # 2) dual_screening_results fulltext include/uncertain (fallback)
            # 3) event_log phase_3_screening summary.included (historical fallback)
            # 4) extraction_records count (legacy fallback)
            included_from_cohort = await (
                await db.execute(
                    """
                    SELECT COUNT(DISTINCT scm.paper_id)
                    FROM study_cohort_membership scm
                    WHERE scm.workflow_id = ?
                      AND scm.synthesis_eligibility = 'included_primary'
                    """
                    ,
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
                    fallback_row = await (
                        await db.execute(
                            """
                            SELECT COUNT(*) FROM extraction_records
                            """
                        )
                    ).fetchone()
                    papers_included = int(fallback_row[0]) if fallback_row else 0
                    included_source = "extraction_records"

            # Guardrail: detect divergence between canonical cohort, durable screening table, and event summary.
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
                    int(included_from_cohort[0]) if (included_from_cohort and included_from_cohort[0] is not None) else 0
                )
                _dual_inc = (
                    int(included_from_dual[0]) if (included_from_dual and included_from_dual[0] is not None) else 0
                )
                # Event-log and dual-screening values can legitimately differ from the
                # canonical cohort after downstream primary-study filtering. Emit warnings
                # only when we are actively using those fallback sources.
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


def _bump_lifecycle_metric(name: str) -> None:
    _lifecycle_metrics[name] = _lifecycle_metrics.get(name, 0) + 1


def _normalize_status(value: str | None) -> str:
    s = (value or "").strip().lower()
    if s in ("done", "completed", "success"):
        return "completed"
    if s in ("failed", "error"):
        return "failed"
    if s in ("cancelled", "interrupted"):
        return "interrupted"
    return s


def _parse_sqlite_ts(value: Any) -> datetime.datetime | None:
    if value is None:
        return None
    try:
        ts = datetime.datetime.fromisoformat(str(value))
    except Exception:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=datetime.UTC)
    return ts


def _age_seconds(value: Any) -> float | None:
    ts = _parse_sqlite_ts(value)
    if ts is None:
        return None
    return (datetime.datetime.now(datetime.UTC) - ts).total_seconds()


def _running_heartbeat_stale(row: aiosqlite.Row) -> bool:
    """Return True if a running workflow heartbeat is stale with grace windows.

    Falls back to updated_at if heartbeat_at is NULL (runs that pre-date the heartbeat column).
    """
    heartbeat_age = _age_seconds(row["heartbeat_at"])
    updated_age = _age_seconds(row["updated_at"])
    created_age = _age_seconds(row["created_at"])
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
    registry_status = _normalize_status(str(row["status"]))
    diagnostics: dict[str, Any] = {
        "registry_status": registry_status,
        "live_run_id": live_run_id,
        "source": "registry",
    }
    if live_run_id and registry_status in {"running", "awaiting_review"}:
        diagnostics["source"] = "active_run"
        return registry_status, diagnostics
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
        heartbeat_age = _age_seconds(row["heartbeat_at"])
        updated_age = _age_seconds(row["updated_at"])
        if heartbeat_age is None or heartbeat_age > _STALE_THRESHOLD_SECONDS:
            if updated_age is None or updated_age > _STALE_THRESHOLD_SECONDS:
                _bump_lifecycle_metric("missing_heartbeat_with_terminal_evidence")
        if registry_status == "running":
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


@app.get("/api/history")
async def list_history(response: Response, run_root: str = "runs") -> list[HistoryEntry]:
    """Return all past runs from the central workflows_registry.db, enriched
    with per-run aggregate stats fetched in parallel from each runtime.db."""
    registry = pathlib.Path(run_root) / "workflows_registry.db"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    if not registry.exists():
        return []
    try:
        async with _open_registry_db(str(registry)) as db:
            db.row_factory = aiosqlite.Row
            # Backward-safe archive migration for registries created before
            # archive columns existed.
            try:
                await db.execute(
                    "ALTER TABLE workflows_registry ADD COLUMN is_archived INTEGER NOT NULL DEFAULT 0"
                )
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE workflows_registry ADD COLUMN archived_at TEXT")
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
                          archived_at
                   FROM workflows_registry
                   ORDER BY created_at DESC"""
            ) as cur:
                rows = await cur.fetchall()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not rows:
        return []

    # Fetch per-run stats from each runtime.db in parallel.
    # return_exceptions=True means one corrupt/slow DB never fails the rest.
    stat_results = await asyncio.gather(
        *[_fetch_run_stats(str(r["db_path"])) for r in rows],
        return_exceptions=True,
    )

    # Build a map from workflow_id -> run_id for all in-process active (not done) runs.
    # This replaces the old "exclude active runs" logic: we now include them but tag
    # them with live_run_id so the frontend can connect SSE instead of replaying DB events.
    active_run_id_by_workflow: dict[str, str] = {
        r.workflow_id: r.run_id for r in _active_runs.values() if r.workflow_id and not r.done
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
            )
        )
    return enriched


# ---------------------------------------------------------------------------
# Notes endpoints
# ---------------------------------------------------------------------------


class _NoteBody(BaseModel):
    note: str
    run_root: str = "runs"


@app.patch("/api/notes/{workflow_id}")
async def save_note(workflow_id: str, body: _NoteBody) -> dict[str, bool]:
    """Persist a user note for a workflow and broadcast it to all connected note-stream clients."""
    await _update_registry_notes(body.run_root, workflow_id, body.note)
    event: dict[str, Any] = {
        "workflow_id": workflow_id,
        "note": body.note,
        "ts": __import__("datetime").datetime.utcnow().isoformat(),
    }
    dead: set[asyncio.Queue[dict[str, Any] | None]] = set()
    for q in list(_notes_subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            dead.add(q)
    _notes_subscribers.difference_update(dead)
    return {"ok": True}


@app.get("/api/notes/stream")
async def notes_stream(request: Request) -> EventSourceResponse:
    """SSE stream that broadcasts note-save events to all connected clients.

    Each browser tab that opens this stream will receive an event whenever any
    client saves a note via PATCH /api/notes/{workflow_id}.  The client uses
    this to update its local notes map and trigger the flash animation.
    """
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
                    # Send a keep-alive comment so the connection stays open.
                    yield {"comment": "ka"}
                    continue
                if event is None:
                    break
                yield {"data": __import__("json").dumps(event)}
        finally:
            _notes_subscribers.discard(queue)

    return EventSourceResponse(_generator())


@app.get("/api/history/{workflow_id}/config")
async def get_run_config(workflow_id: str, run_root: str = "runs") -> dict[str, str]:
    """Return the original review.yaml for a past run.

    The file is written to the run directory after the workflow completes
    (for web-started runs) or copied there by the CLI backfill step.
    Returns 404 if the file does not exist (e.g. old CLI runs before this feature).
    """
    # First try to locate via the registry to get the exact db_path
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
        # Fallback: check well-known path pattern
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


class ResumeRequest(BaseModel):
    workflow_id: str
    db_path: str
    topic: str
    from_phase: str | None = None  # e.g. "phase_3_screening" to resume from that phase
    verbose: bool = False
    debug: bool = False


async def _resume_wrapper(
    record: _RunRecord,
    workflow_id: str,
    db_path: str,
    from_phase: str | None = None,
    verbose: bool = False,
    debug: bool = False,
) -> None:
    """Async task that resumes an interrupted workflow from its last checkpoint."""
    run_root = str(pathlib.Path(db_path).parent.parent.parent.parent)
    record.run_root = run_root
    record.workflow_id = workflow_id

    # Mark workflow as running again in the registry so the sidebar reflects the
    # active state immediately (status may be "interrupted"/"failed" before this).
    try:
        await _update_registry_status(run_root, workflow_id, "running")
    except Exception:
        pass

    # Pre-load historical events so SSE replay includes pre-resume phases
    # (mirrors what attach_history does for completed runs).
    try:
        record.event_log = await _load_event_log_from_db(db_path)
    except Exception:
        pass

    # Inject synthetic phase_done events for phases that completed in a prior
    # run segment but whose phase_done event was never flushed to SQLite (e.g.
    # a server crash between checkpoint write and phase_done emit).  Without
    # these, the UI phase timeline shows those phases as still "running".
    # Insert before the first terminal event (done/error/cancelled) so they
    # appear in correct chronological order in the Activity log.
    try:
        from src.db.database import get_db as _get_db
        from src.db.repositories import WorkflowRepository as _WorkflowRepository
        from src.orchestration.resume import PHASE_ORDER as _PHASE_ORDER

        async with _get_db(db_path) as _chk_db:
            _checkpoints = await _WorkflowRepository(_chk_db).get_checkpoints(workflow_id)
        _phases_with_done = {
            e["phase"] for e in record.event_log if isinstance(e, dict) and e.get("type") == "phase_done"
        }
        # Find index of first terminal event to insert synthetic events before it.
        _insert_index = len(record.event_log)
        for _i, _e in enumerate(record.event_log):
            if isinstance(_e, dict) and _e.get("type") in ("done", "error", "cancelled"):
                _insert_index = _i
                break
        # Use ts from last event before terminal for proper display ordering.
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

    # Strip any terminal events (done/error/cancelled) that were written by
    # the previous run segment.  Keeping them in the in-memory replay buffer
    # causes useSSEStream on the frontend to think the run is already finished
    # when it prefetches events via fetchRunEvents -- it scans the list in
    # reverse for the last terminal, finds the old one (because new events
    # are non-terminal and appended after it), and returns early without
    # opening the SSE stream.  The old terminal remains safely in SQLite for
    # historical replay after a page refresh; this resumed run will append its
    # own fresh terminal event when it actually completes.
    record.event_log = [
        _e for _e in record.event_log if not (isinstance(_e, dict) and _e.get("type") in ("done", "error", "cancelled"))
    ]

    # Mark all pre-loaded events as already flushed so the flusher only writes
    # new events emitted during this resumed run, not the historical ones.
    record._flush_index = len(record.event_log)

    # Start heartbeat immediately -- workflow_id is already known for resumed runs.
    heartbeat_task: asyncio.Task[Any] = asyncio.create_task(
        _heartbeat_loop(run_root, workflow_id, interval=_web_cfg.heartbeat_interval_seconds)
    )
    flusher_task: asyncio.Task[Any] = asyncio.create_task(
        _event_flusher_loop(record, interval=_web_cfg.event_flush_interval_seconds)
    )

    # Use the review.yaml saved alongside runtime.db (written by the original web run).
    # Fall back to the global config if the file is absent (old CLI runs, early crashes).
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
        outputs = await run_workflow_resume(
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
        # When workflow returns status "failed" (e.g. gate failure), emit error event
        # so the UI shows the actual message instead of "An unexpected error occurred".
        if record.outputs.get("status") == "failed":
            err_msg = record.outputs.get("error", "Workflow failed")
            record.error = err_msg
            _gate_err_evt: dict[str, Any] = {"type": "error", "msg": err_msg}
            _append_event(record, _gate_err_evt)
            try:
                await _update_registry_status(run_root, workflow_id, "failed")
            except Exception:
                pass
        else:
            try:
                await _update_registry_status(run_root, workflow_id, "completed")
            except Exception:
                pass
        _done_resume_evt: dict[str, Any] = {"type": "done", "outputs": record.outputs}
        _append_event(record, _done_resume_evt)
    except asyncio.CancelledError:
        record.done = True
        record.error = "Cancelled"
        _cancelled_resume_evt: dict[str, Any] = {"type": "cancelled"}
        _append_event(record, _cancelled_resume_evt)
        try:
            await _update_registry_status(run_root, workflow_id, "interrupted")
        except Exception:
            pass
    except Exception as exc:
        import traceback

        _tb = traceback.format_exc()
        _logger.exception("Resume failed: %s", exc)
        # Safety net: if workflow status is already completed in runtime.db,
        # treat this as a post-finalize/non-fatal exception and avoid flipping
        # registry status back to failed.
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
            _done_resume_evt: dict[str, Any] = {"type": "done", "outputs": record.outputs}
            _append_event(record, _done_resume_evt)
            try:
                await _update_registry_status(run_root, workflow_id, "completed")
            except Exception:
                pass
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
            except Exception:
                pass
    finally:
        heartbeat_task.cancel()
        flusher_task.cancel()
        # Final flush: persist any events not yet written by the flusher loop,
        # including the terminal error/cancelled event appended above.
        await _flush_pending_events(record)


_RESUME_PHASE_ORDER = [
    "phase_2_search",
    "phase_3_screening",
    "phase_4_extraction_quality",
    "phase_4b_embedding",
    "phase_5_synthesis",
    "phase_5b_knowledge_graph",
    "phase_5c_pre_writing_gate",
    "phase_6_writing",
    "phase_7_audit",
    "finalize",
]


@app.get("/api/history/active-run")
async def get_active_run(workflow_id: str) -> RunResponse:
    """Return the run_id for a workflow that is currently being actively resumed.

    Used when the user resumes from CLI: the frontend polls this while viewing
    a run; when it returns 200, the frontend switches to live SSE mode.
    Returns 404 if the workflow is not actively running.
    """
    for record in _active_runs.values():
        if record.workflow_id == workflow_id and not record.done:
            return RunResponse(run_id=record.run_id, topic=record.topic or "")
    raise HTTPException(status_code=404, detail="Workflow not actively running")


@app.post("/api/history/resume", response_model=RunResponse)
async def resume_run(req: ResumeRequest) -> RunResponse:
    """Resume an interrupted workflow from its last checkpoint.

    Creates a new live RunRecord (new run_id) backed by the existing workflow_id
    so the frontend can SSE-connect to watch the resumed run complete.

    If the same workflow_id is already active, returns 409 conflict.

    When from_phase is provided, resumes from that phase (and later) instead of
    the first incomplete phase. Prior phases must have checkpoints.
    """
    if req.from_phase is not None and req.from_phase not in _RESUME_PHASE_ORDER:
        raise HTTPException(
            status_code=400,
            detail=f"from_phase must be one of {_RESUME_PHASE_ORDER}",
        )
    # Guard: prevent double-resume of the same workflow (e.g. user clicks twice).
    for existing in _active_runs.values():
        if existing.workflow_id == req.workflow_id and not existing.done:
            raise HTTPException(
                status_code=409,
                detail="Workflow is already running. Stop the active run before resuming.",
            )

    # Secondary guard: enforce registry status as source of truth to prevent
    # duplicate resumes during in-memory reconciliation windows.
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


@app.delete("/api/history/{workflow_id}")
async def delete_run(workflow_id: str, run_root: str = "runs") -> dict[str, bool]:
    """Delete a run from the registry and remove its run directory.

    Cannot delete a run that is actively running (in _active_runs).
    Returns 404 if workflow not found in registry.
    """
    # Guard: do not delete if run is actively running
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

    # Delete from registry first so the run disappears from history immediately
    try:
        async with _open_registry_db(str(registry)) as db:
            await db.execute(
                "DELETE FROM workflows_registry WHERE workflow_id = ?",
                (workflow_id,),
            )
            await db.commit()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Delete run directory (runtime.db, review.yaml, run_summary.json, etc.)
    try:
        if run_dir.exists():
            shutil.rmtree(run_dir)
    except OSError:
        # Log but do not fail - registry row is already removed
        pass

    return {"ok": True}


@app.post("/api/history/{workflow_id}/archive")
async def archive_history_run(workflow_id: str, run_root: str = "runs") -> dict[str, bool]:
    """Soft-archive a workflow row without deleting any run artifacts."""
    for record in _active_runs.values():
        if record.workflow_id == workflow_id and not record.done:
            raise HTTPException(
                status_code=409,
                detail="Cannot archive a run that is currently in progress",
            )
    db_path = await _resolve_db_path(run_root, workflow_id)
    if not db_path:
        raise HTTPException(status_code=404, detail="Workflow not found in registry")
    await _archive_registry_workflow(run_root, workflow_id)
    return {"ok": True}


@app.post("/api/history/{workflow_id}/restore")
async def restore_history_run(workflow_id: str, run_root: str = "runs") -> dict[str, bool]:
    """Restore a previously archived workflow row into the active list."""
    for record in _active_runs.values():
        if record.workflow_id == workflow_id and not record.done:
            raise HTTPException(
                status_code=409,
                detail="Cannot restore a run that is currently in progress",
            )
    db_path = await _resolve_db_path(run_root, workflow_id)
    if not db_path:
        raise HTTPException(status_code=404, detail="Workflow not found in registry")
    await _restore_registry_workflow(run_root, workflow_id)
    return {"ok": True}


@app.post("/api/history/attach", response_model=RunResponse)
async def attach_history(req: AttachRequest) -> RunResponse:
    """Create a read-only completed _RunRecord from a historical workflow so
    all /api/db/{run_id}/... endpoints work for that past run."""
    run_id = str(uuid.uuid4())[:8]
    record = _RunRecord(run_id=run_id, topic=req.topic)
    record.done = True
    record.db_path = req.db_path
    record.workflow_id = req.workflow_id
    await _ensure_runtime_db_migrated(req.db_path)
    # FinalizeNode writes run_summary.json in the same directory as runtime.db.
    # It contains output_dir and the full artifacts dict (all output file paths).
    summary_path = pathlib.Path(req.db_path).parent / "run_summary.json"
    if summary_path.exists():
        try:
            record.outputs = _json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            pass  # graceful -- outputs stays {}
    # Load persisted events from SQLite for the historical event log viewer.
    record.event_log = await _load_event_log_from_db(req.db_path)
    # Reconcile status against durable runtime evidence so attach does not
    # fabricate stale failures for workflows that actually terminated.
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
    # Inject a synthetic terminal event only as a last resort for unresolved runs.
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
    # Refresh allowed download roots to include the newly attached run's location.
    await _refresh_allowed_roots()
    return RunResponse(run_id=run_id, topic=req.topic)


# ---------------------------------------------------------------------------
# Database explorer endpoints
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

    # Historical read endpoints resolve by workflow_id. Do not run registry
    # fallback scans for short-lived run_id values that are not active.
    if not identifier.startswith("wf-"):
        raise HTTPException(status_code=404, detail="Run not found")

    from src.db.workflow_registry import candidate_run_roots, resolve_workflow_db_path

    roots = candidate_run_roots(run_root, anchor_file=__file__)
    db_path = await resolve_workflow_db_path(identifier, roots)
    if not db_path:
        raise HTTPException(status_code=404, detail="Run not found")
    return db_path


async def _resolve_workflow_id_from_db(db_path: str) -> str | None:
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT workflow_id FROM workflows ORDER BY rowid DESC LIMIT 1") as cur:
                row = await cur.fetchone()
                if row and row[0]:
                    return str(row[0])
    except Exception:
        return None
    return None


async def _query_included_papers_rows(
    db: aiosqlite.Connection,
    workflow_id: str,
    *,
    for_fetch: bool,
) -> list[aiosqlite.Row]:
    """Return included-paper rows with fulltext->extraction fallback precedence."""
    if for_fetch:
        primary_select_cols = "p.paper_id, p.title, p.authors, p.year, p.doi, p.url, p.source_database"
        legacy_select_cols = primary_select_cols
        order_by = "p.paper_id"
        fallback_select_cols = primary_select_cols
    else:
        # study_cohort_membership does not expose a fulltext decision field;
        # in this pathway, every row is already filtered to included_primary.
        primary_select_cols = (
            "p.paper_id, p.title, p.authors, p.year, p.source_database, p.doi, p.url, p.country, "
            "'include' AS final_decision"
        )
        legacy_select_cols = (
            "p.paper_id, p.title, p.authors, p.year, p.source_database, p.doi, p.url, p.country, ft.final_decision"
        )
        order_by = "p.year DESC"
        fallback_select_cols = (
            "p.paper_id, p.title, p.authors, p.year, p.source_database, p.doi, p.url, p.country, "
            "'include' AS final_decision"
        )

    primary_query = f"""
        SELECT {primary_select_cols}
        FROM papers p
        JOIN study_cohort_membership scm
          ON p.paper_id = scm.paper_id
        WHERE scm.workflow_id = ?
          AND scm.synthesis_eligibility = 'included_primary'
        ORDER BY {order_by}
    """
    async with db.execute(primary_query, (workflow_id,)) as cur:
        rows = await cur.fetchall()

    if rows:
        return rows

    legacy_query = f"""
        SELECT {legacy_select_cols}
        FROM papers p
        JOIN dual_screening_results ft
          ON p.paper_id = ft.paper_id AND ft.stage = 'fulltext'
        WHERE ft.workflow_id = ? AND ft.final_decision = 'include'
        ORDER BY {order_by}
    """
    async with db.execute(legacy_query, (workflow_id,)) as cur:
        rows = await cur.fetchall()

    if rows:
        return rows

    fallback_query = f"""
        SELECT {fallback_select_cols}
        FROM papers p
        JOIN extraction_records er
          ON p.paper_id = er.paper_id AND er.workflow_id = ?
        ORDER BY {order_by}
    """
    async with db.execute(fallback_query, (workflow_id,)) as fallback_cur:
        return await fallback_cur.fetchall()


_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "of",
        "in",
        "on",
        "to",
        "for",
        "with",
        "is",
        "are",
        "what",
        "how",
        "why",
        "which",
        "that",
        "this",
        "do",
        "does",
        "from",
        "by",
        "at",
        "as",
        "its",
    }
)


def _make_download_slug(workflow_id: str, topic: str, max_words: int = 5) -> str:
    """Build a filesystem-safe download slug: '<workflow_id>-<short-topic>'.

    Takes the first *max_words* meaningful (non-stop) words from *topic*,
    lowercases them, strips non-alphanumeric characters, and joins with
    hyphens. Falls back gracefully if topic is empty.

    Example: 'wf-ba930803-mindfulness-anxiety-adults-systematic-review'
    """
    import re

    words = re.sub(r"[^a-zA-Z0-9 ]", " ", topic).lower().split()
    meaningful = [w for w in words if w not in _STOP_WORDS and len(w) > 1]
    short = "-".join(meaningful[:max_words]) if meaningful else "review"
    return f"{workflow_id}-{short}"


async def _get_topic_for_db(db_path: str) -> str:
    """Read topic from the workflows table in *db_path*. Returns empty string on failure."""
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT topic FROM workflows LIMIT 1") as cur:
                row = await cur.fetchone()
                return str(row[0]) if row and row[0] else ""
    except Exception:
        return ""


@app.get("/api/db/{run_id}/papers")
async def get_papers(
    run_id: str,
    offset: int = 0,
    limit: int = 50,
    search: str = "",
) -> dict[str, Any]:
    """Paginated papers table from the run's SQLite database."""
    db_path = _get_db_path(run_id)
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            if search:
                like = f"%{search}%"
                async with db.execute(
                    """SELECT paper_id, title, authors, year, source_database, doi, abstract, country
                       FROM papers WHERE title LIKE ? OR abstract LIKE ?
                       ORDER BY year DESC LIMIT ? OFFSET ?""",
                    (like, like, limit, offset),
                ) as cur:
                    rows = await cur.fetchall()
                async with db.execute(
                    "SELECT COUNT(*) FROM papers WHERE title LIKE ? OR abstract LIKE ?",
                    (like, like),
                ) as cur:
                    total = (await cur.fetchone())[0]  # type: ignore[index]
            else:
                async with db.execute(
                    """SELECT paper_id, title, authors, year, source_database, doi, abstract, country
                       FROM papers ORDER BY year DESC LIMIT ? OFFSET ?""",
                    (limit, offset),
                ) as cur:
                    rows = await cur.fetchall()
                async with db.execute("SELECT COUNT(*) FROM papers") as cur:
                    total = (await cur.fetchone())[0]  # type: ignore[index]

            papers = []
            for row in rows:
                authors_raw = row["authors"]
                try:
                    authors = _json.loads(authors_raw) if authors_raw else []
                    if isinstance(authors, list):
                        authors = ", ".join(str(a) for a in authors[:3])
                        if len(_json.loads(row["authors"])) > 3:
                            authors += " et al."
                except Exception:
                    authors = str(authors_raw or "")
                papers.append(
                    {
                        "paper_id": row["paper_id"],
                        "title": row["title"],
                        "authors": authors,
                        "year": row["year"],
                        "source_database": row["source_database"],
                        "doi": row["doi"],
                        "country": row["country"],
                    }
                )
            return {"total": total, "offset": offset, "limit": limit, "papers": papers}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/db/{run_id}/screening")
async def get_screening(
    run_id: str,
    stage: str = "",
    decision: str = "",
    offset: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    """Screening decisions table."""
    db_path = _get_db_path(run_id)
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            conditions = []
            params: list[Any] = []
            if stage:
                conditions.append("stage = ?")
                params.append(stage)
            if decision:
                conditions.append("decision = ?")
                params.append(decision)
            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            async with db.execute(
                f"""SELECT paper_id, stage, decision, reason AS rationale, created_at
                    FROM screening_decisions {where}
                    ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (*params, limit, offset),
            ) as cur:
                rows = await cur.fetchall()
            async with db.execute(f"SELECT COUNT(*) FROM screening_decisions {where}", params) as cur:
                total = (await cur.fetchone())[0]  # type: ignore[index]

            decisions = [dict(row) for row in rows]
            return {"total": total, "offset": offset, "limit": limit, "decisions": decisions}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/db/{run_id}/papers-facets")
async def get_papers_facets(run_id: str) -> dict[str, Any]:
    """Return distinct values for all filter columns (used by autocomplete dropdowns)."""
    db_path = _get_db_path(run_id)
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT DISTINCT year FROM papers WHERE year IS NOT NULL ORDER BY year DESC") as cur:
                years = [row[0] for row in await cur.fetchall()]
            async with db.execute(
                "SELECT DISTINCT source_database FROM papers WHERE source_database IS NOT NULL ORDER BY source_database"
            ) as cur:
                sources = [row[0] for row in await cur.fetchall()]
            async with db.execute(
                "SELECT DISTINCT country FROM papers WHERE country IS NOT NULL ORDER BY country"
            ) as cur:
                countries = [row[0] for row in await cur.fetchall()]
            async with db.execute(
                "SELECT DISTINCT final_decision FROM dual_screening_results "
                "WHERE stage = 'title_abstract' AND final_decision IS NOT NULL ORDER BY final_decision"
            ) as cur:
                ta_decisions = [row[0] for row in await cur.fetchall()]
            async with db.execute(
                "SELECT DISTINCT final_decision FROM dual_screening_results "
                "WHERE stage = 'fulltext' AND final_decision IS NOT NULL ORDER BY final_decision"
            ) as cur:
                ft_decisions = [row[0] for row in await cur.fetchall()]
            async with db.execute(
                """
                SELECT DISTINCT COALESCE(json_extract(er.data, '$.primary_study_status'), 'unknown') AS primary_status
                FROM extraction_records er
                WHERE COALESCE(json_extract(er.data, '$.primary_study_status'), 'unknown') IS NOT NULL
                ORDER BY primary_status
                """
            ) as cur:
                primary_statuses = [row[0] for row in await cur.fetchall()]
        return {
            "years": years,
            "sources": sources,
            "countries": countries,
            "ta_decisions": ta_decisions,
            "ft_decisions": ft_decisions,
            "primary_statuses": primary_statuses,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/db/{run_id}/papers-suggest")
async def get_papers_suggest(
    run_id: str,
    column: str,
    q: str = "",
    limit: int = 10,
) -> dict[str, Any]:
    """Return distinct matching values for a column for autocomplete (title and author)."""
    if column not in ("title", "author"):
        raise HTTPException(status_code=400, detail="column must be 'title' or 'author'")
    db_path = _get_db_path(run_id)
    try:
        async with aiosqlite.connect(db_path) as db:
            like = f"%{q}%"
            if column == "title":
                async with db.execute(
                    "SELECT DISTINCT title FROM papers WHERE title LIKE ? AND title IS NOT NULL ORDER BY title LIMIT ?",
                    (like, limit),
                ) as cur:
                    suggestions = [row[0] for row in await cur.fetchall()]
            else:
                # Authors is stored as a JSON array; LIKE on raw string gives partial matches
                async with db.execute(
                    "SELECT DISTINCT authors FROM papers WHERE authors LIKE ? AND authors IS NOT NULL LIMIT ?",
                    (like, limit),
                ) as cur:
                    raw_rows = [row[0] for row in await cur.fetchall()]
                # Parse JSON arrays and extract distinct author names matching the query
                import json as _json_local

                seen: set[str] = set()
                suggestions = []
                for raw in raw_rows:
                    try:
                        authors_list = _json_local.loads(raw) if raw.startswith("[") else [raw]
                        for a in authors_list:
                            name = (a.get("name") or a.get("raw_name") or str(a)) if isinstance(a, dict) else str(a)
                            if q.lower() in name.lower() and name not in seen:
                                seen.add(name)
                                suggestions.append(name)
                                if len(suggestions) >= limit:
                                    break
                    except Exception:
                        if raw not in seen:
                            seen.add(raw)
                            suggestions.append(raw)
                    if len(suggestions) >= limit:
                        break
        return {"suggestions": suggestions}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/db/{run_id}/papers-all")
async def get_papers_all(
    run_id: str,
    search: str = "",
    title: str = "",
    author: str = "",
    ta_decision: str = "",
    ft_decision: str = "",
    primary_status: str = "",
    year: str = "",
    source: str = "",
    country: str = "",
    offset: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    """Unified per-paper table joining papers with final screening decisions."""
    db_path = _get_db_path(run_id)
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row

            conditions: list[str] = []
            params: list[Any] = []

            if search:
                like = f"%{search}%"
                conditions.append("(p.title LIKE ? OR p.abstract LIKE ? OR p.authors LIKE ?)")
                params.extend([like, like, like])
            if title:
                conditions.append("COALESCE(p.title, '') LIKE ?")
                params.append(f"%{title}%")
            if author:
                conditions.append("COALESCE(p.authors, '') LIKE ?")
                params.append(f"%{author}%")
            if ta_decision:
                conditions.append("COALESCE(ta.final_decision, '') LIKE ?")
                params.append(f"%{ta_decision}%")
            if ft_decision:
                conditions.append("COALESCE(ft.final_decision, '') LIKE ?")
                params.append(f"%{ft_decision}%")
            if primary_status:
                conditions.append(
                    "COALESCE(json_extract(er.data, '$.primary_study_status'), 'unknown') LIKE ?"
                )
                params.append(f"%{primary_status}%")
            if year:
                conditions.append("CAST(p.year AS TEXT) LIKE ?")
                params.append(f"%{year}%")
            if source:
                conditions.append("COALESCE(p.source_database, '') LIKE ?")
                params.append(f"%{source}%")
            if country:
                conditions.append("COALESCE(p.country, '') LIKE ?")
                params.append(f"%{country}%")

            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            base_query = f"""
                FROM papers p
                LEFT JOIN dual_screening_results ta
                  ON p.paper_id = ta.paper_id AND ta.stage = 'title_abstract'
                LEFT JOIN dual_screening_results ft
                  ON p.paper_id = ft.paper_id AND ft.stage = 'fulltext'
                LEFT JOIN extraction_records er
                  ON p.paper_id = er.paper_id
                LEFT JOIN rob_assessments ra
                  ON p.paper_id = ra.paper_id
                {where}
            """

            async with db.execute(
                f"""SELECT p.paper_id, p.title, p.authors, p.year,
                           p.source_database, p.doi, p.url, p.country,
                           ta.final_decision AS ta_decision,
                           ft.final_decision AS ft_decision,
                           COALESCE(json_extract(er.data, '$.primary_study_status'), 'unknown')
                               AS primary_study_status,
                           er.data AS extraction_data,
                           ra.assessment_data AS rob_assessment_data
                    {base_query}
                    ORDER BY p.year DESC LIMIT ? OFFSET ?""",
                (*params, limit, offset),
            ) as cur:
                rows = await cur.fetchall()

            async with db.execute(f"SELECT COUNT(*) {base_query}", params) as cur:
                total = (await cur.fetchone())[0]  # type: ignore[index]

            papers = []
            for row in rows:
                raw = row["authors"] or ""
                try:
                    authors_list = _json.loads(raw) if raw.startswith("[") else [raw]
                    authors_fmt = ", ".join(
                        (a.get("name") or a.get("raw_name") or str(a)) if isinstance(a, dict) else str(a)
                        for a in authors_list
                    )
                except Exception:
                    authors_fmt = raw
                extraction_confidence: float | None = None
                try:
                    if row["extraction_data"]:
                        ed = _json.loads(row["extraction_data"])
                        extraction_confidence = ed.get("extraction_confidence")
                except Exception:
                    pass

                assessment_source: str | None = None
                try:
                    if row["rob_assessment_data"]:
                        rad = _json.loads(row["rob_assessment_data"])
                        assessment_source = rad.get("assessment_source")
                except Exception:
                    pass

                papers.append(
                    {
                        "paper_id": row["paper_id"],
                        "title": row["title"],
                        "authors": authors_fmt,
                        "year": row["year"],
                        "source_database": row["source_database"],
                        "doi": row["doi"],
                        "url": row["url"],
                        "country": row["country"],
                        "ta_decision": row["ta_decision"],
                        "ft_decision": row["ft_decision"],
                        "primary_study_status": row["primary_study_status"],
                        "extraction_confidence": extraction_confidence,
                        "assessment_source": assessment_source,
                    }
                )

            return {"total": total, "offset": offset, "limit": limit, "papers": papers}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/db/{run_id}/costs")
async def get_db_costs(run_id: str) -> dict[str, Any]:
    """Aggregated cost_records from the run's SQLite database."""
    db_path = _get_db_path(run_id)
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT model, phase,
                          COUNT(*) as calls,
                          SUM(tokens_in) as tokens_in,
                          SUM(tokens_out) as tokens_out,
                          SUM(cost_usd) as cost_usd,
                          AVG(latency_ms) as avg_latency_ms
                   FROM cost_records
                   GROUP BY model, phase
                   ORDER BY cost_usd DESC"""
            ) as cur:
                rows = await cur.fetchall()
            async with db.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM cost_records") as cur:
                total_cost = float((await cur.fetchone())[0])  # type: ignore[index]
            async with db.execute(
                """
                SELECT rationale
                FROM decision_log
                WHERE decision_type = 'screening_metric'
                  AND phase = 'phase_3_screening'
                ORDER BY id ASC
                """
            ) as cur:
                metric_rows = await cur.fetchall()

            records = [dict(row) for row in rows]
            screening_metrics: dict[str, float] = {}
            for row in metric_rows:
                try:
                    payload = _json.loads(str(row["rationale"] or "{}"))
                except Exception:
                    continue
                metric_name = payload.get("metric")
                metric_value = payload.get("value")
                if not isinstance(metric_name, str):
                    continue
                if isinstance(metric_value, (int, float)):
                    screening_metrics[metric_name] = float(metric_value)
            screening_diagnostics = {
                "batch_parse_degraded": int(screening_metrics.get("batch_parse_degraded", 0.0)),
                "batch_id_mismatch": int(screening_metrics.get("batch_id_mismatch", 0.0)),
                "batch_missing_fallback": int(screening_metrics.get("batch_missing_fallback", 0.0)),
                "contract_violation_count": int(screening_metrics.get("contract_violation_count", 0.0)),
                "fast_path_include": int(screening_metrics.get("title_abstract_fast_path_include", 0.0)),
                "fast_path_exclude": int(screening_metrics.get("title_abstract_fast_path_exclude", 0.0)),
                "cross_reviewed": int(screening_metrics.get("title_abstract_cross_reviewed", 0.0)),
            }
            return {"total_cost": total_cost, "records": records, "screening_diagnostics": screening_diagnostics}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _build_cost_time_filter(start_ts: str | None, end_ts: str | None) -> tuple[str, list[str]]:
    clauses: list[str] = []
    params: list[str] = []
    if start_ts:
        clauses.append("datetime(created_at) >= datetime(?)")
        params.append(start_ts.strip())
    if end_ts:
        clauses.append("datetime(created_at) <= datetime(?)")
        params.append(end_ts.strip())
    if not clauses:
        return "", params
    return "WHERE " + " AND ".join(clauses), params


def _bucket_created_at(value: Any, granularity: str) -> str:
    ts = _parse_sqlite_ts(value)
    if ts is None:
        return "unknown"
    if granularity == "day":
        return ts.strftime("%Y-%m-%d")
    if granularity == "week":
        return f"{ts.strftime('%Y')}-W{ts.strftime('%W')}"
    if granularity == "month":
        return ts.strftime("%Y-%m")
    raise ValueError(f"unsupported granularity: {granularity}")


def _merge_cost_group_row(
    groups: dict[str, dict[str, Any]],
    key: str,
    *,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    calls: int = 1,
) -> None:
    current = groups.setdefault(
        key,
        {
            "calls": 0,
            "tokens_in": 0,
            "tokens_out": 0,
            "cost_usd": 0.0,
        },
    )
    current["calls"] += calls
    current["tokens_in"] += tokens_in
    current["tokens_out"] += tokens_out
    current["cost_usd"] += cost_usd


async def _fetch_registry_cost_rows(
    run_root: str,
    *,
    start_ts: str | None,
    end_ts: str | None,
    include_archived: bool,
) -> list[dict[str, Any]]:
    registry = pathlib.Path(run_root) / "workflows_registry.db"
    if not registry.exists():
        return []

    async with _open_registry_db(str(registry)) as reg_db:
        reg_db.row_factory = aiosqlite.Row
        where_archived = "" if include_archived else "WHERE COALESCE(is_archived, 0) = 0"
        async with reg_db.execute(
            f"""
            SELECT workflow_id, topic, db_path
            FROM workflows_registry
            {where_archived}
            ORDER BY created_at DESC
            """
        ) as cur:
            registry_rows = await cur.fetchall()

    where_sql, where_params = _build_cost_time_filter(start_ts, end_ts)

    async def _fetch_for_db(entry: aiosqlite.Row) -> list[dict[str, Any]]:
        db_path = str(entry["db_path"] or "")
        if not db_path or not pathlib.Path(db_path).exists():
            return []
        workflow_id = str(entry["workflow_id"] or "")
        topic = str(entry["topic"] or "")
        try:
            async with aiosqlite.connect(db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    f"""
                    SELECT
                        COALESCE(NULLIF(workflow_id, ''), ?) AS workflow_id,
                        COALESCE(NULLIF(model, ''), 'unknown') AS model,
                        COALESCE(NULLIF(phase, ''), 'unknown') AS phase,
                        COALESCE(created_at, '') AS created_at,
                        COALESCE(tokens_in, 0) AS tokens_in,
                        COALESCE(tokens_out, 0) AS tokens_out,
                        COALESCE(cost_usd, 0.0) AS cost_usd
                    FROM cost_records
                    {where_sql}
                    """,
                    [workflow_id, *where_params],
                ) as cur:
                    rows = await cur.fetchall()
            return [
                {
                    "workflow_id": str(row["workflow_id"] or workflow_id or "unknown"),
                    "topic": topic,
                    "model": str(row["model"] or "unknown"),
                    "phase": str(row["phase"] or "unknown"),
                    "created_at": str(row["created_at"] or ""),
                    "tokens_in": int(row["tokens_in"] or 0),
                    "tokens_out": int(row["tokens_out"] or 0),
                    "cost_usd": float(row["cost_usd"] or 0.0),
                }
                for row in rows
            ]
        except Exception:
            return []

    per_db_rows = await asyncio.gather(*[_fetch_for_db(entry) for entry in registry_rows], return_exceptions=True)
    flattened: list[dict[str, Any]] = []
    for item in per_db_rows:
        if isinstance(item, list):
            flattened.extend(item)
    return flattened


def _build_global_cost_aggregates_payload(
    rows: list[dict[str, Any]],
    *,
    start_ts: str | None,
    end_ts: str | None,
) -> dict[str, Any]:
    totals = {
        "total_cost_usd": 0.0,
        "total_calls": 0,
        "total_tokens_in": 0,
        "total_tokens_out": 0,
    }
    by_day: dict[str, dict[str, Any]] = {}
    by_week: dict[str, dict[str, Any]] = {}
    by_month: dict[str, dict[str, Any]] = {}
    by_workflow: dict[str, dict[str, Any]] = {}
    by_phase: dict[str, dict[str, Any]] = {}
    by_model: dict[str, dict[str, Any]] = {}

    for row in rows:
        tokens_in = int(row["tokens_in"])
        tokens_out = int(row["tokens_out"])
        cost_usd = float(row["cost_usd"])
        totals["total_cost_usd"] += cost_usd
        totals["total_calls"] += 1
        totals["total_tokens_in"] += tokens_in
        totals["total_tokens_out"] += tokens_out
        _merge_cost_group_row(by_day, _bucket_created_at(row["created_at"], "day"), tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost_usd)
        _merge_cost_group_row(by_week, _bucket_created_at(row["created_at"], "week"), tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost_usd)
        _merge_cost_group_row(by_month, _bucket_created_at(row["created_at"], "month"), tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost_usd)
        _merge_cost_group_row(by_workflow, str(row["workflow_id"]), tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost_usd)
        _merge_cost_group_row(by_phase, str(row["phase"]), tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost_usd)
        _merge_cost_group_row(by_model, str(row["model"]), tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost_usd)

    return {
        "start_ts": start_ts,
        "end_ts": end_ts,
        "workflow_count": len({str(row["workflow_id"]) for row in rows}),
        "totals": totals,
        "by_day": [{"bucket": key, **value} for key, value in sorted(by_day.items(), key=lambda item: item[0])],
        "by_week": [{"bucket": key, **value} for key, value in sorted(by_week.items(), key=lambda item: item[0])],
        "by_month": [{"bucket": key, **value} for key, value in sorted(by_month.items(), key=lambda item: item[0])],
        "by_workflow": [{"group_key": key, **value} for key, value in sorted(by_workflow.items(), key=lambda item: item[1]["cost_usd"], reverse=True)],
        "by_phase": [{"group_key": key, **value} for key, value in sorted(by_phase.items(), key=lambda item: item[1]["cost_usd"], reverse=True)],
        "by_model": [{"group_key": key, **value} for key, value in sorted(by_model.items(), key=lambda item: item[1]["cost_usd"], reverse=True)],
    }


@app.get("/api/db/{run_id}/costs/aggregates")
async def get_db_cost_aggregates(
    run_id: str,
    start_ts: str | None = None,
    end_ts: str | None = None,
) -> dict[str, Any]:
    """Return day/week/month plus workflow/phase/model cost aggregations."""
    db_path = _get_db_path(run_id)
    where_sql, where_params = _build_cost_time_filter(start_ts, end_ts)
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row

            async def _query_bucket(bucket_sql: str) -> list[dict[str, Any]]:
                query = f"""
                    SELECT {bucket_sql} AS bucket,
                           COUNT(*) AS calls,
                           COALESCE(SUM(tokens_in), 0) AS tokens_in,
                           COALESCE(SUM(tokens_out), 0) AS tokens_out,
                           COALESCE(SUM(cost_usd), 0.0) AS cost_usd
                    FROM cost_records
                    {where_sql}
                    GROUP BY bucket
                    ORDER BY bucket ASC
                """
                rows = await (await db.execute(query, where_params)).fetchall()
                return [dict(r) for r in rows]

            async def _query_group(group_sql: str) -> list[dict[str, Any]]:
                query = f"""
                    SELECT {group_sql} AS group_key,
                           COUNT(*) AS calls,
                           COALESCE(SUM(tokens_in), 0) AS tokens_in,
                           COALESCE(SUM(tokens_out), 0) AS tokens_out,
                           COALESCE(SUM(cost_usd), 0.0) AS cost_usd
                    FROM cost_records
                    {where_sql}
                    GROUP BY group_key
                    ORDER BY cost_usd DESC
                """
                rows = await (await db.execute(query, where_params)).fetchall()
                return [dict(r) for r in rows]

            total_row = await (
                await db.execute(
                    f"""
                    SELECT COALESCE(SUM(cost_usd), 0.0) AS total_cost_usd,
                           COUNT(*) AS total_calls,
                           COALESCE(SUM(tokens_in), 0) AS total_tokens_in,
                           COALESCE(SUM(tokens_out), 0) AS total_tokens_out
                    FROM cost_records
                    {where_sql}
                    """,
                    where_params,
                )
            ).fetchone()

            by_day = await _query_bucket("date(created_at)")
            by_week = await _query_bucket("strftime('%Y-W%W', created_at)")
            by_month = await _query_bucket("strftime('%Y-%m', created_at)")
            by_workflow = await _query_group("COALESCE(NULLIF(workflow_id, ''), 'unknown')")
            by_phase = await _query_group("COALESCE(NULLIF(phase, ''), 'unknown')")
            by_model = await _query_group("COALESCE(NULLIF(model, ''), 'unknown')")

            return {
                "run_id": run_id,
                "start_ts": start_ts,
                "end_ts": end_ts,
                "totals": dict(total_row) if total_row else {},
                "by_day": by_day,
                "by_week": by_week,
                "by_month": by_month,
                "by_workflow": by_workflow,
                "by_phase": by_phase,
                "by_model": by_model,
            }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/history/costs/aggregates")
async def get_history_cost_aggregates(
    run_root: str = "runs",
    start_ts: str | None = None,
    end_ts: str | None = None,
    include_archived: bool = True,
) -> dict[str, Any]:
    """Return cross-run cost aggregates from registry-linked runtime DBs."""
    try:
        rows = await _fetch_registry_cost_rows(
            run_root,
            start_ts=start_ts,
            end_ts=end_ts,
            include_archived=include_archived,
        )
        payload = _build_global_cost_aggregates_payload(rows, start_ts=start_ts, end_ts=end_ts)
        payload["run_root"] = run_root
        payload["include_archived"] = include_archived
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/db/{run_id}/costs/export")
async def export_db_costs_csv(
    run_id: str,
    start_ts: str | None = None,
    end_ts: str | None = None,
    granularity: str = "day",
) -> StreamingResponse:
    """Export reconciliation-friendly grouped cost CSV for a run."""
    db_path = _get_db_path(run_id)
    where_sql, where_params = _build_cost_time_filter(start_ts, end_ts)
    bucket_by_granularity = {
        "day": "date(created_at)",
        "week": "strftime('%Y-W%W', created_at)",
        "month": "strftime('%Y-%m', created_at)",
    }
    if granularity not in bucket_by_granularity:
        raise HTTPException(status_code=400, detail="granularity must be one of: day, week, month")

    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            query = f"""
                SELECT {bucket_by_granularity[granularity]} AS timestamp_bucket,
                       COALESCE(NULLIF(workflow_id, ''), 'unknown') AS workflow_id,
                       COALESCE(NULLIF(phase, ''), 'unknown') AS phase,
                       COALESCE(NULLIF(model, ''), 'unknown') AS model,
                       COUNT(*) AS call_count,
                       COALESCE(SUM(tokens_in), 0) AS tokens_in,
                       COALESCE(SUM(tokens_out), 0) AS tokens_out,
                       COALESCE(SUM(cost_usd), 0.0) AS cost_usd
                FROM cost_records
                {where_sql}
                GROUP BY timestamp_bucket, workflow_id, phase, model
                ORDER BY timestamp_bucket ASC, cost_usd DESC
            """
            rows = await (await db.execute(query, where_params)).fetchall()

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["timestamp_bucket", "workflow_id", "phase", "model", "call_count", "tokens_in", "tokens_out", "cost_usd"])
        for row in rows:
            writer.writerow(
                [
                    row["timestamp_bucket"],
                    row["workflow_id"],
                    row["phase"],
                    row["model"],
                    row["call_count"],
                    row["tokens_in"],
                    row["tokens_out"],
                    row["cost_usd"],
                ]
            )
        csv_text = buffer.getvalue()
        filename = f"cost_export_{run_id}_{granularity}.csv"
        return StreamingResponse(
            iter([csv_text]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/history/costs/export")
async def export_history_costs_csv(
    run_root: str = "runs",
    start_ts: str | None = None,
    end_ts: str | None = None,
    granularity: str = "day",
    include_archived: bool = True,
) -> StreamingResponse:
    """Export cross-run cost CSV grouped over registry-linked runtime DBs."""
    if granularity not in {"day", "week", "month"}:
        raise HTTPException(status_code=400, detail="granularity must be one of: day, week, month")
    try:
        rows = await _fetch_registry_cost_rows(
            run_root,
            start_ts=start_ts,
            end_ts=end_ts,
            include_archived=include_archived,
        )
        grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        for row in rows:
            bucket = _bucket_created_at(row["created_at"], granularity)
            key = (bucket, str(row["workflow_id"]), str(row["phase"]), str(row["model"]))
            current = grouped.setdefault(
                key,
                {
                    "timestamp_bucket": bucket,
                    "workflow_id": str(row["workflow_id"]),
                    "phase": str(row["phase"]),
                    "model": str(row["model"]),
                    "call_count": 0,
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "cost_usd": 0.0,
                },
            )
            current["call_count"] += 1
            current["tokens_in"] += int(row["tokens_in"])
            current["tokens_out"] += int(row["tokens_out"])
            current["cost_usd"] += float(row["cost_usd"])

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["timestamp_bucket", "workflow_id", "phase", "model", "call_count", "tokens_in", "tokens_out", "cost_usd"])
        for row in sorted(grouped.values(), key=lambda item: (str(item["timestamp_bucket"]), -float(item["cost_usd"]))):
            writer.writerow(
                [
                    row["timestamp_bucket"],
                    row["workflow_id"],
                    row["phase"],
                    row["model"],
                    row["call_count"],
                    row["tokens_in"],
                    row["tokens_out"],
                    row["cost_usd"],
                ]
            )
        filename = f"history_cost_export_{granularity}.csv"
        return StreamingResponse(
            iter([buffer.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/workflow/{workflow_id}/validation/summary")
async def get_workflow_validation_summary(workflow_id: str) -> dict[str, Any]:
    """Return latest validation-run summary for a workflow."""
    db_path = await _resolve_db_path_from_run_or_workflow(workflow_id)
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            run_row = await (
                await db.execute(
                    """
                    SELECT validation_run_id, profile, status, tool_version, summary_json, started_at, completed_at
                    FROM validation_runs
                    WHERE workflow_id = ?
                    ORDER BY started_at DESC
                    LIMIT 1
                    """,
                    (workflow_id,),
                )
            ).fetchone()
            if not run_row:
                return {"workflow_id": workflow_id, "latest_run": None}

            check_counts = await (
                await db.execute(
                    """
                    SELECT
                        SUM(CASE WHEN status = 'fail' AND severity = 'error' THEN 1 ELSE 0 END) AS error_count,
                        SUM(CASE WHEN severity = 'warn' AND status IN ('warn', 'fail') THEN 1 ELSE 0 END) AS warn_count,
                        COUNT(*) AS total_checks
                    FROM validation_checks
                    WHERE validation_run_id = ?
                    """,
                    (str(run_row["validation_run_id"]),),
                )
            ).fetchone()
            try:
                summary_payload = _json.loads(str(run_row["summary_json"] or "{}"))
            except Exception:
                summary_payload = {}
            latest_run = {
                "validation_run_id": str(run_row["validation_run_id"]),
                "profile": str(run_row["profile"]),
                "status": str(run_row["status"]),
                "tool_version": str(run_row["tool_version"]),
                "summary": summary_payload,
                "started_at": str(run_row["started_at"] or ""),
                "completed_at": str(run_row["completed_at"] or ""),
                "error_count": int((check_counts[0] or 0) if check_counts else 0),
                "warn_count": int((check_counts[1] or 0) if check_counts else 0),
                "total_checks": int((check_counts[2] or 0) if check_counts else 0),
            }
            return {"workflow_id": workflow_id, "latest_run": latest_run}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/workflow/{workflow_id}/validation/checks")
async def get_workflow_validation_checks(workflow_id: str, validation_run_id: str | None = None) -> dict[str, Any]:
    """Return ordered checks for a validation run (latest when omitted)."""
    db_path = await _resolve_db_path_from_run_or_workflow(workflow_id)
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            run_id = validation_run_id
            if not run_id:
                run_row = await (
                    await db.execute(
                        """
                        SELECT validation_run_id
                        FROM validation_runs
                        WHERE workflow_id = ?
                        ORDER BY started_at DESC
                        LIMIT 1
                        """,
                        (workflow_id,),
                    )
                ).fetchone()
                if not run_row:
                    return {"workflow_id": workflow_id, "validation_run_id": None, "checks": []}
                run_id = str(run_row["validation_run_id"])

            rows = await (
                await db.execute(
                    """
                    SELECT phase, check_name, status, severity, metric_value, details_json, source_module, paper_id, created_at
                    FROM validation_checks
                    WHERE validation_run_id = ?
                    ORDER BY id ASC
                    """,
                    (run_id,),
                )
            ).fetchall()
            checks: list[dict[str, Any]] = []
            for row in rows:
                try:
                    details = _json.loads(str(row["details_json"] or "{}"))
                except Exception:
                    details = {}
                checks.append(
                    {
                        "phase": str(row["phase"]),
                        "check_name": str(row["check_name"]),
                        "status": str(row["status"]),
                        "severity": str(row["severity"]),
                        "metric_value": float(row["metric_value"]) if row["metric_value"] is not None else None,
                        "details": details,
                        "source_module": str(row["source_module"]) if row["source_module"] else None,
                        "paper_id": str(row["paper_id"]) if row["paper_id"] else None,
                        "created_at": str(row["created_at"] or ""),
                    }
                )
            return {"workflow_id": workflow_id, "validation_run_id": run_id, "checks": checks}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/workflow/{workflow_id}/manuscript-audit/summary")
async def get_workflow_manuscript_audit_summary(workflow_id: str, limit: int = 20) -> dict[str, Any]:
    """Return latest and historical phase_7_audit summaries for a workflow."""
    db_path = await _resolve_db_path_from_run_or_workflow(workflow_id)
    try:
        from src.db.repositories import WorkflowRepository as _WorkflowRepository

        async with aiosqlite.connect(db_path) as db:
            repo = _WorkflowRepository(db)
            latest = await repo.get_latest_manuscript_audit(workflow_id)
            history = await repo.get_manuscript_audit_history(workflow_id, limit=max(1, min(limit, 100)))
            return {"workflow_id": workflow_id, "latest_run": latest, "history": history}
    except HTTPException:
        raise
    except Exception as exc:
        if _is_missing_table_error(exc, {"manuscript_audit_runs"}):
            return {"workflow_id": workflow_id, "latest_run": None, "history": []}
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/workflow/{workflow_id}/manuscript-audit/findings")
async def get_workflow_manuscript_audit_findings(
    workflow_id: str,
    audit_run_id: str | None = None,
) -> dict[str, Any]:
    """Return findings for a manuscript audit run (latest when omitted)."""
    db_path = await _resolve_db_path_from_run_or_workflow(workflow_id)
    try:
        from src.db.repositories import WorkflowRepository as _WorkflowRepository

        async with aiosqlite.connect(db_path) as db:
            repo = _WorkflowRepository(db)
            run_id = audit_run_id
            if not run_id:
                latest = await repo.get_latest_manuscript_audit(workflow_id)
                if latest is None:
                    return {"workflow_id": workflow_id, "audit_run_id": None, "findings": []}
                run_id = str(latest["audit_run_id"])
            else:
                scoped_run = await repo.get_manuscript_audit_run(workflow_id, str(run_id))
                if scoped_run is None:
                    return {"workflow_id": workflow_id, "audit_run_id": None, "findings": []}
            findings = await repo.get_manuscript_audit_findings(str(run_id))
            return {"workflow_id": workflow_id, "audit_run_id": run_id, "findings": findings}
    except HTTPException:
        raise
    except Exception as exc:
        if _is_missing_table_error(exc, {"manuscript_audit_runs", "manuscript_audit_findings"}):
            return {"workflow_id": workflow_id, "audit_run_id": None, "findings": []}
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/run/{run_id}/manuscript-audit")
async def get_run_manuscript_audit(run_id: str, history_limit: int = 20) -> dict[str, Any]:
    """Return manuscript audit payload for a run/workflow identifier."""
    db_path = await _resolve_db_path_from_run_or_workflow(run_id)
    workflow_id = run_id
    try:
        from src.db.repositories import WorkflowRepository as _WorkflowRepository

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            repo = _WorkflowRepository(db)
            wf_row = await (
                await db.execute(
                    "SELECT workflow_id FROM workflows ORDER BY updated_at DESC, rowid DESC LIMIT 1"
                )
            ).fetchone()
            workflow_id = str(wf_row["workflow_id"]) if wf_row and wf_row["workflow_id"] else run_id
            latest = await repo.get_latest_manuscript_audit(workflow_id)
            history = await repo.get_manuscript_audit_history(workflow_id, limit=max(1, min(history_limit, 100)))
            findings: list[dict[str, Any]] = []
            if latest is not None:
                findings = await repo.get_manuscript_audit_findings(str(latest["audit_run_id"]))
            return {
                "run_id": run_id,
                "workflow_id": workflow_id,
                "latest_run": latest,
                "history": history,
                "findings": findings,
            }
    except HTTPException:
        raise
    except Exception as exc:
        if _is_missing_table_error(exc, {"manuscript_audit_runs", "manuscript_audit_findings"}):
            return {
                "run_id": run_id,
                "workflow_id": workflow_id,
                "latest_run": None,
                "history": [],
                "findings": [],
            }
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/db/{run_id}/tables")
async def get_db_tables(run_id: str) -> dict[str, Any]:
    """Vision-extracted quantitative outcome table rows grouped by paper.

    Returns outcome rows that have at least one numeric field (effect_size,
    p_value, or ci_lower) so that text-extracted rows without numeric data
    are excluded. The extraction_source field indicates the retrieval tier
    used: 'text', 'pdf_vision', 'hybrid', 'sciencedirect', 'unpaywall_pdf',
    'pmc', or 'abstract'.

    Response shape:
    {
      "total_rows": int,
      "papers": [
        {
          "paper_id": str,
          "title": str,
          "doi": str | null,
          "extraction_source": str,
          "outcomes": [ {name, effect_size, ci_lower, ci_upper, p_value, n, ...} ]
        }
      ]
    }
    """
    db_path = _get_db_path(run_id)
    try:
        import json as _json

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            # Load extraction records (data column holds full ExtractionRecord JSON)
            async with db.execute(
                """
                SELECT er.paper_id, er.data, er.extraction_source, p.title, p.doi
                FROM extraction_records er
                LEFT JOIN papers p USING (paper_id)
                WHERE er.data IS NOT NULL
                ORDER BY er.paper_id
                """
            ) as cur:
                rows = await cur.fetchall()

        papers_out: list[dict[str, Any]] = []
        total_rows = 0
        for row in rows:
            try:
                record_data: dict[str, Any] = _json.loads(row["data"] or "{}")
            except Exception:
                record_data = {}
            outcomes: list[dict[str, Any]] = record_data.get("outcomes") or []
            extraction_source: str = str(row["extraction_source"] or record_data.get("extraction_source") or "text")
            # Keep only rows with at least one numeric field
            numeric_outcomes = [o for o in outcomes if o.get("effect_size") or o.get("p_value") or o.get("ci_lower")]
            if not numeric_outcomes:
                continue
            total_rows += len(numeric_outcomes)
            papers_out.append(
                {
                    "paper_id": row["paper_id"],
                    "title": row["title"] or "",
                    "doi": row["doi"],
                    "extraction_source": extraction_source,
                    "outcomes": numeric_outcomes,
                }
            )

        return {"total_rows": total_rows, "papers": papers_out}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/db/{run_id}/rag-diagnostics")
async def get_db_rag_diagnostics(run_id: str, run_root: str = "runs") -> dict[str, Any]:
    """Return per-section RAG retrieval diagnostics for a run."""
    db_path = await _resolve_db_path_from_run_or_workflow(run_id, run_root)
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT section, query_type, rerank_enabled, candidate_k, final_k,
                       retrieved_count, status, selected_chunks_json, error_message,
                       latency_ms, created_at
                FROM rag_retrieval_diagnostics
                ORDER BY created_at ASC
                """
            ) as cur:
                rows = await cur.fetchall()
        records: list[dict[str, Any]] = []
        for row in rows:
            chunks: list[dict[str, Any]] = []
            try:
                chunks = _json.loads(row["selected_chunks_json"] or "[]")
            except Exception:
                chunks = []
            records.append(
                {
                    "section": row["section"],
                    "query_type": row["query_type"],
                    "rerank_enabled": bool(row["rerank_enabled"]),
                    "candidate_k": row["candidate_k"],
                    "final_k": row["final_k"],
                    "retrieved_count": row["retrieved_count"],
                    "status": row["status"],
                    "selected_chunks": chunks,
                    "error_message": row["error_message"],
                    "latency_ms": row["latency_ms"],
                    "created_at": row["created_at"],
                }
            )
        return {"total": len(records), "records": records}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Run artifacts + export endpoints
# ---------------------------------------------------------------------------


@app.get("/api/run/{run_id}/artifacts")
async def get_run_artifacts(run_id: str) -> dict[str, Any]:
    """Return the run_summary.json for any run (live or historically attached)."""
    db_path = _get_db_path(run_id)
    summary = pathlib.Path(db_path).parent / "run_summary.json"
    if not summary.exists():
        raise HTTPException(status_code=404, detail="run_summary.json not found")
    return _json.loads(summary.read_text(encoding="utf-8"))


@app.get("/api/run/{run_id}/manuscript")
async def get_run_manuscript(run_id: str, fmt: str = "md") -> dict[str, Any]:
    """Return manuscript content, preferring DB assembly over filesystem artifacts."""
    if fmt not in {"md", "tex"}:
        raise HTTPException(status_code=422, detail="fmt must be 'md' or 'tex'")
    db_path = await _resolve_db_path_from_run_or_workflow(run_id)
    workflow_id = await _resolve_workflow_id_from_db(db_path)
    if workflow_id:
        try:
            from src.db.database import get_db as _get_db
            from src.db.repositories import WorkflowRepository as _WorkflowRepository

            async with _get_db(db_path) as db:
                repo = _WorkflowRepository(db)
                assembly = await repo.load_latest_manuscript_assembly(workflow_id, fmt)
            if assembly:
                return {
                    "source": "assembly",
                    "format": fmt,
                    "workflow_id": workflow_id,
                    "content": assembly.content,
                    "assembly_id": assembly.assembly_id,
                }
        except Exception:
            pass

    run_dir = pathlib.Path(db_path).parent
    file_path = run_dir / ("doc_manuscript.md" if fmt == "md" else "doc_manuscript.tex")
    if file_path.exists():
        return {
            "source": "file",
            "format": fmt,
            "workflow_id": workflow_id or "",
            "content": file_path.read_text(encoding="utf-8"),
            "path": str(file_path),
        }
    raise HTTPException(status_code=404, detail=f"manuscript ({fmt}) not found")


@app.get("/api/run/{run_id}/papers-reference")
async def get_papers_reference(run_id: str) -> dict[str, Any]:
    """Return included papers with metadata and file availability for the Reference tab.

    Reads from the papers_manifest.json saved during extraction and merges with
    dual_screening_results to filter to included papers only. Falls back to
    querying the DB when no manifest exists (for older runs).

    Supports both run_id (from _active_runs) and workflow_id (wf-NNNN) for
    historical runs after eviction or server restart.
    """
    db_path = await _resolve_db_path_from_run_or_workflow(run_id)
    run_dir = pathlib.Path(db_path).parent
    manifest_path = run_dir / "data_papers_manifest.json"

    manifest: dict[str, Any] = {}
    if manifest_path.exists():
        try:
            manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}

    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA journal_mode = WAL")
            await db.execute("PRAGMA synchronous = NORMAL")
            await db.execute("PRAGMA foreign_keys = ON")
            _resolved_workflow_id = run_id
            async with db.execute("SELECT workflow_id FROM workflows ORDER BY rowid DESC LIMIT 1") as _wf_cur:
                _wf_row = await _wf_cur.fetchone()
                if _wf_row and _wf_row[0]:
                    _resolved_workflow_id = str(_wf_row[0])
            rows = await _query_included_papers_rows(
                db,
                _resolved_workflow_id,
                for_fetch=False,
            )

        papers_out = []
        for row in rows:
            paper_id = row["paper_id"]
            raw_authors = row["authors"] or ""
            try:
                authors_list = _json.loads(raw_authors) if raw_authors.startswith("[") else [raw_authors]
                authors_fmt = ", ".join(
                    (a.get("name") or a.get("raw_name") or str(a)) if isinstance(a, dict) else str(a)
                    for a in authors_list
                )
            except Exception:
                authors_fmt = raw_authors

            entry = manifest.get(paper_id, {})
            file_type = entry.get("file_type")
            has_file = bool(entry.get("file_path") and pathlib.Path(entry["file_path"]).exists())

            papers_out.append(
                {
                    "paper_id": paper_id,
                    "title": row["title"],
                    "authors": authors_fmt,
                    "year": row["year"],
                    "source_database": row["source_database"],
                    "doi": row["doi"] or entry.get("doi", ""),
                    "url": row["url"] or entry.get("url", ""),
                    "country": row["country"],
                    "retrieval_source": entry.get("source", "abstract"),
                    "has_file": has_file,
                    "file_type": file_type,
                }
            )

        return {"papers": papers_out, "total": len(papers_out)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/run/{run_id}/papers/{paper_id}/file")
async def get_paper_file(run_id: str, paper_id: str) -> StreamingResponse:
    """Stream the saved full-text file (PDF or TXT) for an included paper.

    Returns the file with appropriate Content-Type. Returns 404 when the file
    was not retrieved during extraction (abstract-only extraction run).

    Supports both run_id and workflow_id (wf-NNNN) for historical runs.
    """
    db_path = await _resolve_db_path_from_run_or_workflow(run_id)
    run_dir = pathlib.Path(db_path).parent
    manifest_path = run_dir / "data_papers_manifest.json"

    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="No papers manifest found for this run.")

    try:
        manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read manifest: {exc}") from exc

    entry = manifest.get(paper_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Paper {paper_id} not in manifest.")

    file_path_str = entry.get("file_path")
    if not file_path_str:
        raise HTTPException(
            status_code=404,
            detail="Full-text file not available for this paper. Extraction used abstract only.",
        )

    file_path = pathlib.Path(file_path_str)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Full-text file not found on disk.")

    media_type = "application/pdf" if file_path.suffix == ".pdf" else "text/plain"
    safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in (entry.get("title", paper_id)[:60]))
    filename = f"{safe_title}{file_path.suffix}"

    async def file_iterator() -> Any:
        with open(file_path, "rb") as fh:
            while chunk := fh.read(65536):
                yield chunk

    return StreamingResponse(
        file_iterator(),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/run/{run_id}/studies-files.zip")
async def download_study_files_zip(run_id: str) -> StreamingResponse:
    """Download all available included-study full-text files as a ZIP archive.

    Supports both active run_id and historical workflow_id values in *run_id*.
    Includes files listed in data_papers_manifest.json for papers that are part
    of the included set (fulltext include when present, extraction fallback).
    """
    db_path = await _resolve_db_path_from_run_or_workflow(run_id)
    run_dir = pathlib.Path(db_path).parent
    manifest_path = run_dir / "data_papers_manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="No papers manifest found for this run.")

    try:
        manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read manifest: {exc}") from exc
    if not isinstance(manifest, dict):
        raise HTTPException(status_code=500, detail="Invalid papers manifest format.")

    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA journal_mode = WAL")
            await db.execute("PRAGMA synchronous = NORMAL")
            await db.execute("PRAGMA foreign_keys = ON")
            resolved_workflow_id = run_id
            async with db.execute("SELECT workflow_id FROM workflows ORDER BY rowid DESC LIMIT 1") as wf_cur:
                wf_row = await wf_cur.fetchone()
                if wf_row and wf_row[0]:
                    resolved_workflow_id = str(wf_row[0])
            rows = await _query_included_papers_rows(db, resolved_workflow_id, for_fetch=True)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not rows:
        raise HTTPException(status_code=404, detail="No included studies found for this run.")

    included_ids = {str(row["paper_id"]) for row in rows}
    zip_entries: list[tuple[pathlib.Path, str]] = []
    for paper_id in sorted(included_ids):
        entry = manifest.get(paper_id, {})
        if not isinstance(entry, dict):
            continue
        file_path_str = entry.get("file_path")
        if not file_path_str:
            continue
        file_path = pathlib.Path(file_path_str)
        if not file_path.exists() or not file_path.is_file():
            continue
        suffix = file_path.suffix.lower()
        if suffix not in {".pdf", ".txt"}:
            continue
        zip_entries.append((file_path, f"{paper_id}{suffix}"))

    if not zip_entries:
        raise HTTPException(
            status_code=404,
            detail="No downloadable study files found (PDF/TXT not available for included studies).",
        )

    workflow_id = await _resolve_workflow_id_from_db(db_path)
    topic = await _get_topic_for_db(db_path)
    zip_name = _make_download_slug(workflow_id or run_id, topic) + "-studies-files.zip"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path, arcname in zip_entries:
            zf.write(file_path, arcname=arcname)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )


@app.post("/api/run/{run_id}/fetch-pdfs")
async def fetch_pdfs_for_run(run_id: str) -> StreamingResponse:
    """Retroactively fetch full-text PDFs/text for all included papers in a completed run.

    Streams SSE progress events as each paper is processed, then a final 'done' event.
    Event types: 'start' (total count), 'progress' (per-paper result), 'done' (summary), 'error'.

    Uses the same PDFRetriever code path as paper screening (Unpaywall, Semantic Scholar,
    CORE, Europe PMC, ScienceDirect, PMC, arXiv, Crossref, landing-page resolver, plus
    direct URL download fallback). Saves PDF bytes to {run_dir}/papers/{paper_id}.pdf or
    full text to {paper_id}.txt, then updates data_papers_manifest.json. Safe to call
    multiple times; skips papers that already have a file saved.

    Supports both run_id and workflow_id (wf-NNNN) for historical runs.
    """
    from src.models.papers import CandidatePaper
    from src.search.pdf_retrieval import PDFRetriever

    db_path = await _resolve_db_path_from_run_or_workflow(run_id)
    run_dir = pathlib.Path(db_path).parent
    papers_dir = run_dir / "papers"
    manifest_path = run_dir / "data_papers_manifest.json"

    papers_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {}
    if manifest_path.exists():
        try:
            manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}

    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA journal_mode = WAL")
            await db.execute("PRAGMA synchronous = NORMAL")
            await db.execute("PRAGMA foreign_keys = ON")
            _resolved_workflow_id = run_id
            async with db.execute("SELECT workflow_id FROM workflows ORDER BY rowid DESC LIMIT 1") as _wf_cur:
                _wf_row = await _wf_cur.fetchone()
                if _wf_row and _wf_row[0]:
                    _resolved_workflow_id = str(_wf_row[0])
            rows = await _query_included_papers_rows(
                db,
                _resolved_workflow_id,
                for_fetch=True,
            )
    except Exception as exc:
        _fetch_err = str(exc)

        async def _error_stream() -> AsyncGenerator[str, None]:
            yield f"data: {_json.dumps({'type': 'error', 'detail': _fetch_err})}\n\n"

        return StreamingResponse(
            _error_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def _pdf_fetch_stream() -> AsyncGenerator[str, None]:
        import asyncio as _asyncio

        retriever = PDFRetriever()
        results: list[dict[str, Any]] = []
        succeeded = 0
        skipped = 0
        total = len(rows)

        yield f"data: {_json.dumps({'type': 'start', 'total': total})}\n\n"

        # Emit skipped papers immediately; collect work for the rest
        fetch_work: list[tuple[int, Any]] = []
        for idx, row in enumerate(rows):
            paper_id = row["paper_id"]
            title = row["title"] or "Untitled"
            existing = manifest.get(paper_id, {})
            existing_path = existing.get("file_path")
            if existing_path and pathlib.Path(existing_path).exists():
                skipped += 1
                results.append(
                    {
                        "paper_id": paper_id,
                        "status": "skipped",
                        "source": existing.get("source"),
                        "reason_code": existing.get("reason_code"),
                        "diagnostics": existing.get("diagnostics", []),
                    }
                )
                yield f"data: {_json.dumps({'type': 'progress', 'current': idx + 1, 'total': total, 'paper_id': paper_id, 'title': title, 'status': 'skipped', 'source': existing.get('source')})}\n\n"
            else:
                fetch_work.append((idx, row))

        if fetch_work:
            _sem = _asyncio.Semaphore(8)

            async def _fetch_one(orig_idx: int, row: Any) -> tuple:
                paper_id = row["paper_id"]
                doi = row["doi"] or ""
                url = row["url"] or ""
                title = row["title"] or "Untitled"
                saved_path: str | None = None
                source: str = "abstract"
                reason_code: str | None = None
                diagnostics: list[str] = []
                error_msg: str | None = None
                async with _sem:
                    try:
                        paper = CandidatePaper(
                            paper_id=paper_id,
                            title=title,
                            authors=[],
                            year=row["year"],
                            source_database=row["source_database"] or "",
                            doi=doi or None,
                            url=url or None,
                        )
                        ft_result = await retriever.retrieve(paper)
                        reason_code = ft_result.reason_code
                        diagnostics = list(ft_result.diagnostics or [])
                        if ft_result.success and ft_result.pdf_bytes and len(ft_result.pdf_bytes) > 1000:
                            pdf_dest = papers_dir / f"{paper_id}.pdf"
                            pdf_dest.write_bytes(ft_result.pdf_bytes)
                            saved_path = str(pdf_dest)
                            source = ft_result.source
                        elif ft_result.success and ft_result.full_text and len(ft_result.full_text) >= 500:
                            txt_dest = papers_dir / f"{paper_id}.txt"
                            txt_dest.write_text(ft_result.full_text, encoding="utf-8")
                            saved_path = str(txt_dest)
                            source = ft_result.source
                        else:
                            source = ft_result.source if ft_result.success else "abstract"
                            if not ft_result.success and ft_result.error:
                                error_msg = ft_result.error
                    except Exception as exc:  # noqa: BLE001
                        error_msg = str(exc)
                        reason_code = "exception"
                        _logger.warning("fetch-pdfs: failed for %s: %s", paper_id, exc)
                return (orig_idx, paper_id, title, saved_path, source, reason_code, diagnostics, error_msg)

            gathered = await _asyncio.gather(
                *[_fetch_one(idx, row) for idx, row in fetch_work],
                return_exceptions=True,
            )
            # Emit progress events in original submission order
            for item in sorted(
                (r for r in gathered if not isinstance(r, BaseException)),
                key=lambda t: t[0],
            ):
                orig_idx, paper_id, title, saved_path, source, reason_code, diagnostics, error_msg = item
                doi = rows[orig_idx]["doi"] or ""
                url = rows[orig_idx]["url"] or ""
                file_type = "pdf" if (saved_path and saved_path.endswith(".pdf")) else ("txt" if saved_path else None)
                manifest[paper_id] = {
                    "title": title,
                    "authors": rows[orig_idx]["authors"] or "",
                    "year": rows[orig_idx]["year"],
                    "doi": doi,
                    "url": url,
                    "source": source,
                    "reason_code": reason_code,
                    "diagnostics": diagnostics[-8:] if diagnostics else [],
                    "file_path": saved_path,
                    "file_type": file_type,
                }
                result_status = "ok" if saved_path else "failed"
                if saved_path:
                    succeeded += 1
                results.append(
                    {
                        "paper_id": paper_id,
                        "status": result_status,
                        "source": source,
                        "reason_code": reason_code,
                        "file_type": file_type,
                        "diagnostics": diagnostics[-6:] if diagnostics else [],
                        "error": error_msg,
                    }
                )
                yield f"data: {_json.dumps({'type': 'progress', 'current': orig_idx + 1, 'total': total, 'paper_id': paper_id, 'title': title, 'status': result_status, 'source': source, 'file_type': file_type})}\n\n"

        # Atomic manifest flush after all fetches complete
        manifest_path.write_text(_json.dumps(manifest, indent=2), encoding="utf-8")

        attempted = total - skipped
        failed = attempted - succeeded
        reason_counts: dict[str, int] = {}
        for r in results:
            reason = r.get("reason_code")
            if not reason:
                continue
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        yield f"data: {_json.dumps({'type': 'done', 'attempted': attempted, 'succeeded': succeeded, 'failed': failed, 'skipped': skipped, 'reason_counts': reason_counts, 'results': results})}\n\n"

    return StreamingResponse(
        _pdf_fetch_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/run/{run_id}/events")
async def get_run_events(run_id: str) -> dict[str, Any]:
    """Return the full event log for a run.

    For live or recently completed runs this is served from the in-memory
    replay buffer.  For attached historical runs the buffer is populated from
    the SQLite event_log table when the run is attached.
    """
    record = _active_runs.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"events": record.event_log}


@app.get("/api/workflow/{workflow_id}/events")
async def get_workflow_events(
    workflow_id: str,
    run_root: str = "runs",
) -> dict[str, Any]:
    """Return the full event log for a completed workflow by workflow_id.

    Reads directly from the SQLite event_log table via workflows_registry
    lookup -- no POST /api/history/attach required first.  This lets the
    frontend reload historical event logs after a page refresh without needing
    to recreate an ephemeral RunRecord in _active_runs.
    """
    db_path = await _resolve_db_path(run_root, workflow_id)
    if not db_path:
        raise HTTPException(status_code=404, detail="Workflow not found in registry")
    events = await _load_event_log_from_db(db_path)
    return {"events": events}


@app.post("/api/run/{run_id}/export")
async def trigger_export(run_id: str, run_root: str = "runs", force: bool = False) -> dict[str, Any]:
    """Package the IEEE LaTeX submission for a completed run.

    Reads workflow_id from run_summary.json, calls package_submission(),
    and returns the submission directory path plus a list of output files.

    If force=False (default) and all key files already exist in submission/
    (e.g. pre-populated by FinalizeNode), returns the existing paths immediately
    without re-running pdflatex or DOCX generation.

    Pass force=True to force a full re-package (used by the Refresh button).
    """
    db_path = await _resolve_db_path_from_run_or_workflow(run_id, run_root)
    summary_path = pathlib.Path(db_path).parent / "run_summary.json"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail="run_summary.json not found")
    summary = _json.loads(summary_path.read_text(encoding="utf-8"))
    workflow_id: str | None = summary.get("workflow_id")
    if not workflow_id:
        raise HTTPException(status_code=422, detail="workflow_id not found in run_summary")

    manuscript_md = summary.get("artifacts", {}).get("manuscript_md")
    manuscript_tex = summary.get("artifacts", {}).get("manuscript_tex")
    if manuscript_md and pathlib.Path(str(manuscript_md)).exists():
        cfg = _load_configs()[1]
        mode = getattr(getattr(cfg, "gates", None), "manuscript_contract_mode", "observe")
        _extra_paths: list[str] = []
        for _k in ("protocol", "prospero_form_md"):
            _p = summary.get("artifacts", {}).get(_k)
            if _p and pathlib.Path(str(_p)).is_file():
                _extra_paths.append(str(_p))
        _tex = str(manuscript_tex) if manuscript_tex and pathlib.Path(str(manuscript_tex)).is_file() else None
        scorecard = await compute_readiness_scorecard(
            db_path=db_path,
            workflow_id=str(workflow_id),
            manuscript_md_path=str(manuscript_md),
            manuscript_tex_path=_tex,
            extra_artifact_paths=_extra_paths,
            contract_mode=mode,
            abstract_word_limit=cfg.ieee_export.max_abstract_words,
        )
        if not scorecard.ready:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Readiness scorecard blocked export.",
                    "mode": mode,
                    "blocking_reasons": scorecard.blocking_reasons,
                    "checks": [c.model_dump() for c in scorecard.checks],
                },
            )
    # Fast path: if key files are already present and caller did not force a rebuild,
    # return existing paths immediately (avoids re-running pdflatex and DOCX generation).
    if not force:
        output_dir = summary.get("output_dir", "")
        if output_dir:
            _sub_dir = pathlib.Path(output_dir) / "submission"
            _study_pdfs_dir = _sub_dir / "study_pdfs"
            _key_files = [
                _sub_dir / "manuscript.tex",
                _sub_dir / "references.bib",
                _sub_dir / "manuscript.docx",
            ]
            if all(f.exists() for f in _key_files) and _study_pdfs_dir.exists():
                files = sorted(str(f) for f in _sub_dir.rglob("*") if f.is_file())
                return {"submission_dir": str(_sub_dir), "files": files}
    try:
        submission_dir = await package_submission(workflow_id, run_root)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Export failed: {exc}") from exc
    if submission_dir is None:
        raise HTTPException(status_code=500, detail="Export failed: manuscript not found")
    files = sorted(str(f) for f in submission_dir.rglob("*") if f.is_file())
    return {"submission_dir": str(submission_dir), "files": files}


@app.get("/api/run/{run_id}/readiness")
async def get_run_readiness(run_id: str, run_root: str = "runs") -> dict[str, Any]:
    """Return the readiness scorecard for export and operational review."""
    db_path = await _resolve_db_path_from_run_or_workflow(run_id, run_root)
    summary_path = pathlib.Path(db_path).parent / "run_summary.json"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail="run_summary.json not found")
    summary = _json.loads(summary_path.read_text(encoding="utf-8"))
    workflow_id = summary.get("workflow_id")
    if not workflow_id:
        raise HTTPException(status_code=422, detail="workflow_id not found in run_summary")
    manuscript_md = summary.get("artifacts", {}).get("manuscript_md")
    if not manuscript_md or not pathlib.Path(str(manuscript_md)).exists():
        raise HTTPException(status_code=404, detail="manuscript_md not found")
    manuscript_tex = summary.get("artifacts", {}).get("manuscript_tex")
    cfg = _load_configs()[1]
    mode = getattr(getattr(cfg, "gates", None), "manuscript_contract_mode", "observe")
    extra_paths: list[str] = []
    for _k in ("protocol", "prospero_form_md"):
        _p = summary.get("artifacts", {}).get(_k)
        if _p and pathlib.Path(str(_p)).is_file():
            extra_paths.append(str(_p))
    tex_resolved = str(manuscript_tex) if manuscript_tex and pathlib.Path(str(manuscript_tex)).is_file() else None
    scorecard = await compute_readiness_scorecard(
        db_path=db_path,
        workflow_id=str(workflow_id),
        manuscript_md_path=str(manuscript_md),
        manuscript_tex_path=tex_resolved,
        extra_artifact_paths=extra_paths,
        contract_mode=mode,
        abstract_word_limit=cfg.ieee_export.max_abstract_words,
    )
    return scorecard.model_dump()


@app.get("/api/run/{run_id}/diagnostics")
async def get_run_diagnostics(run_id: str, run_root: str = "runs") -> dict[str, Any]:
    """Return step-journal diagnostics for a workflow run.

    Aggregates readiness, step attempts, failures, recovery policies,
    writing manifests, and fallback events into one diagnostics payload.
    """
    from src.db.database import get_db as _get_db
    from src.db.repositories import WorkflowRepository as _WorkflowRepository

    db_path = await _resolve_db_path_from_run_or_workflow(run_id, run_root)
    summary_path = pathlib.Path(db_path).parent / "run_summary.json"
    workflow_id: str | None = None
    if summary_path.exists():
        summary = _json.loads(summary_path.read_text(encoding="utf-8"))
        workflow_id = summary.get("workflow_id")
    if not workflow_id:
        async with _get_db(db_path) as db:
            cur = await db.execute("SELECT workflow_id FROM workflows LIMIT 1")
            row = await cur.fetchone()
            if row:
                workflow_id = str(row[0])
    if not workflow_id:
        raise HTTPException(status_code=404, detail="workflow_id not found")
    async with _get_db(db_path) as db:
        repo = _WorkflowRepository(db)
        step_summary = await repo.get_step_summary(workflow_id)
        step_failures = await repo.count_step_failures(workflow_id)
        fallback_count = await repo.count_fallback_events(workflow_id)
        fallback_summary = await repo.get_fallback_event_summary(workflow_id)
        writing_manifests = await repo.get_writing_manifests(workflow_id)
    return {
        "workflow_id": workflow_id,
        "step_summary": step_summary,
        "step_failures": step_failures,
        "fallback_count": fallback_count,
        "fallback_summary": fallback_summary,
        "writing_manifests": [m.model_dump(mode="json") for m in writing_manifests],
    }


@app.get("/api/run/{run_id}/submission.zip")
async def download_submission_zip(run_id: str) -> StreamingResponse:
    """Stream the full IEEE submission directory as a ZIP archive.

    The submission directory must exist (call POST /api/run/{run_id}/export first).
    Returns a downloadable application/zip response named
    '<workflow_id>-<short-topic>.zip'.
    """
    db_path = await _resolve_db_path_from_run_or_workflow(run_id)
    summary_path = pathlib.Path(db_path).parent / "run_summary.json"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail="run_summary.json not found -- run export first")
    summary = _json.loads(summary_path.read_text(encoding="utf-8"))
    # Derive submission dir from output_dir stored in run_summary
    output_dir: str | None = summary.get("output_dir")
    if not output_dir:
        raise HTTPException(status_code=404, detail="output_dir not in run_summary")
    submission_dir = pathlib.Path(output_dir) / "submission"
    if not submission_dir.exists():
        raise HTTPException(
            status_code=404,
            detail="Submission directory not found -- click 'Export to LaTeX' first",
        )
    workflow_id: str = summary.get("workflow_id", run_id)
    topic = await _get_topic_for_db(db_path)
    download_name = _make_download_slug(workflow_id, topic) + ".zip"
    # Build ZIP in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fpath in sorted(submission_dir.rglob("*")):
            if fpath.is_file():
                zf.write(fpath, arcname=fpath.relative_to(submission_dir))
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={download_name}"},
    )


@app.get("/api/run/{run_id}/manuscript.docx")
async def download_manuscript_docx(run_id: str) -> FileResponse:
    """Stream the Word manuscript (.docx) generated during export.

    The submission directory must exist (call POST /api/run/{run_id}/export first).
    Returns a downloadable response named '<workflow_id>-<short-topic>.docx'.
    """
    db_path = await _resolve_db_path_from_run_or_workflow(run_id)
    summary_path = pathlib.Path(db_path).parent / "run_summary.json"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail="run_summary.json not found -- run export first")
    summary = _json.loads(summary_path.read_text(encoding="utf-8"))
    output_dir: str | None = summary.get("output_dir")
    if not output_dir:
        raise HTTPException(status_code=404, detail="output_dir not in run_summary")
    docx_path = pathlib.Path(output_dir) / "submission" / "manuscript.docx"
    if not docx_path.exists():
        raise HTTPException(
            status_code=404,
            detail="manuscript.docx not found -- click 'Export to LaTeX' first",
        )
    workflow_id: str = summary.get("workflow_id", run_id)
    topic = await _get_topic_for_db(db_path)
    download_name = _make_download_slug(workflow_id, topic) + ".docx"
    return FileResponse(
        path=str(docx_path),
        filename=download_name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


# ---------------------------------------------------------------------------
# PROSPERO registration form endpoint
# ---------------------------------------------------------------------------


@app.get("/api/run/{run_id}/prospero-form.docx")
async def download_prospero_form(run_id: str) -> FileResponse:
    """Stream the PROSPERO registration form (.docx) generated at run finalization."""
    db_path = await _resolve_db_path_from_run_or_workflow(run_id)
    summary_path = pathlib.Path(db_path).parent / "run_summary.json"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail="run_summary.json not found")
    summary = _json.loads(summary_path.read_text(encoding="utf-8"))
    output_dir: str | None = summary.get("output_dir")
    if not output_dir:
        raise HTTPException(status_code=404, detail="output_dir not in run_summary")
    docx_path = pathlib.Path(output_dir) / "doc_prospero_registration.docx"
    if not docx_path.exists():
        raise HTTPException(
            status_code=404,
            detail="doc_prospero_registration.docx not found -- run must have completed finalization",
        )
    workflow_id: str = summary.get("workflow_id", run_id)
    topic = await _get_topic_for_db(db_path)
    download_name = _make_download_slug(workflow_id, topic) + "_prospero.docx"
    return FileResponse(
        path=str(docx_path),
        filename=download_name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@app.get("/api/run/{run_id}/prospero-form.md")
async def download_prospero_form_markdown(run_id: str) -> FileResponse:
    """Stream the PROSPERO registration form markdown generated at run finalization."""
    db_path = await _resolve_db_path_from_run_or_workflow(run_id)
    summary_path = pathlib.Path(db_path).parent / "run_summary.json"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail="run_summary.json not found")
    summary = _json.loads(summary_path.read_text(encoding="utf-8"))
    output_dir: str | None = summary.get("output_dir")
    if not output_dir:
        raise HTTPException(status_code=404, detail="output_dir not in run_summary")
    md_path = pathlib.Path(output_dir) / "doc_prospero_registration.md"
    if not md_path.exists():
        raise HTTPException(
            status_code=404,
            detail="doc_prospero_registration.md not found -- run must have completed finalization",
        )
    workflow_id: str = summary.get("workflow_id", run_id)
    topic = await _get_topic_for_db(db_path)
    download_name = _make_download_slug(workflow_id, topic) + "_prospero.md"
    return FileResponse(
        path=str(md_path),
        filename=download_name,
        media_type="text/markdown; charset=utf-8",
    )


# ---------------------------------------------------------------------------
# Human-in-the-loop review endpoints
# ---------------------------------------------------------------------------


@app.get("/api/run/{run_id}/screening-summary")
async def get_screening_summary(run_id: str) -> dict:
    """Return screened papers and AI decisions for human review.

    Returns the list of papers that passed screening (included) with their
    AI decisions and rationale, grouped by stage. Used by the frontend
    'Review Screening' tab when run status is 'awaiting_review'.
    """
    db_path = _get_db_path(run_id)
    if not pathlib.Path(db_path).exists():
        raise HTTPException(status_code=404, detail="Run database not found")

    import aiosqlite

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        # Load included papers with their screening decisions
        cursor = await db.execute(
            """
            SELECT
                p.paper_id,
                p.title,
                p.authors,
                p.year,
                p.source_database,
                p.doi,
                p.abstract,
                sd.stage,
                sd.decision,
                sd.reason,
                sd.confidence
            FROM papers p
            JOIN screening_decisions sd ON p.paper_id = sd.paper_id
            WHERE sd.decision IN ('include', 'uncertain')
            ORDER BY sd.stage, p.year DESC
            """,
        )
        rows = await cursor.fetchall()
        papers = [dict(row) for row in rows]

    return {
        "run_id": run_id,
        "total": len(papers),
        "papers": papers,
        "instructions": (
            "Review AI screening decisions below. POST /api/run/{run_id}/approve-screening to proceed with extraction."
        ),
    }


class ScreeningOverride(pydantic.BaseModel):
    """A single human override of an AI screening decision (Idea 4: Active Learning)."""

    paper_id: str
    decision: str  # 'include' | 'exclude'
    reason: str | None = None


class ApproveScreeningRequest(pydantic.BaseModel):
    """Request body for approve-screening endpoint. overrides is optional for backward compat."""

    overrides: list[ScreeningOverride] = []


@app.post("/api/run/{run_id}/approve-screening")
async def approve_screening(
    run_id: str,
    body: ApproveScreeningRequest | None = None,
) -> dict[str, str]:
    """Approve AI screening decisions and resume the workflow.

    When human_in_the_loop.enabled=True, the workflow pauses after screening.
    Calling this endpoint resumes extraction by updating the registry status to 'running'.
    The HumanReviewCheckpointNode polls for this status change.

    Optionally accepts a list of human overrides (Idea 4: Active Learning).
    If overrides are present, they are saved to screening_corrections and
    used to generate refined screening criteria for subsequent runs.
    """
    db_path = _get_db_path(run_id)
    if not pathlib.Path(db_path).exists():
        raise HTTPException(status_code=404, detail="Run database not found")

    import aiosqlite

    from src.db.workflow_registry import find_by_workflow_id_fallback
    from src.db.workflow_registry import update_status as _update_status

    async with aiosqlite.connect(db_path) as _raw_db:
        cursor = await _raw_db.execute("SELECT workflow_id FROM workflows LIMIT 1")
        row = await cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="No workflow found in run database")

    workflow_id = row[0]
    run_root = str(pathlib.Path(db_path).parent.parent.parent.parent)

    # Process human overrides (Idea 4: Active Learning) -- backward-compatible no-op if empty
    overrides = (body.overrides if body else []) or []
    if overrides:
        try:
            from src.db.database import get_db as _get_run_db
            from src.screening.criteria_refinement import (
                ScreeningCorrection,
                refine_criteria_from_corrections,
                save_corrections,
                save_learned_criteria,
            )

            corrections = [
                ScreeningCorrection(
                    paper_id=o.paper_id,
                    ai_decision="unknown",
                    human_decision=o.decision,
                    human_reason=o.reason,
                )
                for o in overrides
            ]

            async with _get_run_db(db_path) as _corr_db:
                # Look up AI decisions from screening_decisions table
                for corr in corrections:
                    async with _corr_db.execute(
                        """
                        SELECT decision FROM screening_decisions
                        WHERE paper_id = ? ORDER BY created_at DESC LIMIT 1
                        """,
                        (corr.paper_id,),
                    ) as _sd_cur:
                        _sd_row = await _sd_cur.fetchone()
                        if _sd_row:
                            corr.ai_decision = _sd_row[0]

                # Look up paper titles for context
                paper_titles: dict[str, str] = {}
                async with _corr_db.execute(
                    "SELECT paper_id, title FROM papers WHERE paper_id IN ({})".format(
                        ",".join("?" * len(corrections))
                    ),
                    [c.paper_id for c in corrections],
                ) as _t_cur:
                    async for _t_row in _t_cur:
                        paper_titles[_t_row[0]] = _t_row[1] or ""

                await save_corrections(_corr_db, workflow_id, corrections)

                # Propagate human overrides to screening_decisions and dual_screening_results
                # so that HumanReviewCheckpointNode's post-approval reload picks them up.
                for _ov in overrides:
                    await _corr_db.execute(
                        """
                        INSERT INTO screening_decisions
                            (workflow_id, paper_id, stage, decision, reason,
                             exclusion_reason, reviewer_type, confidence)
                        VALUES (?, ?, 'fulltext', ?, ?, NULL, 'human_override', 1.0)
                        """,
                        (workflow_id, _ov.paper_id, _ov.decision, _ov.reason or "human override"),
                    )
                    await _corr_db.execute(
                        """
                        INSERT INTO dual_screening_results
                            (workflow_id, paper_id, stage, agreement, final_decision, adjudication_needed)
                        VALUES (?, ?, 'fulltext', 1, ?, 0)
                        ON CONFLICT(workflow_id, paper_id, stage) DO UPDATE SET
                            final_decision = excluded.final_decision,
                            agreement = excluded.agreement,
                            adjudication_needed = excluded.adjudication_needed
                        """,
                        (workflow_id, _ov.paper_id, _ov.decision),
                    )
                await _corr_db.commit()

                # Generate refined criteria via LLM (non-blocking; failures are silent)
                try:
                    import os as _os

                    from src.config.loader import load_configs as _load_cfgs
                    from src.db.repositories import WorkflowRepository as _WorkflowRepository

                    _refine_model: str | None = None
                    try:
                        _, _refine_settings = _load_cfgs(settings_path="config/settings.yaml")
                        _adjudicator_cfg = _refine_settings.agents.get("screening_adjudicator")
                        if _adjudicator_cfg:
                            _refine_model = _adjudicator_cfg.model
                    except Exception:
                        pass
                    if not _refine_model:
                        raise ValueError("screening_adjudicator model not resolved from settings.yaml")
                    learned = await refine_criteria_from_corrections(
                        corrections,
                        paper_titles,
                        model_name=_refine_model,
                        api_key=_os.environ.get("GEMINI_API_KEY", ""),
                        repository=_WorkflowRepository(_corr_db),
                        workflow_id=workflow_id,
                    )
                    if learned:
                        await save_learned_criteria(_corr_db, workflow_id, learned)
                except Exception as _rf_exc:
                    import logging as _logging

                    _logging.getLogger(__name__).warning("Criteria refinement failed (non-fatal): %s", _rf_exc)
        except Exception as _al_exc:
            import logging as _al_log

            _al_log.getLogger(__name__).warning("Active learning processing failed (non-fatal): %s", _al_exc)

    entry = await find_by_workflow_id_fallback(run_root, workflow_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Workflow not found in registry")

    await _update_status(run_root, workflow_id, "running")

    return {
        "status": "approved",
        "workflow_id": workflow_id,
        "overrides_processed": str(len(overrides)),
        "message": "Screening approved. Extraction will resume shortly.",
    }


@app.get("/api/run/{run_id}/knowledge-graph")
async def get_knowledge_graph(run_id: str) -> dict:
    """Return the evidence knowledge graph for a completed run (Idea 5).

    Returns JSON with nodes, edges, communities, and research gaps for
    visualization in the EvidenceNetworkViz frontend component.
    """
    import json as _json

    db_path = _get_db_path(run_id)
    if not pathlib.Path(db_path).exists():
        raise HTTPException(status_code=404, detail="Run database not found")

    import aiosqlite

    async with aiosqlite.connect(db_path) as _kg_db:
        _kg_db.row_factory = aiosqlite.Row

        # Get workflow_id
        async with _kg_db.execute("SELECT workflow_id FROM workflows LIMIT 1") as _wc:
            _wf_row = await _wc.fetchone()
        if not _wf_row:
            raise HTTPException(status_code=404, detail="No workflow found")
        _wf_id = _wf_row[0]

        # Load nodes (papers with community assignments)
        # study_design lives in extraction_records; LEFT JOIN so unextracted papers still appear.
        nodes: list[dict] = []
        async with _kg_db.execute(
            "SELECT p.paper_id, p.title, p.year, COALESCE(er.study_design, 'unknown'), p.authors"
            " FROM papers p"
            " LEFT JOIN extraction_records er"
            "  ON er.paper_id = p.paper_id AND er.workflow_id = ?"
            " WHERE p.paper_id IN (SELECT paper_id FROM extraction_records WHERE workflow_id = ?)",
            (_wf_id, _wf_id),
        ) as _nc:
            async for _nr in _nc:
                _authors_raw = _nr[4] or ""
                _first_author = ""
                if _authors_raw:
                    try:
                        _authors_list = _json.loads(_authors_raw)
                        if isinstance(_authors_list, list) and _authors_list:
                            _first = str(_authors_list[0])
                            _first_author = _first.split()[-1] if _first.split() else _first
                        elif isinstance(_authors_list, str):
                            _first_author = _authors_list.split(",")[0].strip().split()[-1]
                    except (ValueError, TypeError):
                        _first_part = _authors_raw.split(",")[0].strip()
                        _first_author = _first_part.split()[-1] if _first_part.split() else _first_part
                nodes.append(
                    {
                        "id": _nr[0],
                        "title": _nr[1] or "",
                        "year": _nr[2],
                        "study_design": _nr[3] or "unknown",
                        "community_id": -1,
                        "first_author": _first_author,
                        "has_multiple_authors": "," in _authors_raw,
                    }
                )

        # Attach community IDs
        community_map: dict[str, int] = {}
        async with _kg_db.execute(
            "SELECT community_id, paper_ids FROM graph_communities WHERE workflow_id = ?",
            (_wf_id,),
        ) as _cc:
            async for _cr in _cc:
                try:
                    pids = _json.loads(_cr[1])
                    for pid in pids:
                        community_map[pid] = _cr[0]
                except (TypeError, ValueError):
                    pass
        for node in nodes:
            node["community_id"] = community_map.get(node["id"], -1)

        # Load edges
        edges: list[dict] = []
        async with _kg_db.execute(
            """
            SELECT source_paper_id, target_paper_id, rel_type, weight
            FROM paper_relationships WHERE workflow_id = ?
            """,
            (_wf_id,),
        ) as _ec:
            async for _er in _ec:
                edges.append(
                    {
                        "source": _er[0],
                        "target": _er[1],
                        "rel_type": _er[2],
                        "weight": _er[3],
                    }
                )

        # Load communities
        communities: list[dict] = []
        async with _kg_db.execute(
            "SELECT community_id, paper_ids, label FROM graph_communities WHERE workflow_id = ?",
            (_wf_id,),
        ) as _comm_c:
            async for _comm_r in _comm_c:
                try:
                    pids = _json.loads(_comm_r[1])
                except (TypeError, ValueError):
                    pids = []
                communities.append(
                    {
                        "id": _comm_r[0],
                        "paper_ids": pids,
                        "label": _comm_r[2] or f"Cluster {_comm_r[0]}",
                    }
                )

        # Load research gaps
        gaps: list[dict] = []
        async with _kg_db.execute(
            "SELECT gap_id, description, gap_type, related_paper_ids FROM research_gaps WHERE workflow_id = ?",
            (_wf_id,),
        ) as _gc:
            async for _gr in _gc:
                try:
                    rids = _json.loads(_gr[3]) if _gr[3] else []
                except (TypeError, ValueError):
                    rids = []
                gaps.append(
                    {
                        "id": _gr[0],
                        "description": _gr[1],
                        "gap_type": _gr[2],
                        "related_paper_ids": rids,
                    }
                )

    return {
        "run_id": run_id,
        "nodes": nodes,
        "edges": edges,
        "communities": communities,
        "gaps": gaps,
    }


@app.get("/api/run/{run_id}/prisma-checklist")
async def get_prisma_checklist(run_id: str) -> dict:
    """Run the PRISMA 2020 checklist validator against the manuscript draft.

    Reads the manuscript.md draft from the run directory, validates it
    against all 27 PRISMA 2020 items, and returns the structured results
    so the frontend can display the compliance panel.
    """
    from src.export.prisma_checklist import validate_prisma

    # Resolve db_path: try active runs first, then registry by workflow_id.
    # This handles both live runs (short run_id) and historical runs where
    # the frontend may pass a workflow_id (wf-XXXXXXXX) directly.
    resolved_db: str | None = None
    try:
        resolved_db = _get_db_path(run_id)
    except HTTPException:
        # Not in active_runs -- look up by workflow_id in the registry.
        resolved_db = await _resolve_db_path("runs", run_id)
        if resolved_db is None:
            raise HTTPException(status_code=404, detail="Run not found")

    db_path = resolved_db
    # db_path is like runs/<run_id>/runtime.db; run_path is the run dir
    run_path = pathlib.Path(db_path).parent

    # Try to find manuscript draft (md or tex)
    md_content: str | None = None
    tex_content: str | None = None

    for candidate in [
        run_path / "doc_manuscript.md",
        run_path / "manuscript.md",
        run_path / "manuscript_draft.md",
        run_path / "outputs" / "manuscript.md",
    ]:
        if candidate.exists():
            md_content = candidate.read_text(encoding="utf-8", errors="replace")
            break

    for candidate in [
        run_path / "submission" / "manuscript.tex",
        run_path / "manuscript.tex",
    ]:
        if candidate.exists():
            tex_content = candidate.read_text(encoding="utf-8", errors="replace")
            break

    result = validate_prisma(tex_content=tex_content, md_content=md_content)
    return {
        "run_id": run_id,
        "source_state": result.source_state,
        "reported_count": result.reported_count,
        "partial_count": result.partial_count,
        "missing_count": result.missing_count,
        "not_applicable_count": result.not_applicable_count,
        "passed": result.passed,
        "total": result.primary_total,
        "item_total": len(result.items),
        "items": [
            {
                "item_id": item.item_id,
                "section": item.section,
                "description": item.description,
                "status": item.status,
                "rationale": item.rationale,
                "applies": item.applies,
                "evidence_terms": item.evidence_terms,
            }
            for item in result.items
        ],
    }


@app.get("/api/run/{run_id}/grade-sof")
async def get_grade_sof(run_id: str, fmt: str = "json") -> dict:
    """Return the GRADE Summary of Findings table for a completed run.

    Query params:
      fmt=json  (default) -- return structured JSON
      fmt=latex           -- return a LaTeX longtable string
    """
    from src.db.repositories import WorkflowRepository
    from src.quality.grade import build_sof_table

    resolved_db: str | None = None
    try:
        resolved_db = _get_db_path(run_id)
    except HTTPException:
        resolved_db = await _resolve_db_path("runs", run_id)
        if resolved_db is None:
            raise HTTPException(status_code=404, detail="Run not found")

    async with aiosqlite.connect(resolved_db) as db:
        db.row_factory = aiosqlite.Row
        repo = WorkflowRepository(db)

        # Resolve actual workflow_id for the GRADE query.
        wf_id = run_id
        try:
            async with db.execute("SELECT workflow_id FROM workflows ORDER BY rowid DESC LIMIT 1") as cur:
                row = await cur.fetchone()
                if row:
                    wf_id = row[0]
        except Exception:
            pass

        assessments = await repo.load_grade_assessments(wf_id)

    if not assessments:
        raise HTTPException(
            status_code=404,
            detail="No GRADE assessments found for this run. Run the quality assessment phase first.",
        )

    # Derive topic from the run's workflow record if possible.
    topic = run_id
    try:
        async with aiosqlite.connect(resolved_db) as db2:
            async with db2.execute("SELECT topic FROM workflows LIMIT 1") as cur2:
                row2 = await cur2.fetchone()
                if row2:
                    topic = row2[0]
    except Exception:
        pass

    table = build_sof_table(assessments, topic=topic)

    if fmt == "latex":
        from src.export.ieee_latex import render_grade_sof_latex

        return {"run_id": run_id, "latex": render_grade_sof_latex(table)}

    return {
        "run_id": run_id,
        "topic": table.topic,
        "rows": [r.model_dump() for r in table.rows],
    }


@app.post("/api/run/{run_id}/living-refresh")
async def living_refresh(run_id: str) -> RunResponse:
    """Launch an incremental living-review run based on a completed run.

    Reads the prior run's review YAML, enables living_review mode, sets
    last_search_date to today, and starts a new run. The new run inherits
    all prior included papers' DOIs so they are skipped during search.

    Only allowed when the source run is in a completed (done) state.
    """
    from datetime import date as _date

    import yaml as _yaml

    record = _active_runs.get(run_id)
    if record is None:
        # Allow historical runs not in active_runs (e.g. after restart).
        resolved_parent_db = await _resolve_db_path("runs", run_id)
        if resolved_parent_db is None:
            raise HTTPException(status_code=404, detail="Run not found")
        # For historical runs we don't have the YAML in memory -- read from disk.
        parent_yaml_path = pathlib.Path(resolved_parent_db).parent / "review.yaml"
        if not parent_yaml_path.exists():
            raise HTTPException(
                status_code=422,
                detail="review.yaml not found next to prior runtime.db; cannot refresh.",
            )
        prior_yaml = parent_yaml_path.read_text(encoding="utf-8")
        parent_db_path_value = resolved_parent_db
        prior_run_root = str(pathlib.Path(resolved_parent_db).parent.parent.parent.parent)
    else:
        if not record.done:
            raise HTTPException(
                status_code=409,
                detail="Living refresh only allowed on completed runs; this run has not finished yet.",
            )
        prior_yaml = getattr(record, "review_yaml", None)
        parent_db_path_value = record.db_path or None
        prior_run_root = record.run_root

    if not prior_yaml:
        raise HTTPException(status_code=422, detail="Prior run has no review YAML stored; cannot refresh.")

    # Parse the prior YAML, enable living review, and set today as last_search_date
    try:
        config_dict = _yaml.safe_load(prior_yaml) or {}
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to parse prior review YAML: {exc}") from exc

    config_dict["living_review"] = True
    config_dict["last_search_date"] = str(_date.today())

    new_yaml = _yaml.dump(config_dict, allow_unicode=True, default_flow_style=False)

    # Reuse the same API keys as the prior run
    req = RunRequest(
        review_yaml=new_yaml,
        gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
        openalex_api_key=os.environ.get("OPENALEX_API_KEY"),
        ieee_api_key=os.environ.get("IEEE_API_KEY"),
        pubmed_email=os.environ.get("PUBMED_EMAIL"),
        pubmed_api_key=os.environ.get("PUBMED_API_KEY"),
        perplexity_api_key=os.environ.get("PERPLEXITY_SEARCH_API_KEY"),
        semantic_scholar_api_key=os.environ.get("SEMANTIC_SCHOLAR_API_KEY"),
        crossref_email=os.environ.get("CROSSREF_EMAIL"),
        wos_api_key=os.environ.get("WOS_API_KEY"),
        scopus_api_key=os.environ.get("SCOPUS_API_KEY"),
        run_root=prior_run_root,
        parent_db_path=parent_db_path_value,
    )

    new_run_id = str(uuid.uuid4())[:8]
    topic = _extract_topic(new_yaml)

    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        prefix=f"review_{new_run_id}_",
        delete=False,
    )
    tmp.write(new_yaml)
    tmp.flush()
    tmp.close()

    new_record = _RunRecord(run_id=new_run_id, topic=topic)
    new_record.review_yaml = new_yaml
    _active_runs[new_run_id] = new_record

    task = asyncio.create_task(_run_wrapper(new_record, tmp.name, req))
    new_record.task = task

    return RunResponse(run_id=new_run_id, topic=f"[Living refresh] {topic}")


# ---------------------------------------------------------------------------
# Serve React frontend (production)
# ---------------------------------------------------------------------------

_runs_dir = pathlib.Path("runs")
_runs_dir.mkdir(parents=True, exist_ok=True)
app.mount("/runs", StaticFiles(directory=str(_runs_dir)), name="runs")

_static_dir = pathlib.Path(__file__).parent.parent.parent / "frontend" / "dist"


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str) -> FileResponse:
    """SPA catch-all: serve actual static files if they exist in the dist dir;
    otherwise serve index.html so react-router can handle client-side routes
    (e.g. /run/wf-abc123/results) on direct navigation and page refresh.

    This route is registered before the StaticFiles mount so it is evaluated
    first. For real assets (JS/CSS in dist/assets/) the file check short-circuits
    and the file is served directly with the correct MIME type. For unknown paths
    such as /run/:workflowId/:tab, the fallback to index.html lets the SPA boot."""
    if _static_dir.exists():
        candidate = _static_dir / full_path
        if candidate.exists() and candidate.is_file():
            return FileResponse(str(candidate))
        index = _static_dir / "index.html"
        if index.exists():
            return FileResponse(str(index))
    raise HTTPException(status_code=404, detail="Frontend not built. Run: pnpm build")


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
# Log streaming
# ---------------------------------------------------------------------------

_PM2_LOG_DIR = pathlib.Path.home() / ".pm2" / "logs"
_TAIL_LINES = 200


async def _log_stream_generator(log_path: pathlib.Path, request: Request) -> AsyncGenerator[dict[str, str], None]:
    """Yield the last N lines of a PM2 log file, then stream new lines as they arrive."""
    import watchfiles  # noqa: PLC0415 -- deferred to avoid startup cost when unused

    # Emit historical tail first
    if log_path.exists():
        async with aiofiles.open(log_path, errors="replace") as fh:
            raw = await fh.read()
        tail = raw.splitlines()[-_TAIL_LINES:]
        for line in tail:
            if await request.is_disconnected():
                return
            yield {"event": "log", "data": line}

    # If the file doesn't exist yet, yield a placeholder and wait
    if not log_path.exists():
        yield {"event": "log", "data": f"[waiting for {log_path.name}]"}

    last_pos = log_path.stat().st_size if log_path.exists() else 0

    # Watch for new bytes appended to the file
    async for _ in watchfiles.awatch(str(log_path.parent), stop_event=None):
        if await request.is_disconnected():
            return
        if not log_path.exists():
            continue
        current_size = log_path.stat().st_size
        if current_size <= last_pos:
            last_pos = current_size  # truncated -- reset
            continue
        async with aiofiles.open(log_path, errors="replace") as fh:
            await fh.seek(last_pos)
            new_content = await fh.read()
        last_pos = last_pos + len(new_content.encode("utf-8", errors="replace"))
        for line in new_content.splitlines():
            if await request.is_disconnected():
                return
            yield {"event": "log", "data": line}


@app.get("/api/logs/stream")
async def stream_logs(
    request: Request,
    run_id: str | None = None,
    process: str = "backend",
    log_type: str = "out",
) -> EventSourceResponse:
    """Stream a run's app.jsonl log file (when run_id given) or a PM2 log file over SSE.

    When run_id is provided the per-run app.jsonl written by structured_log is
    streamed, giving the user a log scoped to exactly that run.  This works for
    both live and historically attached runs because _active_runs always carries
    db_path for both cases.

    Falls back to the global PM2 log when no run_id is given (backward-compat).

    Args:
        run_id: Optional run identifier from _active_runs.
        process: PM2 process name -- only used when run_id is absent.
        log_type: 'out' / 'err' -- only used when run_id is absent.
    """
    if run_id:
        record = _active_runs.get(run_id)
        if not record or not record.db_path:
            raise HTTPException(status_code=404, detail="Run not found or log not yet available")
        log_path = pathlib.Path(record.db_path).parent / "app.jsonl"
    else:
        if log_type not in ("out", "err"):
            raise HTTPException(status_code=400, detail="log_type must be 'out' or 'err'")
        log_path = _PM2_LOG_DIR / f"{process}-{log_type}.log"
    return EventSourceResponse(
        _log_stream_generator(log_path, request),
        headers={"X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------


def _json_safe(obj: Any) -> str:
    def _default(o: Any) -> Any:
        try:
            return str(o)
        except Exception:
            return None

    return _json.dumps(obj, default=_default)
