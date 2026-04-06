"""Additional typed outputs used by later phases and logging."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from src.models.config import PICOConfig
from src.models.enums import GRADECertainty

_logger = logging.getLogger(__name__)


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
    """PRISMA 2020 flow counts computed once and frozen for all consumers.

    Derived fields (records_after_deduplication, total_included) are pre-computed
    so downstream code and writing LLMs never perform arithmetic on these values.
    """

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

    records_after_deduplication: int = 0
    total_included: int = 0

    def validate_arithmetic(self, *, strict: bool = False) -> bool:
        """Check PRISMA arithmetic invariants and log any violations.

        When *strict* is True, raises ValueError on invalid arithmetic.
        Returns the arithmetic_valid flag.
        """
        violations: list[str] = []

        expected_after_dedup = (
            self.total_identified_databases + self.total_identified_other - self.duplicates_removed
        )
        if self.records_after_deduplication != expected_after_dedup and self.records_after_deduplication > 0:
            violations.append(
                f"records_after_deduplication mismatch: "
                f"stored={self.records_after_deduplication}, "
                f"expected={expected_after_dedup}"
            )

        if not (
            self.records_screened == self.records_excluded_screening + self.reports_sought
            or self.automation_excluded > 0
        ):
            violations.append(
                f"screened != excluded_screening + sought: "
                f"{self.records_screened} != {self.records_excluded_screening} + {self.reports_sought}"
            )

        if self.reports_sought != self.reports_not_retrieved + self.reports_assessed:
            violations.append(
                f"sought != not_retrieved + assessed: "
                f"{self.reports_sought} != {self.reports_not_retrieved} + {self.reports_assessed}"
            )

        expected_included = self.studies_included_qualitative + self.studies_included_quantitative
        if self.total_included != expected_included and self.total_included > 0:
            violations.append(
                f"total_included mismatch: stored={self.total_included}, expected={expected_included}"
            )

        if violations:
            msg = "PRISMA arithmetic violations: " + "; ".join(violations)
            _logger.warning(msg)
            if strict:
                raise ValueError(msg)
        return self.arithmetic_valid


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
    other_methods_searched: list[str] = Field(default_factory=list)


class SummaryOfFindingsRow(BaseModel):
    outcome: str
    participants_studies: str
    certainty: GRADECertainty
    relative_effect: str | None = None
    absolute_effect_control: str | None = None
    absolute_effect_intervention: str | None = None
    plain_language: str


class CostRecord(BaseModel):
    workflow_id: str = ""
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    phase: str
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RagRetrievalDiagnostic(BaseModel):
    """Per-section retrieval diagnostics emitted during writing."""

    workflow_id: str
    section: str
    query_type: str  # hyde|section_fallback|none
    rerank_enabled: bool
    candidate_k: int
    final_k: int
    retrieved_count: int
    status: str  # success|empty|error|skipped
    selected_chunks_json: str = "[]"
    error_message: str | None = None
    latency_ms: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
