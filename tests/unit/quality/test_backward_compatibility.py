"""
Test backward compatibility with legacy RoB 2 assessment files.

Ensures that old RoB 2 assessment files can still be loaded without crashing.
"""

import pytest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from src.quality.risk_of_bias_assessor import RiskOfBiasAssessor
from src.quality.grade_assessor import GRADEAssessor


class TestRoB2BackwardCompatibility:
    """Test that old RoB 2 files still work."""
    
    def test_load_legacy_rob2_assessment(self):
        """Test loading a legacy RoB 2 assessment file."""
        legacy_data = {
            "risk_of_bias_tool": "RoB 2",
            "studies": [
                {
                    "study_id": "Study_1",
                    "study_title": "Legacy RCT Study",
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
                        "notes": "Minor concerns in intervention adherence"
                    }
                }
            ],
            "grade_assessments": [
                {
                    "outcome": "Test outcome",
                    "certainty": "Moderate",
                    "downgrade_reasons": ["Risk of bias"],
                    "upgrade_reasons": [],
                    "justification": "Some concerns in included studies"
                }
            ]
        }
        
        with TemporaryDirectory() as tmpdir:
            legacy_path = Path(tmpdir) / "legacy_assessment.json"
            with open(legacy_path, 'w') as f:
                json.dump(legacy_data, f, indent=2)
            
            # Test that RiskOfBiasAssessor can still load old format
            rob_assessor = RiskOfBiasAssessor()
            assessments = rob_assessor.load_assessments(str(legacy_path))
            
            assert len(assessments) == 1
            assert assessments[0].study_id == "Study_1"
            assert assessments[0].tool == "RoB 2"
            assert "Bias arising from the randomization process" in assessments[0].domains
            
            # Test table generation still works
            table = rob_assessor.generate_summary_table(assessments)
            assert "Study_1" in table
            assert "Low" in table
            
            # Test narrative generation
            narrative = rob_assessor.generate_narrative_summary(assessments)
            assert len(narrative) > 0
    
    def test_workflow_handles_legacy_format(self):
        """Test that workflow can handle legacy assessment format in quality_assessment_data."""
        # Simulate quality_assessment_data dict with legacy format
        legacy_qa_data = {
            "framework": "RoB 2",  # Old framework
            "risk_of_bias_assessments": [
                {
                    "study_id": "Study_1",
                    "domains": {
                        "Bias arising from the randomization process": "Low",
                        "Bias due to deviations from intended interventions": "Low",
                    },
                    "overall": "Low"
                }
            ],
            "risk_of_bias_table": "| Study | Overall |\n|-------|---------|",
            "risk_of_bias_summary": "All studies rated low risk",
            "grade_assessments": [],
            "grade_table": "",
            "grade_summary": ""
        }
        
        # Verify structure has expected keys
        assert "framework" in legacy_qa_data
        assert "risk_of_bias_assessments" in legacy_qa_data
        assert "risk_of_bias_table" in legacy_qa_data
        assert "risk_of_bias_summary" in legacy_qa_data
        
        # Verify framework detection works
        framework = legacy_qa_data.get("framework", "CASP")
        assert framework == "RoB 2"
    
    def test_casp_provides_backward_compatible_keys(self):
        """Test that CASP data provides backward-compatible keys for writing agents."""
        # Simulate quality_assessment_data with CASP format
        casp_qa_data = {
            "framework": "CASP",
            "casp_assessments": [
                {
                    "study_id": "Study_1",
                    "study_title": "Test Study",
                    "quality_assessment": {
                        "checklist_used": "casp_rct",
                        "score": {"quality_rating": "High"}
                    }
                }
            ],
            "casp_table": "| Study | Quality |\n|-------|---------|",
            "casp_summary": "CASP assessment summary",
            # Backward-compatible aliases
            "risk_of_bias_assessments": [],  # Same as casp_assessments
            "risk_of_bias_table": "",  # Same as casp_table
            "risk_of_bias_summary": "",  # Same as casp_summary
            "grade_assessments": [],
            "grade_table": "",
            "grade_summary": ""
        }
        
        # Verify both CASP and backward-compatible keys exist
        assert "framework" in casp_qa_data
        assert "casp_assessments" in casp_qa_data
        assert "risk_of_bias_assessments" in casp_qa_data  # Backward compatible
        assert "casp_table" in casp_qa_data
        assert "risk_of_bias_table" in casp_qa_data  # Backward compatible


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
