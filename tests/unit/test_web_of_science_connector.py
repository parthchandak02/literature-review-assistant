from __future__ import annotations

from src.search.web_of_science import _retryable_status_message


def test_retryable_status_message_for_429_mentions_quota_or_rate() -> None:
    msg = _retryable_status_message(429, "too many requests", 3)
    assert "429" in msg
    assert "rate limit or quota exhaustion" in msg


def test_retryable_status_message_for_512_mentions_provider_fault() -> None:
    msg = _retryable_status_message(512, "internal server error", 3)
    assert "512" in msg
    assert "provider internal server fault" in msg
    assert "quota exhaustion" not in msg


def test_retryable_status_message_for_other_5xx_is_not_quota_specific() -> None:
    msg = _retryable_status_message(503, "service unavailable", 3)
    assert "503" in msg
    assert "persistent server-side failure" in msg
    assert "not necessarily quota exhaustion" in msg
