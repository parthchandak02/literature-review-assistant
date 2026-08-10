from __future__ import annotations

from src.orchestration.helpers.runtime import evaluate_rag_health


def test_evaluate_rag_health_breached() -> None:
    breached, msg = evaluate_rag_health(empty_sections=2, error_sections=1, max_empty_sections=2)
    assert breached is True
    assert "violated" in msg


def test_evaluate_rag_health_not_breached() -> None:
    breached, msg = evaluate_rag_health(empty_sections=1, error_sections=0, max_empty_sections=2)
    assert breached is False
    assert "ok" in msg
