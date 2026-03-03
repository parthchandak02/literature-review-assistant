"""Screening decision models."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from src.models.enums import ExclusionReason, ReviewerType, ScreeningDecisionType


class ScreeningDecision(BaseModel):
    paper_id: str
    decision: ScreeningDecisionType
    reason: str | None = None
    exclusion_reason: ExclusionReason | None = None
    reviewer_type: ReviewerType
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DualScreeningResult(BaseModel):
    paper_id: str
    reviewer_a: ScreeningDecision
    reviewer_b: ScreeningDecision
    agreement: bool
    final_decision: ScreeningDecisionType
    adjudication: ScreeningDecision | None = None
