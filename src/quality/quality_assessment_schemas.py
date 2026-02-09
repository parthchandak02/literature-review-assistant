"""
Pydantic schemas for quality assessment data.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from ..schemas.llm_response_schemas import KeyValuePair


class CASPQuestionResponse(BaseModel):
    """Response to a single CASP checklist question."""

    answer: str = Field(description="Answer: 'Yes', 'No', or 'Can't Tell'")
    justification: str = Field(description="Justification for the answer with specific evidence")


class CASPScore(BaseModel):
    """Score summary for CASP assessment."""

    yes_count: int = Field(description="Number of 'Yes' responses")
    no_count: int = Field(description="Number of 'No' responses")
    cant_tell_count: int = Field(description="Number of 'Can't Tell' responses")
    total_questions: int = Field(description="Total number of questions in checklist")
    quality_rating: str = Field(description="Overall quality rating: 'High', 'Moderate', or 'Low'")


class CASPQuestionPair(BaseModel):
    """Key-value pair for CASP questions for Gemini API compatibility."""
    
    key: str = Field(description="Question ID (e.g., q1, q2)")
    value: CASPQuestionResponse = Field(description="Question response")


class CASPAssessment(BaseModel):
    """CASP quality assessment for a single study."""

    study_id: str = Field(description="Unique identifier for the study")
    study_title: str = Field(description="Title of the study")
    study_design: str = Field(description="Study design (e.g., RCT, cohort, qualitative)")
    detected_type: Optional[str] = Field(
        default=None, description="Auto-detected CASP checklist type"
    )
    detection_confidence: Optional[float] = Field(
        default=None, description="Confidence score for detection (0-1)"
    )
    checklist_used: str = Field(
        description="CASP checklist used: 'casp_rct', 'casp_cohort', or 'casp_qualitative'"
    )
    questions: List[CASPQuestionPair] = Field(
        default_factory=list,
        description="Responses to each question as key-value pairs (e.g., q1, q2, ...)",
    )
    score: CASPScore = Field(description="Score summary")
    overall_notes: str = Field(description="Overall assessment notes and summary")


class RiskOfBiasAssessment(BaseModel):
    """
    DEPRECATED: Legacy risk of bias assessment schema.

    This schema is maintained for backward compatibility only.
    New code should use CASPAssessment instead.
    """

    study_id: str = Field(description="Unique identifier for the study")
    study_title: str = Field(description="Title of the study")
    tool: str = Field(description="Assessment tool used (DEPRECATED - use CASP)")
    domains: List[KeyValuePair] = Field(
        default_factory=list,
        description="Risk of bias ratings for each domain as key-value pairs (DEPRECATED)",
    )
    overall: str = Field(description="Overall risk of bias rating (DEPRECATED)")
    notes: Optional[str] = Field(default=None, description="Additional notes about the assessment")


class GRADEAssessment(BaseModel):
    """GRADE certainty assessment for an outcome."""

    outcome: str = Field(description="Name of the outcome being assessed")
    certainty: str = Field(description="Certainty rating: 'High', 'Moderate', 'Low', 'Very Low'")
    downgrade_reasons: List[str] = Field(
        default_factory=list,
        description="Reasons for downgrading certainty (risk of bias, inconsistency, indirectness, imprecision, publication bias)",
    )
    upgrade_reasons: List[str] = Field(
        default_factory=list,
        description="Reasons for upgrading certainty (large effect, dose-response, all plausible confounding)",
    )
    justification: Optional[str] = Field(
        default=None, description="Narrative justification for the rating"
    )


class QualityAssessmentData(BaseModel):
    """Complete quality assessment data for a systematic review."""

    framework: str = Field(default="CASP", description="Assessment framework used")
    casp_assessments: List[CASPAssessment] = Field(
        default_factory=list, description="CASP quality assessments for each study"
    )
    grade_assessments: List[GRADEAssessment] = Field(
        default_factory=list, description="GRADE assessments for each outcome"
    )
    # Deprecated fields for backward compatibility
    risk_of_bias_assessments: List[RiskOfBiasAssessment] = Field(
        default_factory=list, description="DEPRECATED: Use casp_assessments instead"
    )
