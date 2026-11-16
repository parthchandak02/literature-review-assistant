import pytest

from src.orchestration import workflow as workflow_mod
from src.web import state
from src.web.shared import RunRequest
from src.web.state import _RunRecord


@pytest.mark.asyncio
async def test_done_flag_is_set_only_after_terminal_done_event(monkeypatch, tmp_path) -> None:
    observed: list[tuple[bool, bool]] = []
    record = _RunRecord(run_id="order-test", topic="t")

    async def fake_run_workflow(**_kwargs):
        return {"status": "completed", "workflow_id": "wf-9999"}

    async def fake_resolve(_wf_id, _root):
        observed.append((record.done, any(e.get("type") == "done" for e in record.event_log)))
        return None

    async def fake_terminal(*_args, **_kwargs):
        observed.append((record.done, any(e.get("type") == "done" for e in record.event_log)))

    async def noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(workflow_mod, "run_workflow", fake_run_workflow)
    monkeypatch.setattr(state, "resolve_runtime_db", fake_resolve)
    monkeypatch.setattr(state, "_apply_terminal_registry_status", fake_terminal)
    monkeypatch.setattr(state, "_maybe_persist_registry_stats", noop)
    monkeypatch.setattr(state, "_update_registry_status", noop)

    req = RunRequest(review_yaml="research_question: x", run_root=str(tmp_path))
    await state._run_wrapper(record, str(tmp_path / "review.yaml"), req)

    assert observed and all(done is False for done, _ in observed)
    assert record.done is True
    assert record.event_log[-1]["type"] == "done" or any(e.get("type") == "done" for e in record.event_log)


@pytest.mark.asyncio
async def test_resume_wrapper_done_flag_set_after_registry_updates_on_runtime_completed(monkeypatch, tmp_path) -> None:
    import sqlite3

    run_dir = tmp_path / "wf-resume"
    run_dir.mkdir()
    db_path = run_dir / "runtime.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE workflows (workflow_id TEXT PRIMARY KEY, status TEXT NOT NULL)")
        conn.execute(
            "CREATE TABLE event_log ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "workflow_id TEXT NOT NULL, "
            "event_type TEXT NOT NULL, "
            "payload TEXT NOT NULL, "
            "ts TEXT NOT NULL DEFAULT ''"
            ")"
        )
        conn.execute("INSERT INTO workflows (workflow_id, status) VALUES (?, ?)", ("wf-resume", "completed"))
        conn.commit()
    finally:
        conn.close()

    observed: list[tuple[str, bool]] = []
    record = _RunRecord(run_id="resume-order-test", topic="t")
    record.workflow_id = "wf-resume"
    record.db_path = str(db_path)

    async def fake_resume(**_kwargs):
        raise RuntimeError("boom after completion")

    async def fake_update_registry_status(_run_root, _wf_id, status: str):
        observed.append((f"status:{status}", record.done))

    async def fake_persist_stats(_run_root, _wf_id):
        observed.append(("stats", record.done))

    async def fake_load_events(*_args, **_kwargs):
        return []

    monkeypatch.setattr(workflow_mod, "run_workflow_resume", fake_resume)
    monkeypatch.setattr(state, "_update_registry_status", fake_update_registry_status)
    monkeypatch.setattr(state, "_maybe_persist_registry_stats", fake_persist_stats)
    monkeypatch.setattr(state, "_load_event_log_from_db", fake_load_events)

    await state._resume_wrapper(record, "wf-resume", str(db_path))

    assert observed == [("status:running", False), ("status:completed", False), ("stats", False)]
    assert record.done is True


@pytest.mark.asyncio
async def test_run_wrapper_done_flag_set_after_registry_updates_on_error(monkeypatch, tmp_path) -> None:
    observed: list[tuple[str, bool]] = []
    record = _RunRecord(run_id="err-order-test", topic="t")
    record.workflow_id = "wf-err"
    record.run_root = str(tmp_path)

    async def fake_run_workflow(**_kwargs):
        raise RuntimeError("boom")

    async def fake_update_registry_status(_run_root, _wf_id, status: str):
        observed.append((f"status:{status}", record.done))

    async def fake_persist_stats(_run_root, _wf_id):
        observed.append(("stats", record.done))

    monkeypatch.setattr(workflow_mod, "run_workflow", fake_run_workflow)
    monkeypatch.setattr(state, "_update_registry_status", fake_update_registry_status)
    monkeypatch.setattr(state, "_maybe_persist_registry_stats", fake_persist_stats)

    req = RunRequest(review_yaml="research_question: x", run_root=str(tmp_path))
    await state._run_wrapper(record, str(tmp_path / "review.yaml"), req)

    assert observed == [("status:failed", False), ("stats", False)]
    assert record.done is True
    assert record.error == "boom"
