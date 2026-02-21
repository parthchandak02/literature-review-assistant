"""FastAPI web backend for the systematic review tool.

Run with:
    uv run uvicorn src.web.app:app --reload --port ${PORT:-8000}

Or via Overmind (dev, runs API + Vite together):
    overmind start -f Procfile.dev

Or via Overmind (production, single process):
    overmind start
"""

from __future__ import annotations

import asyncio
import json as _json
import os
import pathlib
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import aiosqlite
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

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
        self.db_path: str | None = None      # set once workflow completes
        self.workflow_id: str | None = None  # set once workflow completes
        self.run_root: str = "runs"
        self.created_at: float = time.monotonic()  # for TTL eviction
        # Append-only log of every emitted event for replay on reconnect.
        self.event_log: list[dict[str, Any]] = []
        # Original review YAML submitted by the user -- saved to run dir after completion.
        self.review_yaml: str = ""

_active_runs: dict[str, _RunRecord] = {}

# Evict completed run records older than 2 hours to prevent unbounded memory growth.
_RUN_TTL_SECONDS = 7200

async def _eviction_loop() -> None:
    while True:
        await asyncio.sleep(1800)  # check every 30 minutes
        cutoff = time.monotonic() - _RUN_TTL_SECONDS
        stale = [k for k, v in list(_active_runs.items()) if v.done and v.created_at < cutoff]
        for k in stale:
            _active_runs.pop(k, None)

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
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


async def _run_wrapper(record: _RunRecord, review_path: str, req: RunRequest) -> None:
    def _on_db_ready(path: str) -> None:
        record.db_path = path

    ctx = WebRunContext(
        queue=record.queue,
        on_db_ready=_on_db_ready,
        on_event=record.event_log.append,
    )
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
        await record.queue.put({"type": "cancelled"})
    except Exception as exc:
        record.done = True
        record.error = str(exc)
        await record.queue.put({"type": "error", "msg": str(exc)})
    finally:
        try:
            pathlib.Path(review_path).unlink(missing_ok=True)
        except Exception:
            pass
        # Persist the full event log to SQLite for historical replay.
        if record.db_path and record.workflow_id:
            await _persist_event_log(record.db_path, record.workflow_id, record.event_log)


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


@app.get("/api/stream/{run_id}")
async def stream_run(run_id: str) -> EventSourceResponse:
    record = _active_runs.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found")

    async def _generator() -> AsyncGenerator[dict[str, Any], None]:
        # Replay buffered events so the client always gets the full history,
        # even on page refresh or reconnect after events were already consumed
        # from the queue.
        replay_index = 0
        for event in list(record.event_log):
            yield {"data": _json_safe(event)}
            replay_index += 1

        # Fast-path: already completed and queue is empty after replay.
        if record.done and record.queue.empty():
            # Only emit the terminal done event if it wasn't already replayed.
            already_has_terminal = any(
                e.get("type") in ("done", "error", "cancelled")
                for e in record.event_log
            )
            if not already_has_terminal:
                yield {"data": _json_safe({"type": "done", "outputs": record.outputs})}
            return

        while True:
            try:
                event = await asyncio.wait_for(record.queue.get(), timeout=15.0)
                yield {"data": _json_safe(event)}
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
    allowed_root = pathlib.Path("runs").resolve()
    if not str(resolved).startswith(str(allowed_root)):
        raise HTTPException(status_code=403, detail="Access denied")
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=str(resolved), filename=resolved.name)


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
                          updated_at
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

    enriched: list[HistoryEntry] = []
    for row, stats in zip(rows, stat_results):
        s = stats if isinstance(stats, dict) else {}
        enriched.append(HistoryEntry(
            workflow_id=row["workflow_id"],
            topic=row["topic"],
            status=row["status"],
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
    review_path = str(pathlib.Path(db_path).parent / "review.yaml")
    run_root = str(pathlib.Path(db_path).parent.parent.parent)

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
        await record.queue.put({"type": "cancelled"})
    except Exception as exc:
        record.done = True
        record.error = str(exc)
        await record.queue.put({"type": "error", "msg": str(exc)})
    finally:
        if record.db_path and record.workflow_id:
            await _persist_event_log(record.db_path, record.workflow_id, record.event_log)


@app.post("/api/history/resume", response_model=RunResponse)
async def resume_run(req: ResumeRequest) -> RunResponse:
    """Resume an interrupted workflow from its last checkpoint.

    Creates a new live RunRecord (new run_id) backed by the existing workflow_id
    so the frontend can SSE-connect to watch the resumed run complete.
    """
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
    _active_runs[run_id] = record
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


@app.get("/api/db/{run_id}/papers-all")
async def get_papers_all(
    run_id: str,
    search: str = "",
    ta_decision: str = "",
    ft_decision: str = "",
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
                conditions.append("(p.title LIKE ? OR p.abstract LIKE ?)")
                params.extend([like, like])
            if ta_decision:
                conditions.append("COALESCE(ta.final_decision, '') = ?")
                params.append(ta_decision)
            if ft_decision:
                conditions.append("COALESCE(ft.final_decision, '') = ?")
                params.append(ft_decision)

            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            base_query = f"""
                FROM papers p
                LEFT JOIN dual_screening_results ta
                  ON p.paper_id = ta.paper_id AND ta.stage = 'title_abstract'
                LEFT JOIN dual_screening_results ft
                  ON p.paper_id = ft.paper_id AND ft.stage = 'fulltext'
                {where}
            """

            async with db.execute(
                f"""SELECT p.paper_id, p.title, p.authors, p.year,
                           p.source_database, p.doi, p.country,
                           ta.final_decision AS ta_decision,
                           ft.final_decision AS ft_decision
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
                papers.append({
                    "paper_id": row["paper_id"],
                    "title": row["title"],
                    "authors": authors_fmt,
                    "year": row["year"],
                    "source_database": row["source_database"],
                    "doi": row["doi"],
                    "country": row["country"],
                    "ta_decision": row["ta_decision"],
                    "ft_decision": row["ft_decision"],
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

def _json_safe(obj: Any) -> str:
    def _default(o: Any) -> Any:
        try:
            return str(o)
        except Exception:
            return None
    return _json.dumps(obj, default=_default)
