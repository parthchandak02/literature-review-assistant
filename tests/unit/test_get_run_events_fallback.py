"""SQLite read-through for GET /api/run/{run_id}/events on historical runs."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from src.db.database import get_db
from src.web.app import _active_runs, _RunRecord, app


@pytest_asyncio.fixture()
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_get_run_events_reads_sqlite_without_attach(
    client: httpx.AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_id = "wf-events-fallback"
    db_path = tmp_path / "runtime.db"
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            (workflow_id, "Topic", "hash", "completed"),
        )
        await db.execute(
            "INSERT INTO event_log (workflow_id, event_type, payload, ts) VALUES (?, ?, ?, ?)",
            (
                workflow_id,
                "phase_start",
                json.dumps({"type": "phase_start", "phase": "phase_1", "ts": "2026-03-10T10:00:00.000Z"}),
                "2026-03-10T10:00:00.000Z",
            ),
        )
        await db.commit()

    async def _resolve(_identifier: str, _run_root: str = "runs") -> str:
        return str(db_path)

    monkeypatch.setattr("src.web.routers.artifacts.resolve_runtime_db", _resolve)

    response = await client.get(f"/api/run/{workflow_id}/events")
    assert response.status_code == 200
    events = response.json()["events"]
    assert any(isinstance(e, dict) and e.get("type") == "phase_start" for e in events)


@pytest.mark.asyncio
async def test_get_run_events_returns_ram_for_done_attach_record(
    client: httpx.AsyncClient,
) -> None:
    run_id = "attach123"
    record = _RunRecord(run_id=run_id, topic="Attached")
    record.workflow_id = "wf-attached"
    record.done = True
    record.event_log = [{"type": "error", "msg": "Workflow appears orphaned", "ts": "2026-03-10T10:00:00.000Z"}]
    _active_runs[run_id] = record
    try:
        response = await client.get(f"/api/run/{run_id}/events")
        assert response.status_code == 200
        assert response.json()["events"] == record.event_log
    finally:
        _active_runs.pop(run_id, None)


@pytest.mark.asyncio
async def test_get_run_events_returns_ram_for_live_run(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = "live1234"
    workflow_id = "wf-live"
    record = _RunRecord(run_id=run_id, topic="Live topic")
    record.workflow_id = workflow_id
    record.done = False
    record.event_log = [{"type": "log", "msg": "live-only", "ts": "2026-03-10T10:00:00.000Z"}]
    _active_runs[run_id] = record
    try:

        async def _resolve(_identifier: str, _run_root: str = "runs") -> str:
            raise AssertionError("resolve_runtime_db should not be called for live runs")

        monkeypatch.setattr("src.web.routers.artifacts.resolve_runtime_db", _resolve)

        response = await client.get(f"/api/run/{run_id}/events")
        assert response.status_code == 200
        assert response.json()["events"] == record.event_log
    finally:
        _active_runs.pop(run_id, None)
