"""
Pydantic schemas for data extraction agent outputs.
"""

from typing import Optional, List, Any
from pydantic import BaseModel, Field, field_validator, ConfigDict


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
    methodology: Optional[str] = Field(default=None, description="Description of research methodology")
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
    # Additional fields for study characteristics table
    country: Optional[str] = Field(
        default=None, description="Country where study was conducted"
    )
    setting: Optional[str] = Field(
        default=None, description="Study setting (e.g., hospital, community, online)"
    )
    sample_size: Optional[int] = Field(
        default=None, description="Number of participants in the study"
    )
    detailed_outcomes: List[str] = Field(
        default_factory=list, description="Detailed outcome measures with units and measurement methods"
    )
    quantitative_results: Optional[str] = Field(
        default=None, description="Quantitative results including effect sizes, confidence intervals, p-values, and statistical tests"
    )
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

    # Bibliometric fields (enhanced from pybliometrics and scholarly)
    citation_count: Optional[int] = Field(
        default=None, description="Total number of citations"
    )
    cited_by_count: Optional[int] = Field(
        default=None, description="Number of papers citing this paper"
    )
    h_index: Optional[int] = Field(
        default=None, description="Author h-index (if available from author profile)"
    )
    coauthors: List[str] = Field(
        default_factory=list, description="List of coauthor names"
    )
    subject_areas: List[str] = Field(
        default_factory=list, description="Subject area classifications"
    )
    related_papers: List[str] = Field(
        default_factory=list, description="Related paper IDs or DOIs"
    )

    @field_validator(
        "authors",
        "study_objectives",
        "outcomes",
        "detailed_outcomes",
        "key_findings",
        "ux_strategies",
        "adaptivity_frameworks",
        "patient_populations",
        "accessibility_features",
        "coauthors",
        "subject_areas",
        "related_papers",
        mode="before",
    )
    @classmethod
    def normalize_list_fields(cls, v: Any) -> List[str]:
        """
        Normalize list fields: convert strings to empty arrays.

        This provides defense-in-depth in case normalization in the agent
        didn't catch all cases.
        """
        if isinstance(v, str):
            # Check if it's a "not available" string
            v_lower = v.lower().strip()
            not_available = [
                "not applicable",
                "not available",
                "n/a",
                "na",
                "none",
                "null",
                "",
            ]
            if v_lower in not_available or v_lower.startswith("not "):
                return []
            # If it's a single string value, wrap it in a list
            return [v]
        elif isinstance(v, list):
            return v
        elif v is None:
            return []
        else:
            # Try to convert to list
            return [str(v)]

    model_config = ConfigDict(
        json_schema_extra={
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
                "country": "United States",
                "setting": "Academic medical center",
                "sample_size": 100,
                "detailed_outcomes": [
                    "User satisfaction score (1-10 scale)",
                    "Task completion rate (%)",
                ],
                "quantitative_results": "Mean satisfaction score: 7.5 (95% CI: 7.1-7.9), p<0.001. Task completion: 85% vs 72% (OR=2.1, 95% CI: 1.3-3.4)",
            }
        }
    )


class ExtractionRequestSchema(BaseModel):
    """Schema for extraction request inputs."""

    title: str = Field(description="Paper title")
    abstract: str = Field(description="Paper abstract")
    full_text: Optional[str] = Field(default=None, description="Full text if available")
    extraction_fields: Optional[List[str]] = Field(
        default=None, description="Specific fields to extract (if None, extracts all)"
    )
