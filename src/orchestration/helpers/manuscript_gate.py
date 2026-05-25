from __future__ import annotations

from src.manuscript.contracts import ManuscriptContractResult
from src.models import ManuscriptAuditResult


def collect_manuscript_gate_failure_reasons(
    contract_result: ManuscriptContractResult,
    audit_result: ManuscriptAuditResult,
) -> list[str]:
    reasons: list[str] = []
    if not contract_result.passed:
        reasons.append(
            f"contract gate failed in mode={contract_result.mode} with {len(contract_result.violations)} violation(s)"
        )
    if not audit_result.passed:
        reasons.append(
            f"audit gate failed in mode={audit_result.mode} "
            f"(verdict={audit_result.verdict}, blocking={audit_result.blocking_count})"
        )
    return reasons


def resolve_manuscript_gate_action(audit_gate_mode: str, gate_blocked: bool) -> str:
    if not gate_blocked:
        return "pass"
    if audit_gate_mode == "advisory":
        return "advisory_only"
    return "strict_block"


def manuscript_gate_blocks_workflow(audit_gate_mode: str, gate_blocked: bool) -> bool:
    return gate_blocked and audit_gate_mode == "strict"
