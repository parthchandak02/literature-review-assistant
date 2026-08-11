"""Unit tests for GET /api/history view=rail and stats query params."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite
import httpx
import pytest
import pytest_asyncio
from fastapi import HTTPException

from src.db.workflow_registry import REGISTRY_SCHEMA
from src.web.app import app
from src.web.routers.history import (
    HistoryRailEntry,
    build_history_rail_entry,
    parse_history_view,
    should_reconcile_history_status,
)


def _registry_row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "workflow_id": "wf-rail-1",
        "topic": "Rail topic",
        "status": "completed",
        "db_path": "/tmp/runtime.db",
        "created_at": "2026-03-10T10:00:00",
        "updated_at": "2026-03-10T11:00:00",
        "heartbeat_at": None,
        "notes": "note text",
        "is_archived": 0,
        "archived_at": None,
        "is_completed_hidden": 0,
        "completed_hidden_at": None,
    }
    base.update(overrides)
    return base


@pytest_asyncio.fixture()
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture()
async def run_root_with_registry(tmp_path: Path) -> Path:
    run_root = tmp_path / "runs"
    run_root.mkdir()
    registry_path = run_root / "workflows_registry.db"

    async with aiosqlite.connect(str(registry_path)) as reg_db:
        await reg_db.executescript(REGISTRY_SCHEMA)
        try:
            await reg_db.execute("ALTER TABLE workflows_registry ADD COLUMN notes TEXT")
        except Exception:
            pass
        await reg_db.execute(
            """
            INSERT INTO workflows_registry
                (workflow_id, topic, config_hash, db_path, status, created_at, updated_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "wf-rail-1",
                "Rail topic",
                "hash",
                str(run_root / "wf-rail-1" / "runtime.db"),
                "completed",
                "2026-03-10T10:00:00",
                "2026-03-10T11:00:00",
                "sidebar note",
            ),
        )
        await reg_db.commit()
    return run_root


def test_parse_history_view_defaults_and_aliases() -> None:
    assert parse_history_view("full") == "full"
    assert parse_history_view("RAIL") == "rail"


def test_parse_history_view_rejects_unknown() -> None:
    with pytest.raises(HTTPException) as exc_info:
        parse_history_view("compact")
    assert exc_info.value.status_code == 422


def test_should_reconcile_history_status_matrix() -> None:
    assert should_reconcile_history_status(view="full", include_stats=True) is True
    assert should_reconcile_history_status(view="full", include_stats=False) is True
    assert should_reconcile_history_status(view="rail", include_stats=True) is True
    assert should_reconcile_history_status(view="rail", include_stats=False) is False


def test_build_history_rail_entry_with_stats() -> None:
    row = _registry_row()
    entry = build_history_rail_entry(
        row,
        effective_status="completed",
        live_run_id=None,
        stats={"papers_found": 10, "papers_included": 3, "total_cost": 1.25, "ok": True},
        include_stats=True,
    )
    assert entry == HistoryRailEntry(
        workflow_id="wf-rail-1",
        topic="Rail topic",
        status="completed",
        db_path="/tmp/runtime.db",
        created_at="2026-03-10T10:00:00",
        live_run_id=None,
        notes="note text",
        is_archived=False,
        is_completed_hidden=False,
        papers_found=10,
        papers_included=3,
        total_cost=1.25,
        stats_ok=True,
    )


def test_build_history_rail_entry_without_stats_omits_metrics() -> None:
    row = _registry_row()
    entry = build_history_rail_entry(
        row,
        effective_status="running",
        live_run_id="run-live",
        stats=None,
        include_stats=False,
    )
    dumped = entry.model_dump()
    assert set(dumped) == {
        "workflow_id",
        "topic",
        "status",
        "db_path",
        "created_at",
        "live_run_id",
        "is_archived",
        "is_completed_hidden",
        "notes",
        "papers_found",
        "papers_included",
        "total_cost",
        "stats_ok",
    }
    assert dumped["papers_found"] is None
    assert dumped["papers_included"] is None
    assert dumped["total_cost"] is None
    assert dumped["stats_ok"] is None
    assert dumped["db_path"] == "/tmp/runtime.db"
    assert "updated_at" not in dumped


@pytest.mark.asyncio
async def test_history_rail_view_response_shape(client: httpx.AsyncClient, run_root_with_registry: Path) -> None:
    mock_stats = AsyncMock(
        return_value={
            "ok": True,
            "papers_found": 42,
            "papers_included": 7,
            "total_cost": 3.5,
            "artifacts_count": 2,
        }
    )
    with patch("src.web.routers.history._fetch_run_stats", mock_stats):
        response = await client.get(
            "/api/history",
            params={"run_root": str(run_root_with_registry), "view": "rail", "stats": "true"},
        )

    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["workflow_id"] == "wf-rail-1"
    assert row["papers_found"] == 42
    assert row["papers_included"] == 7
    assert row["total_cost"] == 3.5
    assert row["stats_ok"] is True
    assert "db_path" in row
    assert row["db_path"]
    assert "updated_at" not in row
    assert "artifacts_count" not in row
    assert "stats_error" not in row
    assert "archived_at" not in row


@pytest.mark.asyncio
async def test_history_rail_view_stats_false_skips_runtime_db(
    client: httpx.AsyncClient,
    run_root_with_registry: Path,
) -> None:
    mock_stats = AsyncMock()
    with patch("src.web.routers.history._fetch_run_stats", mock_stats):
        response = await client.get(
            "/api/history",
            params={"run_root": str(run_root_with_registry), "view": "rail", "stats": "false"},
        )

    assert response.status_code == 200
    row = response.json()[0]
    assert row["status"] == "completed"
    assert row["papers_found"] is None
    assert row["papers_included"] is None
    assert row["total_cost"] is None
    assert row.get("stats_ok") is None
    mock_stats.assert_not_called()


@pytest.mark.asyncio
async def test_history_full_view_default_shape_unchanged(
    client: httpx.AsyncClient,
    run_root_with_registry: Path,
) -> None:
    mock_stats = AsyncMock(
        return_value={
            "ok": True,
            "papers_found": 1,
            "papers_included": 1,
            "total_cost": 0.1,
            "artifacts_count": 0,
        }
    )
    with patch("src.web.routers.history._fetch_run_stats", mock_stats):
        response = await client.get("/api/history", params={"run_root": str(run_root_with_registry)})

    assert response.status_code == 200
    row = response.json()[0]
    assert "db_path" in row
    assert "updated_at" in row
    assert "artifacts_count" in row
    assert row["stats_ok"] is True
