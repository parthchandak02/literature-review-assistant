"""Workflow and gate models."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from src.models.enums import GateStatus


class GateResult(BaseModel):
    workflow_id: str
    gate_name: str
    phase: str
    status: GateStatus
    details: str
    threshold: str | None = None
    actual_value: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DecisionLogEntry(BaseModel):
    decision_type: str
    paper_id: str | None = None
    decision: str
    rationale: str
    actor: str
    phase: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
