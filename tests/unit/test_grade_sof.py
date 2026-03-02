"""Unit tests for GRADE Summary of Findings table (Enhancement #10)."""

from __future__ import annotations

from src.export.ieee_latex import render_grade_sof_latex
from src.models.enums import GRADECertainty
from src.models.quality import GRADEOutcomeAssessment, GradeSoFRow, GradeSoFTable
from src.quality.grade import build_sof_table


def _make_assessment(
    outcome_name="LDL-C reduction",
    n_studies=5,
    study_designs="RCT",
    final_certainty=GRADECertainty.MODERATE,
    risk_of_bias_downgrade=1,
    inconsistency_downgrade=0,
    indirectness_downgrade=0,
    imprecision_downgrade=0,
    publication_bias_downgrade=0,
    large_effect_upgrade=0,
    dose_response_upgrade=0,
    residual_confounding_upgrade=0,
):
    return GRADEOutcomeAssessment(
        outcome_name=outcome_name,
        number_of_studies=n_studies,
        study_designs=study_designs,
        starting_certainty=GRADECertainty.HIGH,
        risk_of_bias_downgrade=risk_of_bias_downgrade,
        inconsistency_downgrade=inconsistency_downgrade,
        indirectness_downgrade=indirectness_downgrade,
        imprecision_downgrade=imprecision_downgrade,
        publication_bias_downgrade=publication_bias_downgrade,
        large_effect_upgrade=large_effect_upgrade,
        dose_response_upgrade=dose_response_upgrade,
        residual_confounding_upgrade=residual_confounding_upgrade,
        final_certainty=final_certainty,
        justification="Test justification.",
    )


def test_build_sof_table_one_row():
    assessment = _make_assessment(
        outcome_name="All-cause mortality", n_studies=3, final_certainty=GRADECertainty.LOW
    )
    table = build_sof_table([assessment], topic="Statins in elderly")
    assert table.topic == "Statins in elderly"
    assert len(table.rows) == 1
    row = table.rows[0]
    assert row.outcome_name == "All-cause mortality"
    assert row.n_studies == 3
    assert row.certainty == GRADECertainty.LOW


def test_build_sof_table_downgrade_labels():
    table = build_sof_table([_make_assessment(risk_of_bias_downgrade=2)])
    assert table.rows[0].risk_of_bias == "very serious"


def test_build_sof_table_not_serious_label():
    table = build_sof_table([_make_assessment(risk_of_bias_downgrade=0)])
    assert table.rows[0].risk_of_bias == "not serious"


def test_build_sof_table_upgrade_labels():
    table = build_sof_table([_make_assessment(large_effect_upgrade=1)])
    assert "large effect" in table.rows[0].other_considerations


def test_build_sof_table_dose_response_upgrade():
    table = build_sof_table([_make_assessment(dose_response_upgrade=1)])
    assert "dose-response" in table.rows[0].other_considerations


def test_build_sof_table_empty_assessments():
    table = build_sof_table([])
    assert isinstance(table, GradeSoFTable)
    assert table.rows == []


def test_render_grade_sof_latex_structure():
    table = build_sof_table([_make_assessment(outcome_name="Cardiovascular events")], topic="Statin RCT")
    latex = render_grade_sof_latex(table)
    assert r"\begin{longtable}" in latex
    assert r"\end{longtable}" in latex
    assert "Appendix: GRADE" in latex
    assert "Cardiovascular events" in latex
    assert "Statin RCT" in latex


def test_render_grade_sof_latex_certainty_label():
    table = build_sof_table([_make_assessment(final_certainty=GRADECertainty.VERY_LOW)])
    latex = render_grade_sof_latex(table)
    assert "VERY LOW" in latex


def test_grade_sof_row_model_roundtrip():
    row = GradeSoFRow(
        outcome_name="Test outcome",
        n_studies=2,
        study_design="RCT",
        risk_of_bias="not serious",
        inconsistency="not serious",
        indirectness="not serious",
        imprecision="serious",
        other_considerations="none",
        certainty=GRADECertainty.HIGH,
        effect_summary="No significant effect.",
    )
    assert row.certainty == GRADECertainty.HIGH
    d = row.model_dump()
    assert d["outcome_name"] == "Test outcome"
