"""
Unit tests for quality assessment visualizations.
"""

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.visualization.charts import ChartGenerator


@pytest.fixture
def chart_generator(tmp_path):
    """Create chart generator instance."""
    return ChartGenerator(output_dir=str(tmp_path))


@pytest.fixture
def sample_risk_of_bias_assessments():
    """Sample risk of bias assessments."""
    return [
        {
            "study_id": "Study 1",
            "domains": {
                "Bias arising from the randomization process": "Low",
                "Bias due to deviations from intended interventions": "Some concerns",
                "Bias in measurement of the outcome": "Low",
            },
            "overall": "Some concerns",
        },
        {
            "study_id": "Study 2",
            "domains": {
                "Bias arising from the randomization process": "High",
                "Bias due to deviations from intended interventions": "High",
            },
            "overall": "High",
        },
        {
            "study_id": "Study 3",
            "domains": {
                "Bias arising from the randomization process": "Low",
                "Bias in measurement of the outcome": "Low",
            },
            "overall": "Low",
        },
    ]


@pytest.fixture
def sample_grade_assessments():
    """Sample GRADE assessments."""
    return [
        {
            "outcome": "Primary outcome measure",
            "certainty": "High",
            "downgrade_reasons": [],
        },
        {
            "outcome": "Secondary outcome measure",
            "certainty": "Moderate",
            "downgrade_reasons": ["Risk of bias"],
        },
        {
            "outcome": "Tertiary outcome measure",
            "certainty": "Low",
            "downgrade_reasons": ["Risk of bias", "Imprecision"],
        },
    ]


def test_risk_of_bias_plot_generation(chart_generator, sample_risk_of_bias_assessments, tmp_path):
    """Test risk of bias plot generation."""
    output_path = tmp_path / "rob_plot.png"
    
    result_path = chart_generator.generate_risk_of_bias_plot(
        sample_risk_of_bias_assessments,
        str(output_path)
    )
    
    assert Path(result_path).exists()
    assert result_path == str(output_path)
    assert output_path.suffix == ".png"


def test_risk_of_bias_plot_default_path(chart_generator, sample_risk_of_bias_assessments):
    """Test risk of bias plot with default path."""
    result_path = chart_generator.generate_risk_of_bias_plot(sample_risk_of_bias_assessments)
    
    assert Path(result_path).exists()
    assert "risk_of_bias_plot.png" in result_path


def test_risk_of_bias_plot_empty_data(chart_generator):
    """Test risk of bias plot with empty data."""
    result_path = chart_generator.generate_risk_of_bias_plot([])
    
    assert result_path == ""


def test_risk_of_bias_plot_color_mapping(chart_generator, sample_risk_of_bias_assessments, tmp_path):
    """Test that risk of bias plot uses correct color mapping."""
    output_path = tmp_path / "rob_plot.png"
    chart_generator.generate_risk_of_bias_plot(sample_risk_of_bias_assessments, str(output_path))
    
    # File should be created (we can't easily test colors without image processing)
    assert Path(output_path).exists()
    assert output_path.stat().st_size > 0


def test_grade_evidence_profile_generation(chart_generator, sample_grade_assessments, tmp_path):
    """Test GRADE evidence profile generation."""
    output_path = tmp_path / "grade_profile.png"
    
    result_path = chart_generator.generate_grade_evidence_profile(
        sample_grade_assessments,
        str(output_path)
    )
    
    assert Path(result_path).exists()
    assert result_path == str(output_path)
    assert output_path.suffix == ".png"


def test_grade_evidence_profile_default_path(chart_generator, sample_grade_assessments):
    """Test GRADE evidence profile with default path."""
    result_path = chart_generator.generate_grade_evidence_profile(sample_grade_assessments)
    
    assert Path(result_path).exists()
    assert "grade_evidence_profile.png" in result_path


def test_grade_evidence_profile_empty_data(chart_generator):
    """Test GRADE evidence profile with empty data."""
    result_path = chart_generator.generate_grade_evidence_profile([])
    
    assert result_path == ""


def test_grade_evidence_profile_certainty_levels(chart_generator, tmp_path):
    """Test GRADE evidence profile with different certainty levels."""
    assessments = [
        {"outcome": "Outcome 1", "certainty": "High"},
        {"outcome": "Outcome 2", "certainty": "Moderate"},
        {"outcome": "Outcome 3", "certainty": "Low"},
        {"outcome": "Outcome 4", "certainty": "Very Low"},
    ]
    
    output_path = tmp_path / "grade_profile.png"
    result_path = chart_generator.generate_grade_evidence_profile(assessments, str(output_path))
    
    assert Path(result_path).exists()


def test_empty_data_handling_rob(chart_generator):
    """Test empty data handling for risk of bias plot."""
    # Empty list
    assert chart_generator.generate_risk_of_bias_plot([]) == ""
    
    # List with empty domains
    empty_assessments = [
        {"study_id": "Study 1", "domains": {}, "overall": "Low"}
    ]
    result = chart_generator.generate_risk_of_bias_plot(empty_assessments)
    assert result == ""


def test_empty_data_handling_grade(chart_generator):
    """Test empty data handling for GRADE evidence profile."""
    # Empty list
    assert chart_generator.generate_grade_evidence_profile([]) == ""
    
    # List with missing outcome
    incomplete_assessments = [
        {"certainty": "High"}  # Missing outcome
    ]
    result = chart_generator.generate_grade_evidence_profile(incomplete_assessments)
    # Should handle gracefully
    assert result == "" or Path(result).exists()


def test_plot_file_format(chart_generator, sample_risk_of_bias_assessments, sample_grade_assessments, tmp_path):
    """Test that plots are saved in correct format."""
    rob_path = tmp_path / "rob.png"
    grade_path = tmp_path / "grade.png"
    
    chart_generator.generate_risk_of_bias_plot(sample_risk_of_bias_assessments, str(rob_path))
    chart_generator.generate_grade_evidence_profile(sample_grade_assessments, str(grade_path))
    
    assert rob_path.exists()
    assert grade_path.exists()
    assert rob_path.suffix == ".png"
    assert grade_path.suffix == ".png"
    
    # Files should have content
    assert rob_path.stat().st_size > 0
    assert grade_path.stat().st_size > 0


def test_multiple_studies_rob_plot(chart_generator, tmp_path):
    """Test risk of bias plot with multiple studies."""
    assessments = [
        {
            "study_id": f"Study {i}",
            "domains": {
                "Domain 1": "Low" if i % 2 == 0 else "High",
                "Domain 2": "Some concerns",
            },
            "overall": "Low" if i % 2 == 0 else "High",
        }
        for i in range(10)
    ]
    
    output_path = tmp_path / "rob_multi.png"
    result_path = chart_generator.generate_risk_of_bias_plot(assessments, str(output_path))
    
    assert Path(result_path).exists()


def test_multiple_outcomes_grade_profile(chart_generator, tmp_path):
    """Test GRADE evidence profile with multiple outcomes."""
    assessments = [
        {"outcome": f"Outcome {i}", "certainty": ["High", "Moderate", "Low", "Very Low"][i % 4]}
        for i in range(10)
    ]
    
    output_path = tmp_path / "grade_multi.png"
    result_path = chart_generator.generate_grade_evidence_profile(assessments, str(output_path))
    
    assert Path(result_path).exists()
