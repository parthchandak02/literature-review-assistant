"""Read-only control-plane facade for workflow step journal, recovery policies, and writing manifests.

Phase 5 centralizes diagnostics reads so routers do not reach into WorkflowRepository
sub-repos directly for control-plane tables.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.models.workflow import RecoveryPolicyRecord, WorkflowStepRecord, WritingManifestRecord

if TYPE_CHECKING:
    from src.db.repositories import WorkflowRepository


@dataclass(frozen=True)
class ControlPlaneSnapshot:
    """Bundled control-plane read model for diagnostics endpoints."""

    workflow_id: str
    step_summary: dict[str, dict[str, int]]
    step_failures: int
    running_steps: int
    recovery_policies: list[RecoveryPolicyRecord]
    writing_manifests: list[WritingManifestRecord]

    def as_diagnostics_payload(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "step_summary": self.step_summary,
            "step_failures": self.step_failures,
            "running_steps": self.running_steps,
            "recovery_policies": [p.model_dump(mode="json") for p in self.recovery_policies],
            "writing_manifests": [m.model_dump(mode="json") for m in self.writing_manifests],
        }


class ControlPlaneService:
    """Thin read API over workflow_steps, recovery_policies, and writing_manifests."""

    def __init__(self, repo: WorkflowRepository) -> None:
        self._repo = repo

    async def get_step_history(
        self, workflow_id: str, phase: str | None = None, *, limit: int = 200
    ) -> list[WorkflowStepRecord]:
        return await self._repo.get_step_history(workflow_id, phase, limit=limit)

    async def get_step_summary(self, workflow_id: str) -> dict[str, dict[str, int]]:
        return await self._repo.get_step_summary(workflow_id)

    async def count_step_failures(self, workflow_id: str, phase: str | None = None) -> int:
        return await self._repo.count_step_failures(workflow_id, phase)

    async def count_running_steps(self, workflow_id: str, phase: str | None = None) -> int:
        return await self._repo.count_running_steps(workflow_id, phase)

    async def get_recovery_policies(self, workflow_id: str, phase: str | None = None) -> list[RecoveryPolicyRecord]:
        return await self._repo.list_recovery_policies(workflow_id, phase)

    async def get_writing_manifests(
        self, workflow_id: str, section_key: str | None = None
    ) -> list[WritingManifestRecord]:
        return await self._repo.get_writing_manifests(workflow_id, section_key)

    async def get_snapshot(self, workflow_id: str) -> ControlPlaneSnapshot:
        return ControlPlaneSnapshot(
            workflow_id=workflow_id,
            step_summary=await self.get_step_summary(workflow_id),
            step_failures=await self.count_step_failures(workflow_id),
            running_steps=await self.count_running_steps(workflow_id),
            recovery_policies=await self.get_recovery_policies(workflow_id),
            writing_manifests=await self.get_writing_manifests(workflow_id),
        )
