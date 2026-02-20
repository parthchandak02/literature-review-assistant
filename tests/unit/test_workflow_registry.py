"""Unit tests for workflow registry."""

from __future__ import annotations

import pytest

from src.db.workflow_registry import (
    find_by_topic,
    find_by_workflow_id,
    find_by_workflow_id_fallback,
    register,
)


@pytest.mark.asyncio
async def test_register_and_find_by_workflow_id(tmp_path) -> None:
    run_root = str(tmp_path)
    db_path = tmp_path / "run" / "runtime.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_text("")
    await register(
        run_root=run_root,
        workflow_id="wf-abc123",
        topic="How do AI tutors impact learning?",
        config_hash="deadbeef",
        db_path=str(db_path),
    )
    entry = await find_by_workflow_id(run_root, "wf-abc123")
    assert entry is not None
    assert entry.workflow_id == "wf-abc123"
    assert entry.topic == "How do AI tutors impact learning?"
    assert entry.config_hash == "deadbeef"
    assert "runtime.db" in entry.db_path


@pytest.mark.asyncio
async def test_find_by_workflow_id_missing_returns_none(tmp_path) -> None:
    run_root = str(tmp_path)
    entry = await find_by_workflow_id(run_root, "wf-nonexistent")
    assert entry is None


@pytest.mark.asyncio
async def test_find_by_workflow_id_missing_db_returns_none(tmp_path) -> None:
    run_root = str(tmp_path)
    db_path = tmp_path / "run" / "runtime.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_text("")
    await register(
        run_root=run_root,
        workflow_id="wf-xyz",
        topic="Test",
        config_hash="abc",
        db_path=str(db_path),
    )
    db_path.unlink()
    entry = await find_by_workflow_id(run_root, "wf-xyz")
    assert entry is None


@pytest.mark.asyncio
async def test_find_by_topic(tmp_path) -> None:
    run_root = str(tmp_path)
    db_path = tmp_path / "run" / "runtime.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_text("")
    await register(
        run_root=run_root,
        workflow_id="wf-t1",
        topic="Conversational AI tutors",
        config_hash="hash1",
        db_path=str(db_path),
    )
    matches = await find_by_topic(run_root, "Conversational AI tutors", "hash1")
    assert len(matches) == 1
    assert matches[0].workflow_id == "wf-t1"


@pytest.mark.asyncio
async def test_find_by_topic_case_insensitive(tmp_path) -> None:
    run_root = str(tmp_path)
    db_path = tmp_path / "run" / "runtime.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_text("")
    await register(
        run_root=run_root,
        workflow_id="wf-t2",
        topic="Conversational AI tutors",
        config_hash="hash2",
        db_path=str(db_path),
    )
    matches = await find_by_topic(run_root, "conversational ai tutors", "hash2")
    assert len(matches) == 1


@pytest.mark.asyncio
async def test_find_by_workflow_id_fallback(tmp_path) -> None:
    """Fallback finds workflow by scanning run_summary.json when registry is missing."""
    run_root = str(tmp_path)
    run_dir = tmp_path / "2026-02-16" / "some-topic-slug" / "run_08-37-54PM"
    run_dir.mkdir(parents=True)
    runtime_db = run_dir / "runtime.db"
    runtime_db.write_bytes(b"")
    run_summary = run_dir / "run_summary.json"
    run_summary.write_text(
        '{"workflow_id":"wf-fallback123","log_dir":"runs/2026-02-16/some-topic-slug/run_08-37-54PM","included_papers":5}',
        encoding="utf-8",
    )
    entry = await find_by_workflow_id_fallback(run_root, "wf-fallback123")
    assert entry is not None
    assert entry.workflow_id == "wf-fallback123"
    assert str(runtime_db) in entry.db_path or entry.db_path.endswith("runtime.db")
    assert entry.status == "completed"


@pytest.mark.asyncio
async def test_find_by_topic_config_hash_mismatch_returns_empty(tmp_path) -> None:
    run_root = str(tmp_path)
    db_path = tmp_path / "run" / "runtime.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_text("")
    await register(
        run_root=run_root,
        workflow_id="wf-t3",
        topic="AI tutors",
        config_hash="hash_a",
        db_path=str(db_path),
    )
    matches = await find_by_topic(run_root, "AI tutors", "hash_b")
    assert len(matches) == 0
