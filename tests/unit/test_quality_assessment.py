"""
Unit tests for quality assessment module.
"""

import pytest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from src.quality import (
    QualityAssessmentTemplateGenerator,
    RiskOfBiasAssessor,
    GRADEAssessor,
)
from src.extraction.data_extractor_agent import ExtractedData


@pytest.fixture
def sample_extracted_data():
    """Create sample extracted data for testing."""
    return [
        ExtractedData(
            title="Study 1",
            authors=["Author 1"],
            year=2023,
            journal="Test Journal",
            doi="10.1000/test1",
            study_objectives=["Objective 1"],
            methodology="RCT",
            study_design="Randomized Controlled Trial",
            participants="100 participants",
            interventions="Intervention A",
            outcomes=["Outcome 1", "Outcome 2"],
            key_findings=["Finding 1"],
            limitations="None",
            country="United States",
            setting="Hospital",
            sample_size=100,
            detailed_outcomes=["Outcome measure (units)"],
            quantitative_results="Effect size: 0.5 (95% CI: 0.3-0.7)",
            ux_strategies=[],
            adaptivity_frameworks=[],
            patient_populations=[],
            accessibility_features=[],
        ),
        ExtractedData(
            title="Study 2",
            authors=["Author 2"],
            year=2024,
            journal="Test Journal 2",
            doi="10.1000/test2",
            study_objectives=["Objective 2"],
            methodology="Observational",
            study_design="Cohort Study",
            participants="200 participants",
            interventions="Intervention B",
            outcomes=["Outcome 3"],
            key_findings=["Finding 2"],
            limitations="Small sample",
            country="Canada",
            setting="Community",
            sample_size=200,
            detailed_outcomes=["Outcome measure 2"],
            quantitative_results="OR: 2.1 (95% CI: 1.3-3.4)",
            ux_strategies=[],
            adaptivity_frameworks=[],
            patient_populations=[],
            accessibility_features=[],
        ),
    ]


def test_template_generator(sample_extracted_data):
    """Test quality assessment template generation."""
    with TemporaryDirectory() as tmpdir:
        generator = QualityAssessmentTemplateGenerator(risk_of_bias_tool="RoB 2")
        template_path = Path(tmpdir) / "test_assessments.json"
        
        template_path_str = generator.generate_template(
            sample_extracted_data,
            str(template_path),
            grade_outcomes=["Outcome 1", "Outcome 2"],
        )
        
        assert Path(template_path_str).exists()
        
        with open(template_path_str, "r") as f:
            template_data = json.load(f)
        
        assert "studies" in template_data
        assert len(template_data["studies"]) == 2
        assert "grade_assessments" in template_data
        assert len(template_data["grade_assessments"]) == 2


def test_risk_of_bias_assessor(sample_extracted_data):
    """Test risk of bias assessor."""
    with TemporaryDirectory() as tmpdir:
        # Generate template
        generator = QualityAssessmentTemplateGenerator(risk_of_bias_tool="RoB 2")
        template_path = Path(tmpdir) / "test_assessments.json"
        generator.generate_template(sample_extracted_data, str(template_path))
        
        # Load and complete assessments
        with open(template_path, "r") as f:
            template_data = json.load(f)
        
        # Complete assessments
        template_data["studies"][0]["risk_of_bias"]["domains"] = {
            "Bias arising from the randomization process": "Low",
            "Bias due to deviations from intended interventions": "Some concerns",
        }
        template_data["studies"][0]["risk_of_bias"]["overall"] = "Some concerns"
        
        template_data["studies"][1]["risk_of_bias"]["domains"] = {
            "Bias arising from the randomization process": "High",
        }
        template_data["studies"][1]["risk_of_bias"]["overall"] = "High"
        
        with open(template_path, "w") as f:
            json.dump(template_data, f)
        
        # Load assessments
        assessor = RiskOfBiasAssessor()
        assessments = assessor.load_assessments(str(template_path))
        
        assert len(assessments) == 2
        
        # Generate summary table
        table = assessor.generate_summary_table(assessments)
        assert "Study ID" in table
        assert "Study 1" in table
        
        # Generate narrative
        narrative = assessor.generate_narrative_summary(assessments)
        assert len(narrative) > 0
        assert "risk of bias" in narrative.lower()


def test_grade_assessor(sample_extracted_data):
    """Test GRADE assessor."""
    with TemporaryDirectory() as tmpdir:
        # Generate template
        generator = QualityAssessmentTemplateGenerator(risk_of_bias_tool="RoB 2")
        template_path = Path(tmpdir) / "test_assessments.json"
        generator.generate_template(
            sample_extracted_data,
            str(template_path),
            grade_outcomes=["Outcome 1", "Outcome 2"],
        )
        
        # Load and complete assessments
        with open(template_path, "r") as f:
            template_data = json.load(f)
        
        # Complete GRADE assessments
        template_data["grade_assessments"][0]["certainty"] = "High"
        template_data["grade_assessments"][0]["downgrade_reasons"] = []
        template_data["grade_assessments"][1]["certainty"] = "Moderate"
        template_data["grade_assessments"][1]["downgrade_reasons"] = ["Risk of bias"]
        
        with open(template_path, "w") as f:
            json.dump(template_data, f)
        
        # Load assessments
        assessor = GRADEAssessor()
        assessments = assessor.load_assessments(str(template_path))
        
        assert len(assessments) == 2
        
        # Generate evidence profile table
        table = assessor.generate_evidence_profile_table(assessments)
        assert "Outcome" in table
        assert "Certainty" in table
        
        # Generate narrative
        narrative = assessor.generate_narrative_summary(assessments)
        assert len(narrative) > 0
        assert "GRADE" in narrative or "certainty" in narrative.lower()
