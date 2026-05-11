from __future__ import annotations

import pytest

from src.manuscript.contracts import ContractViolation, ManuscriptContractResult
from src.models.config import GatesConfig
from src.models.manuscript_review import ManuscriptAuditResult
from src.orchestration.workflow import (
    _collect_manuscript_gate_failure_reasons,
    _manuscript_gate_blocks_workflow,
    _resolve_manuscript_gate_action,
)


def test_gates_config_defaults_to_advisory_audit_gate_mode() -> None:
    config = GatesConfig()
    assert config.audit_gate_mode == "advisory"


def test_advisory_audit_gate_preserves_workflow_completion() -> None:
    assert _resolve_manuscript_gate_action("advisory", gate_blocked=True) == "advisory_only"
    assert _manuscript_gate_blocks_workflow("advisory", gate_blocked=True) is False


def test_strict_audit_gate_blocks_workflow() -> None:
    assert _resolve_manuscript_gate_action("strict", gate_blocked=True) == "strict_block"
    assert _manuscript_gate_blocks_workflow("strict", gate_blocked=True) is True
    assert _resolve_manuscript_gate_action("strict", gate_blocked=False) == "pass"


def test_collect_manuscript_gate_failure_reasons_includes_contract_and_audit_failures() -> None:
    contract_result = ManuscriptContractResult(
        passed=False,
        mode="strict",
        violations=[
            ContractViolation(
                code="PLACEHOLDER_LEAK",
                severity="error",
                message="placeholder leaked",
            )
        ],
    )
    audit_result = ManuscriptAuditResult(
        audit_run_id="audit-001",
        workflow_id="wf-1",
        mode="strict",
        verdict="reject",
        passed=False,
        selected_profiles=["general_systematic_review"],
        summary="failed",
        total_findings=2,
        major_count=1,
        minor_count=1,
        note_count=0,
        blocking_count=1,
        total_cost_usd=0.01,
    )

    reasons = _collect_manuscript_gate_failure_reasons(contract_result, audit_result)

    assert len(reasons) == 2
    assert "contract gate failed" in reasons[0]
    assert "audit gate failed" in reasons[1]


def test_collect_manuscript_gate_failure_reasons_empty_when_both_gates_pass() -> None:
    contract_result = ManuscriptContractResult(passed=True, mode="strict", violations=[])
    audit_result = ManuscriptAuditResult(
        audit_run_id="audit-002",
        workflow_id="wf-1",
        mode="strict",
        verdict="accept",
        passed=True,
        selected_profiles=["general_systematic_review"],
        summary="ok",
        total_findings=0,
        major_count=0,
        minor_count=0,
        note_count=0,
        blocking_count=0,
        total_cost_usd=0.0,
    )

    assert _collect_manuscript_gate_failure_reasons(contract_result, audit_result) == []


def _contract_result(passed: bool) -> ManuscriptContractResult:
    return ManuscriptContractResult(
        passed=passed,
        mode="strict",
        violations=(
            []
            if passed
            else [
                ContractViolation(
                    code="PLACEHOLDER_LEAK",
                    severity="error",
                    message="placeholder leaked",
                )
            ]
        ),
    )


def _audit_result(passed: bool) -> ManuscriptAuditResult:
    return ManuscriptAuditResult(
        audit_run_id="audit-matrix",
        workflow_id="wf-1",
        mode="strict",
        verdict="accept" if passed else "major_revisions",
        passed=passed,
        selected_profiles=["general_systematic_review"],
        summary="ok" if passed else "failed",
        total_findings=0 if passed else 2,
        major_count=0 if passed else 1,
        minor_count=0 if passed else 1,
        note_count=0,
        blocking_count=0 if passed else 1,
        total_cost_usd=0.0,
    )


@pytest.mark.parametrize(
    ("contract_passed", "audit_passed", "expected_reason_count"),
    [
        (True, True, 0),
        (False, True, 1),
        (True, False, 1),
        (False, False, 2),
    ],
)
def test_manuscript_gate_matrix_covers_single_and_combined_failures(
    contract_passed: bool,
    audit_passed: bool,
    expected_reason_count: int,
) -> None:
    reasons = _collect_manuscript_gate_failure_reasons(
        _contract_result(contract_passed),
        _audit_result(audit_passed),
    )

    assert len(reasons) == expected_reason_count
    if not contract_passed:
        assert any("contract gate failed" in reason for reason in reasons)
    if not audit_passed:
        assert any("audit gate failed" in reason for reason in reasons)


@pytest.mark.parametrize(
    ("audit_gate_mode", "contract_passed", "audit_passed", "expected_action", "expected_blocks"),
    [
        ("advisory", True, True, "pass", False),
        ("strict", True, True, "pass", False),
        ("advisory", False, True, "advisory_only", False),
        ("strict", False, True, "strict_block", True),
        ("advisory", True, False, "advisory_only", False),
        ("strict", True, False, "strict_block", True),
    ],
)
def test_manuscript_gate_action_matrix(
    audit_gate_mode: str,
    contract_passed: bool,
    audit_passed: bool,
    expected_action: str,
    expected_blocks: bool,
) -> None:
    reasons = _collect_manuscript_gate_failure_reasons(
        _contract_result(contract_passed),
        _audit_result(audit_passed),
    )
    gate_blocked = len(reasons) > 0

    assert _resolve_manuscript_gate_action(audit_gate_mode, gate_blocked) == expected_action
    assert _manuscript_gate_blocks_workflow(audit_gate_mode, gate_blocked) is expected_blocks
