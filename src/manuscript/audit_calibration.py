"""Calibration helpers for representative manuscript-audit fixtures."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AuditCalibrationCase(BaseModel):
    """Expected audit shape for a representative workflow fixture."""

    workflow_id: str
    run_dir: str
    required_profiles: list[str] = Field(default_factory=list)
    allowed_verdicts: list[str] = Field(default_factory=list)
    blocking_count_min: int = 0
    blocking_count_max: int = 999
    required_category_substrings: list[str] = Field(default_factory=list)
    forbidden_category_substrings: list[str] = Field(default_factory=list)


class ObservedAuditShape(BaseModel):
    """Normalized subset of audit output used for calibration checks."""

    workflow_id: str
    selected_profiles: list[str] = Field(default_factory=list)
    verdict: str
    blocking_count: int = 0
    categories: list[str] = Field(default_factory=list)


def _normalize_fragment(value: str) -> str:
    return " ".join(str(value).replace("_", " ").replace("-", " ").casefold().split())


def compare_audit_shape(expected: AuditCalibrationCase, observed: ObservedAuditShape) -> list[str]:
    """Return human-readable mismatch messages for one calibration case."""
    mismatches: list[str] = []
    observed_profiles = set(observed.selected_profiles)
    missing_profiles = [profile for profile in expected.required_profiles if profile not in observed_profiles]
    if missing_profiles:
        mismatches.append(f"missing required profiles: {', '.join(missing_profiles)}")
    if expected.allowed_verdicts and observed.verdict not in expected.allowed_verdicts:
        mismatches.append(
            f"verdict {observed.verdict!r} not in allowed set {expected.allowed_verdicts!r}"
        )
    if observed.blocking_count < expected.blocking_count_min or observed.blocking_count > expected.blocking_count_max:
        mismatches.append(
            "blocking_count "
            f"{observed.blocking_count} outside expected range "
            f"[{expected.blocking_count_min}, {expected.blocking_count_max}]"
        )
    normalized_categories = [_normalize_fragment(category) for category in observed.categories]
    for fragment in expected.required_category_substrings:
        normalized_fragment = _normalize_fragment(fragment)
        if not any(normalized_fragment in category for category in normalized_categories):
            mismatches.append(f"missing category containing {fragment!r}")
    for fragment in expected.forbidden_category_substrings:
        normalized_fragment = _normalize_fragment(fragment)
        if any(normalized_fragment in category for category in normalized_categories):
            mismatches.append(f"unexpected category containing {fragment!r}")
    return mismatches
