from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, patch

import pytest

from src.config.env_context import (
    async_env_override_context,
    get_env,
    missing_required_env_keys,
    resolve_env_overrides,
)
from src.config.loader import load_configs
from src.web.shared import RunRequest


def _minimal_review_yaml() -> str:
    return "research_question: test question\n"


@pytest.mark.asyncio
async def test_concurrent_env_overrides_do_not_cross_contaminate() -> None:
    observed: dict[str, str | None] = {}

    async def worker(label: str, api_key: str) -> None:
        async with async_env_override_context({"DEEPSEEK_API_KEY": api_key}):
            await asyncio.sleep(0.02)
            observed[label] = get_env("DEEPSEEK_API_KEY")

    await asyncio.gather(
        worker("run-a", "key-for-run-a"),
        worker("run-b", "key-for-run-b"),
    )

    assert observed == {
        "run-a": "key-for-run-a",
        "run-b": "key-for-run-b",
    }


@pytest.mark.asyncio
async def test_get_env_respects_task_local_overrides_and_aliases() -> None:
    async with async_env_override_context({"GEMINI_API_KEY": "ctx-gemini"}):
        assert get_env("GEMINI_API_KEY") == "ctx-gemini"
        assert get_env("GOOGLE_API_KEY") == "ctx-gemini"


@pytest.mark.asyncio
async def test_os_getenv_does_not_see_task_local_overrides() -> None:
    """Raw os reads stay process-scoped after ADR-0004 (no monkeyhooks)."""
    async with async_env_override_context({"GEMINI_API_KEY": "ctx-gemini"}):
        assert get_env("GEMINI_API_KEY") == "ctx-gemini"
        assert os.getenv("GEMINI_API_KEY") != "ctx-gemini"


def test_resolve_env_overrides_from_run_request() -> None:
    req = RunRequest(
        review_yaml=_minimal_review_yaml(),
        deepseek_api_key="ds-task-key",
        pubmed_email="user@example.com",
    )
    overrides = resolve_env_overrides(req)
    assert overrides["DEEPSEEK_API_KEY"] == "ds-task-key"
    assert overrides["PUBMED_EMAIL"] == "user@example.com"
    assert overrides["NCBI_EMAIL"] == "user@example.com"


def test_missing_required_env_keys_uses_request_overrides_without_os_mutation() -> None:
    _, settings = load_configs(settings_path="config/settings.yaml")
    saved = os.environ.pop("DEEPSEEK_API_KEY", None)
    try:
        missing = missing_required_env_keys(settings, {"DEEPSEEK_API_KEY": "provided-in-request"})
        assert "DEEPSEEK_API_KEY" not in missing
    finally:
        if saved is not None:
            os.environ["DEEPSEEK_API_KEY"] = saved


@pytest.mark.asyncio
async def test_start_run_does_not_write_request_keys_to_process_environ() -> None:
    import yaml
    from httpx import ASGITransport, AsyncClient

    from src.web.app import app

    marker = "phase-0-3a-never-in-process-env"
    review_payload = {
        "research_question": "Does test coverage improve software quality?",
        "review_type": "systematic",
        "pico": {
            "population": "software teams",
            "intervention": "high test coverage",
            "comparison": "low test coverage",
            "outcome": "defect rate",
        },
        "keywords": ["test coverage"],
        "domain": "software engineering",
        "scope": "",
        "inclusion_criteria": ["peer reviewed"],
        "exclusion_criteria": ["opinion pieces"],
        "date_range_start": 2015,
        "date_range_end": 2026,
        "target_databases": ["unsupported_db"],
    }

    mock_start = AsyncMock(return_value={"workflow_id": "wf-test", "status": "completed"})
    with patch("src.web.orchestration_facade.start_workflow_run", new=mock_start):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/run",
                json={
                    "review_yaml": yaml.safe_dump(review_payload),
                    "deepseek_api_key": marker,
                    "run_root": "/tmp/litreview_env_context_test",
                },
            )
            await asyncio.sleep(0.05)

    assert response.status_code == 200
    mock_start.assert_awaited()
    assert os.environ.get("DEEPSEEK_API_KEY") != marker
