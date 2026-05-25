"""Domain-scoped repository wrappers around WorkflowRepository."""

from __future__ import annotations

from src.db.repositories import WorkflowRepository
from src.models import (
    CandidatePaper,
    CostRecord,
    ManuscriptAuditFinding,
    ManuscriptAuditResult,
    RagRetrievalDiagnostic,
    ScreeningDecision,
    ValidationCheckRecord,
    ValidationRunRecord,
)


class PaperRepository:
    def __init__(self, repo: WorkflowRepository) -> None:
        self._repo = repo

    async def save_paper(self, paper: CandidatePaper) -> None:
        await self._repo.save_paper(paper)


class ScreeningRepository:
    def __init__(self, repo: WorkflowRepository) -> None:
        self._repo = repo

    async def save_screening_decision(self, workflow_id: str, stage: str, decision: ScreeningDecision) -> None:
        await self._repo.save_screening_decision(workflow_id=workflow_id, stage=stage, decision=decision)

    async def get_processed_paper_ids(self, workflow_id: str, stage: str) -> set[str]:
        return await self._repo.get_processed_paper_ids(workflow_id, stage)


class AuditRepository:
    def __init__(self, repo: WorkflowRepository) -> None:
        self._repo = repo

    async def get_latest_run(self, workflow_id: str) -> ManuscriptAuditResult | None:
        return await self._repo.get_latest_manuscript_audit(workflow_id)

    async def get_run(self, workflow_id: str, audit_run_id: str) -> ManuscriptAuditResult | None:
        return await self._repo.get_manuscript_audit_run(workflow_id, audit_run_id)

    async def get_history(self, workflow_id: str, limit: int = 20) -> list[ManuscriptAuditResult]:
        return await self._repo.get_manuscript_audit_history(workflow_id, limit=limit)

    async def get_findings(self, audit_run_id: str) -> list[ManuscriptAuditFinding]:
        return await self._repo.get_manuscript_audit_findings(audit_run_id)


class CostRepository:
    def __init__(self, repo: WorkflowRepository) -> None:
        self._repo = repo

    async def save_record(self, record: CostRecord) -> None:
        await self._repo.save_cost_record(record)

    async def get_total(self, workflow_id: str | None = None) -> float:
        return await self._repo.get_total_cost(workflow_id)


class WorkflowDiagnosticsRepository:
    def __init__(self, repo: WorkflowRepository) -> None:
        self._repo = repo

    async def get_rag_diagnostics(self, workflow_id: str) -> list[RagRetrievalDiagnostic]:
        return await self._repo.get_rag_retrieval_diagnostics(workflow_id)


class ValidationRepository:
    def __init__(self, repo: WorkflowRepository) -> None:
        self._repo = repo

    async def get_latest_run(self, workflow_id: str) -> ValidationRunRecord | None:
        return await self._repo.get_latest_validation_run(workflow_id)

    async def get_checks(self, validation_run_id: str) -> list[ValidationCheckRecord]:
        return await self._repo.get_validation_checks(validation_run_id)
