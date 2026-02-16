"""Workflow and gate models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from src.models.enums import GateStatus


class GateResult(BaseModel):
    workflow_id: str
    gate_name: str
    phase: str
    status: GateStatus
    details: str
    threshold: Optional[str] = None
    actual_value: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DecisionLogEntry(BaseModel):
    decision_type: str
    paper_id: Optional[str] = None
    decision: str
    rationale: str
    actor: str
    phase: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
