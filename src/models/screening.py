"""Screening decision models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from src.models.enums import ExclusionReason, ReviewerType, ScreeningDecisionType


class ScreeningDecision(BaseModel):
    paper_id: str
    decision: ScreeningDecisionType
    reason: Optional[str] = None
    exclusion_reason: Optional[ExclusionReason] = None
    reviewer_type: ReviewerType
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DualScreeningResult(BaseModel):
    paper_id: str
    reviewer_a: ScreeningDecision
    reviewer_b: ScreeningDecision
    agreement: bool
    final_decision: ScreeningDecisionType
    adjudication: Optional[ScreeningDecision] = None
