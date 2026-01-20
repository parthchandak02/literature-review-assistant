"""
Test fixtures for quality assessments.
"""

from typing import Dict, List, Any


def get_mock_risk_of_bias_assessments() -> List[Dict[str, Any]]:
    """Get mock risk of bias assessments."""
    return [
        {
            "study_id": "Study 1",
            "domains": {
                "Bias arising from the randomization process": "Low",
                "Bias due to deviations from intended interventions": "Some concerns",
                "Bias due to missing outcome data": "Low",
                "Bias in measurement of the outcome": "Low",
                "Bias in selection of the reported result": "Low",
            },
            "overall": "Some concerns",
        },
        {
            "study_id": "Study 2",
            "domains": {
                "Bias arising from the randomization process": "High",
                "Bias due to deviations from intended interventions": "High",
                "Bias due to missing outcome data": "Some concerns",
                "Bias in measurement of the outcome": "Low",
                "Bias in selection of the reported result": "Some concerns",
            },
            "overall": "High",
        },
        {
            "study_id": "Study 3",
            "domains": {
                "Bias arising from the randomization process": "Low",
                "Bias due to deviations from intended interventions": "Low",
                "Bias due to missing outcome data": "Low",
                "Bias in measurement of the outcome": "Low",
                "Bias in selection of the reported result": "Low",
            },
            "overall": "Low",
        },
    ]


def get_mock_grade_assessments() -> List[Dict[str, Any]]:
    """Get mock GRADE assessments."""
    return [
        {
            "outcome": "Primary outcome measure",
            "certainty": "High",
            "downgrade_reasons": [],
            "study_design": "RCT",
            "risk_of_bias": "Low",
            "inconsistency": "Not serious",
            "indirectness": "Not serious",
            "imprecision": "Not serious",
            "publication_bias": "Not serious",
        },
        {
            "outcome": "Secondary outcome measure",
            "certainty": "Moderate",
            "downgrade_reasons": ["Risk of bias"],
            "study_design": "RCT",
            "risk_of_bias": "Serious",
            "inconsistency": "Not serious",
            "indirectness": "Not serious",
            "imprecision": "Not serious",
            "publication_bias": "Not serious",
        },
        {
            "outcome": "Tertiary outcome measure",
            "certainty": "Low",
            "downgrade_reasons": ["Risk of bias", "Imprecision"],
            "study_design": "Observational",
            "risk_of_bias": "Serious",
            "inconsistency": "Not serious",
            "indirectness": "Not serious",
            "imprecision": "Serious",
            "publication_bias": "Not serious",
        },
    ]


def get_mock_quality_assessment_template() -> Dict[str, Any]:
    """Get mock quality assessment template structure."""
    return {
        "risk_of_bias_tool": "RoB 2",
        "studies": [
            {
                "study_id": "Study 1",
                "title": "Test Study 1",
                "risk_of_bias": {
                    "domains": {
                        "Bias arising from the randomization process": "",
                        "Bias due to deviations from intended interventions": "",
                        "Bias due to missing outcome data": "",
                        "Bias in measurement of the outcome": "",
                        "Bias in selection of the reported result": "",
                    },
                    "overall": "",
                },
            },
            {
                "study_id": "Study 2",
                "title": "Test Study 2",
                "risk_of_bias": {
                    "domains": {
                        "Bias arising from the randomization process": "",
                        "Bias due to deviations from intended interventions": "",
                        "Bias due to missing outcome data": "",
                        "Bias in measurement of the outcome": "",
                        "Bias in selection of the reported result": "",
                    },
                    "overall": "",
                },
            },
        ],
        "grade_assessments": [
            {
                "outcome": "Primary outcome measure",
                "certainty": "",
                "downgrade_reasons": [],
            },
            {
                "outcome": "Secondary outcome measure",
                "certainty": "",
                "downgrade_reasons": [],
            },
        ],
    }


def get_completed_quality_assessment_template() -> Dict[str, Any]:
    """Get completed quality assessment template."""
    template = get_mock_quality_assessment_template()
    
    # Complete risk of bias assessments
    template["studies"][0]["risk_of_bias"]["domains"] = {
        "Bias arising from the randomization process": "Low",
        "Bias due to deviations from intended interventions": "Some concerns",
        "Bias due to missing outcome data": "Low",
        "Bias in measurement of the outcome": "Low",
        "Bias in selection of the reported result": "Low",
    }
    template["studies"][0]["risk_of_bias"]["overall"] = "Some concerns"
    
    template["studies"][1]["risk_of_bias"]["domains"] = {
        "Bias arising from the randomization process": "High",
        "Bias due to deviations from intended interventions": "High",
        "Bias due to missing outcome data": "Some concerns",
        "Bias in measurement of the outcome": "Low",
        "Bias in selection of the reported result": "Some concerns",
    }
    template["studies"][1]["risk_of_bias"]["overall"] = "High"
    
    # Complete GRADE assessments
    template["grade_assessments"][0]["certainty"] = "High"
    template["grade_assessments"][1]["certainty"] = "Moderate"
    template["grade_assessments"][1]["downgrade_reasons"] = ["Risk of bias"]
    
    return template
