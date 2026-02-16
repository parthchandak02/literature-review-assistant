"""Additional typed outputs used by later phases and logging."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

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
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MetaAnalysisResult(BaseModel):
    outcome_name: str
    n_studies: int
    effect_measure: str
    pooled_effect: float
    ci_lower: float
    ci_upper: float
    p_value: float
    model: str
    method_re: Optional[str] = None
    cochrans_q: float
    i_squared: float
    tau_squared: Optional[float] = None
    forest_plot_path: Optional[str] = None
    funnel_plot_path: Optional[str] = None


class PRISMACounts(BaseModel):
    databases_records: Dict[str, int]
    other_sources_records: Dict[str, int]
    total_identified_databases: int
    total_identified_other: int
    duplicates_removed: int
    records_screened: int
    records_excluded_screening: int
    reports_sought: int
    reports_not_retrieved: int
    reports_assessed: int
    reports_excluded_with_reasons: Dict[str, int]
    studies_included_qualitative: int
    studies_included_quantitative: int
    arithmetic_valid: bool


class ProtocolDocument(BaseModel):
    workflow_id: str
    research_question: str
    pico: PICOConfig
    eligibility_criteria: List[str]
    planned_databases: List[str]
    planned_screening_method: str
    planned_rob_tools: List[str]
    planned_synthesis_method: str
    prospero_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SummaryOfFindingsRow(BaseModel):
    outcome: str
    participants_studies: str
    certainty: GRADECertainty
    relative_effect: Optional[str] = None
    absolute_effect_control: Optional[str] = None
    absolute_effect_intervention: Optional[str] = None
    plain_language: str


class CostRecord(BaseModel):
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    phase: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
