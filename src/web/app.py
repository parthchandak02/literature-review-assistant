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
import datetime
import io
import json as _json
import os
import pathlib
import tempfile
import time
import uuid
import zipfile
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import aiofiles
import aiosqlite
import yaml
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import pydantic
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.db.workflow_registry import update_heartbeat as _update_registry_heartbeat
from src.db.workflow_registry import update_status as _update_registry_status
from src.export.submission_packager import package_submission
from src.orchestration.context import WebRunContext
from src.orchestration.workflow import run_workflow, run_workflow_resume
from src.utils.structured_log import load_events_from_jsonl

# ---------------------------------------------------------------------------
# State: in-process registry of active runs
# ---------------------------------------------------------------------------

class _RunRecord:
    def __init__(self, run_id: str, topic: str) -> None:
        self.run_id = run_id
        self.topic = topic
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.task: asyncio.Task[Any] | None = None
        self.done = False
        self.error: str | None = None
        self.outputs: dict[str, Any] = {}
        self.db_path: str | None = None      # set by on_db_ready callback when DB is created
        self.workflow_id: str | None = None  # set by on_workflow_id_ready callback early in SearchNode
        self.run_root: str = "runs"          # set immediately from req.run_root in _run_wrapper
        self.created_at: float = time.monotonic()  # for TTL eviction
        # Append-only log of every emitted event for replay on reconnect.
        self.event_log: list[dict[str, Any]] = []
        # Index into event_log up to which events have already been flushed to SQLite.
        # The flusher task advances this so the final flush only writes the tail.
        self._flush_index: int = 0
        # Original review YAML submitted by the user -- saved to run dir after completion.
        self.review_yaml: str = ""

_active_runs: dict[str, _RunRecord] = {}

# Evict completed run records older than 2 hours to prevent unbounded memory growth.
_RUN_TTL_SECONDS = 7200

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
            async with aiosqlite.connect(str(registry)) as db:
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
        await asyncio.sleep(1800)  # check every 30 minutes
        cutoff = time.monotonic() - _RUN_TTL_SECONDS
        stale = [k for k, v in list(_active_runs.items()) if v.done and v.created_at < cutoff]
        for k in stale:
            _active_runs.pop(k, None)

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    await _refresh_allowed_roots()
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
    run_root: str = "runs"


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


class AttachRequest(BaseModel):
    workflow_id: str
    topic: str
    db_path: str
    status: str = "completed"


# ---------------------------------------------------------------------------
# Helper: inject API keys
# ---------------------------------------------------------------------------

def _inject_env(req: RunRequest) -> None:
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


def _extract_topic(review_yaml: str) -> str:
    try:
        data = yaml.safe_load(review_yaml)
        return str(data.get("research_question", "Untitled review"))
    except Exception:
        return "Untitled review"


async def _resolve_db_path(run_root: str, workflow_id: str) -> str | None:
    """Look up db_path in the central workflows_registry.db."""
    registry = pathlib.Path(run_root) / "workflows_registry.db"
    if not registry.exists():
        return None
    try:
        async with aiosqlite.connect(str(registry)) as db:
            async with db.execute(
                "SELECT db_path FROM workflows_registry WHERE workflow_id = ?",
                (workflow_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return str(row[0]) if row else None
    except Exception:
        return None


async def _persist_event_log(db_path: str, workflow_id: str, events: list[dict[str, Any]]) -> None:
    """Write buffered SSE events to the run's SQLite database for historical replay."""
    if not events or not workflow_id:
        return
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.executemany(
                "INSERT OR IGNORE INTO event_log (workflow_id, event_type, payload, ts) VALUES (?, ?, ?, ?)",
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


async def _load_event_log_from_db(db_path: str) -> list[dict[str, Any]]:
    """Load persisted SSE events from a historical run's SQLite database.

    If the event_log table is empty (e.g. the run was launched via CLI rather
    than the web server), falls back to reading and normalizing the sibling
    app.jsonl written by structured_log.
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT payload FROM event_log ORDER BY id ASC"
            ) as cur:
                rows = await cur.fetchall()
        events: list[dict[str, Any]] = [_json.loads(row["payload"]) for row in rows]
    except Exception:
        events = []

    if not events:
        jsonl_path = pathlib.Path(db_path).parent / "app.jsonl"
        if jsonl_path.exists():
            events = load_events_from_jsonl(str(jsonl_path))

    return events


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
            if record.db_path and record.workflow_id:
                new = record.event_log[record._flush_index:]
                if new:
                    await _persist_event_log(record.db_path, record.workflow_id, new)
                    record._flush_index += len(new)
    except asyncio.CancelledError:
        pass


async def _run_wrapper(record: _RunRecord, review_path: str, req: RunRequest) -> None:
    record.run_root = req.run_root
    heartbeat_task: asyncio.Task[Any] | None = None

    def _on_db_ready(path: str) -> None:
        record.db_path = path

    def _on_workflow_id_ready(workflow_id: str, run_root: str) -> None:
        record.workflow_id = workflow_id
        record.run_root = run_root
        # Emit early so the frontend can deduplicate the sidebar before the run completes.
        event: dict[str, Any] = {"type": "workflow_id_ready", "workflow_id": workflow_id}
        record.queue.put_nowait(event)
        record.event_log.append(event)
        nonlocal heartbeat_task
        if heartbeat_task is None or heartbeat_task.done():
            heartbeat_task = asyncio.create_task(_heartbeat_loop(run_root, workflow_id))

    ctx = WebRunContext(
        queue=record.queue,
        on_db_ready=_on_db_ready,
        on_event=record.event_log.append,
        on_workflow_id_ready=_on_workflow_id_ready,
    )
    # Flusher starts immediately; no-ops until db_path and workflow_id are set.
    flusher_task: asyncio.Task[Any] = asyncio.create_task(_event_flusher_loop(record))
    try:
        outputs = await run_workflow(
            review_path=review_path,
            settings_path="config/settings.yaml",
            run_root=req.run_root,
            run_context=ctx,
            fresh=True,
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

        await record.queue.put({
            "type": "done",
            "outputs": record.outputs,
        })
    except asyncio.CancelledError:
        record.done = True
        record.error = "Cancelled"
        _cancelled_evt: dict[str, Any] = {"type": "cancelled"}
        record.event_log.append(_cancelled_evt)
        await record.queue.put(_cancelled_evt)
        if record.workflow_id and record.run_root:
            try:
                await _update_registry_status(record.run_root, record.workflow_id, "interrupted")
            except Exception:
                pass
    except Exception as exc:
        record.done = True
        record.error = str(exc)
        _error_evt: dict[str, Any] = {"type": "error", "msg": str(exc)}
        record.event_log.append(_error_evt)
        await record.queue.put(_error_evt)
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
        if record.db_path and record.workflow_id:
            remaining = record.event_log[record._flush_index:]
            if remaining:
                await _persist_event_log(record.db_path, record.workflow_id, remaining)


# ---------------------------------------------------------------------------
# Core endpoints
# ---------------------------------------------------------------------------

@app.post("/api/run", response_model=RunResponse)
async def start_run(req: RunRequest) -> RunResponse:
    _inject_env(req)
    topic = _extract_topic(req.review_yaml)
    run_id = str(uuid.uuid4())[:8]

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", prefix=f"review_{run_id}_", delete=False,
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
    csv_path.write_bytes(content)

    # Inject masterlist_csv_path into the review YAML.
    try:
        config_data = yaml.safe_load(review_yaml) or {}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid review YAML: {exc}") from exc

    config_data["masterlist_csv_path"] = str(csv_path.resolve())
    modified_yaml = yaml.dump(config_data, default_flow_style=False, allow_unicode=True)

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
        run_root=run_root,
    )
    _inject_env(req)

    topic = _extract_topic(modified_yaml)

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", prefix=f"review_{run_id}_", delete=False,
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
        # Replay buffered events the client has not yet seen. Each event is
        # tagged with its sequential id so the browser can send Last-Event-ID
        # on reconnect to skip already-received events.
        snapshot = list(record.event_log)
        for idx, event in enumerate(snapshot):
            if idx < resume_from:
                continue
            yield {"id": str(idx), "data": _json_safe(event)}

        replay_index = len(snapshot)

        # Fast-path: already completed and queue is empty after replay.
        if record.done and record.queue.empty():
            # Only emit the terminal done event if it wasn't already replayed.
            already_has_terminal = any(
                e.get("type") in ("done", "error", "cancelled")
                for e in record.event_log
            )
            if not already_has_terminal:
                yield {"id": str(replay_index), "data": _json_safe({"type": "done", "outputs": record.outputs})}
            return

        while True:
            try:
                event = await asyncio.wait_for(record.queue.get(), timeout=15.0)
                yield {"id": str(replay_index), "data": _json_safe(event)}
                replay_index += 1
                if event.get("type") in ("done", "error", "cancelled"):
                    break
            except asyncio.TimeoutError:
                yield {"event": "heartbeat", "data": "{}"}
                if record.done:
                    break

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
    return [
        RunInfo(run_id=r.run_id, topic=r.topic, done=r.done, error=r.error)
        for r in _active_runs.values()
    ]


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
        raise HTTPException(status_code=422, detail="Gemini API key is required to generate a config. Add it in the API Keys section.")
    try:
        yaml_content = await generate_config_yaml(req.research_question)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"yaml": yaml_content}


# ---------------------------------------------------------------------------
# Run history endpoints (reads workflows_registry.db from run_root)
# ---------------------------------------------------------------------------

async def _fetch_run_stats(db_path: str) -> dict[str, Any]:
    """Open a run's runtime.db and return lightweight aggregate stats.

    Uses WAL mode for safe concurrent reads (no exclusive lock needed).
    Returns {} on any error so a corrupt/missing DB never blocks the endpoint.
    Also reads the sibling run_summary.json to count generated artifacts.
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            papers_found = (await (await db.execute(
                "SELECT COUNT(*) FROM papers"
            )).fetchone())[0]
            papers_included = (await (await db.execute(
                "SELECT COUNT(*) FROM dual_screening_results WHERE final_decision='include'"
            )).fetchone())[0]
            total_cost = (await (await db.execute(
                "SELECT COALESCE(SUM(cost_usd), 0.0) FROM cost_records"
            )).fetchone())[0]

        artifacts_count: int | None = None
        summary_path = pathlib.Path(db_path).parent / "run_summary.json"
        if summary_path.exists():
            try:
                summary = _json.loads(summary_path.read_text(encoding="utf-8"))
                artifacts_count = len(summary.get("artifacts", {}))
            except Exception:
                pass

        return {
            "papers_found": int(papers_found),
            "papers_included": int(papers_included),
            "total_cost": float(total_cost),
            "artifacts_count": artifacts_count,
        }
    except Exception:
        return {}


_STALE_THRESHOLD_SECONDS = 5 * 60  # 5 minutes


def _is_stale(row: aiosqlite.Row) -> bool:
    """Return True if a 'running' row has not received a heartbeat in 5 minutes.

    Falls back to updated_at if heartbeat_at is NULL (runs that pre-date the heartbeat column).
    """
    heartbeat = row["heartbeat_at"] or row["updated_at"]
    if not heartbeat:
        return True
    try:
        import datetime
        ts = datetime.datetime.fromisoformat(str(heartbeat))
        # SQLite datetime() produces naive UTC strings; treat them as UTC.
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=datetime.timezone.utc)
        age = (datetime.datetime.now(datetime.timezone.utc) - ts).total_seconds()
        return age > _STALE_THRESHOLD_SECONDS
    except Exception:
        return True


@app.get("/api/history")
async def list_history(run_root: str = "runs") -> list[HistoryEntry]:
    """Return all past runs from the central workflows_registry.db, enriched
    with per-run aggregate stats fetched in parallel from each runtime.db."""
    registry = pathlib.Path(run_root) / "workflows_registry.db"
    if not registry.exists():
        return []
    try:
        async with aiosqlite.connect(str(registry)) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT workflow_id, topic, status, db_path,
                          COALESCE(created_at, '') AS created_at,
                          updated_at,
                          heartbeat_at
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

    # Exclude workflow_ids that are actively running in-process to avoid showing
    # the same run twice in the sidebar (live card + history entry).
    active_workflow_ids = {
        r.workflow_id
        for r in _active_runs.values()
        if r.workflow_id and not r.done
    }

    enriched: list[HistoryEntry] = []
    for row, stats in zip(rows, stat_results):
        if row["workflow_id"] in active_workflow_ids:
            continue
        s = stats if isinstance(stats, dict) else {}
        # Mark workflows that are stuck as 'running' after a crash as 'stale'.
        # We do NOT write this back to the DB; it is a computed view-only status.
        effective_status = row["status"]
        if effective_status.lower() == "running" and _is_stale(row):
            effective_status = "stale"
        enriched.append(HistoryEntry(
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
        ))
    return enriched


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
            async with aiosqlite.connect(str(registry)) as db:
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


async def _resume_wrapper(record: _RunRecord, workflow_id: str, db_path: str) -> None:
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
    try:
        from src.orchestration.resume import PHASE_ORDER as _PHASE_ORDER
        from src.db.database import get_db as _get_db
        from src.db.repositories import WorkflowRepository as _WorkflowRepository
        async with _get_db(db_path) as _chk_db:
            _checkpoints = await _WorkflowRepository(_chk_db).get_checkpoints(workflow_id)
        _phases_with_done = {
            e["phase"]
            for e in record.event_log
            if isinstance(e, dict) and e.get("type") == "phase_done"
        }
        for _phase in _PHASE_ORDER:
            if _phase in _checkpoints and _phase not in _phases_with_done:
                record.event_log.append({
                    "type": "phase_done",
                    "phase": _phase,
                    "summary": {},
                    "total": None,
                    "completed": None,
                    "synthetic": True,
                })
    except Exception:
        pass

    # Mark all pre-loaded events as already flushed so the flusher only writes
    # new events emitted during this resumed run, not the historical ones.
    record._flush_index = len(record.event_log)

    # Start heartbeat immediately -- workflow_id is already known for resumed runs.
    heartbeat_task: asyncio.Task[Any] = asyncio.create_task(
        _heartbeat_loop(run_root, workflow_id)
    )
    flusher_task: asyncio.Task[Any] = asyncio.create_task(_event_flusher_loop(record))

    # Use the review.yaml saved alongside runtime.db (written by the original web run).
    # Fall back to the global config if the file is absent (old CLI runs, early crashes).
    run_dir = pathlib.Path(db_path).parent
    stored_yaml = run_dir / "review.yaml"
    review_path = str(stored_yaml) if stored_yaml.exists() else "config/review.yaml"

    def _on_db_ready(path: str) -> None:
        record.db_path = path

    ctx = WebRunContext(
        queue=record.queue,
        on_db_ready=_on_db_ready,
        on_event=record.event_log.append,
    )
    try:
        outputs = await run_workflow_resume(
            workflow_id=workflow_id,
            review_path=review_path,
            settings_path="config/settings.yaml",
            run_root=run_root,
            run_context=ctx,
        )
        record.outputs = outputs if isinstance(outputs, dict) else {}
        record.workflow_id = workflow_id
        record.db_path = db_path
        record.done = True
        await record.queue.put({"type": "done", "outputs": record.outputs})
    except asyncio.CancelledError:
        record.done = True
        record.error = "Cancelled"
        _cancelled_resume_evt: dict[str, Any] = {"type": "cancelled"}
        record.event_log.append(_cancelled_resume_evt)
        await record.queue.put(_cancelled_resume_evt)
        try:
            await _update_registry_status(run_root, workflow_id, "interrupted")
        except Exception:
            pass
    except Exception as exc:
        record.done = True
        record.error = str(exc)
        _error_resume_evt: dict[str, Any] = {"type": "error", "msg": str(exc)}
        record.event_log.append(_error_resume_evt)
        await record.queue.put(_error_resume_evt)
        try:
            await _update_registry_status(run_root, workflow_id, "failed")
        except Exception:
            pass
    finally:
        heartbeat_task.cancel()
        flusher_task.cancel()
        # Final flush: persist any events not yet written by the flusher loop,
        # including the terminal error/cancelled event appended above.
        if record.db_path and record.workflow_id:
            remaining = record.event_log[record._flush_index:]
            if remaining:
                await _persist_event_log(record.db_path, record.workflow_id, remaining)


@app.post("/api/history/resume", response_model=RunResponse)
async def resume_run(req: ResumeRequest) -> RunResponse:
    """Resume an interrupted workflow from its last checkpoint.

    Creates a new live RunRecord (new run_id) backed by the existing workflow_id
    so the frontend can SSE-connect to watch the resumed run complete.

    If the same workflow_id is already being actively resumed, returns the
    existing run_id instead of spawning a second concurrent task.
    """
    # Guard: prevent double-resume of the same workflow (e.g. user clicks twice).
    for existing in _active_runs.values():
        if existing.workflow_id == req.workflow_id and not existing.done:
            return RunResponse(run_id=existing.run_id, topic=req.topic)

    run_id = str(uuid.uuid4())[:8]
    record = _RunRecord(run_id=run_id, topic=req.topic)
    record.db_path = req.db_path
    record.workflow_id = req.workflow_id
    _active_runs[run_id] = record
    task = asyncio.create_task(_resume_wrapper(record, req.workflow_id, req.db_path))
    record.task = task
    return RunResponse(run_id=run_id, topic=req.topic)


@app.post("/api/history/attach", response_model=RunResponse)
async def attach_history(req: AttachRequest) -> RunResponse:
    """Create a read-only completed _RunRecord from a historical workflow so
    all /api/db/{run_id}/... endpoints work for that past run."""
    run_id = str(uuid.uuid4())[:8]
    record = _RunRecord(run_id=run_id, topic=req.topic)
    record.done = True
    record.db_path = req.db_path
    record.workflow_id = req.workflow_id
    # Reflect non-completed status so the frontend can differentiate failed/interrupted runs.
    if req.status not in ("completed", "done"):
        record.error = f"Workflow {req.status}"
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
    # Inject a synthetic terminal event when the event log has no terminal event
    # (type "done"/"error"/"cancelled") and the run did not complete normally.
    # This ensures the ActivityView phase timeline settles into a final state.
    if req.status not in ("completed", "done"):
        has_terminal = any(
            isinstance(e, dict) and e.get("type") in ("done", "error", "cancelled")
            for e in record.event_log
        )
        if not has_terminal:
            record.event_log.append({
                "type": "error",
                "msg": f"Run ended with status: {req.status}",
                "ts": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
            })
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
                papers.append({
                    "paper_id": row["paper_id"],
                    "title": row["title"],
                    "authors": authors,
                    "year": row["year"],
                    "source_database": row["source_database"],
                    "doi": row["doi"],
                    "country": row["country"],
                })
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
            async with db.execute(
                f"SELECT COUNT(*) FROM screening_decisions {where}", params
            ) as cur:
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
            async with db.execute(
                "SELECT DISTINCT year FROM papers WHERE year IS NOT NULL ORDER BY year DESC"
            ) as cur:
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
        return {
            "years": years,
            "sources": sources,
            "countries": countries,
            "ta_decisions": ta_decisions,
            "ft_decisions": ft_decisions,
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
                    "SELECT DISTINCT title FROM papers WHERE title LIKE ? AND title IS NOT NULL "
                    "ORDER BY title LIMIT ?",
                    (like, limit),
                ) as cur:
                    suggestions = [row[0] for row in await cur.fetchall()]
            else:
                # Authors is stored as a JSON array; LIKE on raw string gives partial matches
                async with db.execute(
                    "SELECT DISTINCT authors FROM papers WHERE authors LIKE ? AND authors IS NOT NULL "
                    "LIMIT ?",
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
                            name = (
                                (a.get("name") or a.get("raw_name") or str(a))
                                if isinstance(a, dict)
                                else str(a)
                            )
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
                        (a.get("name") or a.get("raw_name") or str(a))
                        if isinstance(a, dict)
                        else str(a)
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

                papers.append({
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
                    "extraction_confidence": extraction_confidence,
                    "assessment_source": assessment_source,
                })

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
            async with db.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) FROM cost_records"
            ) as cur:
                total_cost = float((await cur.fetchone())[0])  # type: ignore[index]

            records = [dict(row) for row in rows]
            return {"total_cost": total_cost, "records": records}
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
async def trigger_export(run_id: str, run_root: str = "runs") -> dict[str, Any]:
    """Package the IEEE LaTeX submission for a completed run.

    Reads workflow_id from run_summary.json, calls package_submission(),
    and returns the submission directory path plus a list of output files.
    """
    db_path = _get_db_path(run_id)
    summary_path = pathlib.Path(db_path).parent / "run_summary.json"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail="run_summary.json not found")
    summary = _json.loads(summary_path.read_text(encoding="utf-8"))
    workflow_id: str | None = summary.get("workflow_id")
    if not workflow_id:
        raise HTTPException(status_code=422, detail="workflow_id not found in run_summary")
    try:
        submission_dir = await package_submission(workflow_id, run_root)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Export failed: {exc}") from exc
    if submission_dir is None:
        raise HTTPException(status_code=500, detail="Export failed: manuscript not found")
    files = sorted(str(f) for f in submission_dir.rglob("*") if f.is_file())
    return {"submission_dir": str(submission_dir), "files": files}


@app.get("/api/run/{run_id}/submission.zip")
async def download_submission_zip(run_id: str) -> StreamingResponse:
    """Stream the full IEEE submission directory as a ZIP archive.

    The submission directory must exist (call POST /api/run/{run_id}/export first).
    Returns a downloadable application/zip response.
    """
    db_path = _get_db_path(run_id)
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
        headers={"Content-Disposition": "attachment; filename=submission.zip"},
    )


@app.get("/api/run/{run_id}/manuscript.docx")
async def download_manuscript_docx(run_id: str) -> FileResponse:
    """Stream the Word manuscript (.docx) generated during export.

    The submission directory must exist (call POST /api/run/{run_id}/export first).
    Returns a downloadable application/vnd.openxmlformats-officedocument.wordprocessingml.document response.
    """
    db_path = _get_db_path(run_id)
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
    return FileResponse(
        path=str(docx_path),
        filename="manuscript.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
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
                sd.rationale,
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
            "Review AI screening decisions below. "
            "POST /api/run/{run_id}/approve-screening to proceed with extraction."
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

    from src.db.workflow_registry import find_by_workflow_id_fallback, update_status as _update_status

    import aiosqlite
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

                # Generate refined criteria via LLM (non-blocking; failures are silent)
                try:
                    import os as _os
                    learned = await refine_criteria_from_corrections(
                        corrections,
                        paper_titles,
                        api_key=_os.environ.get("GEMINI_API_KEY", ""),
                    )
                    if learned:
                        await save_learned_criteria(_corr_db, workflow_id, learned)
                except Exception as _rf_exc:
                    import logging as _logging
                    _logging.getLogger(__name__).warning(
                        "Criteria refinement failed (non-fatal): %s", _rf_exc
                    )
        except Exception as _al_exc:
            import logging as _al_log
            _al_log.getLogger(__name__).warning(
                "Active learning processing failed (non-fatal): %s", _al_exc
            )

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
        nodes: list[dict] = []
        async with _kg_db.execute(
            "SELECT paper_id, title, year, study_design FROM papers"
        ) as _nc:
            async for _nr in _nc:
                nodes.append({
                    "id": _nr[0],
                    "title": _nr[1] or "",
                    "year": _nr[2],
                    "study_design": _nr[3] or "unknown",
                    "community_id": -1,
                })

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
                edges.append({
                    "source": _er[0],
                    "target": _er[1],
                    "rel_type": _er[2],
                    "weight": _er[3],
                })

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
                communities.append({
                    "id": _comm_r[0],
                    "paper_ids": pids,
                    "label": _comm_r[2] or f"Cluster {_comm_r[0]}",
                })

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
                gaps.append({
                    "id": _gr[0],
                    "description": _gr[1],
                    "gap_type": _gr[2],
                    "related_paper_ids": rids,
                })

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

    db_path = _get_db_path(run_id)
    # db_path is like runs/<run_id>/runtime.db; run_path is the run dir
    run_path = pathlib.Path(db_path).parent

    # Try to find manuscript draft (md or tex)
    md_content: str | None = None
    tex_content: str | None = None

    for candidate in [
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
        "reported_count": result.reported_count,
        "partial_count": result.partial_count,
        "missing_count": result.missing_count,
        "passed": result.passed,
        "total": len(result.items),
        "items": [
            {
                "item_id": item.item_id,
                "section": item.section,
                "description": item.description,
                "status": item.status,
                "rationale": item.rationale,
            }
            for item in result.items
        ],
    }


@app.post("/api/run/{run_id}/living-refresh")
async def living_refresh(run_id: str) -> RunResponse:
    """Launch an incremental living-review run based on a completed run.

    Reads the prior run's review YAML, enables living_review mode, sets
    last_search_date to today, and starts a new run. The new run inherits
    all prior included papers' DOIs so they are skipped during search.

    Only allowed when the source run is in a completed (done) state.
    """
    import yaml as _yaml
    from datetime import date as _date

    record = _active_runs.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found")

    if not record.done:
        raise HTTPException(
            status_code=409,
            detail="Living refresh only allowed on completed runs; this run has not finished yet.",
        )

    prior_yaml: str | None = getattr(record, "review_yaml", None)
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
        perplexity_api_key=os.environ.get("PERPLEXITY_API_KEY"),
        semantic_scholar_api_key=os.environ.get("SEMANTIC_SCHOLAR_API_KEY"),
        crossref_email=os.environ.get("CROSSREF_EMAIL"),
        run_root=record.run_root,
    )

    new_run_id = str(uuid.uuid4())[:8]
    topic = _extract_topic(new_yaml)

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", prefix=f"review_{new_run_id}_", delete=False,
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
if _static_dir.exists():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
# Log streaming
# ---------------------------------------------------------------------------

_PM2_LOG_DIR = pathlib.Path.home() / ".pm2" / "logs"
_TAIL_LINES = 200


async def _log_stream_generator(
    log_path: pathlib.Path, request: Request
) -> AsyncGenerator[dict[str, str], None]:
    """Yield the last N lines of a PM2 log file, then stream new lines as they arrive."""
    import watchfiles  # noqa: PLC0415 -- deferred to avoid startup cost when unused

    # Emit historical tail first
    if log_path.exists():
        async with aiofiles.open(log_path, "r", errors="replace") as fh:
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
        async with aiofiles.open(log_path, "r", errors="replace") as fh:
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
