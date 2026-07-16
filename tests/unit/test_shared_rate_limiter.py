"""Unit tests for credential-keyed shared rate limiters."""

from __future__ import annotations

import pytest

from src.config.env_context import async_env_override_context
from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.llm.provider import LLMProvider
from src.llm.shared_rate_limiter import clear_shared_rate_limiters, get_shared_rate_limiter
from src.models import SettingsConfig


def _settings() -> SettingsConfig:
    return SettingsConfig(
        agents={"writing": {"model": "google:gemini-2.5-flash-lite", "temperature": 0.1}},
    )


@pytest.fixture(autouse=True)
def _reset_shared_limiters() -> None:
    clear_shared_rate_limiters()
    yield
    clear_shared_rate_limiters()


@pytest.mark.asyncio
async def test_same_credential_shares_rate_limiter(tmp_path) -> None:
    async with async_env_override_context({"GEMINI_API_KEY": "shared-key"}):
        async with get_db(str(tmp_path / "shared_a.db")) as db:
            repo = WorkflowRepository(db)
            provider_a = LLMProvider(_settings(), repo)
        async with get_db(str(tmp_path / "shared_b.db")) as db:
            repo = WorkflowRepository(db)
            provider_b = LLMProvider(_settings(), repo)

    assert provider_a.rate_limiter is provider_b.rate_limiter


@pytest.mark.asyncio
async def test_different_credentials_get_separate_limiters(tmp_path) -> None:
    settings = _settings()

    async with async_env_override_context({"GEMINI_API_KEY": "key-alpha"}):
        async with get_db(str(tmp_path / "alpha.db")) as db:
            repo = WorkflowRepository(db)
            provider_a = LLMProvider(settings, repo)

    async with async_env_override_context({"GEMINI_API_KEY": "key-beta"}):
        async with get_db(str(tmp_path / "beta.db")) as db:
            repo = WorkflowRepository(db)
            provider_b = LLMProvider(settings, repo)

    assert provider_a.rate_limiter is not provider_b.rate_limiter


def test_get_shared_rate_limiter_reuses_cached_instance() -> None:
    settings = _settings()
    first = get_shared_rate_limiter(settings)
    second = get_shared_rate_limiter(settings)
    assert first is second
