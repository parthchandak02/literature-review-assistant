"""
Pydantic schemas for quality assessment data.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class RiskOfBiasAssessment(BaseModel):
    """Risk of bias assessment for a single study."""

    study_id: str = Field(description="Unique identifier for the study")
    study_title: str = Field(description="Title of the study")
    tool: str = Field(
        description="Assessment tool used (RoB 2, ROBINS-I, CASP, etc.)"
    )
    domains: Dict[str, str] = Field(
        description="Risk of bias ratings for each domain. Values: 'Low', 'Some concerns', 'High', 'Critical'"
    )
    overall: str = Field(
        description="Overall risk of bias rating: 'Low', 'Some concerns', 'High', 'Critical'"
    )
    notes: Optional[str] = Field(
        default=None, description="Additional notes about the assessment"
    )


class GRADEAssessment(BaseModel):
    """GRADE certainty assessment for an outcome."""

    outcome: str = Field(description="Name of the outcome being assessed")
    certainty: str = Field(
        description="Certainty rating: 'High', 'Moderate', 'Low', 'Very Low'"
    )
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

    risk_of_bias_assessments: List[RiskOfBiasAssessment] = Field(
        default_factory=list, description="Risk of bias assessments for each study"
    )
    grade_assessments: List[GRADEAssessment] = Field(
        default_factory=list, description="GRADE assessments for each outcome"
    )
