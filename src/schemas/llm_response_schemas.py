"""
Pydantic schemas for LLM response validation across all agents.

This module provides comprehensive response models for structured outputs
from LLM calls, ensuring type safety and automatic validation.
"""

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Re-export existing schemas for convenience
from .extraction_schemas import ExtractedDataSchema
from .screening_schemas import InclusionDecision, ScreeningResultSchema

__all__ = [
    # Writing responses
    "AbstractResponse",
    # Quality assessment responses
    "CASPScoreResponse",
    "DiscussionResponse",
    # Existing schemas (re-exported)
    "ExtractedDataSchema",
    "HumanizationResponse",
    "InclusionDecision",
    "IntroductionResponse",
    "MethodsResponse",
    "QualityAssessmentResponse",
    # Search and tool responses
    "QueryBuilderResponse",
    "ResultsResponse",
    "ScreeningResultSchema",
    "SearchStrategyResponse",
    "StudyTypeDetectionResponse",
    "WritingSectionResponse",
]


# ============================================================================
# Writing Agent Response Models
# ============================================================================


class WritingSectionResponse(BaseModel):
    """Base response schema for article section writing."""

    section_content: str = Field(
        min_length=100,
        description="Written section content in markdown format",
    )
    key_citations: List[str] = Field(
        default_factory=list,
        description="Citation keys used in this section (e.g., ['Smith2020', 'Jones2019'])",
    )
    subsection_headers: List[str] = Field(
        default_factory=list,
        description="Subsection headers used in this section",
    )
    word_count: int = Field(description="Approximate word count of the section (positive integer)")
    writing_notes: Optional[str] = Field(
        default=None,
        description="Internal notes about writing decisions or challenges",
    )

    @field_validator("section_content")
    @classmethod
    def validate_content_not_empty(cls, v: str) -> str:
        """Ensure content is not just whitespace."""
        if not v.strip():
            raise ValueError("Section content cannot be empty")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "section_content": "## Introduction\n\nThis study examines...",
                "key_citations": ["Smith2020", "Jones2019"],
                "subsection_headers": ["Background", "Research Gap"],
                "word_count": 450,
                "writing_notes": "Emphasized clinical relevance per guidelines",
            }
        }
    )


class IntroductionResponse(WritingSectionResponse):
    """Response schema for introduction section writing."""

    research_gap_identified: bool = Field(
        default=True,
        description="Whether a clear research gap was identified and stated",
    )
    background_coverage: Literal["comprehensive", "adequate", "minimal"] = Field(
        default="adequate",
        description="Assessment of background literature coverage",
    )


class MethodsResponse(WritingSectionResponse):
    """Response schema for methods section writing."""

    methodology_clarity: Literal["clear", "adequate", "needs_improvement"] = Field(
        default="clear",
        description="Assessment of methodology description clarity",
    )
    reproducibility_score: float = Field(
        ge=0.0,
        le=1.0,
        default=0.8,
        description="Estimated reproducibility based on detail provided",
    )


class ResultsResponse(WritingSectionResponse):
    """Response schema for results section writing."""

    tables_mentioned: List[str] = Field(
        default_factory=list,
        description="List of table references included (e.g., ['Table 1', 'Table 2'])",
    )
    figures_mentioned: List[str] = Field(
        default_factory=list,
        description="List of figure references included (e.g., ['Figure 1', 'Figure 2'])",
    )
    statistical_tests_reported: bool = Field(
        default=True,
        description="Whether statistical tests and p-values were reported",
    )


class DiscussionResponse(WritingSectionResponse):
    """Response schema for discussion section writing."""

    limitations_addressed: bool = Field(
        default=True,
        description="Whether study limitations were discussed",
    )
    future_directions_provided: bool = Field(
        default=True,
        description="Whether future research directions were suggested",
    )
    implications_discussed: bool = Field(
        default=True,
        description="Whether clinical/practical implications were discussed",
    )


class AbstractResponse(BaseModel):
    """Response schema for abstract writing."""

    abstract_content: str = Field(
        min_length=150,
        max_length=350,
        description="Complete abstract text (typically 150-350 words)",
    )
    word_count: int = Field(description="Exact word count (positive integer)")
    structured_sections: Dict[str, str] = Field(
        default_factory=dict,
        description="Structured abstract sections (Background, Methods, Results, Conclusions)",
    )
    keywords: List[str] = Field(
        default_factory=list,
        description="Suggested keywords for the paper",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "abstract_content": "Background: This systematic review examined...",
                "word_count": 247,
                "structured_sections": {
                    "Background": "This systematic review examined...",
                    "Methods": "We searched five databases...",
                    "Results": "We identified 23 studies...",
                    "Conclusions": "The findings suggest...",
                },
                "keywords": ["telemedicine", "user experience", "accessibility"],
            }
        }
    )


class HumanizationResponse(BaseModel):
    """Response schema for text humanization/naturalness improvement."""

    humanized_content: str = Field(
        min_length=100,
        description="Humanized version of the input text",
    )
    changes_made: List[str] = Field(
        default_factory=list,
        description="List of specific changes made to improve naturalness",
    )
    naturalness_score_before: float = Field(
        ge=0.0,
        le=1.0,
        description="Estimated naturalness score before humanization",
    )
    naturalness_score_after: float = Field(
        ge=0.0,
        le=1.0,
        description="Estimated naturalness score after humanization",
    )
    tone_adjustments: List[str] = Field(
        default_factory=list,
        description="Tone adjustments made (e.g., 'reduced formality', 'added transitions')",
    )

    @field_validator("naturalness_score_after")
    @classmethod
    def validate_improvement(cls, v: float, info) -> float:
        """Ensure naturalness improved or stayed the same."""
        if "naturalness_score_before" in info.data:
            if v < info.data["naturalness_score_before"]:
                raise ValueError(
                    "Naturalness score after should be >= score before"
                )
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "humanized_content": "The findings suggest that telemedicine...",
                "changes_made": [
                    "Replaced passive voice with active voice",
                    "Added transition phrases",
                    "Simplified complex sentences",
                ],
                "naturalness_score_before": 0.65,
                "naturalness_score_after": 0.88,
                "tone_adjustments": ["reduced formality", "improved flow"],
            }
        }
    )


# ============================================================================
# Quality Assessment Response Models
# ============================================================================


class CASPScoreResponse(BaseModel):
    """Response schema for individual CASP criterion scoring."""

    criterion: str = Field(description="CASP criterion being evaluated")
    score: Literal["yes", "no", "unclear", "not_applicable"] = Field(
        description="Score for this criterion"
    )
    reasoning: str = Field(
        min_length=20,
        description="Justification for the score",
    )
    evidence_quote: Optional[str] = Field(
        default=None,
        description="Direct quote from paper supporting the score",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "criterion": "Did the study address a clearly focused question?",
                "score": "yes",
                "reasoning": "The study clearly states the research question in the introduction",
                "evidence_quote": "This study aimed to examine the effectiveness of...",
            }
        }
    )


class QualityAssessmentResponse(BaseModel):
    """Response schema for complete quality assessment."""

    overall_quality: Literal["high", "moderate", "low"] = Field(
        description="Overall study quality rating"
    )
    casp_scores: Dict[str, str] = Field(
        description="Dictionary mapping CASP criteria to scores (yes/no/unclear/not_applicable)"
    )
    casp_detailed_scores: List[CASPScoreResponse] = Field(
        default_factory=list,
        description="Detailed scores with reasoning for each CASP criterion",
    )
    risk_of_bias: Literal["low", "moderate", "high", "unclear"] = Field(
        description="Overall risk of bias assessment"
    )
    grade_assessment: Optional[str] = Field(
        default=None,
        description="GRADE quality of evidence assessment if applicable",
    )
    recommendations: List[str] = Field(
        default_factory=list,
        description="Recommendations for interpreting study findings",
    )
    strengths: List[str] = Field(
        default_factory=list,
        description="Key strengths of the study",
    )
    limitations: List[str] = Field(
        default_factory=list,
        description="Key limitations of the study",
    )
    confidence_in_findings: Literal["high", "moderate", "low", "very_low"] = Field(
        description="Confidence in the study findings"
    )

    @field_validator("casp_scores")
    @classmethod
    def validate_casp_scores(cls, v: Dict[str, str]) -> Dict[str, str]:
        """Ensure CASP scores use valid values."""
        valid_scores = {"yes", "no", "unclear", "not_applicable"}
        for criterion, score in v.items():
            if score.lower() not in valid_scores:
                raise ValueError(
                    f"Invalid CASP score '{score}' for criterion '{criterion}'. "
                    f"Must be one of: {valid_scores}"
                )
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "overall_quality": "moderate",
                "casp_scores": {
                    "clearly_focused_question": "yes",
                    "appropriate_method": "yes",
                    "acceptable_recruitment": "unclear",
                },
                "casp_detailed_scores": [],
                "risk_of_bias": "moderate",
                "grade_assessment": "Moderate quality of evidence",
                "recommendations": [
                    "Findings should be interpreted with caution due to limited sample size"
                ],
                "strengths": ["Rigorous methodology", "Clear reporting"],
                "limitations": ["Small sample size", "Single-center study"],
                "confidence_in_findings": "moderate",
            }
        }
    )


class StudyTypeDetectionResponse(BaseModel):
    """Response schema for study type detection (for CASP checklist selection)."""

    study_type: Literal[
        "randomized_controlled_trial",
        "cohort_study",
        "case_control_study",
        "qualitative_study",
        "systematic_review",
        "diagnostic_study",
        "economic_evaluation",
        "other",
    ] = Field(description="Detected study type")
    casp_checklist: Literal[
        "casp_rct",
        "casp_cohort",
        "casp_case_control",
        "casp_qualitative",
        "casp_systematic_review",
        "casp_diagnostic",
        "casp_economic",
    ] = Field(description="Recommended CASP checklist")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in study type detection",
    )
    reasoning: str = Field(
        min_length=30,
        description="Explanation for study type classification",
    )
    key_indicators: List[str] = Field(
        default_factory=list,
        description="Key features that led to this classification",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "study_type": "randomized_controlled_trial",
                "casp_checklist": "casp_rct",
                "confidence": 0.95,
                "reasoning": "Study mentions randomization, control group, and intervention",
                "key_indicators": [
                    "Random allocation mentioned",
                    "Control and intervention groups",
                    "Blinded assessment",
                ],
            }
        }
    )


# ============================================================================
# Search and Tool Response Models
# ============================================================================


class SearchStrategyResponse(BaseModel):
    """Response schema for search strategy generation."""

    search_terms: List[str] = Field(
        min_length=3,
        description="List of search terms to use",
    )
    boolean_operators: List[str] = Field(
        default_factory=list,
        description="Boolean operators to connect terms (AND, OR, NOT)",
    )
    search_string: str = Field(
        min_length=10,
        description="Complete search string ready for database query",
    )
    databases_recommended: List[str] = Field(
        default_factory=list,
        description="Recommended databases for this search",
    )
    expected_results: Optional[int] = Field(
        default=None,
        gt=0,
        description="Expected number of results",
    )
    search_rationale: str = Field(
        min_length=30,
        description="Explanation of search strategy choices",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "search_terms": ["telemedicine", "user experience", "accessibility"],
                "boolean_operators": ["AND", "OR"],
                "search_string": "(telemedicine OR telehealth) AND (user experience OR usability) AND accessibility",
                "databases_recommended": ["PubMed", "Scopus", "Web of Science"],
                "expected_results": 250,
                "search_rationale": "Broad terms combined with specific focus on accessibility",
            }
        }
    )


class QueryBuilderResponse(BaseModel):
    """Response schema for query builder tool."""

    optimized_query: str = Field(
        min_length=10,
        description="Optimized search query",
    )
    query_components: Dict[str, List[str]] = Field(
        description="Query broken down into components (concepts, synonyms, etc.)",
    )
    filters_suggested: Dict[str, str] = Field(
        default_factory=dict,
        description="Suggested filters (date range, publication type, etc.)",
    )
    expansion_terms: List[str] = Field(
        default_factory=list,
        description="Additional terms to consider for query expansion",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "optimized_query": "(telemedicine[MeSH] OR telehealth) AND (usability OR user experience)",
                "query_components": {
                    "primary_concept": ["telemedicine", "telehealth"],
                    "secondary_concept": ["usability", "user experience"],
                },
                "filters_suggested": {
                    "date_range": "2018-2024",
                    "publication_type": "Journal Article",
                },
                "expansion_terms": ["remote healthcare", "digital health"],
            }
        }
    )
