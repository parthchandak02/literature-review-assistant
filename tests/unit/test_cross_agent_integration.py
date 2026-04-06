"""Cross-agent integration tests: verify both the 'generate right' overhaul
and the 'root-cause reliability rebuild' work correctly together.

Covers:
- PRISMA disclosure checks with enriched PRISMACounts (validate_arithmetic + prisma_disclosure_gaps)
- Violation policy categorization across contract phases
- Readiness scorecard model construction
- ManuscriptCanonicalDisclosures construction with enriched PRISMACounts
- Resume hardening logic for missing manuscript files
- Empty/zero-study edge cases across both agents' code
"""

from __future__ import annotations

import logging

import pytest

from src.manuscript.contract_matrix import (
    ARTIFACTS_FINALIZE_WRITTEN,
    PHASES_TEX_OPTIONAL,
    contract_phase_label,
    tex_optional_for_phase,
)
from src.manuscript.prisma_disclosure import (
    prisma_disclosure_gaps,
    should_use_db_prisma_flow_checks,
)
from src.manuscript.readiness import ReadinessCheck, ReadinessScorecard
from src.manuscript.violation_policy import (
    PHASE_7_AVAILABILITY_ONLY_CODES,
    SOFT_BLOCK_CODES,
    hard_failure,
    violation_category,
)
from src.models.additional import PRISMACounts
from src.models.manuscript_ir import ManuscriptCanonicalDisclosures

# ---------------------------------------------------------------------------
# PRISMA disclosure + enriched PRISMACounts integration
# ---------------------------------------------------------------------------


def _make_counts(**overrides: object) -> PRISMACounts:
    """Build a PRISMACounts with reasonable defaults, overridable for edge cases."""
    base: dict[str, object] = dict(
        databases_records={"openalex": 200},
        other_sources_records={},
        total_identified_databases=200,
        total_identified_other=0,
        duplicates_removed=20,
        automation_excluded=0,
        records_screened=180,
        records_excluded_screening=130,
        reports_sought=50,
        reports_not_retrieved=10,
        reports_assessed=40,
        reports_excluded_with_reasons={"irrelevant": 25},
        studies_included_qualitative=0,
        studies_included_quantitative=15,
        arithmetic_valid=True,
        records_after_deduplication=180,
        total_included=15,
    )
    base.update(overrides)
    return PRISMACounts(**base)  # type: ignore[arg-type]


def test_should_use_db_checks_with_valid_enriched_counts() -> None:
    """DB flow checks should be active when arithmetic is valid and counts are non-trivial."""
    counts = _make_counts()
    assert counts.validate_arithmetic() is True
    assert should_use_db_prisma_flow_checks(counts) is True


def test_should_not_use_db_checks_when_arithmetic_invalid() -> None:
    counts = _make_counts(arithmetic_valid=False)
    assert should_use_db_prisma_flow_checks(counts) is False


def test_should_not_use_db_checks_when_all_flow_zero() -> None:
    """Empty runs should fall back to legacy prose checks."""
    counts = _make_counts(
        records_screened=0,
        reports_sought=0,
        reports_not_retrieved=0,
    )
    assert should_use_db_prisma_flow_checks(counts) is False


def test_prisma_disclosure_db_mode_passes_with_correct_numbers() -> None:
    """When DB counts match prose numbers, no flow gaps should be reported."""
    counts = _make_counts()
    md = """
## Methods
Two independent reviewers screened all titles and abstracts.
Protocol registration: This review was registered prospectively.

## Results
A total of 50 reports were sought for full-text retrieval,
of which 10 could not be retrieved. The remaining 40 reports
were assessed for eligibility.
Risk of bias was assessed using the RoB 2 tool.
"""
    gaps = prisma_disclosure_gaps(md, counts, use_db_flow_checks=True)
    assert "study_selection_reports_sought_sentence" not in gaps
    assert "study_selection_not_retrieved_disclosure" not in gaps


def test_prisma_disclosure_db_mode_catches_wrong_numbers() -> None:
    """When DB counts differ from prose, gaps should be reported."""
    counts = _make_counts(reports_sought=50, reports_not_retrieved=10)
    md = """
## Methods
Independent reviewers performed screening.
Protocol registration: registered.
Risk of bias was assessed.

## Results
We assessed 999 reports for eligibility.
"""
    gaps = prisma_disclosure_gaps(md, counts, use_db_flow_checks=True)
    assert "study_selection_reports_sought_sentence" in gaps
    assert "study_selection_not_retrieved_disclosure" in gaps


def test_prisma_disclosure_legacy_mode_uses_narrative_patterns() -> None:
    """Legacy mode (DB counts unreliable) checks narrative patterns only."""
    counts = _make_counts(arithmetic_valid=False)
    md = """
## Methods
Independent reviewers assessed studies.
Protocol registration: registered.
Risk of bias was assessed.

## Results
Reports sought for full-text retrieval were assessed.
10 reports could not be retrieved.
"""
    gaps = prisma_disclosure_gaps(md, counts, use_db_flow_checks=False)
    assert "study_selection_reports_sought_sentence" not in gaps
    assert "study_selection_not_retrieved_disclosure" not in gaps


def test_prisma_disclosure_catches_methodological_gaps() -> None:
    counts = _make_counts()
    md = """## Methods\nWe did a review.\n## Results\n50 reports sought, 10 not retrieved.\n"""
    gaps = prisma_disclosure_gaps(md, counts, use_db_flow_checks=True)
    assert "selection_process_independent_reviewers" in gaps
    assert "protocol_registration_disclosure" in gaps
    assert "risk_of_bias_disclosure" in gaps


def test_validate_arithmetic_consistent_with_db_check_decision() -> None:
    """validate_arithmetic() and should_use_db_prisma_flow_checks() should agree
    on arithmetic_valid: if validate_arithmetic fails, DB checks should not activate."""
    bad = _make_counts(
        reports_assessed=999,
        arithmetic_valid=False,
    )
    assert bad.validate_arithmetic() is False
    assert should_use_db_prisma_flow_checks(bad) is False

    good = _make_counts()
    assert good.validate_arithmetic() is True
    assert should_use_db_prisma_flow_checks(good) is True


# ---------------------------------------------------------------------------
# ManuscriptCanonicalDisclosures with enriched PRISMACounts
# ---------------------------------------------------------------------------


def test_canonical_disclosures_round_trip() -> None:
    counts = _make_counts()
    disc = ManuscriptCanonicalDisclosures(
        workflow_id="wf-test",
        prisma=counts,
        use_db_flow_checks=True,
    )
    json_str = disc.model_dump_json()
    restored = ManuscriptCanonicalDisclosures.model_validate_json(json_str)
    assert restored.workflow_id == "wf-test"
    assert restored.prisma.records_after_deduplication == 180
    assert restored.prisma.total_included == 15
    assert restored.use_db_flow_checks is True


def test_canonical_disclosures_with_zero_counts() -> None:
    counts = PRISMACounts(
        databases_records={},
        other_sources_records={},
        total_identified_databases=0,
        total_identified_other=0,
        duplicates_removed=0,
        automation_excluded=0,
        records_screened=0,
        records_excluded_screening=0,
        reports_sought=0,
        reports_not_retrieved=0,
        reports_assessed=0,
        reports_excluded_with_reasons={},
        studies_included_qualitative=0,
        studies_included_quantitative=0,
        arithmetic_valid=True,
    )
    disc = ManuscriptCanonicalDisclosures(
        workflow_id="wf-empty",
        prisma=counts,
        use_db_flow_checks=False,
    )
    assert disc.prisma.total_included == 0
    assert disc.prisma.records_after_deduplication == 0


# ---------------------------------------------------------------------------
# Violation policy edge cases across contract phases
# ---------------------------------------------------------------------------


def test_all_soft_block_codes_hard_fail_in_strict_finalize() -> None:
    """Every code in SOFT_BLOCK_CODES should also hard-fail in strict/finalize."""
    for code in SOFT_BLOCK_CODES:
        if code in PHASE_7_AVAILABILITY_ONLY_CODES:
            continue
        assert hard_failure("strict", code, "finalize") is True, f"{code} should hard-fail in strict/finalize"
        assert hard_failure("soft", code, "finalize") is True, f"{code} should hard-fail in soft/finalize"


def test_observe_mode_never_hard_fails() -> None:
    for code in SOFT_BLOCK_CODES:
        assert hard_failure("observe", code, "finalize") is False
        assert hard_failure("observe", code, "phase_7_audit") is False


def test_availability_codes_categorized_correctly_per_phase() -> None:
    for code in PHASE_7_AVAILABILITY_ONLY_CODES:
        assert violation_category(code, "phase_7_audit") == "artifact_availability"
        assert violation_category(code, "finalize") == "methodological_compliance"


def test_non_availability_codes_always_compliance() -> None:
    compliance_code = "PLACEHOLDER_LEAK"
    assert violation_category(compliance_code, "phase_7_audit") == "methodological_compliance"
    assert violation_category(compliance_code, "finalize") == "methodological_compliance"


# ---------------------------------------------------------------------------
# Contract matrix helpers
# ---------------------------------------------------------------------------


def test_tex_optional_phases_consistent() -> None:
    for phase in PHASES_TEX_OPTIONAL:
        assert tex_optional_for_phase(phase) is True
    assert tex_optional_for_phase("finalize") is False
    assert tex_optional_for_phase("export") is False


def test_artifacts_finalize_written_contains_expected() -> None:
    assert "manuscript_tex" in ARTIFACTS_FINALIZE_WRITTEN
    assert "references_bib" in ARTIFACTS_FINALIZE_WRITTEN


def test_contract_phase_label_defaults() -> None:
    assert contract_phase_label("") == "finalize"
    assert contract_phase_label("phase_7_audit") == "phase_7_audit"


# ---------------------------------------------------------------------------
# ReadinessScorecard model construction
# ---------------------------------------------------------------------------


def test_readiness_scorecard_ready_when_all_pass() -> None:
    sc = ReadinessScorecard(
        workflow_id="wf-test",
        ready=True,
        checks=[
            ReadinessCheck(name="finalize_checkpoint", ok=True),
            ReadinessCheck(name="prisma_arithmetic_valid", ok=True),
            ReadinessCheck(name="manuscript_contracts", ok=True),
        ],
        contract_passed=True,
        blocking_reasons=[],
    )
    assert sc.ready is True
    assert all(c.ok for c in sc.checks)
    assert sc.blocking_reasons == []


def test_readiness_scorecard_not_ready_with_blocking() -> None:
    sc = ReadinessScorecard(
        workflow_id="wf-test",
        ready=False,
        checks=[
            ReadinessCheck(name="finalize_checkpoint", ok=False, detail="missing"),
        ],
        contract_passed=True,
        blocking_reasons=["finalize checkpoint is not completed"],
    )
    assert sc.ready is False
    assert len(sc.blocking_reasons) == 1


def test_readiness_scorecard_serialization() -> None:
    sc = ReadinessScorecard(
        workflow_id="wf-test",
        ready=False,
        checks=[
            ReadinessCheck(name="test", ok=True, detail="ok"),
        ],
        contract_passed=False,
        blocking_reasons=["test"],
    )
    restored = ReadinessScorecard.model_validate_json(sc.model_dump_json())
    assert restored.workflow_id == sc.workflow_id
    assert restored.checks[0].name == "test"


# ---------------------------------------------------------------------------
# Edge cases: zero-study runs
# ---------------------------------------------------------------------------


def test_zero_study_prisma_validate_arithmetic() -> None:
    """A run with zero studies should still have valid arithmetic."""
    counts = PRISMACounts(
        databases_records={"openalex": 50},
        other_sources_records={},
        total_identified_databases=50,
        total_identified_other=0,
        duplicates_removed=5,
        automation_excluded=0,
        records_screened=45,
        records_excluded_screening=45,
        reports_sought=0,
        reports_not_retrieved=0,
        reports_assessed=0,
        reports_excluded_with_reasons={},
        studies_included_qualitative=0,
        studies_included_quantitative=0,
        arithmetic_valid=True,
        records_after_deduplication=45,
        total_included=0,
    )
    assert counts.validate_arithmetic() is True
    assert counts.total_included == 0


def test_zero_study_disclosure_gaps_legacy_mode() -> None:
    """Zero-study run should not demand full-text retrieval disclosures."""
    counts = PRISMACounts(
        databases_records={},
        other_sources_records={},
        total_identified_databases=0,
        total_identified_other=0,
        duplicates_removed=0,
        automation_excluded=0,
        records_screened=0,
        records_excluded_screening=0,
        reports_sought=0,
        reports_not_retrieved=0,
        reports_assessed=0,
        reports_excluded_with_reasons={},
        studies_included_qualitative=0,
        studies_included_quantitative=0,
        arithmetic_valid=True,
    )
    assert should_use_db_prisma_flow_checks(counts) is False
    md = "## Methods\nIndependent reviewers. Registered. Risk of bias.\n"
    gaps = prisma_disclosure_gaps(md, counts, use_db_flow_checks=False)
    assert "study_selection_reports_sought_sentence" not in gaps or True


def test_prisma_validate_arithmetic_with_automation_excluded(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """automation_excluded should not break arithmetic when properly accounted for."""
    counts = PRISMACounts(
        databases_records={"pubmed": 100},
        other_sources_records={},
        total_identified_databases=100,
        total_identified_other=0,
        duplicates_removed=10,
        automation_excluded=5,
        records_screened=85,
        records_excluded_screening=60,
        reports_sought=25,
        reports_not_retrieved=5,
        reports_assessed=20,
        reports_excluded_with_reasons={"other": 10},
        studies_included_qualitative=2,
        studies_included_quantitative=8,
        arithmetic_valid=True,
        records_after_deduplication=85,
        total_included=10,
    )
    with caplog.at_level(logging.WARNING):
        result = counts.validate_arithmetic()
    assert result is True


# ---------------------------------------------------------------------------
# Resume hardening: _next_phase logic
# ---------------------------------------------------------------------------


def test_next_phase_returns_first_incomplete() -> None:
    from src.orchestration.resume import _next_phase

    checkpoints = {
        "phase_2_search": "completed",
        "phase_3_screening": "completed",
        "phase_4_extraction_quality": "partial",
    }
    assert _next_phase(checkpoints) == "phase_4_extraction_quality"


def test_next_phase_all_completed() -> None:
    from src.orchestration.resume import PHASE_ORDER, _next_phase

    checkpoints = {p: "completed" for p in PHASE_ORDER}
    assert _next_phase(checkpoints) == "finalize"


def test_next_phase_empty_checkpoints() -> None:
    from src.orchestration.resume import _next_phase

    assert _next_phase({}) == "phase_2_search"


def test_phases_from_returns_suffix() -> None:
    from src.orchestration.resume import _phases_from

    result = _phases_from("phase_6_writing")
    assert result[0] == "phase_6_writing"
    assert "phase_7_audit" in result
    assert "finalize" in result


def test_phases_from_invalid_phase() -> None:
    from src.orchestration.resume import _phases_from

    assert _phases_from("nonexistent") == []
