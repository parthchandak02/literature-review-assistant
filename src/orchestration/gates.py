"""Quality gate execution and persistence."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.db.workflow_registry import update_status as update_registry_status
from src.models import GateResult, GateStatus, SettingsConfig
from src.models.workflow import WorkflowRunResult, WorkflowRunStatus

if TYPE_CHECKING:
    from src.orchestration.state import ReviewState

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
        sparse_min = self.settings.search.low_recall_warning_threshold
        sparse_mode = (total_records < minimum) and (sparse_min > 0) and (total_records >= sparse_min)

        if sparse_mode:
            status = GateStatus.WARNING
            details = (
                f"total_records={total_records}, minimum={minimum}, "
                f"sparse_search_min={sparse_min}, continuation=enabled"
            )
        else:
            passed = total_records >= minimum
            status = self._status_for(passed)
            details = f"total_records={total_records}, minimum={minimum}"

        result = GateResult(
            workflow_id=workflow_id,
            gate_name="search_volume",
            phase=phase,
            status=status,
            details=details,
            threshold=str(minimum),
            actual_value=str(total_records),
        )
        await self.repository.save_gate_result(result)
        return result

    async def run_screening_safeguard_gate(
        self,
        workflow_id: str,
        phase: str,
        passed_screening: int,
    ) -> GateResult:
        minimum = self.settings.gates.screening_minimum
        sparse_min = self.settings.gates.sparse_topic_min
        sparse_continuation = self.settings.gates.sparse_topic_continuation

        passed = passed_screening >= minimum
        sparse_mode = (passed_screening < minimum) and sparse_continuation
        if sparse_mode:
            status = GateStatus.WARNING
            continuation_mode = (
                "zero_evidence_continuation"
                if passed_screening == 0
                else (
                    "below_sparse_topic_min_continuation"
                    if passed_screening < sparse_min
                    else "sparse_topic_continuation"
                )
            )
            details = (
                f"passed_screening={passed_screening}, minimum={minimum}, "
                f"sparse_topic_min={sparse_min}, continuation=enabled, "
                f"mode={continuation_mode}"
            )
        elif passed:
            status = GateStatus.PASSED
            details = f"passed_screening={passed_screening}, minimum={minimum}"
        else:
            status = GateStatus.FAILED
            details = f"passed_screening={passed_screening}, minimum={minimum}, sparse_topic_min={sparse_min}"

        result = GateResult(
            workflow_id=workflow_id,
            gate_name="screening_safeguard",
            phase=phase,
            status=status,
            details=details,
            threshold=str(minimum),
            actual_value=str(passed_screening),
        )
        await self.repository.save_gate_result(result)
        return result

    async def run_extraction_completeness_gate(
        self,
        workflow_id: str,
        phase: str,
        completeness_ratio: float,
        weak_evidence_rate: float | None = None,
        metric_details: str | None = None,
    ) -> GateResult:
        threshold = self.settings.gates.extraction_completeness_threshold
        max_empty_rate = self.settings.gates.extraction_max_empty_rate

        async def check() -> tuple[bool, str, str, str]:
            passed = completeness_ratio >= threshold
            details = f"completeness_ratio={completeness_ratio:.2f}, threshold={threshold:.2f}"
            threshold_value = f"{threshold:.2f}"
            actual_value = f"{completeness_ratio:.2f}"
            if weak_evidence_rate is not None:
                passed = passed and weak_evidence_rate <= max_empty_rate
                details += f", weak_evidence_rate={weak_evidence_rate:.2f}, max_empty_rate={max_empty_rate:.2f}"
                threshold_value = f"completeness>={threshold:.2f}, weak<={max_empty_rate:.2f}"
                actual_value = f"completeness={completeness_ratio:.2f}, weak={weak_evidence_rate:.2f}"
            if metric_details:
                details += f", {metric_details}"
            return (
                passed,
                details,
                threshold_value,
                actual_value,
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

    async def run_cost_budget_boundary_gate(self, workflow_id: str, phase: str) -> GateResult | None:
        """Check summed ``cost_records`` spend before entering a paid phase.

        The budget is a hard ceiling in every gate profile: an exceeded budget is
        always recorded as FAILED. Returns None when ``cost_budget_max <= 0`` (disabled).
        """
        max_cost = self.settings.gates.cost_budget_max
        if max_cost <= 0:
            return None
        total_cost = await self.repository.get_total_cost(workflow_id)
        exceeded = total_cost >= max_cost
        result = GateResult(
            workflow_id=workflow_id,
            gate_name="cost_budget",
            phase=phase,
            status=GateStatus.FAILED if exceeded else GateStatus.PASSED,
            details=f"total_cost={total_cost:.4f}, max={max_cost:.4f}",
            threshold=f"{max_cost:.4f}",
            actual_value=f"{total_cost:.4f}",
        )
        await self.repository.save_gate_result(result)
        return result

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


async def enforce_cost_budget(state: ReviewState, phase: str) -> WorkflowRunResult | None:
    """Stop the workflow before ``phase`` when run spend has reached ``gates.cost_budget_max``.

    Returns a FAILED ``WorkflowRunResult`` (gate ``cost_budget``) after persisting the
    gate result, run summary, and workflow/registry status; otherwise None.
    """
    if state.settings is None or not state.db_path or not state.workflow_id:
        return None
    async with get_db(state.db_path) as db:
        repository = WorkflowRepository(db)
        result = await GateRunner(repository, state.settings).run_cost_budget_boundary_gate(state.workflow_id, phase)
        if result is None or result.status != GateStatus.FAILED:
            return None
        err_msg = (
            f"Cost budget exceeded before {phase}: spent ${result.actual_value} "
            f"of ${result.threshold} (gates.cost_budget_max). Raise the budget and resume to continue."
        )
        await repository.update_workflow_status(state.workflow_id, "failed")
    await update_registry_status(state.run_root, state.workflow_id, "failed")

    run_result = WorkflowRunResult(
        status=WorkflowRunStatus.FAILED,
        workflow_id=state.workflow_id,
        db_path=state.db_path,
        output_dir=state.output_dir or None,
        error=err_msg,
        phase=phase,
        gate="cost_budget",
        details={
            "total_cost_usd": float(result.actual_value or 0.0),
            "cost_budget_max": float(result.threshold or 0.0),
        },
    )
    run_summary_path = state.artifacts.get("run_summary")
    if run_summary_path:
        Path(run_summary_path).write_text(json.dumps(run_result.to_output_dict(), indent=2), encoding="utf-8")
    rc = state.run_context
    if rc:
        rc.log_status(err_msg)
        rc.emit_phase_done(phase, {"error": err_msg, "gate": "cost_budget"})
    return run_result
