"""Shared synthesis constants and helpers."""

from __future__ import annotations

from src.models.config import MetaAnalysisConfig

GENERIC_OUTCOME_NAMES = frozenset(
    {
        "",
        "primary_outcome",
        "secondary_outcome",
        "not_reported",
        "not reported",
    }
)

DEFAULT_HETEROGENEITY_THRESHOLD = float(MetaAnalysisConfig.model_fields["heterogeneity_threshold"].default)


def normalize_outcome_name(name: str) -> str:
    """Normalize outcome names for cross-module matching."""
    return str(name or "").strip().lower().replace(" ", "_")
