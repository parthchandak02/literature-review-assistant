from __future__ import annotations

from src.models import ExtractionRecord, OutcomeRecord, StudyDesign
from src.synthesis.sensitivity import leave_one_out, run_sensitivity_analysis, subgroup_analysis


def _record(paper_id: str, effect: str, se: str, design: StudyDesign = StudyDesign.RCT) -> ExtractionRecord:
    return ExtractionRecord(
        paper_id=paper_id,
        study_design=design,
        intervention_description="AI tutoring intervention",
        outcomes=[
            OutcomeRecord(
                name="exam_score",
                effect_size=effect,
                se=se,
                title=paper_id,
            )
        ],
        results_summary={"summary": "Structured effect available."},
    )


def test_leave_one_out_requires_three_studies() -> None:
    records = [_record("p1", "0.2", "0.1"), _record("p2", "0.3", "0.1")]
    assert leave_one_out(records, "exam_score") == []


def test_run_sensitivity_analysis_returns_subgroups() -> None:
    records = [
        _record("p1", "0.2", "0.1", StudyDesign.RCT),
        _record("p2", "0.3", "0.1", StudyDesign.RCT),
        _record("p3", "0.4", "0.1", StudyDesign.NON_RANDOMIZED),
    ]
    result = run_sensitivity_analysis(records, "exam_score", subgroup_cols=["study_design"])
    assert result is not None
    assert result.n_studies == 3
    assert "study_design" in result.subgroup_results


def test_subgroup_analysis_skips_singleton_groups() -> None:
    records = [
        _record("p1", "0.2", "0.1", StudyDesign.RCT),
        _record("p2", "0.3", "0.1", StudyDesign.RCT),
        _record("p3", "0.4", "0.1", StudyDesign.NON_RANDOMIZED),
    ]
    groups = subgroup_analysis(records, "exam_score", subgroup_cols=["study_design"])
    assert "study_design" in groups
    assert all(group.n_studies >= 2 for group in groups["study_design"])
