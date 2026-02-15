"""Reliability gates for checkpoint, citation, and budget controls."""

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class GateResult:
    """Outcome of a single reliability gate."""

    gate_name: str
    passed: bool
    details: str


class ReliabilityGateRunner:
    """Evaluates restart reliability criteria before final export."""

    def __init__(
        self,
        max_invalid_citation_ratio: float = 0.01,
        max_cost_usd: float | None = None,
    ):
        self.max_invalid_citation_ratio = max_invalid_citation_ratio
        self.max_cost_usd = max_cost_usd

    def run(self, state: Mapping[str, Any]) -> list[GateResult]:
        results = [
            self._checkpoint_gate(state),
            self._citation_gate(state),
            self._cost_gate(state),
        ]
        return results

    def _checkpoint_gate(self, state: Mapping[str, Any]) -> GateResult:
        enabled = bool(state.get("checkpoint_resume_enabled", False))
        return GateResult(
            gate_name="checkpoint_resume",
            passed=enabled,
            details="checkpoint resume is enabled" if enabled else "checkpoint resume is disabled",
        )

    def _citation_gate(self, state: Mapping[str, Any]) -> GateResult:
        invalid = int(state.get("invalid_citation_count", 0))
        total = int(state.get("total_citation_count", 0))
        ratio = (invalid / total) if total else 0.0
        passed = ratio <= self.max_invalid_citation_ratio
        return GateResult(
            gate_name="citation_quality",
            passed=passed,
            details=f"invalid_ratio={ratio:.4f} threshold={self.max_invalid_citation_ratio:.4f}",
        )

    def _cost_gate(self, state: Mapping[str, Any]) -> GateResult:
        if self.max_cost_usd is None:
            return GateResult(
                gate_name="cost_budget",
                passed=True,
                details="cost gate disabled",
            )
        observed = float(state.get("total_cost_usd", 0.0))
        passed = observed <= self.max_cost_usd
        return GateResult(
            gate_name="cost_budget",
            passed=passed,
            details=f"observed={observed:.4f} budget={self.max_cost_usd:.4f}",
        )
