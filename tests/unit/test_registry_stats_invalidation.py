"""Unit tests for registry stats write-time invalidation helpers."""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from src.db.workflow_registry import REGISTRY_SCHEMA
from src.web.routers import history as history_module
from src.web.routers.history import (
    clear_registry_stats,
    invalidate_stats_cache,
    should_use_registry_stats,
)


async def _seed_registry_with_stats(tmp_path: Path, workflow_id: str = "wf-stats-1") -> tuple[Path, str]:
    run_root = tmp_path / "runs"
    run_root.mkdir()
    registry_path = run_root / "workflows_registry.db"
    db_path = str(run_root / workflow_id / "runtime.db")

    async with aiosqlite.connect(str(registry_path)) as reg_db:
        await reg_db.executescript(REGISTRY_SCHEMA)
        for col_name, col_type in (
            ("papers_found", "INTEGER"),
            ("papers_included", "INTEGER"),
            ("total_cost", "REAL"),
            ("stats_updated_at", "TEXT"),
        ):
            try:
                await reg_db.execute(f"ALTER TABLE workflows_registry ADD COLUMN {col_name} {col_type}")
            except Exception:
                pass
        await reg_db.execute(
            """
            INSERT INTO workflows_registry
                (workflow_id, topic, config_hash, db_path, status,
                 papers_found, papers_included, total_cost, stats_updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workflow_id,
                "Stats topic",
                "hash",
                db_path,
                "completed",
                100,
                12,
                4.25,
                "2026-03-10T12:00:00",
            ),
        )
        await reg_db.commit()
    return registry_path, workflow_id


@pytest.mark.asyncio
async def test_clear_registry_stats_nulls_persisted_columns(tmp_path: Path) -> None:
    registry_path, workflow_id = await _seed_registry_with_stats(tmp_path)

    await clear_registry_stats(str(registry_path), workflow_id)

    async with aiosqlite.connect(str(registry_path)) as reg_db:
        reg_db.row_factory = aiosqlite.Row
        async with reg_db.execute(
            """
            SELECT papers_found, papers_included, total_cost, stats_updated_at
            FROM workflows_registry
            WHERE workflow_id = ?
            """,
            (workflow_id,),
        ) as cur:
            row = await cur.fetchone()

    assert row is not None
    assert row["papers_found"] is None
    assert row["papers_included"] is None
    assert row["total_cost"] is None
    assert row["stats_updated_at"] is None


@pytest.mark.asyncio
async def test_clear_registry_stats_invalidates_in_memory_cache(tmp_path: Path) -> None:
    registry_path, workflow_id = await _seed_registry_with_stats(tmp_path)
    history_module._stats_cache[workflow_id] = {"ok": True, "papers_found": 99}

    await clear_registry_stats(str(registry_path), workflow_id)

    assert workflow_id not in history_module._stats_cache


def test_invalidate_stats_cache_removes_entry() -> None:
    history_module._stats_cache["wf-evict"] = {"ok": True}
    invalidate_stats_cache("wf-evict")
    assert "wf-evict" not in history_module._stats_cache


@pytest.mark.asyncio
async def test_cleared_registry_stats_not_used_for_terminal_rows(tmp_path: Path) -> None:
    registry_path, workflow_id = await _seed_registry_with_stats(tmp_path)
    await clear_registry_stats(str(registry_path), workflow_id)

    assert (
        should_use_registry_stats(
            reg_status="completed",
            stats_updated_at=None,
            live_run_id=None,
        )
        is False
    )


@pytest.mark.asyncio
async def test_apply_terminal_registry_status_skips_stats_for_parked_states(monkeypatch) -> None:
    from src.web import state as state_module

    fetch_calls: list[str] = []
    status_updates: list[str] = []

    async def fake_update(_run_root: str, _workflow_id: str, status: str) -> None:
        status_updates.append(status)

    async def fake_fetch(_db_path: str, *, workflow_id: str | None = None) -> dict:
        fetch_calls.append(workflow_id or "")
        return {"ok": True}

    async def fake_resolve(_workflow_id: str, _run_root: str) -> str:
        return "/tmp/runtime.db"

    monkeypatch.setattr(state_module, "_update_registry_status", fake_update)
    monkeypatch.setattr(state_module._run_resolver, "resolve_registry_db_path", fake_resolve)
    monkeypatch.setattr("src.web.routers.history._fetch_run_stats", fake_fetch)

    await state_module._apply_terminal_registry_status("/runs", "wf-parked", {"status": "awaiting_review"})
    assert status_updates == ["awaiting_review"]
    assert fetch_calls == []

    await state_module._apply_terminal_registry_status("/runs", "wf-done", {"status": "completed"})
    assert "wf-done" in fetch_calls
