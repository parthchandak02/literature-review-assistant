"""FastAPI web backend for the systematic review tool.

Run with:
    uv run uvicorn src.web.app:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import tempfile
import uuid
from typing import Any, AsyncGenerator

import yaml
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.orchestration.context import WebRunContext
from src.orchestration.workflow import run_workflow


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

_active_runs: dict[str, _RunRecord] = {}


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Research Review API", version="1.0.0")

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
    log_root: str = "logs"
    output_root: str = "data/outputs"


class RunResponse(BaseModel):
    run_id: str
    topic: str


class RunInfo(BaseModel):
    run_id: str
    topic: str
    done: bool
    error: str | None


# ---------------------------------------------------------------------------
# Helper: inject API keys into environment for the duration of the task
# ---------------------------------------------------------------------------

def _inject_env(req: RunRequest) -> None:
    """Mutate os.environ with keys from the request.

    Safe for single-user local deployment because each run is sequential per
    process. Multi-user deployments would require per-task isolation via
    subprocesses.
    """
    os.environ["GEMINI_API_KEY"] = req.gemini_api_key
    if req.openalex_api_key:
        os.environ["OPENALEX_API_KEY"] = req.openalex_api_key
    if req.ieee_api_key:
        os.environ["IEEE_API_KEY"] = req.ieee_api_key


def _extract_topic(review_yaml: str) -> str:
    """Pull research_question from YAML text, with a safe fallback."""
    try:
        data = yaml.safe_load(review_yaml)
        return str(data.get("research_question", "Untitled review"))
    except Exception:
        return "Untitled review"


async def _run_wrapper(record: _RunRecord, review_path: str, req: RunRequest) -> None:
    """Wrap run_workflow to handle completion / error and emit terminal events."""
    ctx = WebRunContext(queue=record.queue)
    try:
        outputs = await run_workflow(
            review_path=review_path,
            settings_path="config/settings.yaml",
            log_root=req.log_root,
            output_root=req.output_root,
            run_context=ctx,
            fresh=True,
        )
        record.outputs = outputs if isinstance(outputs, dict) else {}
        record.done = True
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
        # Clean up temp review file
        try:
            pathlib.Path(review_path).unlink(missing_ok=True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/run", response_model=RunResponse)
async def start_run(req: RunRequest) -> RunResponse:
    """Start a new systematic review run."""
    _inject_env(req)

    topic = _extract_topic(req.review_yaml)
    run_id = str(uuid.uuid4())[:8]

    # Write the review YAML to a temp file so run_workflow can load it
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
    _active_runs[run_id] = record

    task = asyncio.create_task(_run_wrapper(record, tmp.name, req))
    record.task = task

    return RunResponse(run_id=run_id, topic=topic)


@app.get("/api/stream/{run_id}")
async def stream_run(run_id: str) -> EventSourceResponse:
    """SSE stream of events for a running review."""
    record = _active_runs.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found")

    async def _generator() -> AsyncGenerator[dict[str, Any], None]:
        while True:
            try:
                event = await asyncio.wait_for(record.queue.get(), timeout=15.0)
                yield {"data": _json_safe(event)}
                if event.get("type") in ("done", "error", "cancelled"):
                    break
            except asyncio.TimeoutError:
                # Heartbeat keeps the SSE connection alive through long phases
                yield {"event": "heartbeat", "data": "{}"}
                if record.done:
                    break

    return EventSourceResponse(_generator())


@app.post("/api/cancel/{run_id}")
async def cancel_run(run_id: str) -> dict[str, str]:
    """Cancel an in-progress review run."""
    record = _active_runs.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if record.task and not record.task.done():
        record.task.cancel()
    return {"status": "cancelled"}


@app.get("/api/runs")
async def list_runs() -> list[RunInfo]:
    """List all runs from the current server session."""
    return [
        RunInfo(
            run_id=r.run_id,
            topic=r.topic,
            done=r.done,
            error=r.error,
        )
        for r in _active_runs.values()
    ]


@app.get("/api/results/{run_id}")
async def get_results(run_id: str) -> dict[str, Any]:
    """Return output file paths for a completed run."""
    record = _active_runs.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if not record.done:
        raise HTTPException(status_code=409, detail="Run not complete")
    return {"run_id": run_id, "outputs": record.outputs}


@app.get("/api/download")
async def download_file(path: str) -> FileResponse:
    """Serve an output file for download. Only paths inside data/outputs/ are allowed."""
    resolved = pathlib.Path(path).resolve()
    allowed_root = pathlib.Path("data/outputs").resolve()
    if not str(resolved).startswith(str(allowed_root)):
        raise HTTPException(status_code=403, detail="Access denied")
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=str(resolved), filename=resolved.name)


@app.get("/api/config/review")
async def get_review_config() -> dict[str, str]:
    """Return the default review.yaml content for the frontend editor."""
    try:
        content = pathlib.Path("config/review.yaml").read_text()
    except Exception:
        content = ""
    return {"content": content}


# ---------------------------------------------------------------------------
# Serve React frontend static build (production mode)
# ---------------------------------------------------------------------------

_static_dir = pathlib.Path(__file__).parent.parent.parent / "frontend" / "dist"
if _static_dir.exists():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

import json as _json


def _json_safe(obj: Any) -> str:
    """Serialize event dict to JSON string, skipping non-serializable values."""
    def _default(o: Any) -> Any:
        try:
            return str(o)
        except Exception:
            return None
    return _json.dumps(obj, default=_default)
