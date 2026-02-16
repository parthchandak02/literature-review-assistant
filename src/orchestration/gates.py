"""Quality gate execution and persistence."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from src.db.repositories import WorkflowRepository
from src.models import GateResult, GateStatus, SettingsConfig


GateCheck = Callable[[], Awaitable[tuple[bool, str, str, str]]]


@dataclass
class GateOutcome:
    passed: bool
    details: str
    threshold: str
    actual_value: str


class GateRunner:
    def __init__(self, repository: WorkflowRepository, settings: SettingsConfig):
        self.repository = repository
        self.settings = settings

    def _status_for(self, passed: bool) -> GateStatus:
        if passed:
            return GateStatus.PASSED
        if self.settings.gates.profile == "warning":
            return GateStatus.WARNING
        return GateStatus.FAILED

    async def run_gate(
        self,
        workflow_id: str,
        phase: str,
        gate_name: str,
        check_fn: GateCheck,
    ) -> GateResult:
        passed, details, threshold, actual_value = await check_fn()
        result = GateResult(
            workflow_id=workflow_id,
            gate_name=gate_name,
            phase=phase,
            status=self._status_for(passed),
            details=details,
            threshold=threshold,
            actual_value=actual_value,
        )
        await self.repository.save_gate_result(result)
        return result

    async def run_search_volume_gate(
        self,
        workflow_id: str,
        phase: str,
        total_records: int,
    ) -> GateResult:
        minimum = self.settings.gates.search_volume_minimum

        async def check() -> tuple[bool, str, str, str]:
            passed = total_records >= minimum
            return (
                passed,
                f"total_records={total_records}, minimum={minimum}",
                str(minimum),
                str(total_records),
            )

        return await self.run_gate(workflow_id, phase, "search_volume", check)

    async def run_screening_safeguard_gate(
        self,
        workflow_id: str,
        phase: str,
        passed_screening: int,
    ) -> GateResult:
        minimum = self.settings.gates.screening_minimum

        async def check() -> tuple[bool, str, str, str]:
            passed = passed_screening >= minimum
            return (
                passed,
                f"passed_screening={passed_screening}, minimum={minimum}",
                str(minimum),
                str(passed_screening),
            )

        return await self.run_gate(workflow_id, phase, "screening_safeguard", check)

    async def run_extraction_completeness_gate(
        self,
        workflow_id: str,
        phase: str,
        completeness_ratio: float,
    ) -> GateResult:
        threshold = self.settings.gates.extraction_completeness_threshold

        async def check() -> tuple[bool, str, str, str]:
            passed = completeness_ratio >= threshold
            return (
                passed,
                f"completeness_ratio={completeness_ratio:.2f}, threshold={threshold:.2f}",
                f"{threshold:.2f}",
                f"{completeness_ratio:.2f}",
            )

        return await self.run_gate(workflow_id, phase, "extraction_completeness", check)

    async def run_citation_lineage_gate(
        self,
        workflow_id: str,
        phase: str,
        unresolved_items: int,
    ) -> GateResult:
        async def check() -> tuple[bool, str, str, str]:
            passed = unresolved_items == 0
            return (
                passed,
                f"unresolved_items={unresolved_items}",
                "0",
                str(unresolved_items),
            )

        return await self.run_gate(workflow_id, phase, "citation_lineage", check)

    async def run_cost_budget_gate(
        self,
        workflow_id: str,
        phase: str,
        total_cost: float,
    ) -> GateResult:
        max_cost = self.settings.gates.cost_budget_max

        async def check() -> tuple[bool, str, str, str]:
            passed = total_cost < max_cost
            return (
                passed,
                f"total_cost={total_cost:.4f}, max={max_cost:.4f}",
                f"{max_cost:.4f}",
                f"{total_cost:.4f}",
            )

        return await self.run_gate(workflow_id, phase, "cost_budget", check)

    async def run_resume_integrity_gate(
        self,
        workflow_id: str,
        phase: str,
    ) -> GateResult:
        async def check() -> tuple[bool, str, str, str]:
            valid = await self.repository.has_checkpoint_integrity(workflow_id)
            details = "workflow and checkpoints are consistent" if valid else "workflow metadata missing"
            return (valid, details, "valid", "valid" if valid else "invalid")

        return await self.run_gate(workflow_id, phase, "resume_integrity", check)
