"""Workflow state model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.models import CandidatePaper, ExtractionRecord, ReviewConfig, SettingsConfig
from src.orchestration.context import RunContext

if TYPE_CHECKING:
    from src.synthesis.contradiction_detector import ContradictionFlag


@dataclass
class ReviewState:
    review_path: str
    settings_path: str
    run_root: str
    run_context: RunContext | None = None
    run_id: str = ""
    workflow_id: str = ""
    review: ReviewConfig | None = None
    settings: SettingsConfig | None = None
    db_path: str = ""
    log_dir: str = ""
    output_dir: str = ""
    connector_init_failures: dict[str, str] = field(default_factory=dict)
    search_counts: dict[str, int] = field(default_factory=dict)
    search_queries: dict[str, str] = field(default_factory=dict)
    dedup_count: int = 0
    deduped_papers: list[CandidatePaper] = field(default_factory=list)
    included_papers: list[CandidatePaper] = field(default_factory=list)
    extraction_records: list[ExtractionRecord] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    next_phase: str = ""  # Set when resuming; first phase to run
    cohens_kappa: float | None = None
    kappa_stage: str | None = None
    kappa_n: int = 0  # number of papers in the uncertain-paper subset used for kappa
    sensitivity_results: list[str] = field(default_factory=list)
    contradiction_flags: list[ContradictionFlag] = field(default_factory=list)
    parent_db_path: str | None = None  # set for living-review delta runs
    # Count of quality assessments that used heuristic fallback (LLM timed out).
    # Surfaced in the Methods section grounding block for transparency.
    heuristic_assessment_count: int = 0
    # Batch LLM pre-ranker counts (set during screening phase).
    # Used by the writing grounding block to describe the 3-stage screening funnel.
    batch_screen_forwarded: int = 0
    batch_screen_excluded: int = 0
    # Model name and threshold used for batch pre-ranking (surfaced in Methods grounding block
    # so the writing LLM can cite the exact model and threshold for methodological transparency).
    batch_screener_model: str | None = None
    batch_screen_threshold: float = 0.35
    # Validation of batch-excluded abstracts: a random sample re-scored to compute NPV.
    # batch_screen_validation_n: number of excluded abstracts sampled for cross-validation.
    # batch_screen_validation_npv: negative predictive value (0.0-1.0) of the validation.
    # Both are 0 when no validation was performed.
    batch_screen_validation_n: int = 0
    batch_screen_validation_npv: float = 0.0
    batch_screen_borderline_forwarded: int = 0
    # PRISMA full-text retrieval counts (set after PDF retrieval).
    # fulltext_sought: papers sent to stage-2 full-text screening.
    # fulltext_not_retrieved: papers excluded because no PDF could be obtained.
    fulltext_sought: int = 0
    fulltext_not_retrieved: int = 0
    # RAG retrieval health counters recorded during writing.
    rag_sections_total: int = 0
    rag_sections_success: int = 0
    rag_sections_empty: int = 0
    rag_sections_error: int = 0
    rag_sections_skipped: int = 0
    rag_threshold_breached: bool = False
