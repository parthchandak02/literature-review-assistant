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
    workflow_id: str = ""
    decision_type: str
    paper_id: str | None = None
    decision: str
    rationale: str
    actor: str
    phase: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ValidationRunRecord(BaseModel):
    """Workflow-scoped validation execution metadata."""

    validation_run_id: str
    workflow_id: str
    profile: str
    status: str
    tool_version: str
    summary_json: str = "{}"
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


class ValidationCheckRecord(BaseModel):
    """Single validation check emitted during replay analysis."""

    validation_run_id: str
    workflow_id: str
    phase: str
    check_name: str
    status: str
    severity: str
    metric_value: float | None = None
    details_json: str = "{}"
    source_module: str | None = None
    paper_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ValidationArtifactRecord(BaseModel):
    """Optional artifact emitted by replay validation runs."""

    validation_run_id: str
    workflow_id: str
    artifact_key: str
    artifact_type: str
    content_path: str | None = None
    content_text: str | None = None
    meta_json: str = "{}"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
