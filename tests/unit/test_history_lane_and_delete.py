"""Sidebar lane pins (lane_override) and delete cleanup of run directories."""

from __future__ import annotations

import os
import pathlib

import aiosqlite
import httpx
import pytest
import pytest_asyncio

from src.db import workflow_registry as reg
from src.web import app as web_app
from src.web.path_guard import RUNS_ROOTS_ENV
from src.web.run_cleanup import remove_workflow_run_dirs

WF = "wf-9901"
WF_OTHER = "wf-9902"


@pytest.fixture
def runs_root(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(RUNS_ROOTS_ENV, raising=False)
    root = tmp_path / "runs"
    root.mkdir()
    return root.resolve()


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=web_app.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _make_run_dir(root: pathlib.Path, folder: str, run_name: str = "run_01-00-00AM") -> pathlib.Path:
    run_dir = root / "2026-09-01" / folder / run_name
    run_dir.mkdir(parents=True)
    (run_dir / "runtime.db").write_bytes(b"")
    (run_dir / "doc_manuscript.md").write_text("x", encoding="utf-8")
    return run_dir


async def _register(root: pathlib.Path, workflow_id: str, run_dir: pathlib.Path, status: str = "completed") -> None:
    await reg.register(str(root), workflow_id, "Topic", "hash", str(run_dir / "runtime.db"), status=status)


async def _row(root: pathlib.Path, workflow_id: str) -> aiosqlite.Row | None:
    async with aiosqlite.connect(str(root / "workflows_registry.db")) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT is_completed_hidden, completed_hidden_at, lane_override, is_archived "
            "FROM workflows_registry WHERE workflow_id = ?",
            (workflow_id,),
        ) as cur:
            return await cur.fetchone()


# ---------------------------------------------------------------------------
# Registry persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_lane_override_round_trip_keeps_completed_flag_in_sync(runs_root: pathlib.Path) -> None:
    run_dir = _make_run_dir(runs_root, f"{WF}-topic")
    await _register(runs_root, WF, run_dir)

    await reg.set_lane_override(str(runs_root), WF, "in_progress")
    row = await _row(runs_root, WF)
    assert row["lane_override"] == "in_progress"
    assert row["is_completed_hidden"] == 0

    await reg.set_lane_override(str(runs_root), WF, "completed")
    row = await _row(runs_root, WF)
    assert row["lane_override"] == "completed"
    assert row["is_completed_hidden"] == 1
    assert row["completed_hidden_at"] is not None

    await reg.set_lane_override(str(runs_root), WF, None)
    row = await _row(runs_root, WF)
    assert row["lane_override"] is None
    assert row["is_completed_hidden"] == 0
    assert row["completed_hidden_at"] is None


@pytest.mark.asyncio
async def test_set_lane_override_rejects_unknown_lane(runs_root: pathlib.Path) -> None:
    with pytest.raises(ValueError):
        await reg.set_lane_override(str(runs_root), WF, "archived")


@pytest.mark.asyncio
async def test_legacy_endpoints_update_lane_override(runs_root: pathlib.Path) -> None:
    run_dir = _make_run_dir(runs_root, f"{WF}-topic")
    await _register(runs_root, WF, run_dir)

    await reg.hide_completed_workflow(str(runs_root), WF)
    assert (await _row(runs_root, WF))["lane_override"] == "completed"
    await reg.restore_completed_workflow(str(runs_root), WF)
    assert (await _row(runs_root, WF))["lane_override"] is None

    await reg.set_lane_override(str(runs_root), WF, "in_progress")
    await reg.archive_workflow(str(runs_root), WF)
    row = await _row(runs_root, WF)
    assert row["is_archived"] == 1
    assert row["lane_override"] == "in_progress"


def test_effective_lane_override_prefers_legacy_completed_flag() -> None:
    assert reg.effective_lane_override(None, 1) == "completed"
    assert reg.effective_lane_override("in_progress", 0) == "in_progress"
    assert reg.effective_lane_override("completed", 0) is None
    assert reg.effective_lane_override(None, 0) is None


@pytest.mark.asyncio
async def test_ensure_registry_migrates_existing_db_without_lane_column(runs_root: pathlib.Path) -> None:
    registry = runs_root / "workflows_registry.db"
    async with aiosqlite.connect(str(registry)) as db:
        await db.execute(
            "CREATE TABLE workflows_registry (workflow_id TEXT PRIMARY KEY, topic TEXT NOT NULL, "
            "config_hash TEXT NOT NULL, db_path TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'running', "
            "created_at TEXT, updated_at TEXT)"
        )
        await db.commit()
    await reg._ensure_registry(str(runs_root))
    async with aiosqlite.connect(str(registry)) as db:
        async with db.execute("PRAGMA table_info(workflows_registry)") as cur:
            columns = {r[1] for r in await cur.fetchall()}
    assert "lane_override" in columns


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lane_endpoint_persists_and_history_exposes_it(
    runs_root: pathlib.Path, client: httpx.AsyncClient
) -> None:
    run_dir = _make_run_dir(runs_root, f"{WF}-topic")
    await _register(runs_root, WF, run_dir)
    params = {"run_root": str(runs_root)}

    resp = await client.post(f"/api/history/{WF}/lane", params=params, json={"lane": "in_progress"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "lane_override": "in_progress"}

    for view in ("full", "rail"):
        rows = (await client.get("/api/history", params={**params, "view": view, "stats": "false"})).json()
        row = next(r for r in rows if r["workflow_id"] == WF)
        assert row["lane_override"] == "in_progress"
        assert row["is_completed_hidden"] is False

    resp = await client.post(f"/api/history/{WF}/lane", params=params, json={"lane": "completed"})
    assert resp.status_code == 200
    rows = (await client.get("/api/history", params={**params, "view": "rail", "stats": "false"})).json()
    row = next(r for r in rows if r["workflow_id"] == WF)
    assert row["lane_override"] == "completed"
    assert row["is_completed_hidden"] is True

    resp = await client.post(f"/api/history/{WF}/lane", params=params, json={"lane": None})
    assert resp.status_code == 200
    rows = (await client.get("/api/history", params={**params, "view": "rail", "stats": "false"})).json()
    row = next(r for r in rows if r["workflow_id"] == WF)
    assert row["lane_override"] is None
    assert row["is_completed_hidden"] is False


@pytest.mark.asyncio
async def test_legacy_complete_hide_reports_completed_lane(runs_root: pathlib.Path, client: httpx.AsyncClient) -> None:
    run_dir = _make_run_dir(runs_root, f"{WF}-topic")
    await _register(runs_root, WF, run_dir)
    params = {"run_root": str(runs_root)}
    assert (await client.post(f"/api/history/{WF}/complete-hide", params=params)).status_code == 200
    rows = (await client.get("/api/history", params={**params, "view": "rail", "stats": "false"})).json()
    assert next(r for r in rows if r["workflow_id"] == WF)["lane_override"] == "completed"


@pytest.mark.asyncio
async def test_lane_endpoint_validates_body_and_workflow(runs_root: pathlib.Path, client: httpx.AsyncClient) -> None:
    run_dir = _make_run_dir(runs_root, f"{WF}-topic")
    await _register(runs_root, WF, run_dir)
    params = {"run_root": str(runs_root)}
    bad = await client.post(f"/api/history/{WF}/lane", params=params, json={"lane": "archived"})
    assert bad.status_code == 422
    missing = await client.post("/api/history/wf-9999/lane", params=params, json={"lane": None})
    assert missing.status_code == 404


# ---------------------------------------------------------------------------
# Delete cleanup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_removes_all_run_dirs_and_empty_parents(
    runs_root: pathlib.Path, client: httpx.AsyncClient
) -> None:
    run_dir = _make_run_dir(runs_root, f"{WF}-topic")
    sibling = run_dir.parent / "run_02-00-00AM"
    sibling.mkdir()
    (sibling / "app.jsonl").write_text("{}", encoding="utf-8")
    await _register(runs_root, WF, run_dir)

    resp = await client.delete(f"/api/history/{WF}", params={"run_root": str(runs_root)})
    assert resp.status_code == 200
    assert not run_dir.exists()
    assert not sibling.exists()
    assert not run_dir.parent.exists()
    assert not (runs_root / "2026-09-01").exists()
    assert runs_root.exists()
    assert (runs_root / "workflows_registry.db").exists()
    assert await reg.find_by_workflow_id(str(runs_root), WF) is None


@pytest.mark.asyncio
async def test_delete_keeps_other_workflows_and_non_run_files(
    runs_root: pathlib.Path, client: httpx.AsyncClient
) -> None:
    run_dir = _make_run_dir(runs_root, f"{WF}-topic")
    stray = run_dir.parent / "notes.txt"
    stray.write_text("keep", encoding="utf-8")
    other = _make_run_dir(runs_root, f"{WF_OTHER}-topic")
    await _register(runs_root, WF, run_dir)
    await _register(runs_root, WF_OTHER, other)

    resp = await client.delete(f"/api/history/{WF}", params={"run_root": str(runs_root)})
    assert resp.status_code == 200
    assert not run_dir.exists()
    assert stray.exists()
    assert other.exists()
    assert await reg.find_by_workflow_id(str(runs_root), WF_OTHER) is not None


def test_cleanup_only_removes_own_run_in_shared_legacy_folder(runs_root: pathlib.Path) -> None:
    run_dir = _make_run_dir(runs_root, "legacy-topic-slug", "run_01-00-00AM")
    neighbour = _make_run_dir(runs_root, "legacy-topic-slug", "run_02-00-00AM")

    result = remove_workflow_run_dirs(run_dir, runs_root, WF)
    assert result.removed == [run_dir]
    assert neighbour.exists()


def test_cleanup_keeps_sibling_owned_by_another_registry_row(runs_root: pathlib.Path) -> None:
    run_dir = _make_run_dir(runs_root, f"{WF}-topic", "run_01-00-00AM")
    claimed = _make_run_dir(runs_root, f"{WF}-topic", "run_02-00-00AM")

    result = remove_workflow_run_dirs(run_dir, runs_root, WF, protected_dirs=[claimed])
    assert not run_dir.exists()
    assert claimed.exists()
    assert claimed in result.kept


def test_cleanup_never_follows_symlinks_outside_root(runs_root: pathlib.Path, tmp_path: pathlib.Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "precious.txt").write_text("keep", encoding="utf-8")
    run_dir = _make_run_dir(runs_root, f"{WF}-topic")
    (run_dir.parent / "run_99-99-99PM").symlink_to(outside, target_is_directory=True)
    (run_dir / "link").symlink_to(outside, target_is_directory=True)

    remove_workflow_run_dirs(run_dir, runs_root, WF)
    assert not run_dir.exists()
    assert (outside / "precious.txt").exists()
    assert (run_dir.parent / "run_99-99-99PM").is_symlink()


def test_cleanup_rejects_paths_outside_root(runs_root: pathlib.Path, tmp_path: pathlib.Path) -> None:
    outside = tmp_path / "elsewhere" / "run_01"
    outside.mkdir(parents=True)
    with pytest.raises(ValueError):
        remove_workflow_run_dirs(outside, runs_root, WF)
    with pytest.raises(ValueError):
        remove_workflow_run_dirs(runs_root, runs_root, WF)
    assert outside.exists()


def test_cleanup_rejects_symlinked_run_dir_resolving_outside_root(
    runs_root: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    outside = tmp_path / "outside_run"
    outside.mkdir()
    link = runs_root / "2026-09-01" / f"{WF}-topic" / "run_01-00-00AM"
    link.parent.mkdir(parents=True)
    os.symlink(outside, link, target_is_directory=True)
    with pytest.raises(ValueError):
        remove_workflow_run_dirs(link, runs_root, WF)
    assert outside.exists()
