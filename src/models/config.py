"""Configuration models loaded from YAML."""

from __future__ import annotations

import uuid
from typing import Dict, List

from pydantic import BaseModel, Field

from src.models.enums import ReviewType


class PICOConfig(BaseModel):
    population: str
    intervention: str
    comparison: str
    outcome: str


class ProtocolRegistration(BaseModel):
    registered: bool = False
    registry: str = "PROSPERO"
    registration_number: str = ""
    url: str = ""


class FundingInfo(BaseModel):
    source: str = "No funding received"
    grant_number: str = ""
    funder: str = ""


class ReviewConfig(BaseModel):
    project_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    research_question: str
    review_type: ReviewType
    pico: PICOConfig
    keywords: List[str] = Field(min_length=1)
    domain: str
    scope: str
    inclusion_criteria: List[str] = Field(min_length=1)
    exclusion_criteria: List[str] = Field(min_length=1)
    date_range_start: int
    date_range_end: int
    target_databases: List[str] = Field(min_length=1)
    target_sections: List[str] = Field(
        default_factory=lambda: [
            "abstract",
            "introduction",
            "methods",
            "results",
            "discussion",
            "conclusion",
        ]
    )
    protocol: ProtocolRegistration = Field(default_factory=ProtocolRegistration)
    funding: FundingInfo = Field(default_factory=FundingInfo)
    conflicts_of_interest: str = "The authors declare no conflicts of interest."


class AgentConfig(BaseModel):
    model: str
    temperature: float = Field(ge=0.0, le=1.0, default=0.2)


class ScreeningConfig(BaseModel):
    stage1_include_threshold: float = Field(ge=0.0, le=1.0, default=0.85)
    stage1_exclude_threshold: float = Field(ge=0.0, le=1.0, default=0.80)


class DualReviewConfig(BaseModel):
    enabled: bool = True
    kappa_warning_threshold: float = Field(ge=0.0, le=1.0, default=0.4)


class GatesConfig(BaseModel):
    profile: str = "strict"
    search_volume_minimum: int = 50
    screening_minimum: int = 5
    extraction_completeness_threshold: float = 0.80
    extraction_max_empty_rate: float = 0.35
    cost_budget_max: float = 20.0


class WritingConfig(BaseModel):
    style_extraction: bool = True
    humanization: bool = True
    humanization_iterations: int = Field(ge=1, le=5, default=2)
    naturalness_threshold: float = Field(ge=0.0, le=1.0, default=0.75)
    checkpoint_per_section: bool = True
    llm_timeout: int = 120


class RiskOfBiasConfig(BaseModel):
    rct_tool: str = "rob2"
    non_randomized_tool: str = "robins_i"
    qualitative_tool: str = "casp"


class MetaAnalysisConfig(BaseModel):
    enabled: bool = True
    heterogeneity_threshold: int = 40
    funnel_plot_minimum_studies: int = 10
    effect_measure_dichotomous: str = "risk_ratio"
    effect_measure_continuous: str = "mean_difference"


class IEEEExportConfig(BaseModel):
    enabled: bool = True
    template: str = "IEEEtran"
    bibliography_style: str = "IEEEtran"
    max_abstract_words: int = 250
    target_page_range: List[int] = Field(default_factory=lambda: [7, 10])


class CitationLineageConfig(BaseModel):
    block_export_on_unresolved: bool = True
    minimum_evidence_score: float = 0.5


class SettingsConfig(BaseModel):
    agents: Dict[str, AgentConfig]
    screening: ScreeningConfig = Field(default_factory=ScreeningConfig)
    dual_review: DualReviewConfig = Field(default_factory=DualReviewConfig)
    gates: GatesConfig = Field(default_factory=GatesConfig)
    writing: WritingConfig = Field(default_factory=WritingConfig)
    risk_of_bias: RiskOfBiasConfig = Field(default_factory=RiskOfBiasConfig)
    meta_analysis: MetaAnalysisConfig = Field(default_factory=MetaAnalysisConfig)
    ieee_export: IEEEExportConfig = Field(default_factory=IEEEExportConfig)
    citation_lineage: CitationLineageConfig = Field(default_factory=CitationLineageConfig)
