"""
Pydantic schemas for screening agent outputs.
"""

from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator, ConfigDict


class InclusionDecision(str, Enum):
    """Screening decision types."""

    INCLUDE = "include"
    EXCLUDE = "exclude"
    UNCERTAIN = "uncertain"


class ScreeningResultSchema(BaseModel):
    """Structured output schema for screening results."""

    decision: InclusionDecision = Field(
        description="The inclusion decision: include, exclude, or uncertain"
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")
    reasoning: str = Field(description="Brief explanation of the decision")
    exclusion_reason: Optional[str] = Field(
        default=None,
        description="If excluding, specify which exclusion criterion applies",
    )

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Ensure confidence is between 0 and 1."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("Confidence must be between 0.0 and 1.0")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "decision": "include",
                "confidence": 0.85,
                "reasoning": "Paper addresses telemedicine UX for diverse populations",
                "exclusion_reason": None,
            }
        }
    )


class ScreeningRequestSchema(BaseModel):
    """Schema for screening request inputs."""

    title: str = Field(description="Paper title")
    abstract: str = Field(description="Paper abstract")
    inclusion_criteria: List[str] = Field(description="List of inclusion criteria")
    exclusion_criteria: List[str] = Field(description="List of exclusion criteria")
    full_text: Optional[str] = Field(default=None, description="Full text if available")
