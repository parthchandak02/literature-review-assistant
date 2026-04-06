"""Resume state loading and next-phase determination."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from src.config.loader import load_configs
from src.db.database import get_db, repair_foreign_key_integrity

logger = logging.getLogger(__name__)
from src.db.repositories import WorkflowRepository
from src.models import ExtractionRecord
from src.models.config import ReviewConfig
from src.orchestration.state import ReviewState
from src.search.deduplication import deduplicate_papers

PHASE_ORDER = [
    "phase_2_search",
    "phase_3_screening",
    "phase_4_extraction_quality",
    "phase_4b_embedding",
    "phase_5_synthesis",
    "phase_5b_knowledge_graph",
    "phase_6_writing",
    "phase_7_audit",
    "finalize",
]


def _next_phase(checkpoints: dict[str, str]) -> str:
    """Return first phase that is missing or not completed.

    Checkpoint status matters: `partial` must be treated as incomplete so resume
    re-enters that phase instead of skipping ahead.
    """
    for phase in PHASE_ORDER:
        if checkpoints.get(phase) != "completed":
            return phase
    return "finalize"


def _phases_from(from_phase: str) -> list[str]:
    """Return from_phase and all later phases in PHASE_ORDER."""
    try:
        idx = PHASE_ORDER.index(from_phase)
        return list(PHASE_ORDER[idx:])
    except ValueError:
        return []


async def load_resume_state(
    db_path: str,
    workflow_id: str,
    review_path: str,
    settings_path: str,
    run_root: str,
    from_phase: str | None = None,
) -> tuple[ReviewState, str]:
    """Load ReviewState from existing db and determine next phase to run.

    Returns (state, next_phase). next_phase is one of PHASE_ORDER or 'finalize'.
    All artifacts (log files and output documents) now live in the same run dir.

    When from_phase is provided: validate it is in PHASE_ORDER, ensure all prior
    phases have checkpoints, clear checkpoints for from_phase and later, and
    return next_phase=from_phase.
    """
    run_dir = Path(db_path).resolve().parent
    run_dir.mkdir(parents=True, exist_ok=True)
    review, settings = load_configs(review_path, settings_path)
    # Resume must use the run's captured review config, not the mutable workspace
    # config/review.yaml, otherwise placeholder template text can leak into reruns.
    snapshot_path = run_dir / "config_snapshot.yaml"
    if snapshot_path.exists():
        try:
            snapshot_data = yaml.safe_load(snapshot_path.read_text(encoding="utf-8")) or {}
            review = ReviewConfig.model_validate(snapshot_data)
        except Exception as snapshot_err:
            logger.warning("Could not load review config from %s: %s", snapshot_path, snapshot_err)
    log_dir = str(run_dir)
    output_dir = log_dir  # same directory

    cohens_kappa_restored: float | None = None
    kappa_stage_restored: str | None = None
    kappa_n_restored: int = 0

    async with get_db(db_path) as db:
        await repair_foreign_key_integrity(db)
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

        # Restore Cohen's kappa from the screening_calibration phase_done event.
        # kappa is computed during screening but not persisted to the workflows
        # table, so on resume state.cohens_kappa is None and the grounding block
        # incorrectly says kappa was not computed.
        _calib_event = await repo.get_last_event_of_type(workflow_id, "phase_done")
        # get_last_event_of_type returns the most recent phase_done; we need
        # specifically the screening_calibration one, so query directly.
        try:
            import json as _json

            _calib_cur = await db.execute(
                """
                SELECT payload FROM event_log
                WHERE workflow_id = ? AND event_type = 'phase_done'
                  AND json_extract(payload, '$.phase') = 'screening_calibration'
                ORDER BY ts DESC LIMIT 1
                """,
                (workflow_id,),
            )
            _calib_row = await _calib_cur.fetchone()
            if _calib_row:
                _calib_payload = _json.loads(_calib_row[0]) if isinstance(_calib_row[0], str) else _calib_row[0]
                _summary = (_calib_payload or {}).get("summary", {}) or {}
                if _summary.get("kappa") is not None:
                    cohens_kappa_restored = float(_summary["kappa"])
                    kappa_stage_restored = "title_abstract"
                    kappa_n_restored = int(_summary.get("sample_size", 0))
        except Exception as _kappa_exc:
            logger.warning("Could not restore kappa from event_log on resume: %s", _kappa_exc)

        # Sub-phase checkpoints that must be cleared when their parent phase is re-run.
        # These are mid-phase markers not in PHASE_ORDER but used for resume skipping.
        _SUB_PHASE_CHECKPOINTS: dict[str, list[str]] = {
            "phase_3_screening": ["phase_3b_fulltext"],
            "phase_6_writing": [
                "phase_6a_hyde",
                "phase_6b_phase_a",
                "phase_6c_phase_b",
                "phase_6d_assembly",
                "phase_6e_concepts",
            ],
        }

        if from_phase is not None:
            if from_phase not in PHASE_ORDER:
                raise ValueError(f"from_phase must be one of {PHASE_ORDER!r}, got {from_phase!r}")
            from_idx = PHASE_ORDER.index(from_phase)
            prior_phases = PHASE_ORDER[:from_idx]
            for p in prior_phases:
                if p not in checkpoints:
                    # Auto-fallback: user selected invalid phase (e.g. frontend/backend
                    # mismatch). Resume from first incomplete instead.
                    fallback = _next_phase(checkpoints)
                    logger.warning(
                        "Cannot resume from %s: phase %s has no checkpoint. Falling back to %s.",
                        from_phase,
                        p,
                        fallback,
                    )
                    next_phase = fallback
                    break
            else:
                phases_to_clear = _phases_from(from_phase)
                # Also clear any sub-phase checkpoints for phases being re-run so that
                # mid-phase skip guards do not incorrectly fire on an explicit re-run.
                extra: list[str] = []
                for phase in phases_to_clear:
                    extra.extend(_SUB_PHASE_CHECKPOINTS.get(phase, []))
                phases_to_clear = list(phases_to_clear) + extra
                await repo.delete_checkpoints_for_phases(workflow_id, phases_to_clear)
                # Clear persisted downstream data so a rewind is a true replay,
                # not an append onto stale rows from later phases.
                await repo.rollback_phase_data(workflow_id, from_phase)
                # Re-running writing (or any earlier phase that includes writing)
                # must clear persisted section_drafts; otherwise WritingNode sees
                # sections as already completed and skips regeneration.
                if "phase_6_writing" in phases_to_clear:
                    await repo.delete_section_drafts(workflow_id)
                # Refresh in-memory state after rollback so returned ReviewState
                # reflects the post-rewind DB contents.
                checkpoints = await repo.get_checkpoints(workflow_id)
                search_counts = await repo.get_search_counts(workflow_id)
                all_papers = await repo.get_all_papers()
                deduped, recomputed_dedup_count = deduplicate_papers(all_papers)
                stored_dedup_count = await repo.get_dedup_count(workflow_id)
                dedup_count = stored_dedup_count if stored_dedup_count is not None else recomputed_dedup_count
                included_ids = await repo.get_included_paper_ids(workflow_id)
                if not included_ids:
                    included_ids = await repo.get_title_abstract_include_ids(workflow_id)
                included_papers_sorted = [p for p in deduped if p.paper_id in included_ids]
                extraction_records_list = []
                if "phase_4_extraction_quality" in checkpoints:
                    extraction_records_list = await repo.load_extraction_records(workflow_id)
                next_phase = from_phase
        else:
            next_phase = _next_phase(checkpoints)
            # Guard: the phase_6_writing checkpoint can be saved before the
            # manuscript file is written (if the process crashes during assembly).
            # If the file is absent, clear the stale checkpoint so WritingNode
            # re-runs and produces the manuscript; section_drafts already hold all
            # completed LLM outputs so only the assembly step is repeated.
            if next_phase == "finalize" and "phase_6_writing" in checkpoints:
                manuscript_md_path = run_dir / "doc_manuscript.md"
                if not manuscript_md_path.exists():
                    logger.warning(
                        "phase_6_writing checkpoint exists but %s is missing; "
                        "clearing checkpoint so WritingNode re-runs assembly.",
                        manuscript_md_path,
                    )
                    await repo.delete_checkpoints_for_phases(workflow_id, ["phase_6_writing"])
                    next_phase = "phase_6_writing"

        if next_phase == "finalize" and checkpoints.get("phase_7_audit") == "completed":
            _audit_md = run_dir / "doc_manuscript.md"
            if not _audit_md.exists():
                logger.warning(
                    "phase_7_audit checkpoint completed but %s is missing; "
                    "clearing checkpoint so ManuscriptAuditNode can re-run.",
                    _audit_md,
                )
                await repo.delete_checkpoints_for_phases(workflow_id, ["phase_7_audit"])
                checkpoints = await repo.get_checkpoints(workflow_id)
                next_phase = "phase_7_audit"

    artifacts = {
        "run_summary": str(run_dir / "run_summary.json"),
        "search_appendix": str(run_dir / "doc_search_strategies_appendix.md"),
        "protocol": str(run_dir / "doc_protocol.md"),
        "coverage_report": str(run_dir / "doc_fulltext_retrieval_coverage.md"),
        "disagreements_report": str(run_dir / "doc_disagreements_report.md"),
        "rob_traffic_light": str(run_dir / "fig_rob_traffic_light.png"),
        "rob2_traffic_light": str(run_dir / "fig_rob2_traffic_light.png"),
        "narrative_synthesis": str(run_dir / "data_narrative_synthesis.json"),
        "manuscript_md": str(run_dir / "doc_manuscript.md"),
        "manuscript_tex": str(run_dir / "doc_manuscript.tex"),
        "references_bib": str(run_dir / "references.bib"),
        "evidence_network": str(run_dir / "fig_evidence_network.png"),
        "papers_dir": str(run_dir / "papers"),
        "papers_manifest": str(run_dir / "data_papers_manifest.json"),
        "prisma_diagram": str(run_dir / "fig_prisma_flow.png"),
        "timeline": str(run_dir / "fig_publication_timeline.png"),
        "geographic": str(run_dir / "fig_geographic_distribution.png"),
        "fig_forest_plot": str(run_dir / "fig_forest_plot.png"),
        "fig_funnel_plot": str(run_dir / "fig_funnel_plot.png"),
        "concept_taxonomy": str(run_dir / "fig_concept_taxonomy.svg"),
        "conceptual_framework": str(run_dir / "fig_conceptual_framework.svg"),
        "methodology_flow": str(run_dir / "fig_methodology_flow.svg"),
        "prospero_form_md": str(run_dir / "doc_prospero_registration.md"),
        "prospero_form": str(run_dir / "doc_prospero_registration.docx"),
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
        cohens_kappa=cohens_kappa_restored,
        kappa_stage=kappa_stage_restored,
        kappa_n=kappa_n_restored,
    )
    return state, next_phase
