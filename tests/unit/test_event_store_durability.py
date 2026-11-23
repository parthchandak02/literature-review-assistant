"""Durability guarantees for EventStore flush/persist behavior."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch

import aiosqlite
import pytest

from src.db.database import get_db
from src.web.event_store import DURABLE_EVENT_TYPES, EventStore


@dataclass
class _StubRecord:
    event_log: list[dict] = field(default_factory=list)
    _flush_index: int = 0
    _flush_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _event_cond: asyncio.Condition = field(default_factory=asyncio.Condition)
    db_path: str | None = None
    workflow_id: str | None = None


async def _init_runtime_db(db_path: Path, workflow_id: str) -> None:
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            (workflow_id, "durability-test", "hash", "running"),
        )
        await db.commit()


@pytest.mark.asyncio
async def test_persist_raises_on_db_failure(tmp_path: Path) -> None:
    store = EventStore()
    db_path = tmp_path / "runtime.db"
    await _init_runtime_db(db_path, "wf-persist-fail")

    with patch("src.web.event_store.open_runtime_db", side_effect=RuntimeError("db locked")):
        with pytest.raises(RuntimeError, match="db locked"):
            await store.persist(str(db_path), "wf-persist-fail", [{"type": "phase_start", "ts": "t0"}])


@pytest.mark.asyncio
async def test_flush_index_not_advanced_when_persist_fails(tmp_path: Path) -> None:
    store = EventStore()
    db_path = tmp_path / "runtime.db"
    workflow_id = "wf-flush-fail"
    await _init_runtime_db(db_path, workflow_id)

    record = _StubRecord(db_path=str(db_path), workflow_id=workflow_id)
    record.event_log.append({"type": "phase_start", "phase": "phase_1", "ts": "t0"})

    with patch("src.web.event_store.open_runtime_db", side_effect=RuntimeError("write failed")):
        with pytest.raises(RuntimeError, match="write failed"):
            await store.flush_pending(record)

    assert record._flush_index == 0

    await store.flush_pending(record)
    assert record._flush_index == 1

    async with aiosqlite.connect(str(db_path)) as db:
        row = await (await db.execute("SELECT COUNT(*) FROM event_log WHERE workflow_id=?", (workflow_id,))).fetchone()
    assert row is not None
    assert int(row[0]) == 1


@pytest.mark.asyncio
async def test_append_schedules_tracked_flush_task(tmp_path: Path) -> None:
    store = EventStore()
    db_path = tmp_path / "runtime.db"
    workflow_id = "wf-tracked-flush"
    await _init_runtime_db(db_path, workflow_id)

    record = _StubRecord(db_path=str(db_path), workflow_id=workflow_id)
    store.append(record, {"type": "phase_start", "phase": "phase_1"})

    await store.await_pending_flushes(record, timeout=5.0)
    assert record._flush_index == 1

    async with aiosqlite.connect(str(db_path)) as db:
        row = await (
            await db.execute(
                "SELECT event_type, payload FROM event_log WHERE workflow_id=?",
                (workflow_id,),
            )
        ).fetchone()
    assert row is not None
    assert row[0] == "phase_start"
    payload = json.loads(row[1])
    assert payload["phase"] == "phase_1"


@pytest.mark.asyncio
async def test_append_keeps_strong_ref_to_notify_task() -> None:
    """Non-durable appends must retain the notify task until it finishes (RUF006)."""
    store = EventStore()
    record = _StubRecord()
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_notify(rec: _StubRecord) -> None:
        started.set()
        await release.wait()
        async with rec._event_cond:
            rec._event_cond.notify_all()

    with patch.object(store, "notify", side_effect=slow_notify):
        store.append(record, {"type": "progress", "msg": "x"})
        await started.wait()
        key = id(record)
        pending = store._flush_tasks.get(key, set())
        assert len(pending) == 1
        assert not next(iter(pending)).done()
        release.set()
        await store.await_pending_flushes(record, timeout=5.0)
        assert key not in store._flush_tasks


@pytest.mark.asyncio
async def test_failed_flush_retries_on_next_flush(tmp_path: Path) -> None:
    store = EventStore()
    db_path = tmp_path / "runtime.db"
    workflow_id = "wf-retry"
    await _init_runtime_db(db_path, workflow_id)

    record = _StubRecord(db_path=str(db_path), workflow_id=workflow_id)
    record.event_log.extend(
        [
            {"type": "phase_start", "phase": "phase_1", "ts": "t0"},
            {"type": "phase_done", "phase": "phase_1", "ts": "t1"},
        ]
    )

    call_count = 0
    real_open = store.persist

    async def flaky_persist(db_path_arg: str, workflow_id_arg: str, events: list[dict]) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("transient failure")
        await real_open(db_path_arg, workflow_id_arg, events)

    with patch.object(store, "persist", side_effect=flaky_persist):
        with pytest.raises(RuntimeError, match="transient failure"):
            await store.flush_pending(record)
        assert record._flush_index == 0

        await store.flush_pending(record)
        assert record._flush_index == 2

    async with aiosqlite.connect(str(db_path)) as db:
        row = await (await db.execute("SELECT COUNT(*) FROM event_log WHERE workflow_id=?", (workflow_id,))).fetchone()
    assert row is not None
    assert int(row[0]) == 2


def test_durable_event_types_include_terminal_markers() -> None:
    assert {"done", "error", "cancelled", "phase_start", "phase_done"}.issubset(DURABLE_EVENT_TYPES)


@pytest.mark.asyncio
async def test_load_logs_warning_with_db_path_on_error(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = EventStore()
    db_path = tmp_path / "missing_or_corrupt.db"

    with caplog.at_level(logging.WARNING, logger="src.web.event_store"):
        with patch("src.web.event_store.connect_sqlite", side_effect=OSError("disk error")):
            events = await store.load(str(db_path))

    assert events == []
    assert any(
        record.levelno == logging.WARNING and str(db_path) in record.message and "disk error" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_append_logs_warning_when_background_flush_fails(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = EventStore()
    db_path = tmp_path / "runtime.db"
    workflow_id = "wf-bg-flush-fail"
    await _init_runtime_db(db_path, workflow_id)

    record = _StubRecord(db_path=str(db_path), workflow_id=workflow_id)
    with caplog.at_level(logging.WARNING, logger="src.web.event_store"):
        with patch("src.web.event_store.open_runtime_db", side_effect=RuntimeError("sqlite busy")):
            store.append(record, {"type": "phase_start", "phase": "phase_1"})
            await store.await_pending_flushes(record, timeout=5.0)

    assert record._flush_index == 0
    assert any(
        rec.levelno == logging.WARNING
        and "flush_pending" in rec.message
        and workflow_id in rec.message
        and str(db_path) in rec.message
        and "sqlite busy" in rec.message
        for rec in caplog.records
    )


def test_append_without_running_loop_logs_debug_context(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = EventStore()
    record = _StubRecord(db_path="/tmp/runtime.db", workflow_id="wf-no-loop")

    with caplog.at_level(logging.DEBUG, logger="src.web.event_store"):
        store.append(record, {"type": "phase_start", "phase": "phase_1"})

    assert len(record.event_log) == 1
    assert any(
        rec.levelno == logging.DEBUG
        and "no running event loop" in rec.message
        and "wf-no-loop" in rec.message
        and "phase_start" in rec.message
        for rec in caplog.records
    )


@pytest.mark.asyncio
async def test_append_logs_warning_on_unexpected_schedule_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = EventStore()
    record = _StubRecord(db_path="/tmp/runtime.db", workflow_id="wf-sched-fail")

    with caplog.at_level(logging.WARNING, logger="src.web.event_store"):
        with patch("src.web.event_store.asyncio.create_task", side_effect=ValueError("loop closing")):
            store.append(record, {"type": "done"})

    assert len(record.event_log) == 1
    assert any(
        rec.levelno == logging.WARNING
        and "wf-sched-fail" in rec.message
        and "done" in rec.message
        and "loop closing" in rec.message
        and rec.exc_info is not None
        for rec in caplog.records
    )


@pytest.mark.asyncio
async def test_drain_all_flushes_logs_warning_on_timeout(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = EventStore()
    record = _StubRecord(db_path="/tmp/runtime.db", workflow_id="wf-drain-timeout")
    gate = asyncio.Event()

    async def stuck_notify(_rec: _StubRecord) -> None:
        await gate.wait()

    with caplog.at_level(logging.WARNING, logger="src.web.event_store"):
        with patch.object(store, "notify", side_effect=stuck_notify):
            store.append(record, {"type": "progress", "msg": "stuck"})
            await store.drain_all_flushes(timeout=0.01)

    assert any(
        rec.levelno == logging.WARNING
        and "drain_all_flushes timed out" in rec.message
        and "waiting for 1 task(s)" in rec.message
        for rec in caplog.records
    )
