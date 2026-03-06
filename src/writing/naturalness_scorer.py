"""Naturalness scoring for AI-generated text (0.0-1.0)."""

from __future__ import annotations


def _get_model_from_settings() -> str:
    try:
        from src.config.loader import load_configs

        _, s = load_configs(settings_path="config/settings.yaml")
        return s.agents["naturalness_scorer"].model
    except Exception:
        return "google-gla:gemini-3.1-flash-lite-preview"


def score_naturalness(
    text: str,
    max_chars: int = 3_000,
) -> float:
    """Score text for academic naturalness. 0.0-1.0 scale.

    Baseline: returns 0.8 (pass). Hardening target: LLM evaluation.
    Truncation: 3,000 chars input per spec.
    """
    _ = text
    _ = max_chars
    return 0.8


async def score_naturalness_async(
    text: str,
    model: str | None = None,
    max_chars: int = 3_000,
) -> float:
    """Async naturalness scoring. Placeholder for LLM integration.

    The model parameter is accepted for future LLM-based implementation.
    Default reads from settings.yaml naturalness_scorer agent.
    """
    if model is None:
        model = _get_model_from_settings()
    _ = model
    return score_naturalness(text, max_chars=max_chars)
