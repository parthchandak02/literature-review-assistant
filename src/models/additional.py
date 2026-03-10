"""Additional typed outputs used by later phases and logging."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from src.models.config import PICOConfig
from src.models.enums import GRADECertainty


class InterRaterReliability(BaseModel):
    stage: str
    total_screened: int
    total_agreements: int
    total_disagreements: int
    cohens_kappa: float
    percent_agreement: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MetaAnalysisResult(BaseModel):
    outcome_name: str
    n_studies: int
    effect_measure: str
    pooled_effect: float
    ci_lower: float
    ci_upper: float
    p_value: float
    model: str
    method_re: str | None = None
    cochrans_q: float
    i_squared: float
    tau_squared: float | None = None
    forest_plot_path: str | None = None
    funnel_plot_path: str | None = None


class PRISMACounts(BaseModel):
    databases_records: dict[str, int]
    other_sources_records: dict[str, int]
    total_identified_databases: int
    total_identified_other: int
    duplicates_removed: int
    # Records excluded before LLM screening by automated pre-filter (BM25 ranking
    # auto-exclusion or keyword hard-gate). PRISMA 2020 labels this as
    # "Records removed before screening: Automation tools (n=X)".
    automation_excluded: int = 0
    records_screened: int
    records_excluded_screening: int
    reports_sought: int
    reports_not_retrieved: int
    reports_assessed: int
    reports_excluded_with_reasons: dict[str, int]
    studies_included_qualitative: int
    studies_included_quantitative: int
    arithmetic_valid: bool


class ProtocolDocument(BaseModel):
    workflow_id: str
    research_question: str
    pico: PICOConfig
    eligibility_criteria: list[str]
    planned_databases: list[str]
    planned_screening_method: str
    planned_rob_tools: list[str]
    planned_synthesis_method: str
    prospero_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProsperoRunData(BaseModel):
    """Post-run data collected from ReviewState to populate the PROSPERO registration form."""

    search_counts: dict[str, int] = Field(default_factory=dict)
    search_queries: dict[str, str] = Field(default_factory=dict)
    included_count: int = 0
    fulltext_retrieved_count: int = 0
    run_id: str = ""
    synthesis_method: str = ""


class SummaryOfFindingsRow(BaseModel):
    outcome: str
    participants_studies: str
    certainty: GRADECertainty
    relative_effect: str | None = None
    absolute_effect_control: str | None = None
    absolute_effect_intervention: str | None = None
    plain_language: str


class CostRecord(BaseModel):
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    phase: str
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
