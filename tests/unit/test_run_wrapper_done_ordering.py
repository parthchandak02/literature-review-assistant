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
