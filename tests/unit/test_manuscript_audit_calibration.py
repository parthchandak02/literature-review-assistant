from __future__ import annotations

import json
from pathlib import Path

from src.manuscript.audit_calibration import (
    AuditCalibrationCase,
    ObservedAuditShape,
    compare_audit_shape,
)


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "manuscript_audit"


def _load_case(name: str) -> AuditCalibrationCase:
    payload = json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
    return AuditCalibrationCase.model_validate(payload)


def test_calibration_fixture_schema_loads() -> None:
    case_0080 = _load_case("wf_0080_expected.json")
    case_0081 = _load_case("wf_0081_expected.json")

    assert case_0080.workflow_id == "wf-0080"
    assert case_0081.workflow_id == "wf-0081"
    assert case_0080.blocking_count_min <= case_0080.blocking_count_max
    assert case_0081.blocking_count_min <= case_0081.blocking_count_max


def test_compare_audit_shape_accepts_current_wf_0080_shape() -> None:
    expected = _load_case("wf_0080_expected.json")
    observed = ObservedAuditShape(
        workflow_id="wf-0080",
        selected_profiles=["general_systematic_review", "implementation_science"],
        verdict="reject",
        blocking_count=8,
        categories=[
            "Reporting Transparency",
            "Methods-to-Results Coherence",
            "Reporting Completeness",
            "Search and Selection Transparency",
        ],
    )

    assert compare_audit_shape(expected, observed) == []


def test_compare_audit_shape_accepts_current_wf_0081_shape() -> None:
    expected = _load_case("wf_0081_expected.json")
    observed = ObservedAuditShape(
        workflow_id="wf-0081",
        selected_profiles=["general_systematic_review", "implementation_science"],
        verdict="major_revisions",
        blocking_count=3,
        categories=[
            "Evidence-quality interpretation, Risk-of-bias and certainty alignment",
            "Search and selection transparency",
            "Overclaiming, Claim calibration",
        ],
    )

    assert compare_audit_shape(expected, observed) == []
