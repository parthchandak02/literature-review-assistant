"""Runner for ScreeningNode – extracted from workflow.py lines 783-2015."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic_graph import End, GraphRunContext
from rich.table import Table

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.db.workflow_registry import (
    update_status as update_registry_status,
)
from src.llm.provider import LLMProvider
from src.manuscript.cohort import IncludedSetResolver
from src.models import (
    CandidatePaper,
    CohortMembershipRecord,
    DecisionLogEntry,
    GateStatus,
    WorkflowStepRecord,
)
from src.orchestration.context import RunContext
from src.orchestration.gates import GateRunner
from src.orchestration.helpers.runtime import llm_available as helper_llm_available
from src.orchestration.helpers.runtime import rc as helper_rc
from src.orchestration.helpers.runtime import rc_print as helper_rc_print
from src.orchestration.helpers.step_journal import journal_step_complete as helper_journal_step_complete
from src.orchestration.helpers.step_journal import journal_step_start as helper_journal_step_start
from src.orchestration.state import ReviewState
from src.screening.dual_screener import DualReviewerScreener
from src.screening.gemini_client import PydanticAIScreeningClient
from src.screening.keyword_filter import bm25_rank_and_cap, keyword_prefilter, metadata_prefilter
from src.screening.reliability import compute_cohens_kappa, log_reliability_to_decision_log
from src.search.citation_chasing import CitationChaser
from src.search.pdf_retrieval import PDFRetriever

_log = logging.getLogger(__name__)
logger = logging.getLogger(__name__)


def _rc(state: ReviewState) -> RunContext | None:
    return helper_rc(state)


def _rc_print(rc: RunContext | None, message: object) -> None:
    helper_rc_print(rc, message)


def _llm_available(settings=None, settings_cfg=None) -> bool:
    return helper_llm_available(settings=settings, settings_cfg=settings_cfg)


async def _journal_step_start(
    repo: WorkflowRepository,
    workflow_id: str,
    phase: str,
    step_name: str,
    *,
    paper_id: str | None = None,
    parent_step_id: str | None = None,
    max_attempts: int = 1,
) -> WorkflowStepRecord:
    return await helper_journal_step_start(
        repo,
        workflow_id,
        phase,
        step_name,
        paper_id=paper_id,
        parent_step_id=parent_step_id,
        max_attempts=max_attempts,
    )


async def _journal_step_complete(repo: WorkflowRepository, record: WorkflowStepRecord, **kwargs) -> None:
    await helper_journal_step_complete(repo, record, **kwargs)


async def run_screening_node(state: ReviewState, ctx: GraphRunContext[ReviewState]) -> End[dict] | None:
    rc = _rc(state)
    if rc:
        rc.emit_phase_start(
            "phase_3_screening",
            f"Screening {len(state.deduped_papers)} papers...",
            total=len(state.deduped_papers),
        )
        if rc.verbose:
            _rc_print(rc, "[dim]Press Ctrl+C once to proceed with partial results, twice to abort.[/]")
    assert state.review is not None
    assert state.settings is not None

    _screening_step: WorkflowStepRecord | None = None

    async with get_db(state.db_path) as db:
        repository = WorkflowRepository(db)
        _screening_step = await _journal_step_start(
            repository,
            state.workflow_id,
            "phase_3_screening",
            "screening_phase",
        )
        gate_runner = GateRunner(repository, state.settings)
        on_waiting = None
        on_resolved = None
        if rc:

            def _on_waiting(t: object, u: object, limit: object, waited: object = 0.0) -> None:
                rc.log_rate_limit_wait(t, u, limit, waited)  # type: ignore[union-attr]

            def _on_resolved(t: object, waited: object) -> None:
                rc.log_rate_limit_resolved(t, waited)  # type: ignore[union-attr]

            on_waiting = _on_waiting
            on_resolved = _on_resolved
        provider = LLMProvider(state.settings, repository, on_waiting=on_waiting, on_resolved=on_resolved)
        on_llm_call = None
        if rc and rc.verbose:

            def _on_llm_call(*args: object, **kwargs: object) -> None:
                """Accept both positional and keyword callback signatures safely."""
                source = kwargs.pop("source", args[0] if len(args) > 0 else "screening")
                status = kwargs.pop("status", args[1] if len(args) > 1 else "success")
                details = kwargs.pop("details", args[2] if len(args) > 2 else "")
                records = kwargs.pop("records", args[3] if len(args) > 3 else None)
                call_type = kwargs.pop("call_type", "llm_screening")
                rc.log_api_call(source, status, details, records, call_type=call_type, **kwargs)  # type: ignore[union-attr]

            on_llm_call = _on_llm_call
        use_real_client = _llm_available(settings_cfg=state.settings) and (rc is None or not rc.offline)
        llm_client = PydanticAIScreeningClient() if use_real_client else None
        on_progress = None
        if rc:

            def _on_progress(p: object, c: object, t: object) -> None:
                rc.advance_screening(p, c, t)  # type: ignore[union-attr]

            on_progress = _on_progress
        on_prompt = None
        if rc and rc.debug:

            def _on_prompt(a: object, p: object, pid: object) -> None:
                rc.log_prompt(a, p, pid)  # type: ignore[union-attr]

            on_prompt = _on_prompt
        should_proceed = (
            (lambda: rc.should_proceed_with_partial()) if rc and hasattr(rc, "should_proceed_with_partial") else None
        )
        on_screening_decision = None
        if rc and hasattr(rc, "log_screening_decision"):
            _papers_by_id = {p.paper_id: p for p in state.deduped_papers}
            _heuristic_prefixes = (
                "insufficient_content_heuristic",
                "protocol_only_heuristic",
                "fulltext_no_pdf_heuristic",
                "metadata_incomplete",
                "keyword_filter",
                "low_relevance_score",
                "batch_screened_low",
            )

            def _on_screening_decision(
                pid: object,
                stg: object,
                dec: object,
                reason: object = None,
                conf: float | None = None,
            ) -> None:
                _reason_str = str(reason) if reason is not None else None
                _method = (
                    "heuristic"
                    if _reason_str and any(_reason_str.startswith(p) for p in _heuristic_prefixes)
                    else "llm"
                )
                _paper = _papers_by_id.get(str(pid))
                _title = _paper.title if _paper else None
                rc.log_screening_decision(  # type: ignore[union-attr]
                    pid,
                    stg,
                    dec,
                    _reason_str,
                    conf,
                    title=_title,
                    method=_method,
                )

            on_screening_decision = _on_screening_decision
        _on_status = rc.log_status if rc and hasattr(rc, "log_status") else None
        screener = DualReviewerScreener(
            repository=repository,
            provider=provider,
            review=state.review,
            settings=state.settings,
            llm_client=llm_client,
            on_llm_call=on_llm_call,
            on_progress=on_progress,
            on_prompt=on_prompt,
            should_proceed_with_partial=should_proceed,
            on_screening_decision=on_screening_decision,
            on_status=_on_status,
        )

        # --- Gate 0: Metadata pre-filter (no LLM cost) ---
        meta_acceptable, meta_rejected = metadata_prefilter(state.deduped_papers)
        if meta_rejected:
            meta_rejected_papers = [
                p for p in state.deduped_papers if any(d.paper_id == p.paper_id for d in meta_rejected)
            ]
            await repository.bulk_save_screening_decisions(
                workflow_id=state.workflow_id,
                stage="title_abstract",
                papers=meta_rejected_papers,
                decisions=meta_rejected,
            )
            if rc and hasattr(rc, "log_status"):
                rc.log_status(
                    f"Metadata pre-filter: {len(meta_rejected)} rejected (missing title/abstract/year), "
                    f"{len(meta_acceptable)} forwarded."
                )
            if rc and hasattr(rc, "log_screening_decision"):
                _meta_paper_by_id = {p.paper_id: p for p in meta_rejected_papers}
                for _meta_decision in meta_rejected:
                    _meta_paper = _meta_paper_by_id.get(_meta_decision.paper_id)
                    rc.log_screening_decision(
                        _meta_decision.paper_id,
                        "title_abstract",
                        _meta_decision.decision.value,
                        "metadata_incomplete|missing required metadata fields",
                        _meta_decision.confidence,
                        title=_meta_paper.title if _meta_paper else None,
                        method="heuristic",
                    )

        # --- Pre-screening: BM25 ranking (when cap is set) or keyword filter ---
        cap = state.settings.screening.max_llm_screen
        bm25_validation_forwarded = 0
        bm25_validation_tail_ids: set[str] = set()
        bm25_overflow_candidates: list[CandidatePaper] = []
        paper_by_id = {p.paper_id: p for p in meta_acceptable}
        keyword_prefilter_excluded = 0
        keyword_prefilter_fallback_applied = False
        empty_abstract_pool = 0
        empty_abstract_excluded = 0
        empty_abstract_rescued = 0
        no_full_text_excluded = 0

        if cap is not None:
            kw_min = state.settings.screening.keyword_filter_min_matches
            kw_fallback_threshold = float(
                getattr(state.settings.screening, "keyword_prefilter_fallback_exclusion_ratio", 0.80)
            )
            kw_excluded, to_rank = keyword_prefilter(meta_acceptable, state.review, state.settings.screening)
            if kw_min > 0:
                _kw_only_exclusions = sum(
                    1
                    for d in kw_excluded
                    if getattr(getattr(d, "exclusion_reason", None), "value", "") == "keyword_filter"
                )
                keyword_prefilter_excluded = _kw_only_exclusions
                exclusion_ratio = _kw_only_exclusions / max(len(meta_acceptable), 1)
                if exclusion_ratio > kw_fallback_threshold:
                    keyword_prefilter_fallback_applied = True
                    if rc and hasattr(rc, "log_status"):
                        rc.log_status(
                            f"WARNING: Keyword pre-filter excluded {exclusion_ratio:.0%} of papers "
                            f"(threshold: {kw_fallback_threshold:.0%}). Config keyword list is too narrow -- "
                            f"falling back to BM25-only ranking for this run."
                        )
                    kw_excluded = [
                        d
                        for d in kw_excluded
                        if getattr(getattr(d, "exclusion_reason", None), "value", "") != "keyword_filter"
                    ]
                    excluded_ids = {d.paper_id for d in kw_excluded}
                    to_rank = [p for p in meta_acceptable if p.paper_id not in excluded_ids]

            # BM25 ranks keyword-accepted papers; top N go to LLM, tail auto-excluded.
            papers_for_llm, bm25_excluded = bm25_rank_and_cap(to_rank, state.review, state.settings.screening)
            if cap is not None:
                bm25_validation_forwarded = max(len(papers_for_llm) - min(cap, len(to_rank)), 0)
                if bm25_validation_forwarded > 0:
                    bm25_validation_tail_ids = {p.paper_id for p in papers_for_llm[-bm25_validation_forwarded:]}
            pre_excluded = kw_excluded + bm25_excluded
            bm25_overflow_candidates = [paper_by_id[d.paper_id] for d in bm25_excluded if d.paper_id in paper_by_id]

            if kw_excluded:
                await repository.bulk_save_screening_decisions(
                    workflow_id=state.workflow_id,
                    stage="title_abstract",
                    papers=[paper_by_id[d.paper_id] for d in kw_excluded if d.paper_id in paper_by_id],
                    decisions=kw_excluded,
                )
            if bm25_excluded:
                await repository.bulk_save_screening_decisions(
                    workflow_id=state.workflow_id,
                    stage="title_abstract",
                    papers=[paper_by_id[d.paper_id] for d in bm25_excluded if d.paper_id in paper_by_id],
                    decisions=bm25_excluded,
                )
            if rc and hasattr(rc, "log_status"):
                rc.log_status(
                    f"Keyword pre-filter: {len(kw_excluded)} auto-excluded. "
                    f"BM25 ranking: {len(to_rank)} scored, {len(papers_for_llm)} top-ranked to LLM "
                    f"(cap={cap}), "
                    f"{len(bm25_excluded)} auto-excluded (low relevance), "
                    f"{bm25_validation_forwarded} near-cutoff forwarded for validation."
                )
        else:
            # No cap set: keyword hard-gate -> all passers go to LLM.
            pre_excluded, papers_for_llm = keyword_prefilter(meta_acceptable, state.review, state.settings.screening)
            if pre_excluded:
                pre_excluded_papers = [paper_by_id[d.paper_id] for d in pre_excluded if d.paper_id in paper_by_id]
                await repository.bulk_save_screening_decisions(
                    workflow_id=state.workflow_id,
                    stage="title_abstract",
                    papers=pre_excluded_papers,
                    decisions=pre_excluded,
                )
                if rc and hasattr(rc, "log_status"):
                    rc.log_status(
                        f"Keyword pre-filter: {len(pre_excluded)} auto-excluded, "
                        f"{len(papers_for_llm)} forwarded to LLM screening."
                    )

        if pre_excluded and rc and hasattr(rc, "log_screening_decision"):
            for _pref_decision in pre_excluded:
                _reason = getattr(getattr(_pref_decision, "exclusion_reason", None), "value", "other")
                _paper = paper_by_id.get(_pref_decision.paper_id)
                rc.log_screening_decision(
                    _pref_decision.paper_id,
                    "title_abstract",
                    _pref_decision.decision.value,
                    f"{_reason}|automation pre-filter exclusion",
                    _pref_decision.confidence,
                    title=_paper.title if _paper else None,
                    method="heuristic",
                )

        # Emit structured prefilter summary so the frontend can render the full
        # paper funnel (deduped -> after metadata -> to LLM) for both live and
        # historical runs.
        if rc and hasattr(rc, "_emit"):
            import datetime as _dt_pf
            import random as _random

            _prefilter_reason_breakdown: dict[str, int] = {}
            for _d in pre_excluded:
                _raw = getattr(getattr(_d, "exclusion_reason", None), "value", None)
                if _raw is None:
                    _raw = "other"
                _prefilter_reason_breakdown[str(_raw)] = _prefilter_reason_breakdown.get(str(_raw), 0) + 1
            _empty_abstract_pool = sum(1 for p in meta_acceptable if not (p.abstract or "").strip())
            _empty_abstract_excluded = sum(
                1
                for d in pre_excluded
                if (
                    getattr(getattr(d, "exclusion_reason", None), "value", "") == "insufficient_data"
                    and "empty abstract" in str(getattr(d, "reason", "")).lower()
                )
            )
            _empty_abstract_rescued = max(_empty_abstract_pool - _empty_abstract_excluded, 0)
            empty_abstract_pool = _empty_abstract_pool
            empty_abstract_excluded = _empty_abstract_excluded
            empty_abstract_rescued = _empty_abstract_rescued
            rc._emit(
                {
                    "type": "screening_prefilter_done",
                    "deduped": len(state.deduped_papers),
                    "metadata_rejected": len(meta_rejected),
                    "after_metadata": len(meta_acceptable),
                    "automation_excluded": len(pre_excluded),
                    "to_llm": len(papers_for_llm),
                    "dual_review_cap": cap,
                    "bm25_validation_forwarded": bm25_validation_forwarded,
                    "keyword_filter_excluded": keyword_prefilter_excluded,
                    "keyword_fallback_applied": keyword_prefilter_fallback_applied,
                    "keyword_fallback_threshold": kw_fallback_threshold,
                    "empty_abstract_pool": _empty_abstract_pool,
                    "empty_abstract_excluded": _empty_abstract_excluded,
                    "empty_abstract_rescued": _empty_abstract_rescued,
                    "reason_breakdown": _prefilter_reason_breakdown,
                    "action": "skipped",
                    "entity_type": "phase",
                    "entity_id": "phase_3_screening",
                    "reason_code": "prefilter_applied",
                    "reason_label": "Automated pre-screening exclusions applied",
                    "ts": _dt_pf.datetime.utcnow().isoformat(),
                }
            )
            _qa_reasons = {
                "insufficient_data",
                "wrong_study_design",
                "protocol_only",
            }
            _deterministic_decisions = [
                d
                for d in pre_excluded
                if str(getattr(getattr(d, "exclusion_reason", None), "value", "other")) in _qa_reasons
            ]
            _qa_n = min(
                max(getattr(state.settings.screening, "deterministic_exclude_qa_sample_size", 0), 0),
                len(_deterministic_decisions),
            )
            if _qa_n > 0:
                _sampled = _random.sample(_deterministic_decisions, _qa_n)
                _qa_rows: list[dict[str, str]] = []
                for _d in _sampled:
                    _p = paper_by_id.get(_d.paper_id)
                    _qa_rows.append(
                        {
                            "paper_id": _d.paper_id,
                            "reason_code": str(getattr(getattr(_d, "exclusion_reason", None), "value", "other")),
                            "title": (_p.title if _p else ""),
                        }
                    )
                rc._emit(
                    {
                        "type": "deterministic_exclusion_qa_sample",
                        "sample_size": _qa_n,
                        "pool_size": len(_deterministic_decisions),
                        "items": _qa_rows,
                        "action": "needs_review",
                        "entity_type": "phase",
                        "entity_id": "phase_3_screening",
                        "ts": _dt_pf.datetime.utcnow().isoformat(),
                    }
                )

        # --- Adaptive threshold calibration (optional) ---
        screening_cfg = state.settings.screening
        _already_decided_ids = await repository.get_processed_paper_ids(state.workflow_id, "title_abstract")
        _is_screening_resume = len(_already_decided_ids) > 0
        if (
            not _is_screening_resume
            and getattr(screening_cfg, "calibrate_threshold", True)
            and papers_for_llm
            and use_real_client
            and not state.parent_db_path  # skip for living-refresh delta runs
        ):
            from src.screening.reliability import calibrate_threshold as _calibrate_threshold

            _calib_sample_size = getattr(screening_cfg, "calibration_sample_size", 30)
            _calib_max_iter = getattr(screening_cfg, "calibration_max_iterations", 3)
            _calib_total = min(_calib_sample_size, len(papers_for_llm)) * _calib_max_iter

            if rc:
                rc.emit_phase_start(
                    "screening_calibration",
                    description=(
                        f"Calibrating screening thresholds ({_calib_sample_size} papers, "
                        f"up to {_calib_max_iter} iterations)..."
                    ),
                    total=_calib_total,
                )

            _calib_completed: list[int] = [0]

            def _calib_on_progress(phase: object, current: object, total: object) -> None:
                _calib_completed[0] += 1
                if rc:
                    rc.advance_screening("screening_calibration", _calib_completed[0], _calib_total)

            async def _calibration_screener(
                sample_papers: list[CandidatePaper],
                threshold: float,
            ) -> list:
                original_include = getattr(screener.settings.screening, "stage1_include_threshold", 0.85)
                exclude_margin = float(getattr(screening_cfg, "calibration_exclude_margin", 0.05))
                try:
                    screener.settings.screening.stage1_include_threshold = threshold
                    screener.settings.screening.stage1_exclude_threshold = max(0.0, threshold - exclude_margin)
                    results = await screener.screen_batch_for_calibration(
                        workflow_id=f"{state.workflow_id}_calib",
                        papers=sample_papers,
                        on_progress=_calib_on_progress,
                    )
                    return list(results)
                finally:
                    screener.settings.screening.stage1_include_threshold = original_include
                    screener.settings.screening.stage1_exclude_threshold = max(0.0, original_include - exclude_margin)

            try:
                calibrated = await _calibrate_threshold(
                    papers=papers_for_llm,
                    screener_fn=_calibration_screener,
                    target_kappa=getattr(screening_cfg, "calibration_target_kappa", 0.7),
                    max_iterations=_calib_max_iter,
                    sample_size=_calib_sample_size,
                    initial_include_threshold=screening_cfg.stage1_include_threshold,
                )
                screening_cfg.stage1_include_threshold = calibrated.include_threshold
                screening_cfg.stage1_exclude_threshold = calibrated.exclude_threshold
                logger.info(
                    "Screening calibration: threshold adjusted to %.3f (kappa=%.4f, %d iter)",
                    calibrated.include_threshold,
                    calibrated.achieved_kappa,
                    calibrated.iterations,
                )
                if rc:
                    rc.emit_phase_done(
                        "screening_calibration",
                        summary={
                            "include_threshold": calibrated.include_threshold,
                            "exclude_threshold": calibrated.exclude_threshold,
                            "kappa": calibrated.achieved_kappa,
                            "iterations": calibrated.iterations,
                            "sample_size": calibrated.sample_size,
                        },
                    )
                    rc._emit(
                        {
                            "type": "screening_calibration",
                            "include_threshold": calibrated.include_threshold,
                            "exclude_threshold": calibrated.exclude_threshold,
                            "kappa": calibrated.achieved_kappa,
                            "iterations": calibrated.iterations,
                            "sample_size": calibrated.sample_size,
                        }
                    )
                await repository.save_screening_metric(
                    state.workflow_id,
                    "calibration_include_threshold",
                    calibrated.include_threshold,
                    phase="screening_calibration",
                )
                await repository.save_screening_metric(
                    state.workflow_id,
                    "calibration_kappa",
                    calibrated.achieved_kappa,
                    phase="screening_calibration",
                )
            except Exception as _cal_err:
                logger.warning("Screening calibration failed (%s) -- using default thresholds", _cal_err)
                if rc:
                    rc.emit_phase_done(
                        "screening_calibration",
                        summary={"error": str(_cal_err), "using_defaults": True},
                    )

        # --- Batch LLM pre-ranker (optional) ---
        state.batch_screen_threshold = float(getattr(screening_cfg, "batch_screen_threshold", 0.20))
        if getattr(screening_cfg, "batch_screen_enabled", True) and papers_for_llm and use_real_client:
            from src.screening.batch_ranker import BatchLLMRanker, PydanticAIBatchRankerClient

            _batch_agent_key = "batch_screener"
            _batch_agent = state.settings.agents.get(
                _batch_agent_key,
                state.settings.agents.get("screening_reviewer_a"),
            )
            if _batch_agent is None:
                logger.warning(
                    "ScreeningNode: 'batch_screener' agent not found in settings.yaml; skipping batch pre-ranker."
                )
            else:
                _already_screened = await repository.get_processed_paper_ids(state.workflow_id, "title_abstract")
                _papers_for_batch = [p for p in papers_for_llm if p.paper_id not in _already_screened]

                _batch_forwarded: list[CandidatePaper] = []
                _batch_excluded_decisions: list = []

                if _papers_for_batch:
                    _br = BatchLLMRanker(
                        screening=screening_cfg,
                        model=_batch_agent.model,
                        temperature=_batch_agent.temperature,
                        research_question=state.review.research_question,
                        topic_focus=state.review.expert_topic(),
                        domain=state.review.domain,
                        population=state.review.pico.population,
                        intervention=state.review.pico.intervention,
                        outcome=state.review.pico.outcome,
                        keywords=state.review.keywords,
                        expert_terms=state.review.domain_signal_terms(limit=12),
                        anchor_terms=state.review.intervention_anchor_terms(limit=10),
                        related_terms=state.review.related_context_terms(limit=10),
                        excluded_terms=state.review.discouraged_terminology(),
                        client=PydanticAIBatchRankerClient(),
                        on_status=_on_status,
                        provider=provider,
                        workflow_id=state.workflow_id,
                        reserve_agent=_batch_agent_key
                        if _batch_agent_key in state.settings.agents
                        else "screening_reviewer_a",
                    )
                    _batch_forwarded, _batch_excluded_decisions = await _br.rank_and_split(_papers_for_batch)
                    state.batch_screener_model = _batch_agent.model
                    state.batch_screen_threshold = screening_cfg.batch_screen_threshold
                    state.batch_screen_validation_n = _br.validation_sampled_n
                    state.batch_screen_validation_npv = _br.validation_npv
                    state.batch_screen_borderline_forwarded = _br.borderline_forwarded_n

                    if _batch_excluded_decisions:
                        _batch_excl_papers = [
                            paper_by_id[d.paper_id] for d in _batch_excluded_decisions if d.paper_id in paper_by_id
                        ]
                        await repository.bulk_save_screening_decisions(
                            workflow_id=state.workflow_id,
                            stage="title_abstract",
                            papers=_batch_excl_papers,
                            decisions=_batch_excluded_decisions,
                        )
                else:
                    logger.info(
                        "ScreeningNode: all %d papers already processed; skipping batch pre-ranker on resume.",
                        len(papers_for_llm),
                    )

                import datetime as _dt_bs

                _batch_n_scored = len(_papers_for_batch)
                _batch_n_excl = len(_batch_excluded_decisions)
                _batch_n_fwd = len(_batch_forwarded)
                _batch_n_borderline = int(getattr(state, "batch_screen_borderline_forwarded", 0))
                _batch_n_skip = len(_already_screened.intersection({p.paper_id for p in papers_for_llm}))
                if _batch_n_fwd > 0 or state.batch_screen_forwarded == 0:
                    state.batch_screen_forwarded = _batch_n_fwd
                    state.batch_screen_excluded = _batch_n_excl
                if rc and hasattr(rc, "_emit"):
                    rc._emit(
                        {
                            "type": "batch_screen_done",
                            "scored": _batch_n_scored,
                            "forwarded": _batch_n_fwd,
                            "excluded": _batch_n_excl,
                            "borderline_forwarded": _batch_n_borderline,
                            "skipped_resume": _batch_n_skip,
                            "threshold": screening_cfg.batch_screen_threshold,
                            "action": "skipped" if _batch_n_excl > 0 else "included",
                            "entity_type": "phase",
                            "entity_id": "phase_3_screening",
                            "reason_code": "batch_screened_low" if _batch_n_excl > 0 else None,
                            "reason_label": (
                                "Auto-excluded by batch pre-ranker score threshold" if _batch_n_excl > 0 else None
                            ),
                            "ts": _dt_bs.datetime.utcnow().isoformat(),
                        }
                    )

                if rc and hasattr(rc, "log_status"):
                    rc.log_status(
                        f"Batch LLM pre-ranker: {_batch_n_scored} scored in "
                        f"{(_batch_n_scored + screening_cfg.batch_screen_size - 1) // max(screening_cfg.batch_screen_size, 1)} "
                        f"batches, {_batch_n_fwd} forwarded to dual-reviewer, "
                        f"{_batch_n_borderline} forwarded by uncertain band, "
                        f"{_batch_n_excl} auto-excluded "
                        f"(score < {screening_cfg.batch_screen_threshold:.2f})"
                        + (f", {_batch_n_skip} skipped (resume)." if _batch_n_skip else ".")
                    )

                # Cap safety valve
                _overflow_cfg = state.settings.screening
                _overflow_enabled = bool(getattr(_overflow_cfg, "cap_overflow_enabled", False))
                _overflow_trigger = float(getattr(_overflow_cfg, "cap_overflow_trigger_include_rate", 0.20))
                _overflow_min_n = int(getattr(_overflow_cfg, "cap_overflow_min_validation_n", 10))
                _overflow_slice = int(getattr(_overflow_cfg, "cap_overflow_slice_size", 25))
                _overflow_max = int(getattr(_overflow_cfg, "cap_overflow_max_extra", 50))
                _validation_tail_n = len(bm25_validation_tail_ids)
                _validation_tail_forwarded = sum(1 for p in _batch_forwarded if p.paper_id in bm25_validation_tail_ids)
                _validation_tail_rate = (
                    (_validation_tail_forwarded / _validation_tail_n) if _validation_tail_n > 0 else 0.0
                )
                _overflow_candidates = [p for p in bm25_overflow_candidates if p.paper_id not in _already_screened]
                _overflow_take = 0
                _overflow_forwarded_n = 0
                if (
                    _overflow_enabled
                    and _papers_for_batch
                    and _validation_tail_n >= _overflow_min_n
                    and _validation_tail_rate >= _overflow_trigger
                    and _overflow_candidates
                ):
                    _overflow_take = min(_overflow_slice, _overflow_max, len(_overflow_candidates))
                    _overflow_batch = _overflow_candidates[:_overflow_take]
                    if rc and hasattr(rc, "log_status"):
                        rc.log_status(
                            f"Cap safety valve triggered: validation-tail forward rate "
                            f"{_validation_tail_rate:.1%} >= {_overflow_trigger:.1%}. "
                            f"Evaluating +{_overflow_take} near-cutoff papers."
                        )
                    _overflow_forwarded, _overflow_excluded = await _br.rank_and_split(_overflow_batch)
                    _overflow_forwarded_n = len(_overflow_forwarded)
                    if _overflow_excluded:
                        _overflow_excl_papers = [
                            paper_by_id[d.paper_id] for d in _overflow_excluded if d.paper_id in paper_by_id
                        ]
                        await repository.bulk_save_screening_decisions(
                            workflow_id=state.workflow_id,
                            stage="title_abstract",
                            papers=_overflow_excl_papers,
                            decisions=_overflow_excluded,
                        )
                    _batch_forwarded = _batch_forwarded + _overflow_forwarded
                    state.batch_screen_forwarded = state.batch_screen_forwarded + _overflow_forwarded_n
                    if rc and hasattr(rc, "_emit"):
                        rc._emit(
                            {
                                "type": "screening_cap_overflow",
                                "trigger": "validation_tail_yield",
                                "validation_tail_n": _validation_tail_n,
                                "validation_tail_forwarded": _validation_tail_forwarded,
                                "validation_tail_forward_rate": _validation_tail_rate,
                                "trigger_threshold": _overflow_trigger,
                                "overflow_candidates": len(_overflow_candidates),
                                "overflow_evaluated": _overflow_take,
                                "overflow_forwarded": _overflow_forwarded_n,
                                "action": "included" if _overflow_forwarded_n > 0 else "skipped",
                                "entity_type": "phase",
                                "entity_id": "phase_3_screening",
                                "reason_code": "cap_overflow_validation_tail",
                                "reason_label": "Cap safety valve overflow slice evaluated",
                                "ts": _dt_bs.datetime.utcnow().isoformat(),
                            }
                        )
                    if rc and hasattr(rc, "log_status"):
                        rc.log_status(
                            f"Cap safety valve result: {_overflow_forwarded_n}/{_overflow_take} "
                            f"overflow candidates forwarded to dual-reviewer."
                        )

                papers_for_llm = _batch_forwarded

        # --- Stage 1: title/abstract LLM dual-review ---
        stage1_llm = await screener.screen_batch(
            workflow_id=state.workflow_id,
            stage="title_abstract",
            papers=papers_for_llm,
        )
        all_stage1 = list(pre_excluded) + list(stage1_llm)
        include_ids = {d.paper_id for d in all_stage1 if d.decision.value in ("include", "uncertain")}
        prior_ta_includes = await repository.get_title_abstract_include_ids(state.workflow_id)
        include_ids.update(prior_ta_includes)
        stage1_survivors = [p for p in meta_acceptable if p.paper_id in include_ids]

        # --- Intermediate checkpoint guard for fulltext PDF retrieval + LLM ---
        _existing_cps = await repository.get_checkpoints(state.workflow_id)
        if "phase_3b_fulltext" in _existing_cps:
            state.fulltext_sought = len(stage1_survivors)
            if rc and hasattr(rc, "log_status"):
                rc.log_status(
                    f"Skipping fulltext PDF retrieval and LLM screening "
                    f"(phase_3b_fulltext checkpoint found; "
                    f"{len(state.included_papers)} papers included from prior run)."
                )
        else:
            # --- Reset interrupt flag so stage 2 always runs to completion ---
            screener.reset_partial_flag()

            # --- Stage 2: full-text screening ---
            if rc:
                rc.emit_phase_start(
                    "fulltext_pdf_retrieval",
                    f"Fetching full text for {len(stage1_survivors)} papers...",
                    total=len(stage1_survivors),
                )

            def _pdf_progress(done: int, total: int) -> None:
                if rc:
                    rc.advance_screening("fulltext_pdf_retrieval", done, total)

            def _on_pdf_result(
                paper_id: str,
                title: str,
                source: str,
                success: bool,
                reason_code: str | None,
            ) -> None:
                if rc:
                    rc.log_pdf_result(paper_id, title, source, success, reason_code=reason_code)

            stage2 = await screener.screen_batch(
                workflow_id=state.workflow_id,
                stage="fulltext",
                papers=stage1_survivors,
                full_text_by_paper=None,
                retriever=PDFRetriever(extraction_config=state.settings.extraction),
                coverage_report_path=state.artifacts["coverage_report"],
                on_pdf_progress=_pdf_progress if rc else None,
                on_pdf_result=_on_pdf_result if rc else None,
            )

            if rc:
                rc.emit_phase_done(
                    "fulltext_pdf_retrieval",
                    {"fetched": len(stage1_survivors)},
                )
            from src.models.enums import ExclusionReason as _ExclusionReason

            state.fulltext_sought = len(stage1_survivors)
            _ft_coverage = getattr(screener, "last_fulltext_coverage", None)
            if _ft_coverage is not None:
                state.fulltext_not_retrieved = _ft_coverage.failed
            else:
                state.fulltext_not_retrieved = sum(
                    1 for d in stage2 if getattr(d, "exclusion_reason", None) == _ExclusionReason.NO_FULL_TEXT
                )
            no_full_text_excluded = sum(
                1 for d in stage2 if getattr(d, "exclusion_reason", None) == _ExclusionReason.NO_FULL_TEXT
            )
            if stage1_survivors and not stage2:
                _ft_processed = await repository.get_processed_paper_ids(state.workflow_id, "fulltext")
                if _ft_processed:
                    _ft_included_ids = await repository.get_included_paper_ids(state.workflow_id)
                    state.included_papers = [p for p in stage1_survivors if p.paper_id in _ft_included_ids]
                    await repository.append_decision_log(
                        DecisionLogEntry(
                            decision_type="screening_stage2_resume",
                            decision="info",
                            rationale=(
                                f"Stage 2 returned 0 new decisions for {len(stage1_survivors)} "
                                f"stage-1 survivors; {len(_ft_processed)} fulltext decisions "
                                f"already in DB from prior run. Loaded {len(state.included_papers)} "
                                f"included papers from persisted decisions."
                            ),
                            actor="workflow_run",
                            phase="phase_3_screening",
                        )
                    )
                else:
                    await repository.append_decision_log(
                        DecisionLogEntry(
                            decision_type="screening_stage2_fallback",
                            decision="warning",
                            rationale=(
                                f"Stage 2 returned 0 decisions for {len(stage1_survivors)} "
                                f"stage-1 survivors; treating stage-1 include decisions as final."
                            ),
                            actor="workflow_run",
                            phase="phase_3_screening",
                        )
                    )
                    state.included_papers = list(stage1_survivors)
            else:
                include_ids = {d.paper_id for d in stage2 if d.decision.value in ("include", "uncertain")}
                state.included_papers = [p for p in stage1_survivors if p.paper_id in include_ids]

            # Persist canonical screening cohort membership for downstream parity checks.
            _screening_resolver = IncludedSetResolver(repository, state.workflow_id)
            _included_ids = {p.paper_id for p in state.included_papers}
            _fulltext_final = await repository.get_fulltext_final_decisions(state.workflow_id)
            _not_retrieved_ids = await repository.get_fulltext_not_retrieved_ids(state.workflow_id)
            await repository.bulk_upsert_cohort_memberships(
                [
                    CohortMembershipRecord(
                        workflow_id=state.workflow_id,
                        paper_id=p.paper_id,
                        screening_status=(
                            "included"
                            if _fulltext_final.get(p.paper_id) in {"include", "uncertain"}
                            or p.paper_id in _included_ids
                            else "excluded"
                        ),
                        fulltext_status=(
                            "not_retrieved"
                            if p.paper_id in _not_retrieved_ids
                            else ("assessed" if p.paper_id in _fulltext_final else "unknown")
                        ),
                        synthesis_eligibility=(
                            "pending"
                            if _fulltext_final.get(p.paper_id) in {"include", "uncertain"}
                            or p.paper_id in _included_ids
                            else "excluded_screening"
                        ),
                        exclusion_reason_code=(
                            None
                            if _fulltext_final.get(p.paper_id) in {"include", "uncertain"}
                            or p.paper_id in _included_ids
                            else ("no_full_text" if p.paper_id in _not_retrieved_ids else "screening_excluded")
                        ),
                        source_phase="phase_3_screening",
                    )
                    for p in stage1_survivors
                ]
            )

            # Save intermediate checkpoint
            await repository.save_checkpoint(
                state.workflow_id,
                "phase_3b_fulltext",
                papers_processed=len(state.included_papers),
            )

        pre_filter_method = "bm25_rank_and_cap" if cap is not None else "keyword_prefilter"
        await repository.append_decision_log(
            DecisionLogEntry(
                decision_type="screening_summary",
                decision="completed",
                rationale=(
                    f"pre_filter_method={pre_filter_method}, "
                    f"pre_filtered={len(pre_excluded)}, "
                    f"title_abstract_llm={len(stage1_llm)}, "
                    f"fulltext_total={len(stage2)}, "
                    f"included={len(state.included_papers)}"
                ),
                actor="workflow_run",
                phase="phase_3_screening",
            )
        )
        # -- Compute Cohen's kappa from dual-review pairs (where both reviewers ran) --
        if screener._dual_results:
            reliability = compute_cohens_kappa(screener._dual_results, stage="title_abstract")
            state.cohens_kappa = reliability.cohens_kappa
            state.kappa_stage = reliability.stage
            state.kappa_n = len(screener._dual_results)
            await log_reliability_to_decision_log(repository, reliability)

        # Persist screening QA counters for auditability and run-to-run comparison.
        await repository.save_screening_metric(
            state.workflow_id,
            "bm25_validation_forwarded",
            bm25_validation_forwarded,
        )
        await repository.save_screening_metric(
            state.workflow_id,
            "prefilter_metadata_rejected",
            len(meta_rejected),
        )
        await repository.save_screening_metric(
            state.workflow_id,
            "prefilter_automation_excluded",
            len(pre_excluded),
        )
        await repository.save_screening_metric(
            state.workflow_id,
            "prefilter_to_llm",
            len(papers_for_llm),
        )
        await repository.save_screening_metric(
            state.workflow_id,
            "keyword_filter_excluded",
            keyword_prefilter_excluded,
        )
        await repository.save_screening_metric(
            state.workflow_id,
            "keyword_fallback_applied",
            int(keyword_prefilter_fallback_applied),
        )
        await repository.save_screening_metric(
            state.workflow_id,
            "empty_abstract_pool",
            empty_abstract_pool,
        )
        await repository.save_screening_metric(
            state.workflow_id,
            "empty_abstract_excluded",
            empty_abstract_excluded,
        )
        await repository.save_screening_metric(
            state.workflow_id,
            "empty_abstract_rescued",
            empty_abstract_rescued,
        )
        await repository.save_screening_metric(
            state.workflow_id,
            "batch_borderline_forwarded",
            state.batch_screen_borderline_forwarded,
        )
        await repository.save_screening_metric(
            state.workflow_id,
            "title_abstract_fast_path_include",
            getattr(screener, "fast_path_include_count", 0),
        )
        await repository.save_screening_metric(
            state.workflow_id,
            "title_abstract_fast_path_exclude",
            getattr(screener, "fast_path_exclude_count", 0),
        )
        await repository.save_screening_metric(
            state.workflow_id,
            "title_abstract_cross_reviewed",
            getattr(screener, "cross_review_count", 0),
        )
        await repository.save_screening_metric(
            state.workflow_id,
            "batch_parse_degraded",
            getattr(screener, "batch_parse_degraded_count", 0),
        )
        await repository.save_screening_metric(
            state.workflow_id,
            "batch_id_mismatch",
            getattr(screener, "batch_id_mismatch_count", 0),
        )
        await repository.save_screening_metric(
            state.workflow_id,
            "batch_missing_fallback",
            getattr(screener, "batch_missing_fallback_count", 0),
        )
        await repository.save_screening_metric(
            state.workflow_id,
            "contract_violation_count",
            getattr(screener, "contract_violation_count", 0),
        )
        await repository.save_screening_metric(
            state.workflow_id,
            "fulltext_sought",
            getattr(state, "fulltext_sought", 0),
        )
        await repository.save_screening_metric(
            state.workflow_id,
            "fulltext_not_retrieved",
            getattr(state, "fulltext_not_retrieved", 0),
        )
        await repository.save_screening_metric(
            state.workflow_id,
            "fulltext_no_full_text_excluded",
            no_full_text_excluded,
        )

        # -- Forward citation chasing (PRISMA 2020 snowball supplement) --
        _citation_chasing = state.settings.search.citation_chasing_enabled if state.settings else False
        if state.included_papers and _citation_chasing:
            if rc:
                rc.emit_phase_start(
                    "citation_chasing",
                    f"Following citations for {len(state.included_papers)} included papers...",
                    total=len(state.included_papers),
                )
            try:
                import asyncio

                known_dois = {p.doi for p in state.deduped_papers if p.doi}
                chaser = CitationChaser(workflow_id=state.workflow_id)
                if rc and hasattr(rc, "log_status"):
                    rc.log_status(
                        f"Citation chasing: querying forward citations for {len(state.included_papers)} papers..."
                    )
                _chase_concurrency = getattr(getattr(state.settings, "search", None), "citation_chasing_concurrency", 5)
                chased_results = await chaser.chase_citations_to_search_results(
                    state.included_papers, known_dois, concurrency=_chase_concurrency
                )
                if chased_results:
                    await asyncio.gather(*[repository.save_search_result(sr) for sr in chased_results])
                    new_papers = [p for sr in chased_results for p in sr.papers]
                    if rc and hasattr(rc, "log_status"):
                        rc.log_status(f"Citation chasing: screening {len(new_papers)} newly discovered papers...")
                    rc.advance_screening("citation_chasing", 1, 3) if rc else None
                    chased_included: list[CandidatePaper] = []
                    if new_papers:
                        chased_ta = await screener.screen_batch(
                            workflow_id=state.workflow_id,
                            stage="title_abstract",
                            papers=new_papers,
                        )
                        chased_ta_include_ids = {
                            d.paper_id for d in chased_ta if d.decision.value in ("include", "uncertain")
                        }
                        chased_ta_survivors = [p for p in new_papers if p.paper_id in chased_ta_include_ids]
                        rc.advance_screening("citation_chasing", 2, 3) if rc else None
                        if chased_ta_survivors:
                            if rc and hasattr(rc, "log_status"):
                                rc.log_status(
                                    f"Citation chasing: fetching full text for {len(chased_ta_survivors)} survivors..."
                                )

                            def _chased_pdf_progress(done: int, total: int) -> None:
                                if rc:
                                    rc.log_status(f"Citation chasing: PDF retrieval {done}/{total}...")

                            chased_ft = await screener.screen_batch(
                                workflow_id=state.workflow_id,
                                stage="fulltext",
                                papers=chased_ta_survivors,
                                full_text_by_paper=None,
                                retriever=PDFRetriever(extraction_config=state.settings.extraction),
                                coverage_report_path=state.artifacts["coverage_report"],
                                on_pdf_progress=_chased_pdf_progress if rc else None,
                            )
                            chased_ft_include_ids = {
                                d.paper_id for d in chased_ft if d.decision.value in ("include", "uncertain")
                            }
                            chased_included = [p for p in chased_ta_survivors if p.paper_id in chased_ft_include_ids]
                            for _p in chased_ta_survivors:
                                await _screening_resolver.persist_screening_outcome(
                                    _p.paper_id,
                                    fulltext_decision=(
                                        "include" if _p.paper_id in chased_ft_include_ids else "exclude"
                                    ),
                                    source_phase="phase_3_screening_citation_chasing",
                                )
                    state.deduped_papers = state.deduped_papers + new_papers
                    state.included_papers = state.included_papers + chased_included
                    rc.advance_screening("citation_chasing", 3, 3) if rc else None
                    if rc:
                        rc.emit_phase_done(
                            "citation_chasing",
                            {
                                "new_papers": len(new_papers),
                                "chased_included": len(chased_included),
                            },
                        )
                else:
                    if rc:
                        rc.emit_phase_done("citation_chasing", {"new_papers": 0})
            except Exception as _cc_exc:
                logger.warning("Citation chasing failed: %s", _cc_exc)
                if rc:
                    rc.emit_phase_done("citation_chasing", {"new_papers": 0, "error": str(_cc_exc)})

        if rc and hasattr(rc, "log_status"):
            rc.log_status(f"Running screening safeguard gate on {len(state.included_papers)} included papers...")
        async with get_db(state.db_path) as _gate_db:
            _gate_repository = WorkflowRepository(_gate_db)
            _gate_runner = GateRunner(_gate_repository, state.settings)
            gr = await _gate_runner.run_screening_safeguard_gate(
                workflow_id=state.workflow_id,
                phase="phase_3_screening",
                passed_screening=len(state.included_papers),
            )
        state.sparse_evidence_mode = gr.status == GateStatus.WARNING
        if rc and hasattr(rc, "log_status"):
            rc.log_status(
                f"Screening safeguard gate recorded as {gr.status.value} "
                f"(actual={gr.actual_value}, threshold={gr.threshold})."
            )
        if state.sparse_evidence_mode and rc:
            rc.log_status(
                "Screening safeguard: sparse-evidence continuation mode active "
                f"({len(state.included_papers)} included; minimum {gr.threshold})."
            )
        if state.settings.gates.profile == "strict":
            if gr and gr.status == GateStatus.FAILED:
                err_msg = (
                    f"Screening safeguard gate failed: {gr.actual_value or 0} studies "
                    f"included (minimum {gr.threshold or '?'}). Cannot proceed."
                )
                summary = {
                    "workflow_id": state.workflow_id,
                    "status": "failed",
                    "error": err_msg,
                    "gate": "screening_safeguard",
                    "phase": "phase_3_screening",
                }
                Path(state.artifacts["run_summary"]).write_text(json.dumps(summary, indent=2), encoding="utf-8")
                await repository.update_workflow_status(state.workflow_id, "failed")
                await update_registry_status(state.run_root, state.workflow_id, "failed")
                if rc:
                    rc.emit_phase_done(
                        "phase_3_screening",
                        {"error": err_msg, "included": len(state.included_papers)},
                    )
                return End(summary)

        checkpoint_status = "partial" if (rc and rc.should_proceed_with_partial()) else "completed"
        await repository.save_checkpoint(
            state.workflow_id,
            "phase_3_screening",
            papers_processed=len(state.included_papers),
            status=checkpoint_status,
        )
        if rc and rc.verbose:
            summary_rows = await repository.get_screening_summary(state.workflow_id)
            if summary_rows:
                table = Table(title="Screening Summary")
                table.add_column("Paper ID", style="dim")
                table.add_column("Stage", style="cyan")
                table.add_column("Decision", style="bold")
                table.add_column("Reason", style="white")
                for paper_id, stage, decision, rationale in summary_rows:
                    table.add_row(paper_id[:16] + "...", stage, decision, rationale)
                _rc_print(rc, table)
    if rc:
        if hasattr(rc, "log_status"):
            rc.log_status(
                f"Saving checkpoint... {len(state.included_papers)} papers included of {len(state.deduped_papers)} screened."
            )
        _stage2_local = locals().get("stage2", [])
        _screening_reason_breakdown: dict[str, int] = {}
        for _decision in list(pre_excluded) + list(_stage2_local):
            _reason_value = getattr(getattr(_decision, "exclusion_reason", None), "value", None)
            if not _reason_value:
                continue
            _screening_reason_breakdown[str(_reason_value)] = _screening_reason_breakdown.get(str(_reason_value), 0) + 1
        rc.emit_phase_done(
            "phase_3_screening",
            {
                "included": len(state.included_papers),
                "screened": len(state.deduped_papers),
                "kappa": state.cohens_kappa,
                "excluded": max(len(state.deduped_papers) - len(state.included_papers), 0),
                "reason_breakdown": _screening_reason_breakdown,
                "bm25_validation_forwarded": bm25_validation_forwarded,
                "batch_borderline_forwarded": state.batch_screen_borderline_forwarded,
                "fast_path_include": getattr(screener, "fast_path_include_count", 0),
                "fast_path_exclude": getattr(screener, "fast_path_exclude_count", 0),
                "cross_reviewed": getattr(screener, "cross_review_count", 0),
                "batch_parse_degraded": getattr(screener, "batch_parse_degraded_count", 0),
                "batch_id_mismatch": getattr(screener, "batch_id_mismatch_count", 0),
                "batch_missing_fallback": getattr(screener, "batch_missing_fallback_count", 0),
                "contract_violation_count": getattr(screener, "contract_violation_count", 0),
                "keyword_filter_excluded": keyword_prefilter_excluded,
                "keyword_fallback_applied": keyword_prefilter_fallback_applied,
                "empty_abstract_excluded": empty_abstract_excluded,
                "empty_abstract_rescued": empty_abstract_rescued,
                "fulltext_sought": getattr(state, "fulltext_sought", 0),
                "fulltext_not_retrieved": getattr(state, "fulltext_not_retrieved", 0),
                "fulltext_retrieved": max(
                    getattr(state, "fulltext_sought", 0) - getattr(state, "fulltext_not_retrieved", 0),
                    0,
                ),
                "fulltext_no_full_text_excluded": no_full_text_excluded,
                "sparse_evidence_mode": state.sparse_evidence_mode,
            },
        )
        if rc.debug:
            rc.emit_debug_state(
                "phase_3_screening",
                {"included_papers": len(state.included_papers), "screened": len(state.deduped_papers)},
            )

    if _screening_step:
        try:
            async with get_db(state.db_path) as _jdb:
                await _journal_step_complete(WorkflowRepository(_jdb), _screening_step)
        except Exception:
            _log.warning("ScreeningNode: step journal write failed", exc_info=True)

    return None
