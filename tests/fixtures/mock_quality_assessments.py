"""
Test fixtures for quality assessments.

Includes both CASP (primary) and legacy RoB 2 fixtures for backward compatibility.
"""

from typing import Any, Dict, List


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


def get_mock_casp_assessments() -> List[Dict[str, Any]]:
    """Get mock CASP quality assessments."""
    return [
        {
            "study_id": "Study_1",
            "study_title": "AI Tutoring RCT Study",
            "study_design": "Randomized Controlled Trial",
            "detected_type": "casp_rct",
            "detection_confidence": 0.95,
            "quality_assessment": {
                "checklist_used": "casp_rct",
                "questions": {
                    "q1": {"answer": "Yes", "justification": "Clear PICO elements defined"},
                    "q2": {"answer": "Yes", "justification": "Computer-generated randomization"},
                    "q3": {"answer": "Yes", "justification": "All participants accounted for"},
                    "q4": {
                        "answer": "No",
                        "justification": "Not blinded due to intervention nature",
                    },
                    "q5": {"answer": "Yes", "justification": "Groups well-matched at baseline"},
                    "q6": {"answer": "Yes", "justification": "Equal treatment except intervention"},
                    "q7": {"answer": "Yes", "justification": "Large effect size (d=0.8)"},
                    "q8": {"answer": "Yes", "justification": "Narrow confidence intervals"},
                    "q9": {
                        "answer": "Yes",
                        "justification": "Setting applicable to similar contexts",
                    },
                    "q10": {"answer": "Yes", "justification": "Comprehensive outcome measures"},
                    "q11": {"answer": "Yes", "justification": "Benefits outweigh minimal harms"},
                },
                "score": {
                    "yes_count": 10,
                    "no_count": 1,
                    "cant_tell_count": 0,
                    "total_questions": 11,
                    "quality_rating": "High",
                },
                "overall_notes": "High quality RCT with minor limitation in blinding",
            },
        },
        {
            "study_id": "Study_2",
            "study_title": "Chatbot Usage Cohort Study",
            "study_design": "Cohort Study",
            "detected_type": "casp_cohort",
            "detection_confidence": 0.88,
            "quality_assessment": {
                "checklist_used": "casp_cohort",
                "questions": {
                    "q1": {"answer": "Yes", "justification": "Clear focused research question"},
                    "q2": {"answer": "Yes", "justification": "Appropriate recruitment strategy"},
                    "q3": {"answer": "Yes", "justification": "Exposure measured consistently"},
                    "q4": {"answer": "Yes", "justification": "Valid outcome measures used"},
                    "q5": {
                        "answer": "Can't Tell",
                        "justification": "Some confounders not identified",
                    },
                    "q6": {"answer": "Yes", "justification": "Multivariable analysis conducted"},
                    "q7": {"answer": "No", "justification": "30% loss to follow-up"},
                    "q8": {"answer": "Yes", "justification": "Adequate follow-up duration"},
                    "q9": {"answer": "Yes", "justification": "Clear effect estimates reported"},
                    "q10": {"answer": "Yes", "justification": "Narrow confidence intervals"},
                    "q11": {"answer": "Yes", "justification": "Plausible results"},
                    "q12": {
                        "answer": "Yes",
                        "justification": "Results applicable to similar settings",
                    },
                },
                "score": {
                    "yes_count": 9,
                    "no_count": 1,
                    "cant_tell_count": 2,
                    "total_questions": 12,
                    "quality_rating": "Moderate",
                },
                "overall_notes": "Moderate quality cohort study with some attrition concerns",
            },
        },
        {
            "study_id": "Study_3",
            "study_title": "Student Experiences Qualitative Study",
            "study_design": "Qualitative Interview Study",
            "detected_type": "casp_qualitative",
            "detection_confidence": 0.92,
            "quality_assessment": {
                "checklist_used": "casp_qualitative",
                "questions": {
                    "q1": {"answer": "Yes", "justification": "Clear research aims stated"},
                    "q2": {"answer": "Yes", "justification": "Qualitative methodology appropriate"},
                    "q3": {"answer": "Yes", "justification": "Research design fits aims"},
                    "q4": {"answer": "Yes", "justification": "Purposive sampling used"},
                    "q5": {
                        "answer": "Yes",
                        "justification": "Semi-structured interviews appropriate",
                    },
                    "q6": {"answer": "Yes", "justification": "Reflexivity discussed"},
                    "q7": {"answer": "Yes", "justification": "Ethics approval obtained"},
                    "q8": {"answer": "Yes", "justification": "Rigorous thematic analysis"},
                    "q9": {"answer": "Yes", "justification": "Clear findings with quotes"},
                    "q10": {"answer": "Yes", "justification": "Valuable insights for practice"},
                },
                "score": {
                    "yes_count": 10,
                    "no_count": 0,
                    "cant_tell_count": 0,
                    "total_questions": 10,
                    "quality_rating": "High",
                },
                "overall_notes": "High quality qualitative study with robust methodology",
            },
        },
    ]


def get_mock_casp_template() -> Dict[str, Any]:
    """Get mock CASP quality assessment template structure."""
    return {
        "framework": "CASP",
        "studies": [
            {
                "study_id": "Study_1",
                "study_title": "Test Study 1",
                "study_design": "Randomized Controlled Trial",
                "detected_type": "casp_rct",
                "detection_confidence": 0.95,
                "quality_assessment": {
                    "checklist_used": "casp_rct",
                    "questions": {
                        f"q{i}": {"answer": "", "justification": ""} for i in range(1, 12)
                    },
                    "score": {
                        "yes_count": None,
                        "no_count": None,
                        "cant_tell_count": None,
                        "total_questions": 11,
                        "quality_rating": "",
                    },
                    "overall_notes": "",
                },
            },
            {
                "study_id": "Study_2",
                "study_title": "Test Study 2",
                "study_design": "Cohort Study",
                "detected_type": "casp_cohort",
                "detection_confidence": 0.85,
                "quality_assessment": {
                    "checklist_used": "casp_cohort",
                    "questions": {
                        f"q{i}": {"answer": "", "justification": ""} for i in range(1, 13)
                    },
                    "score": {
                        "yes_count": None,
                        "no_count": None,
                        "cant_tell_count": None,
                        "total_questions": 12,
                        "quality_rating": "",
                    },
                    "overall_notes": "",
                },
            },
        ],
        "grade_assessments": [
            {
                "outcome": "Primary outcome measure",
                "certainty": "",
                "downgrade_reasons": [],
                "upgrade_reasons": [],
                "justification": "",
            },
            {
                "outcome": "Secondary outcome measure",
                "certainty": "",
                "downgrade_reasons": [],
                "upgrade_reasons": [],
                "justification": "",
            },
        ],
    }
