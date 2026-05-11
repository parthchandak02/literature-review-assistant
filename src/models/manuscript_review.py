"""Typed models for manuscript audit stage."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

AuditProfileName = Literal[
    "general_systematic_review",
    "health_economics",
    "education",
    "implementation_science",
    "qualitative_methods",
]

AuditSeverity = Literal["major", "minor", "note"]
AuditVerdict = Literal["accept", "minor_revisions", "major_revisions", "reject"]


class ManuscriptAuditProfileSelection(BaseModel):
    """Profile routing result for phase_7_audit."""

    selected_profiles: list[AuditProfileName] = Field(default_factory=list)
    routing_reason: str = ""


class ManuscriptAuditFinding(BaseModel):
    """Single structured audit finding."""

    finding_id: str
    profile: AuditProfileName
    severity: AuditSeverity
    category: str
    section: str | None = None
    evidence: str
    recommendation: str
    owner_module: str
    blocking: bool = False
    created_at: datetime | None = None


class ManuscriptContractViolation(BaseModel):
    """Contract violation attached to a manuscript audit run."""

    code: str
    severity: str
    message: str
    expected: str | None = None
    actual: str | None = None


class ManuscriptAuditResult(BaseModel):
    """Merged result for a single manuscript audit run."""

    audit_run_id: str
    workflow_id: str
    mode: str
    verdict: AuditVerdict
    passed: bool
    selected_profiles: list[AuditProfileName] = Field(default_factory=list)
    summary: str = ""
    total_findings: int = 0
    major_count: int = 0
    minor_count: int = 0
    note_count: int = 0
    blocking_count: int = 0
    total_cost_usd: float = 0.0
    contract_mode: str = "observe"
    contract_passed: bool = True
    contract_violation_count: int = 0
    contract_violations: list[ManuscriptContractViolation] = Field(default_factory=list)
    gate_blocked: bool = False
    gate_mode: str = "strict"
    gate_action: str = "strict_block"
    gate_failure_reasons: list[str] = Field(default_factory=list)
    top_recommendations: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_audited_at: datetime | None = None

