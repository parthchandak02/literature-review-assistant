"""Workflow state model."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.models import CandidatePaper, ExtractionRecord, ReviewConfig, SettingsConfig
from src.orchestration.context import RunContext


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
    dedup_count: int = 0
    deduped_papers: list[CandidatePaper] = field(default_factory=list)
    included_papers: list[CandidatePaper] = field(default_factory=list)
    extraction_records: list[ExtractionRecord] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    next_phase: str = ""  # Set when resuming; first phase to run
    cohens_kappa: float | None = None
    kappa_stage: str | None = None
    sensitivity_results: list[str] = field(default_factory=list)
