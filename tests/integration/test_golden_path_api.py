"""Deterministic API golden path: POST /api/run with mocked LLM, terminal SSE, workflow row."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
import pytest_asyncio
import yaml

from src.config import loader as config_loader
from src.db.database import get_db
from src.web.app import _active_runs, app
from tests.integration.conftest import MINIMAL_REVIEW


@pytest_asyncio.fixture()
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def warning_gate_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use warning gates so zero-paper search runs complete without strict gate failure."""
    real_load = config_loader.load_configs

    def _warning_load_configs(review_path: str, settings_path: str) -> tuple[Any, Any]:
        review, settings = real_load(review_path, settings_path)
        return review, settings.model_copy(update={"gates": settings.gates.model_copy(update={"profile": "warning"})})

    for target in (
        "src.config.loader.load_configs",
        "src.orchestration.workflow.load_configs",
        "src.orchestration.runners.start_runner.load_configs",
    ):
        monkeypatch.setattr(target, _warning_load_configs)


def _minimal_review_yaml() -> str:
    return yaml.safe_dump(MINIMAL_REVIEW, sort_keys=False)


@pytest.mark.asyncio
async def test_post_start_reaches_terminal_done_with_workflow_row(
    client: httpx.AsyncClient,
    tmp_path,
    mock_llm_boundary: object,
    mock_search_connectors: None,
    warning_gate_profile: None,
) -> None:
    _ = (mock_llm_boundary, mock_search_connectors)
    run_root = tmp_path / "runs"
    response = await client.post(
        "/api/run",
        json={
            "review_yaml": _minimal_review_yaml(),
            "gemini_api_key": "fake-test-key",
            "run_root": str(run_root),
        },
    )
    assert response.status_code == 200
    run_id = response.json()["run_id"]
    assert run_id

    record = None
    for _ in range(150):
        record = _active_runs.get(run_id)
        if record is not None and record.done:
            break
        await asyncio.sleep(0.2)

    try:
        assert record is not None, "run record missing from active runs"
        assert record.done, f"run did not finish within timeout: error={record.error!r}"

        events_resp = await client.get(f"/api/run/{run_id}/events")
        assert events_resp.status_code == 200
        events = events_resp.json()["events"]
        event_types = {event.get("type") for event in events}
        assert "done" in event_types or "error" in event_types
        assert "done" in event_types, f"expected golden-path done event, got {event_types}, error={record.error!r}"

        assert record.workflow_id
        assert record.db_path

        async with get_db(record.db_path) as db:
            row = await (
                await db.execute(
                    "SELECT workflow_id, status FROM workflows WHERE workflow_id = ?",
                    (record.workflow_id,),
                )
            ).fetchone()
        assert row is not None
        assert row[0] == record.workflow_id
        assert row[1] == "completed"
    finally:
        _active_runs.pop(run_id, None)
