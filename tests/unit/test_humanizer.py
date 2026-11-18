"""Unit tests for humanizer integrity guardrails and failure logging."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.writing.humanizer import _passes_integrity_checks, humanize_async


def test_integrity_checks_pass_for_safe_rewrite() -> None:
    before = "This suggests that effect size was 1.20 [Smith2023]."
    after = "Effect size was 1.20 [Smith2023]."
    assert _passes_integrity_checks(before, after) is True


def test_integrity_checks_fail_on_citation_change() -> None:
    before = "Result [Smith2023]."
    after = "Result [Jones2024]."
    assert _passes_integrity_checks(before, after) is False


def test_integrity_checks_fail_on_numeric_change() -> None:
    before = "OR 1.47 and p 0.01 [Smith2023]."
    after = "OR 2.47 and p 0.01 [Smith2023]."
    assert _passes_integrity_checks(before, after) is False


@pytest.mark.asyncio
async def test_humanize_async_logs_section_model_and_exception_on_llm_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """LLM failures must log section, model, and exception detail while returning original text."""
    original = "Effect size was 1.20 [Smith2023]."
    failing_client = MagicMock()
    failing_client.complete_with_usage = AsyncMock(side_effect=TimeoutError("deadline exceeded"))
    monkeypatch.setattr("src.writing.humanizer.get_chat_client", lambda timeout_seconds=None: failing_client)

    with caplog.at_level(logging.WARNING, logger="src.writing.humanizer"):
        result = await humanize_async(
            original,
            section="results",
            model="test-model",
            timeout_seconds=1.0,
        )

    assert result == original
    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "section 'results'" in message
    assert "model=test-model" in message
    assert "TimeoutError" in message
    assert "deadline exceeded" in message
    assert "returning original text" in message
