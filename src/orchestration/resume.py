"""Resume state loading and next-phase determination."""

from __future__ import annotations

from pathlib import Path

from src.config.loader import load_configs
from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.models import ExtractionRecord
from src.orchestration.state import ReviewState
from src.search.deduplication import deduplicate_papers

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
    run_root: str,
) -> tuple[ReviewState, str]:
    """Load ReviewState from existing db and determine next phase to run.

    Returns (state, next_phase). next_phase is one of PHASE_ORDER or 'finalize'.
    All artifacts (log files and output documents) now live in the same run dir.
    """
    review, settings = load_configs(review_path, settings_path)
    run_dir = Path(db_path).resolve().parent
    run_dir.mkdir(parents=True, exist_ok=True)
    log_dir = str(run_dir)
    output_dir = log_dir  # same directory

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

        # Prefer fulltext-stage decisions; fall back to title_abstract when
        # skip_fulltext_if_no_pdf=True leaves the fulltext table empty.
        included_ids = await repo.get_included_paper_ids(workflow_id)
        if not included_ids:
            included_ids = await repo.get_title_abstract_include_ids(workflow_id)
        included_papers_sorted = [p for p in deduped if p.paper_id in included_ids]

        extraction_records_list: list[ExtractionRecord] = []
        if "phase_4_extraction_quality" in checkpoints:
            extraction_records_list = await repo.load_extraction_records(workflow_id)

    next_phase = _next_phase(checkpoints)

    artifacts = {
        "run_summary": str(run_dir / "run_summary.json"),
        "search_appendix": str(run_dir / "doc_search_strategies_appendix.md"),
        "protocol": str(run_dir / "doc_protocol.md"),
        "coverage_report": str(run_dir / "doc_fulltext_retrieval_coverage.md"),
        "disagreements_report": str(run_dir / "doc_disagreements_report.md"),
        "rob_traffic_light": str(run_dir / "fig_rob_traffic_light.png"),
        "narrative_synthesis": str(run_dir / "data_narrative_synthesis.json"),
        "manuscript_md": str(run_dir / "doc_manuscript.md"),
        "prisma_diagram": str(run_dir / "fig_prisma_flow.png"),
        "timeline": str(run_dir / "fig_publication_timeline.png"),
        "geographic": str(run_dir / "fig_geographic_distribution.png"),
        "fig_forest_plot": str(run_dir / "fig_forest_plot.png"),
        "fig_funnel_plot": str(run_dir / "fig_funnel_plot.png"),
    }

    state = ReviewState(
        review_path=review_path,
        settings_path=settings_path,
        run_root=run_root,
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
