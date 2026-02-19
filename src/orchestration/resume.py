"""Resume state loading and next-phase determination."""

from __future__ import annotations

from pathlib import Path

from src.config.loader import load_configs
from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.models import CandidatePaper, ExtractionRecord, ReviewConfig, SettingsConfig
from src.orchestration.state import ReviewState
from src.search.deduplication import deduplicate_papers
from src.utils.logging_paths import OutputRunPaths, workflow_slug

PHASE_ORDER = [
    "phase_2_search",
    "phase_3_screening",
    "phase_4_extraction_quality",
    "phase_5_synthesis",
    "phase_6_writing",
    "finalize",
]


def _next_phase(checkpoints: dict[str, str]) -> str:
    """Return the first phase not in checkpoints, or 'finalize' if all done."""
    for phase in PHASE_ORDER:
        if phase not in checkpoints:
            return phase
    return "finalize"


async def load_resume_state(
    db_path: str,
    workflow_id: str,
    review_path: str,
    settings_path: str,
    log_root: str,
    output_root: str,
) -> tuple[ReviewState, str]:
    """Load ReviewState from existing db and determine next phase to run.

    Returns (state, next_phase). next_phase is one of PHASE_ORDER or 'finalize'.
    """
    review, settings = load_configs(review_path, settings_path)
    log_dir = str(Path(db_path).resolve().parent)
    run_dir_name = Path(db_path).parent.name
    date_folder = Path(db_path).parent.parent.parent.name
    topic = review.research_question
    output_dir_path = Path(output_root) / date_folder / workflow_slug(topic) / run_dir_name
    output_dir_path.mkdir(parents=True, exist_ok=True)
    output_dir = str(output_dir_path)

    async with get_db(db_path) as db:
        repo = WorkflowRepository(db)
        checkpoints = await repo.get_checkpoints(workflow_id)
        search_counts = await repo.get_search_counts(workflow_id)

        all_papers = await repo.get_all_papers()
        deduped, recomputed_dedup_count = deduplicate_papers(all_papers)

        # Use stored dedup_count when available; fall back to recomputed value for
        # older runs that predate the dedup_count column.
        stored_dedup_count = await repo.get_dedup_count(workflow_id)
        dedup_count = stored_dedup_count if stored_dedup_count is not None else recomputed_dedup_count

        included_ids = await repo.get_included_paper_ids(workflow_id)
        included_papers_sorted = [p for p in deduped if p.paper_id in included_ids]

        extraction_records_list: list[ExtractionRecord] = []
        if "phase_4_extraction_quality" in checkpoints:
            extraction_records_list = await repo.load_extraction_records(workflow_id)

    next_phase = _next_phase(checkpoints)

    artifacts = {
        "run_summary": str(Path(log_dir) / "run_summary.json"),
        "search_appendix": str(Path(output_dir) / "doc_search_strategies_appendix.md"),
        "protocol": str(Path(output_dir) / "doc_protocol.md"),
        "coverage_report": str(Path(output_dir) / "doc_fulltext_retrieval_coverage.md"),
        "disagreements_report": str(Path(output_dir) / "doc_disagreements_report.md"),
        "rob_traffic_light": str(Path(output_dir) / "fig_rob_traffic_light.png"),
        "narrative_synthesis": str(Path(output_dir) / "data_narrative_synthesis.json"),
        "manuscript_md": str(Path(output_dir) / "doc_manuscript.md"),
        "prisma_diagram": str(Path(output_dir) / "fig_prisma_flow.png"),
        "timeline": str(Path(output_dir) / "fig_publication_timeline.png"),
        "geographic": str(Path(output_dir) / "fig_geographic_distribution.png"),
    }

    state = ReviewState(
        review_path=review_path,
        settings_path=settings_path,
        log_root=log_root,
        output_root=output_root,
        run_context=None,
        run_id="",
        workflow_id=workflow_id,
        review=review,
        settings=settings,
        db_path=db_path,
        log_dir=log_dir,
        output_dir=output_dir,
        connector_init_failures={},
        search_counts=search_counts,
        dedup_count=dedup_count,
        deduped_papers=deduped,
        included_papers=included_papers_sorted,
        extraction_records=extraction_records_list,
        artifacts=artifacts,
        next_phase=next_phase,
    )
    return state, next_phase
