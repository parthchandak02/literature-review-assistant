"""
Pydantic schemas for data extraction agent outputs.
"""

from typing import Optional, List
from pydantic import BaseModel, Field


class ExtractedDataSchema(BaseModel):
    """Structured output schema for extracted data from papers."""

    # Basic metadata
    title: str = Field(description="Paper title")
    authors: List[str] = Field(default_factory=list, description="List of authors")
    year: Optional[int] = Field(default=None, description="Publication year")
    journal: Optional[str] = Field(default=None, description="Journal name")
    doi: Optional[str] = Field(default=None, description="DOI")

    # Study characteristics
    study_objectives: List[str] = Field(
        default_factory=list, description="List of main research objectives"
    )
    methodology: str = Field(default="", description="Description of research methodology")
    study_design: Optional[str] = Field(
        default=None, description="Type of study (e.g., RCT, case study, survey)"
    )
    participants: Optional[str] = Field(
        default=None, description="Description of study participants"
    )
    interventions: Optional[str] = Field(
        default=None, description="Description of interventions or treatments"
    )
    outcomes: List[str] = Field(default_factory=list, description="List of measured outcomes")
    key_findings: List[str] = Field(
        default_factory=list, description="List of key findings/results"
    )
    limitations: Optional[str] = Field(default=None, description="Study limitations")

    # Domain-specific fields
    ux_strategies: List[str] = Field(
        default_factory=list, description="UX design strategies mentioned"
    )
    adaptivity_frameworks: List[str] = Field(
        default_factory=list, description="Adaptive/personalization frameworks used"
    )
    patient_populations: List[str] = Field(
        default_factory=list, description="Patient populations studied"
    )
    accessibility_features: List[str] = Field(
        default_factory=list, description="Accessibility features mentioned"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "title": "Adaptive Telemedicine Interface Design",
                "authors": ["Smith, J.", "Doe, A."],
                "year": 2022,
                "journal": "Journal of Telemedicine",
                "doi": "10.1000/example",
                "study_objectives": [
                    "Evaluate adaptive interface effectiveness",
                    "Assess user satisfaction",
                ],
                "methodology": "Randomized controlled trial",
                "study_design": "RCT",
                "participants": "100 patients with varying digital literacy",
                "interventions": "Adaptive interface vs standard interface",
                "outcomes": ["User satisfaction", "Task completion rate"],
                "key_findings": [
                    "Adaptive interfaces improved satisfaction by 30%",
                    "No significant difference in task completion",
                ],
                "limitations": "Small sample size, single institution",
                "ux_strategies": ["Personalization", "Progressive disclosure"],
                "adaptivity_frameworks": ["Rule-based adaptation"],
                "patient_populations": ["Elderly", "Low digital literacy"],
                "accessibility_features": [
                    "Screen reader support",
                    "High contrast mode",
                ],
            }
        }


class ExtractionRequestSchema(BaseModel):
    """Schema for extraction request inputs."""

    title: str = Field(description="Paper title")
    abstract: str = Field(description="Paper abstract")
    full_text: Optional[str] = Field(default=None, description="Full text if available")
    extraction_fields: Optional[List[str]] = Field(
        default=None, description="Specific fields to extract (if None, extracts all)"
    )
