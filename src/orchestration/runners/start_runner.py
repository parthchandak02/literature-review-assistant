"""Runner helpers for StartNode and ResumeStartNode."""

from __future__ import annotations

from pathlib import Path

from src.config.loader import load_configs
from src.db.workflow_registry import allocate_workflow_id, find_by_workflow_id
from src.orchestration.state import ReviewState
from src.utils import structured_log
from src.utils.logging_paths import create_run_paths


def _rc(state: ReviewState):
    return getattr(state, "run_context", None)


def _now_utc() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


async def run_start_node(state: ReviewState) -> None:
    """Populate initial workflow state and run paths."""
    rc = _rc(state)
    if rc:
        rc.emit_phase_start("start", "Loading configs...")
    review, settings = load_configs(state.review_path, state.settings_path)
    state.review = review
    state.settings = settings
    state.run_id = _now_utc()
    state.workflow_id = await allocate_workflow_id(state.run_root)

    run_paths = create_run_paths(
        run_root=state.run_root,
        workflow_description=review.research_question,
        workflow_id=state.workflow_id,
    )
    state.log_dir = str(run_paths.run_dir)
    state.output_dir = str(run_paths.run_dir)
    state.db_path = str(run_paths.runtime_db)
    structured_log.configure_run_logging(state.log_dir)
    structured_log.bind_run(state.workflow_id, state.run_id, log_dir=state.log_dir)
    state.artifacts["run_summary"] = str(run_paths.run_summary)
    state.artifacts["search_appendix"] = str(run_paths.search_appendix)
    state.artifacts["protocol"] = str(run_paths.protocol_markdown)
    state.artifacts["coverage_report"] = str(run_paths.run_dir / "doc_fulltext_retrieval_coverage.md")
    state.artifacts["disagreements_report"] = str(run_paths.run_dir / "doc_disagreements_report.md")
    state.artifacts["rob_traffic_light"] = str(run_paths.run_dir / "fig_rob_traffic_light.png")
    state.artifacts["rob2_traffic_light"] = str(run_paths.run_dir / "fig_rob2_traffic_light.png")
    state.artifacts["narrative_synthesis"] = str(run_paths.run_dir / "data_narrative_synthesis.json")
    state.artifacts["manuscript_md"] = str(run_paths.run_dir / "doc_manuscript.md")
    state.artifacts["manuscript_tex"] = str(run_paths.run_dir / "doc_manuscript.tex")
    state.artifacts["references_bib"] = str(run_paths.run_dir / "references.bib")
    state.artifacts["prisma_diagram"] = str(run_paths.run_dir / "fig_prisma_flow.png")
    state.artifacts["timeline"] = str(run_paths.run_dir / "fig_publication_timeline.png")
    state.artifacts["geographic"] = str(run_paths.run_dir / "fig_geographic_distribution.png")
    state.artifacts["fig_forest_plot"] = str(run_paths.run_dir / "fig_forest_plot.png")
    state.artifacts["fig_funnel_plot"] = str(run_paths.run_dir / "fig_funnel_plot.png")
    state.artifacts["concept_taxonomy"] = str(run_paths.run_dir / "fig_concept_taxonomy.svg")
    state.artifacts["conceptual_framework"] = str(run_paths.run_dir / "fig_conceptual_framework.svg")
    state.artifacts["methodology_flow"] = str(run_paths.run_dir / "fig_methodology_flow.svg")
    state.artifacts["evidence_network"] = str(run_paths.run_dir / "fig_evidence_network.png")
    state.artifacts["papers_dir"] = str(run_paths.run_dir / "papers")
    state.artifacts["papers_manifest"] = str(run_paths.run_dir / "data_papers_manifest.json")
    state.artifacts["prospero_form_md"] = str(run_paths.run_dir / "doc_prospero_registration.md")
    state.artifacts["prospero_form"] = str(run_paths.run_dir / "doc_prospero_registration.docx")

    config_src = Path(state.review_path) if Path(state.review_path).exists() else Path("config/review.yaml")
    snapshot_dest = run_paths.run_dir / "config_snapshot.yaml"
    header = f"# workflow_id: {state.workflow_id}\n# run_dir: {run_paths.run_dir}\n# created_at: {state.run_id}\n#\n"
    if config_src.exists():
        snapshot_dest.write_text(
            header + config_src.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    else:
        snapshot_dest.write_text(header, encoding="utf-8")

    if rc:
        rc.emit_phase_done("start", {"workflow_id": state.workflow_id})
        if hasattr(rc, "set_db_path"):
            rc.set_db_path(state.db_path)


async def resolve_resume_next_phase(state: ReviewState) -> str:
    """Resolve next phase key for resume routing."""
    rc = _rc(state)
    if rc:
        rc.emit_phase_start("resume", f"Resuming from {state.next_phase}...")
    structured_log.configure_run_logging(state.log_dir)
    structured_log.bind_run(state.workflow_id, state.run_id or "resume", log_dir=state.log_dir)
    try:
        reg_entry = await find_by_workflow_id(state.run_root, state.workflow_id)
        if reg_entry and str(getattr(reg_entry, "status", "")) == "awaiting_review":
            return "human_review_checkpoint"
    except Exception:
        pass
    return state.next_phase or "phase_2_search"
