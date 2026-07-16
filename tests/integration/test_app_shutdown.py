"""Integration tests for FastAPI lifespan shutdown behavior."""

from __future__ import annotations

import asyncio
import time

import pytest

import src.web.app as app_module
from src.web.app import app, lifespan
from src.web.state import _active_runs, _RunRecord


@pytest.mark.asyncio
async def test_lifespan_shutdown_awaits_cancelled_workflow_finalizers() -> None:
    cleanup_done = asyncio.Event()

    async def workflow_with_slow_finally() -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await asyncio.sleep(0.05)
            cleanup_done.set()
            raise

    run_id = "shutdown-finalizer-test"
    record = _RunRecord(run_id, "shutdown topic")
    record.task = asyncio.create_task(workflow_with_slow_finally())
    _active_runs[run_id] = record

    try:
        async with lifespan(app):
            pass
    finally:
        _active_runs.pop(run_id, None)

    assert cleanup_done.is_set()
    assert record.task.done()


@pytest.mark.asyncio
async def test_lifespan_shutdown_respects_bounded_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    timeout_seconds = 0.1
    monkeypatch.setattr(app_module, "_SHUTDOWN_TASK_TIMEOUT_SECONDS", timeout_seconds)

    async def workflow_with_slow_finally() -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await asyncio.sleep(5.0)
            raise

    run_id = "shutdown-timeout-test"
    record = _RunRecord(run_id, "timeout topic")
    record.task = asyncio.create_task(workflow_with_slow_finally())
    _active_runs[run_id] = record

    started = time.monotonic()
    try:
        async with lifespan(app):
            pass
    finally:
        _active_runs.pop(run_id, None)
        if record.task and not record.task.done():
            record.task.cancel()
            try:
                await record.task
            except asyncio.CancelledError:
                pass

    elapsed = time.monotonic() - started
    assert elapsed < 2.0
    assert elapsed >= timeout_seconds * 0.5
