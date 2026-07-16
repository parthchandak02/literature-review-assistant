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
from src.orchestration.phase_catalog import (
    PHASE_ORDER,
    SUB_PHASE_CHECKPOINTS,
    USER_RESUMABLE_PHASE_ORDER,
)
from src.orchestration.state import ReviewState
from src.search.deduplication import deduplicate_papers

__all__ = [
    "PHASE_ORDER",
    "USER_RESUMABLE_PHASE_ORDER",
    "ResumeNotAllowedError",
    "load_resume_state",
    "validate_resume_allowed",
]


class ResumeNotAllowedError(ValueError):
    """Raised when a resume request would replay a finished workflow."""


async def validate_resume_allowed(
    db_path: str,
    workflow_id: str,
    *,
    from_phase: str | None,
) -> None:
    """Reject resume calls that would rewind and replay an already-finished run."""
    async with get_db(db_path) as db:
        repo = WorkflowRepository(db)
        checkpoints = await repo.get_checkpoints(workflow_id)

    finalize_done = checkpoints.get("finalize") == "completed"
    all_phases_done = all(checkpoints.get(phase) == "completed" for phase in PHASE_ORDER)

    if from_phase is not None and finalize_done:
        raise ResumeNotAllowedError(
            "Workflow finalize checkpoint is completed; from_phase resume would replay "
            "earlier phases and duplicate screening/extraction work. "
            "Start a fresh run if you need a full rerun."
        )

    if from_phase is None and finalize_done:
        raise ResumeNotAllowedError("Workflow finalize checkpoint is completed; nothing remains to resume.")

    if from_phase is None and all_phases_done:
        raise ResumeNotAllowedError("All workflow phase checkpoints are completed; nothing remains to resume.")


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


def _extract_screening_kappa_from_phase_done_payloads(
    payloads: list[dict[str, object]],
) -> tuple[float | None, str | None, int]:
    """Return the first usable screening kappa from provided phase_done payloads."""
    for payload in payloads:
        summary = payload.get("summary", {})
        if not isinstance(summary, dict):
            continue
        raw_kappa = summary.get("kappa")
        if raw_kappa is None:
            continue
        try:
            kappa_value = float(raw_kappa)
        except (TypeError, ValueError):
            continue
        raw_n = summary.get("sample_size", 0) or summary.get("kappa_n", 0) or 0
        try:
            kappa_n = int(raw_n)
        except (TypeError, ValueError):
            kappa_n = 0
        return kappa_value, "title_abstract", kappa_n
    return None, None, 0


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
    await validate_resume_allowed(db_path, workflow_id, from_phase=from_phase)

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

        # Restore Cohen's kappa from phase_done events.
        # Kappa is computed during screening but not persisted to the workflows
        # table, so resume must recover it from event_log. Prefer the dedicated
        # screening_calibration event when present, then fall back to the normal
        # phase_3_screening summary used by non-calibrated runs.
        try:
            import json as _json

            _phase_payloads: list[dict[str, object]] = []
            for _phase_name in ("screening_calibration", "phase_3_screening"):
                _phase_cur = await db.execute(
                    """
                    SELECT payload FROM event_log
                    WHERE workflow_id = ? AND event_type = 'phase_done'
                      AND json_extract(payload, '$.phase') = ?
                    ORDER BY ts DESC LIMIT 1
                    """,
                    (workflow_id, _phase_name),
                )
                _phase_row = await _phase_cur.fetchone()
                if not _phase_row:
                    continue
                _phase_payload = _json.loads(_phase_row[0]) if isinstance(_phase_row[0], str) else _phase_row[0]
                if isinstance(_phase_payload, dict):
                    _phase_payloads.append(_phase_payload)
            (
                cohens_kappa_restored,
                kappa_stage_restored,
                kappa_n_restored,
            ) = _extract_screening_kappa_from_phase_done_payloads(_phase_payloads)
        except Exception as _kappa_exc:
            logger.warning("Could not restore kappa from event_log on resume: %s", _kappa_exc)

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
                    extra.extend(SUB_PHASE_CHECKPOINTS.get(phase, []))
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
            if next_phase in {"phase_7_audit", "finalize"} and "phase_6_writing" in checkpoints:
                manuscript_md_path = run_dir / "doc_manuscript.md"
                if not manuscript_md_path.exists():
                    logger.warning(
                        "phase_6_writing checkpoint exists but %s is missing; "
                        "clearing checkpoint so WritingNode re-runs assembly.",
                        manuscript_md_path,
                    )
                    await repo.delete_checkpoints_for_phases(workflow_id, ["phase_6_writing"])
                    next_phase = "phase_6_writing"

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
        "custom_diagram_01": str(run_dir / "fig_custom_01.png"),
        "custom_diagram_02": str(run_dir / "fig_custom_02.png"),
        "custom_diagram_03": str(run_dir / "fig_custom_03.png"),
        "diagram_brief_pack": str(run_dir / "data_diagram_brief_pack.json"),
        "diagram_placement_plan": str(run_dir / "data_diagram_placement_plan.json"),
        "diagram_generation_report": str(run_dir / "data_diagram_generation_report.json"),
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
