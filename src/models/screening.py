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


class ScreeningResponsePayload(BaseModel):
    """Schema-constrained single-paper screening payload from LLM."""

    decision: ScreeningDecisionType
    confidence: float = Field(ge=0.0, le=1.0)
    short_reason: str | None = Field(default=None, description="One-line summary, max 80 chars")
    reasoning: str
    exclusion_reason: ExclusionReason | None = None


class BatchScreeningItemPayload(BaseModel):
    """Schema-constrained per-paper item in a batch screening response."""

    paper_id: str
    decision: ScreeningDecisionType
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    short_reason: str | None = None
    reasoning: str = "Batch response omitted reasoning."
    exclusion_reason: ExclusionReason | None = None


class BatchScreeningResponsePayload(BaseModel):
    """Envelope for batched screening responses."""

    decisions: list[BatchScreeningItemPayload] = Field(default_factory=list)


class DualScreeningResult(BaseModel):
    paper_id: str
    reviewer_a: ScreeningDecision
    reviewer_b: ScreeningDecision
    agreement: bool
    final_decision: ScreeningDecisionType
    adjudication: ScreeningDecision | None = None
