"""Naturalness scoring for AI-generated text (0.0-1.0)."""

from __future__ import annotations


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
    model: str = "google-gla:gemini-2.5-pro",
    max_chars: int = 3_000,
) -> float:
    """Async naturalness scoring. Placeholder for LLM integration."""
    _ = model
    return score_naturalness(text, max_chars=max_chars)
