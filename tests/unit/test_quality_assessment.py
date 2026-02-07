"""
Unit tests for quality assessment module.

Tests both CASP framework (primary) and backward compatibility with legacy RoB 2.
"""

import pytest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from src.quality import (
    QualityAssessmentTemplateGenerator,
    GRADEAssessor,
)
# Import deprecated classes for backward compatibility tests
from src.quality.risk_of_bias_assessor import RiskOfBiasAssessor
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


def test_template_generator_casp(sample_extracted_data):
    """Test CASP quality assessment template generation."""
    with TemporaryDirectory() as tmpdir:
        generator = QualityAssessmentTemplateGenerator(framework="CASP")
        template_path = Path(tmpdir) / "test_casp_assessments.json"
        
        template_path_str = generator.generate_template(
            sample_extracted_data,
            str(template_path),
            grade_outcomes=["Outcome 1", "Outcome 2"],
        )
        
        assert Path(template_path_str).exists()
        
        with open(template_path_str, "r") as f:
            template_data = json.load(f)
        
        assert "framework" in template_data
        assert template_data["framework"] == "CASP"
        assert "studies" in template_data
        assert len(template_data["studies"]) == 2
        assert "grade_assessments" in template_data
        assert len(template_data["grade_assessments"]) == 2
        
        # Verify CASP structure
        study = template_data["studies"][0]
        assert "quality_assessment" in study
        assert "checklist_used" in study["quality_assessment"]
        assert "questions" in study["quality_assessment"]
        assert "score" in study["quality_assessment"]


def test_template_generator_legacy_rob2(sample_extracted_data):
    """Test legacy RoB 2 template generation (backward compatibility)."""
    with TemporaryDirectory() as tmpdir:
        generator = QualityAssessmentTemplateGenerator(framework="RoB 2")
        template_path = Path(tmpdir) / "test_rob2_assessments.json"
        
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


def test_risk_of_bias_assessor_legacy(sample_extracted_data):
    """Test legacy risk of bias assessor can load old RoB 2 files (backward compatibility)."""
    with TemporaryDirectory() as tmpdir:
        # Create a legacy RoB 2 assessment file manually
        template_path = Path(tmpdir) / "legacy_rob2_assessments.json"
        legacy_data = {
            "risk_of_bias_tool": "RoB 2",
            "studies": [
                {
                    "study_id": "Study_1",
                    "study_title": "Study 1",
                    "study_design": "RCT",
                    "risk_of_bias": {
                        "tool": "RoB 2",
                        "domains": {
                            "Bias arising from the randomization process": "Low",
                            "Bias due to deviations from intended interventions": "Some concerns",
                            "Bias due to missing outcome data": "Low",
                            "Bias in measurement of the outcome": "Low",
                            "Bias in selection of the reported result": "Low"
                        },
                        "overall": "Some concerns",
                        "notes": "Minor concerns"
                    }
                },
                {
                    "study_id": "Study_2",
                    "study_title": "Study 2",
                    "study_design": "Cohort",
                    "risk_of_bias": {
                        "tool": "RoB 2",
                        "domains": {
                            "Bias arising from the randomization process": "High",
                            "Bias due to deviations from intended interventions": "High",
                        },
                        "overall": "High",
                        "notes": "High risk"
                    }
                }
            ],
            "grade_assessments": []
        }
        
        with open(template_path, "w") as f:
            json.dump(legacy_data, f)
        
        # Verify RiskOfBiasAssessor can load old format
        assessor = RiskOfBiasAssessor()
        assessments = assessor.load_assessments(str(template_path))
        
        assert len(assessments) == 2
        
        # Generate summary table
        table = assessor.generate_summary_table(assessments)
        assert "Study ID" in table or "Study_1" in table
        
        # Generate narrative
        narrative = assessor.generate_narrative_summary(assessments)
        assert len(narrative) > 0
        assert "risk of bias" in narrative.lower() or "bias" in narrative.lower()


def test_grade_assessor(sample_extracted_data):
    """Test GRADE assessor with CASP framework."""
    with TemporaryDirectory() as tmpdir:
        # Generate template
        generator = QualityAssessmentTemplateGenerator(framework="CASP")
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
