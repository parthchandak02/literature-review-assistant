"""Runner for SynthesisNode — extracted from workflow.py."""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path

from pydantic_graph import GraphRunContext

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.llm.factory import get_chat_client
from src.llm.provider import LLMProvider
from src.models import DecisionLogEntry
from src.orchestration.helpers.runtime import llm_available as helper_llm_available
from src.orchestration.helpers.runtime import rc as helper_rc
from src.orchestration.helpers.runtime import rc_print as helper_rc_print
from src.orchestration.state import ReviewState
from src.synthesis import assess_meta_analysis_feasibility, build_narrative_synthesis
from src.synthesis.meta_analysis import pool_effects
from src.synthesis.sensitivity import run_sensitivity_analysis
from src.visualization.forest_plot import render_forest_plot
from src.visualization.funnel_plot import render_funnel_plot

logger = logging.getLogger(__name__)


def _rc(state: ReviewState):
    return helper_rc(state)


def _rc_print(rc, message: object) -> None:
    helper_rc_print(rc, message)


def _llm_available(settings=None, settings_cfg=None):
    return helper_llm_available(settings=settings, settings_cfg=settings_cfg)


def _try_meta_analysis(
    records: list,
    outcome_name: str,
    het_threshold: float,
    effect_measure: str,
    forest_path: str,
    funnel_path: str,
    funnel_min_studies: int = 10,
) -> tuple:
    """Attempt to pool effect sizes from ExtractionRecord.outcomes.

    Returns (MetaAnalysisResult | None, forest_path | None, funnel_path | None).
    Effect sizes are extracted from outcomes[*].effect_size and outcomes[*].se keys
    (populated by LLM extraction; absent in heuristic extraction).
    No LLM statistics -- all pooling done via statsmodels pool_effects().
    """
    effects: list[float] = []
    variances: list[float] = []
    labels: list[str] = []

    for record in records:
        for outcome in record.outcomes or []:
            name = outcome.name.lower().replace(" ", "_")
            if outcome_name not in name:
                continue
            effect_str = outcome.effect_size or ""
            se_str = outcome.se or ""
            var_str = outcome.variance or ""

            def _first_float(s: str) -> float | None:
                """Return the first token in *s* that parses as a finite float."""
                for tok in str(s).replace("=", " ").replace(",", " ").split():
                    try:
                        val = float(tok)
                        if math.isfinite(val):
                            return val
                    except ValueError:
                        continue
                return None

            effect_val = _first_float(effect_str) if effect_str else None

            variance_val: float | None = None
            if var_str:
                variance_val = _first_float(var_str)
            elif se_str:
                se_val = _first_float(se_str)
                variance_val = se_val**2 if se_val is not None else None

            if effect_val is None or variance_val is None:
                logger.debug(
                    "_try_meta_analysis: skipping outcome '%s' for paper %s "
                    "(effect_str=%r var_str=%r se_str=%r -> effect=%s variance=%s)",
                    outcome.name,
                    record.paper_id[:12],
                    effect_str,
                    var_str,
                    se_str,
                    effect_val,
                    variance_val,
                )

            if effect_val is not None and variance_val is not None and variance_val > 0:
                effects.append(effect_val)
                variances.append(variance_val)
                labels.append(record.paper_id[:12])
                break

    if len(effects) < 2:
        return None, None, None

    try:
        meta_result = pool_effects(
            outcome_name=outcome_name,
            effect_measure=effect_measure,
            effects=effects,
            variances=variances,
            heterogeneity_threshold=het_threshold,
        )
    except Exception:
        return None, None, None

    rendered_forest: str | None = None
    rendered_funnel: str | None = None

    try:
        rendered_forest = render_forest_plot(
            effects=effects,
            variances=variances,
            labels=labels,
            output_path=forest_path,
            title=f"Forest plot: {outcome_name} ({effect_measure})",
        )
        meta_result = meta_result.model_copy(update={"forest_plot_path": rendered_forest})
    except Exception:
        pass

    if len(effects) >= funnel_min_studies:
        try:
            ses = [math.sqrt(v) for v in variances]
            rendered_funnel = render_funnel_plot(
                effect_sizes=effects,
                standard_errors=ses,
                pooled_effect=meta_result.pooled_effect,
                output_path=funnel_path,
                title=f"Funnel plot: {outcome_name}",
                minimum_studies=funnel_min_studies,
            )
            if rendered_funnel:
                meta_result = meta_result.model_copy(update={"funnel_plot_path": rendered_funnel})
        except Exception:
            pass

    return meta_result, rendered_forest, rendered_funnel


async def run_synthesis_node(state: ReviewState, ctx: GraphRunContext[ReviewState]) -> None:
    rc = _rc(state)
    assert state.settings is not None
    if rc:
        rc.emit_phase_start("phase_5_synthesis", "Building synthesis...", total=1)
    if rc:
        rc.log_status(f"Assessing meta-analysis feasibility across {len(state.extraction_records)} included papers...")
    feasibility = assess_meta_analysis_feasibility(state.extraction_records)
    _use_llm = _llm_available(settings_cfg=state.settings) and (rc is None or not rc.offline)
    _synth_timeout = float(getattr(getattr(state.settings, "llm", None), "request_timeout_seconds", 120))
    _synth_llm = get_chat_client(timeout_seconds=_synth_timeout) if _use_llm else None
    if rc:
        rc.log_status("Building narrative synthesis (LLM direction classification)...")
    if _use_llm:
        async with get_db(state.db_path) as _synth_db:
            _synth_repo = WorkflowRepository(_synth_db)
            _synth_on_waiting = None
            _synth_on_resolved = None
            if rc:

                def _on_waiting(t: object, u: object, limit: object, waited: object = 0.0) -> None:
                    rc.log_rate_limit_wait(t, u, limit, waited)  # type: ignore[union-attr]

                def _on_resolved(t: object, waited: object) -> None:
                    rc.log_rate_limit_resolved(t, waited)  # type: ignore[union-attr]

                _synth_on_waiting = _on_waiting
                _synth_on_resolved = _on_resolved
            _synth_provider = LLMProvider(
                state.settings,
                _synth_repo,
                on_waiting=_synth_on_waiting,
                on_resolved=_synth_on_resolved,
            )
            narrative = await build_narrative_synthesis(
                "primary_outcome",
                state.extraction_records,
                llm_client=_synth_llm,
                settings=state.settings,
                review_question=state.review.research_question if state.review else "",
                pico=state.review.pico if state.review else None,
                llm_provider=_synth_provider,
                workflow_id=state.workflow_id,
            )
    else:
        narrative = await build_narrative_synthesis(
            "primary_outcome",
            state.extraction_records,
            llm_client=_synth_llm,
            settings=state.settings,
            review_question=state.review.research_question if state.review else "",
            pico=state.review.pico if state.review else None,
            workflow_id=state.workflow_id,
        )

    meta_result = None
    rendered_forest = None
    rendered_funnel = None
    sensitivity_texts: list[str] = []
    if state.sparse_evidence_mode and rc:
        rc.log_status("Sparse-evidence mode: skipping quantitative meta-analysis and using narrative-only synthesis.")
    if feasibility.feasible and state.settings.meta_analysis.enabled and not state.sparse_evidence_mode:
        if rc:
            rc.log_status(
                f"Running quantitative meta-analysis and sensitivity analysis "
                f"({len(feasibility.groupings)} outcome group(s))..."
            )
        het_threshold = float(state.settings.meta_analysis.heterogeneity_threshold)
        effect_measure = state.settings.meta_analysis.effect_measure_continuous
        funnel_min = state.settings.meta_analysis.funnel_plot_minimum_studies
        for group in feasibility.groupings:
            meta_result, rendered_forest, rendered_funnel = _try_meta_analysis(
                records=state.extraction_records,
                outcome_name=group,
                het_threshold=het_threshold,
                effect_measure=effect_measure,
                forest_path=state.artifacts["fig_forest_plot"],
                funnel_path=state.artifacts["fig_funnel_plot"],
                funnel_min_studies=funnel_min,
            )
            if meta_result is not None:
                sens = run_sensitivity_analysis(
                    records=state.extraction_records,
                    outcome_name=group,
                    effect_measure=effect_measure,
                    subgroup_cols=["study_design"],
                    heterogeneity_threshold=het_threshold,
                )
                if sens is not None:
                    sensitivity_texts.append(sens.to_grounding_text())
                break

    state.sensitivity_results = sensitivity_texts

    if rc:
        rc.log_synthesis(
            feasible=feasibility.feasible,
            groups=feasibility.groupings,
            rationale=feasibility.rationale,
            n_studies=narrative.n_studies,
            direction=narrative.effect_direction_summary,
        )
        if rc.verbose:
            if meta_result is not None:
                _rc_print(
                    rc,
                    f"  Meta-analysis: {meta_result.model}={meta_result.model}, "
                    f"I2={meta_result.i_squared:.1f}%, forest={rendered_forest is not None}, "
                    f"funnel={rendered_funnel is not None}",
                )
            else:
                _rc_print(rc, "  Meta-analysis: insufficient numeric effect data; using narrative synthesis.")

    synthesis_payload: dict = {
        "feasibility": feasibility.model_dump(),
        "narrative": narrative.model_dump(),
        "sparse_evidence_mode": state.sparse_evidence_mode,
    }
    if meta_result is not None:
        synthesis_payload["meta_analysis"] = meta_result.model_dump()

    Path(state.artifacts["narrative_synthesis"]).write_text(
        json.dumps(synthesis_payload, indent=2),
        encoding="utf-8",
    )
    async with get_db(state.db_path) as db:
        repository = WorkflowRepository(db)
        await repository.save_synthesis_result(state.workflow_id, feasibility, narrative)
        await repository.append_decision_log(
            DecisionLogEntry(
                decision_type="synthesis_summary",
                decision="completed",
                rationale=(
                    f"feasible={feasibility.feasible}, groups={len(feasibility.groupings)}, "
                    f"narrative_studies={narrative.n_studies}, "
                    f"meta_analysis={'yes' if meta_result else 'no'}, "
                    f"forest={'yes' if rendered_forest else 'no'}, "
                    f"funnel={'yes' if rendered_funnel else 'no'}"
                ),
                actor="workflow_run",
                phase="phase_5_synthesis",
            )
        )
        await repository.save_checkpoint(
            state.workflow_id,
            "phase_5_synthesis",
            papers_processed=len(state.extraction_records),
        )
    if rc:
        rc.emit_phase_done(
            "phase_5_synthesis",
            {
                "feasible": feasibility.feasible,
                "n_studies": len(state.extraction_records),
                "meta_analysis": meta_result is not None,
                "forest_plot": rendered_forest is not None,
                "funnel_plot": rendered_funnel is not None,
            },
        )
        if rc.debug:
            rc.emit_debug_state(
                "phase_5_synthesis",
                {"feasible": feasibility.feasible, "n_studies": len(state.extraction_records)},
            )
