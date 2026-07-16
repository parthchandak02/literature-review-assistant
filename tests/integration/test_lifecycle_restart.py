"""Integration tests for lifecycle restart: durability, shutdown flush, SSE replay, stale resume."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import aiosqlite
import httpx
import pytest
import pytest_asyncio

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.db.workflow_registry import REGISTRY_SCHEMA
from src.web.app import _active_runs, app, lifespan
from src.web.event_store import EventStore
from src.web.state import (
    _append_event,
    _event_store,
    _flush_pending_events,
    _resume_wrapper,
    _RunRecord,
)


@pytest_asyncio.fixture()
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _init_runtime_db(db_path: Path, workflow_id: str, *, status: str = "interrupted") -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with get_db(str(db_path)) as db:
        await db.executescript(Path("src/db/schema.sql").read_text())
        repo = WorkflowRepository(db)
        await repo.create_workflow(workflow_id, "Lifecycle restart topic", "hash-1")
        await repo.update_workflow_status(workflow_id, status)
        await db.commit()


async def _init_registry(
    registry_path: Path,
    *,
    workflow_id: str,
    db_path: Path,
    status: str,
    created_at: str = "2020-01-01T00:00:00",
    updated_at: str = "2020-01-01T00:00:00",
    heartbeat_at: str | None = None,
) -> None:
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(registry_path)) as reg_db:
        await reg_db.executescript(REGISTRY_SCHEMA)
        await reg_db.execute(
            """
            INSERT OR REPLACE INTO workflows_registry
                (workflow_id, topic, config_hash, db_path, status, created_at, updated_at, heartbeat_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workflow_id,
                "Lifecycle restart topic",
                "hash-1",
                str(db_path),
                status,
                created_at,
                updated_at,
                heartbeat_at,
            ),
        )
        await reg_db.commit()


@pytest.mark.asyncio
async def test_durable_events_persist_to_runtime_db(tmp_path: Path) -> None:
    workflow_id = "wf-durable"
    db_path = tmp_path / "runtime.db"
    await _init_runtime_db(db_path, workflow_id)

    record = _RunRecord("run-durable", "Lifecycle restart topic")
    record.db_path = str(db_path)
    record.workflow_id = workflow_id

    _append_event(record, {"type": "phase_start", "phase": "phase_2_search"})
    await _event_store.await_pending_flushes(record, timeout=5.0)

    async with aiosqlite.connect(str(db_path)) as db:
        row = await (
            await db.execute(
                "SELECT event_type, payload FROM event_log WHERE workflow_id = ?",
                (workflow_id,),
            )
        ).fetchone()
    assert row is not None
    assert row[0] == "phase_start"
    payload = json.loads(row[1])
    assert payload["phase"] == "phase_2_search"


@pytest.mark.asyncio
async def test_shutdown_flushes_durable_events_on_workflow_cancel(tmp_path: Path) -> None:
    workflow_id = "wf-shutdown-flush"
    db_path = tmp_path / "runtime.db"
    await _init_runtime_db(db_path, workflow_id, status="running")

    record = _RunRecord("run-shutdown-flush", "Lifecycle restart topic")
    record.db_path = str(db_path)
    record.workflow_id = workflow_id
    _active_runs[record.run_id] = record

    async def workflow_with_durable_event() -> None:
        _append_event(record, {"type": "phase_start", "phase": "phase_3_screening"})
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await _flush_pending_events(record)
            raise

    record.task = asyncio.create_task(workflow_with_durable_event())
    await asyncio.sleep(0.05)

    try:
        async with lifespan(app):
            pass
    finally:
        _active_runs.pop(record.run_id, None)

    async with aiosqlite.connect(str(db_path)) as db:
        row = await (
            await db.execute(
                "SELECT COUNT(*) FROM event_log WHERE workflow_id = ? AND event_type = ?",
                (workflow_id, "phase_start"),
            )
        ).fetchone()
    assert row is not None
    assert int(row[0]) == 1


@pytest.mark.asyncio
async def test_sse_stream_replays_events_after_history_attach(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    workflow_id = "wf-sse-attach"
    db_path = tmp_path / "runtime.db"
    await _init_runtime_db(db_path, workflow_id, status="completed")

    async with get_db(str(db_path)) as db:
        await db.execute(
            """
            INSERT INTO event_log (workflow_id, event_type, payload, ts)
            VALUES (?, ?, ?, ?)
            """,
            (
                workflow_id,
                "phase_start",
                json.dumps(
                    {
                        "type": "phase_start",
                        "phase": "phase_2_search",
                        "msg": "search phase started",
                        "ts": "2026-03-10T10:00:00.000Z",
                    }
                ),
                "2026-03-10T10:00:00.000Z",
            ),
        )
        await db.execute(
            """
            INSERT INTO event_log (workflow_id, event_type, payload, ts)
            VALUES (?, ?, ?, ?)
            """,
            (
                workflow_id,
                "done",
                json.dumps(
                    {
                        "type": "done",
                        "outputs": {"status": "completed"},
                        "ts": "2026-03-10T11:00:00.000Z",
                    }
                ),
                "2026-03-10T11:00:00.000Z",
            ),
        )
        await db.commit()

    attach_resp = await client.post(
        "/api/history/attach",
        json={
            "workflow_id": workflow_id,
            "topic": "Lifecycle restart topic",
            "db_path": str(db_path),
            "status": "completed",
        },
    )
    assert attach_resp.status_code == 200
    run_id = attach_resp.json()["run_id"]

    stream_resp = await client.get(f"/api/stream/{run_id}")
    assert stream_resp.status_code == 200
    body = stream_resp.text
    assert "search phase started" in body
    assert '"type":"done"' in body or '"type": "done"' in body
    assert "id: 0" in body
    assert "id: 1" in body

    _active_runs.pop(run_id, None)


@pytest.mark.asyncio
async def test_resume_allowed_for_stale_registry_running_claim(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "runs"
    db_path = run_root / "2026-03-10" / "wf-stale-running-topic" / "run_01-00-00PM" / "runtime.db"
    workflow_id = "wf-stale-running"
    await _init_runtime_db(db_path, workflow_id, status="interrupted")
    await _init_registry(
        run_root / "workflows_registry.db",
        workflow_id=workflow_id,
        db_path=db_path,
        status="running",
        created_at="2020-01-01T00:00:00",
        updated_at="2020-01-01T00:00:00",
        heartbeat_at=None,
    )

    resume_started = asyncio.Event()

    async def _fake_resume(**_kwargs):  # type: ignore[no-untyped-def]
        resume_started.set()
        return {"status": "completed", "workflow_id": workflow_id}

    monkeypatch.setattr("src.web.orchestration_facade.resume_workflow_run", _fake_resume)

    resp = await client.post(
        "/api/history/resume",
        json={
            "workflow_id": workflow_id,
            "db_path": str(db_path),
            "topic": "Lifecycle restart topic",
        },
    )
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]

    await asyncio.wait_for(resume_started.wait(), timeout=5.0)

    for _ in range(30):
        runs = (await client.get("/api/runs")).json()
        item = next((r for r in runs if r["run_id"] == run_id), None)
        if item and item.get("done"):
            break
        await asyncio.sleep(0.1)

    _active_runs.pop(run_id, None)


@pytest.mark.asyncio
async def test_resume_rejects_fresh_registry_running_claim(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "runs"
    db_path = run_root / "2026-03-10" / "wf-fresh-running-topic" / "run_01-00-00PM" / "runtime.db"
    workflow_id = "wf-fresh-running"
    await _init_runtime_db(db_path, workflow_id, status="running")
    await _init_registry(
        run_root / "workflows_registry.db",
        workflow_id=workflow_id,
        db_path=db_path,
        status="running",
        created_at="datetime('now')",
        updated_at="datetime('now')",
        heartbeat_at="datetime('now')",
    )

    async with aiosqlite.connect(str(run_root / "workflows_registry.db")) as reg_db:
        await reg_db.execute(
            """
            UPDATE workflows_registry
            SET created_at = datetime('now'),
                updated_at = datetime('now'),
                heartbeat_at = datetime('now')
            WHERE workflow_id = ?
            """,
            (workflow_id,),
        )
        await reg_db.commit()

    resp = await client.post(
        "/api/history/resume",
        json={
            "workflow_id": workflow_id,
            "db_path": str(db_path),
            "topic": "Lifecycle restart topic",
        },
    )
    assert resp.status_code == 409
    assert "already running" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_resume_wrapper_flushes_durable_events_on_cancel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_id = "wf-resume-flush"
    db_path = tmp_path / "runtime.db"
    await _init_runtime_db(db_path, workflow_id, status="interrupted")

    async def _fake_resume(**kwargs):  # type: ignore[no-untyped-def]
        run_context = kwargs.get("run_context")
        if run_context is not None:
            run_context.on_event({"type": "phase_start", "phase": "phase_4_extraction_quality"})
        await asyncio.Event().wait()

    monkeypatch.setattr("src.web.orchestration_facade.resume_workflow_run", _fake_resume)

    record = _RunRecord("run-resume-flush", "Lifecycle restart topic")
    record.db_path = str(db_path)
    record.workflow_id = workflow_id
    _active_runs[record.run_id] = record
    record.task = asyncio.create_task(_resume_wrapper(record, workflow_id, str(db_path)))

    await asyncio.sleep(0.1)
    record.task.cancel()
    try:
        await record.task
    except asyncio.CancelledError:
        pass

    store = EventStore()
    await store.await_pending_flushes(record, timeout=5.0)

    async with aiosqlite.connect(str(db_path)) as db:
        row = await (
            await db.execute(
                "SELECT COUNT(*) FROM event_log WHERE workflow_id = ? AND event_type = ?",
                (workflow_id, "phase_start"),
            )
        ).fetchone()
    assert row is not None
    assert int(row[0]) >= 1

    _active_runs.pop(record.run_id, None)
