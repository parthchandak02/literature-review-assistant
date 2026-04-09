"""Workflow and gate models."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from src.models.enums import (
    FailureCategory,
    GateStatus,
    RecoveryAction,
    StepStatus,
)


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


class FallbackEventRecord(BaseModel):
    """Structured record for degraded-mode execution during a workflow run."""

    workflow_id: str
    phase: str
    module: str
    fallback_type: str
    reason: str
    paper_id: str | None = None
    details_json: str = "{}"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PreWritingGateCheck(BaseModel):
    """One deterministic pre-writing validation check."""

    name: str
    ok: bool
    detail: str | None = None
    blocking: bool = True
    rewind_phase: str | None = None


class PreWritingGateReport(BaseModel):
    """Aggregate pre-writing validation state before manuscript generation."""

    workflow_id: str
    ready: bool
    checks: list[PreWritingGateCheck] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    rewind_phase: str | None = None
    attempt_number: int = 1


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


class WorkflowStepRecord(BaseModel):
    """Fine-grained step execution record within a phase.

    Each important operation in the workflow graph writes a step record
    so the DB becomes the control plane for resume, retry, and diagnostics.
    """

    step_id: str
    workflow_id: str
    phase: str
    step_name: str
    status: StepStatus = StepStatus.PENDING
    attempt_number: int = 1
    max_attempts: int = 1
    paper_id: str | None = None
    input_hash: str | None = None
    output_hash: str | None = None
    error_message: str | None = None
    failure_category: FailureCategory | None = None
    recovery_action: RecoveryAction | None = None
    parent_step_id: str | None = None
    duration_ms: int | None = None
    meta_json: str = "{}"
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in (StepStatus.SUCCEEDED, StepStatus.FAILED, StepStatus.SKIPPED)


class RecoveryPolicyRecord(BaseModel):
    """Bounded retry/rewind policy stored in DB for a workflow phase or step.

    Drives "attempt 2 of 3" messaging and prevents unbounded retries.
    """

    workflow_id: str
    phase: str
    step_name: str
    max_retries: int = 3
    max_rewinds: int = 1
    current_retries: int = 0
    current_rewinds: int = 0
    rewind_target_phase: str | None = None
    policy_status: str = "active"
    meta_json: str = "{}"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def retries_exhausted(self) -> bool:
        return self.current_retries >= self.max_retries

    @property
    def rewinds_exhausted(self) -> bool:
        return self.current_rewinds >= self.max_rewinds

    def status_label(self) -> str:
        if self.retries_exhausted and self.rewinds_exhausted:
            return "exhausted"
        return f"retry {self.current_retries}/{self.max_retries}, rewind {self.current_rewinds}/{self.max_rewinds}"


class WritingManifestRecord(BaseModel):
    """Per-section writing manifest tracking evidence provenance and retries.

    Keyed by workflow + section + attempt so the DB records every writing
    attempt with its grounding hash, evidence sources, and contract status.
    """

    workflow_id: str
    section_key: str
    attempt_number: int = 1
    grounding_hash: str | None = None
    evidence_source_ids: str = "[]"
    citation_catalog_hash: str | None = None
    contract_status: str = "pending"
    contract_issues: str = "[]"
    fallback_used: bool = False
    retry_count: int = 0
    word_count: int | None = None
    meta_json: str = "{}"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def evidence_ids(self) -> list[str]:
        return json.loads(self.evidence_source_ids)

    @property
    def issues(self) -> list[str]:
        return json.loads(self.contract_issues)
