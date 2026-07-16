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
import logging
import os
import pathlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import aiosqlite
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.db.workflow_registry import _open_registry as _open_registry_db
from src.web.routers import (
    advanced_router,
    artifacts_router,
    config_router,
    costs_router,
    database_explorer_router,
    history_router,
    run_lifecycle_router,
    screening_review_router,
    system_router,
    validation_router,
)

# Re-export helpers that tests import from src.web.app
from src.web.routers.history import _fetch_run_stats as _fetch_run_stats  # noqa: F811
from src.web.routers.run_lifecycle import _inject_csv_paths_into_yaml as _inject_csv_paths_into_yaml  # noqa: F811
from src.web.state import (
    _active_runs,
    _eviction_loop,
    _lifecycle_coordinator,
    _notes_broadcaster,
    _refresh_allowed_roots,
    _repair_registry_statuses_from_runtime,
    _run_registry,
    _RunRecord,
)
from src.web.state import _active_runs as _active_runs  # noqa: F811  -- re-export
from src.web.state import _lifecycle_coordinator as _lifecycle_coordinator  # noqa: F811  -- re-export

# Re-export symbols that external code (tests) import from src.web.app
from src.web.state import _RunRecord as _RunRecord  # noqa: F811  -- re-export

_logger = logging.getLogger(__name__)

_SHUTDOWN_TASK_TIMEOUT_SECONDS = 30.0


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    _app.state.run_registry = _run_registry
    _app.state.notes_broadcaster = _notes_broadcaster
    await _refresh_allowed_roots()
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
    eviction.cancel()
    try:
        await eviction
    except asyncio.CancelledError:
        pass

    pending_workflow_tasks: list[asyncio.Task[Any]] = []
    for record in list(_active_runs.values()):
        if not record.done and record.task and not record.task.done():
            record.task.cancel()
            pending_workflow_tasks.append(record.task)
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

    if pending_workflow_tasks:
        try:
            await asyncio.wait_for(
                asyncio.gather(*pending_workflow_tasks, return_exceptions=True),
                timeout=_SHUTDOWN_TASK_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            _logger.warning(
                "Shutdown timed out after %.0fs waiting for %d workflow task(s)",
                _SHUTDOWN_TASK_TIMEOUT_SECONDS,
                len(pending_workflow_tasks),
            )


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="LitReview API", version="1.0.0", lifespan=lifespan)

app.include_router(system_router)
app.include_router(config_router)
app.include_router(run_lifecycle_router)
app.include_router(history_router)
app.include_router(database_explorer_router)
app.include_router(costs_router)
app.include_router(validation_router)
app.include_router(artifacts_router)
app.include_router(screening_review_router)
app.include_router(advanced_router)

_default_cors_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8001",
    "http://127.0.0.1:8001",
]
_cors_env = os.getenv("LITREVIEW_CORS_ORIGINS", "").strip()
_cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()] if _cors_env else _default_cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    otherwise serve index.html so react-router can handle client-side routes."""
    if _static_dir.exists():
        candidate = _static_dir / full_path
        if candidate.exists() and candidate.is_file():
            return FileResponse(str(candidate))
        index = _static_dir / "index.html"
        if index.exists():
            return FileResponse(str(index))
    raise HTTPException(status_code=404, detail="Frontend not built. Run: pnpm build")
