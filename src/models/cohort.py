"""Canonical manuscript cohort models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

ScreeningStatus = Literal["unknown", "included", "excluded"]
FulltextStatus = Literal["unknown", "assessed", "not_retrieved", "not_required"]
SynthesisEligibility = Literal[
    "pending",
    "included_primary",
    "excluded_screening",
    "excluded_non_primary",
    "excluded_failed_extraction",
    "excluded_low_quality",
]


class CohortMembershipRecord(BaseModel):
    """One canonical workflow->paper cohort row.

    This model is the single source of truth for cohort semantics across
    screening, extraction, synthesis, and export read paths.
    """

    workflow_id: str
    paper_id: str
    screening_status: ScreeningStatus = "unknown"
    fulltext_status: FulltextStatus = "unknown"
    synthesis_eligibility: SynthesisEligibility = "pending"
    exclusion_reason_code: str | None = None
    source_phase: str = "unknown"
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

