from src.manuscript.contracts import ContractViolation, ManuscriptContractResult
from src.models.manuscript_review import ManuscriptAuditResult
from src.orchestration.workflow import _collect_manuscript_gate_failure_reasons


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
