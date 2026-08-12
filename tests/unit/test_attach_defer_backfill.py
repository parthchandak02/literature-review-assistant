"""Attach endpoint: idempotent attach, legacy migration, deferred backfill."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import aiosqlite
import httpx
import pytest
import pytest_asyncio

from src.db.database import get_db
from src.web.app import _active_runs, app


@pytest_asyncio.fixture()
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _attach_payload(db_path: Path, workflow_id: str = "wf-attach-idempotent", topic: str = "Topic") -> dict:
    return {
        "workflow_id": workflow_id,
        "topic": topic,
        "db_path": str(db_path),
        "status": "completed",
    }


@pytest.mark.asyncio
async def test_attach_history_idempotent_returns_same_run_id(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    workflow_id = "wf-attach-idempotent"
    db_path = tmp_path / "runtime.db"
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            (workflow_id, "Topic", "hash", "completed"),
        )
        await db.commit()

    payload = await _attach_payload(db_path, workflow_id)
    try:
        first = await client.post("/api/history/attach", json=payload)
        assert first.status_code == 200
        first_run_id = first.json()["run_id"]

        second = await client.post("/api/history/attach", json=payload)
        assert second.status_code == 200
        assert second.json()["run_id"] == first_run_id
    finally:
        for run_id in list(_active_runs):
            if _active_runs[run_id].workflow_id == workflow_id:
                _active_runs.pop(run_id, None)


@pytest.mark.asyncio
async def test_attach_history_still_migrates_legacy_schema(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "legacy_runtime.db"
    async with aiosqlite.connect(str(db_path)) as db:
        await db.executescript(
            """
            CREATE TABLE workflows (workflow_id TEXT PRIMARY KEY, topic TEXT, config_hash TEXT, status TEXT);
            CREATE TABLE event_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                ts TEXT NOT NULL
            );
            CREATE TABLE decision_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decision_type TEXT NOT NULL,
                paper_id TEXT,
                decision TEXT NOT NULL,
                rationale TEXT NOT NULL,
                actor TEXT NOT NULL,
                phase TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE cost_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model TEXT NOT NULL,
                tokens_in INTEGER NOT NULL,
                tokens_out INTEGER NOT NULL,
                cost_usd REAL NOT NULL,
                latency_ms INTEGER NOT NULL,
                phase TEXT NOT NULL
            );
            """
        )
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            ("wf-legacy", "Legacy Topic", "hash", "completed"),
        )
        await db.commit()

    resp = await client.post(
        "/api/history/attach",
        json={
            "workflow_id": "wf-legacy",
            "topic": "Legacy Topic",
            "db_path": str(db_path),
            "status": "completed",
        },
    )
    assert resp.status_code == 200

    async with aiosqlite.connect(str(db_path)) as db:
        cols = await (await db.execute("PRAGMA table_info(decision_log)")).fetchall()
    col_names = {str(r[1]) for r in cols}
    assert "workflow_id" in col_names

    run_id = resp.json()["run_id"]
    _active_runs.pop(run_id, None)


@pytest.mark.asyncio
async def test_attach_history_returns_without_waiting_for_backfill(
    client: httpx.AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_id = "wf-attach-backfill"
    db_path = tmp_path / "runtime.db"
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            (workflow_id, "Topic", "hash", "completed"),
        )
        await db.commit()

    backfill_started = asyncio.Event()
    backfill_release = asyncio.Event()

    async def _slow_defer_backfill(_db_path: str) -> None:
        backfill_started.set()
        await backfill_release.wait()

    monkeypatch.setattr(
        "src.web.shared._defer_runtime_db_manuscript_backfill",
        _slow_defer_backfill,
    )

    payload = await _attach_payload(db_path, workflow_id)
    start = time.monotonic()
    resp = await client.post("/api/history/attach", json=payload)
    elapsed = time.monotonic() - start

    assert resp.status_code == 200
    assert elapsed < 1.0
    for _ in range(50):
        if backfill_started.is_set():
            break
        await asyncio.sleep(0.01)
    assert backfill_started.is_set()

    backfill_release.set()
    run_id = resp.json()["run_id"]
    _active_runs.pop(run_id, None)


@pytest.mark.asyncio
async def test_attach_history_returns_without_waiting_for_refresh_roots(
    client: httpx.AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_id = "wf-attach-refresh"
    db_path = tmp_path / "runtime.db"
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            (workflow_id, "Topic", "hash", "completed"),
        )
        await db.commit()

    refresh_started = asyncio.Event()
    refresh_release = asyncio.Event()

    async def _slow_refresh() -> None:
        refresh_started.set()
        await refresh_release.wait()

    monkeypatch.setattr("src.web.routers.history._refresh_allowed_roots", _slow_refresh)

    payload = await _attach_payload(db_path, workflow_id)
    start = time.monotonic()
    resp = await client.post("/api/history/attach", json=payload)
    elapsed = time.monotonic() - start

    assert resp.status_code == 200
    assert elapsed < 1.0
    for _ in range(50):
        if refresh_started.is_set():
            break
        await asyncio.sleep(0.01)
    assert refresh_started.is_set()

    refresh_release.set()
    run_id = resp.json()["run_id"]
    _active_runs.pop(run_id, None)
