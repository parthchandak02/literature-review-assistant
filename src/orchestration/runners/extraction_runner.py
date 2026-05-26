"""Runner for ExtractionQualityNode — extracted from workflow.py."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from pydantic_graph import End, GraphRunContext

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.db.workflow_registry import update_status as update_registry_status
from src.export.markdown_refs import is_extraction_failed
from src.extraction import ExtractionService, StudyClassifier
from src.extraction.extractor import detect_scope_mismatch
from src.llm.factory import get_chat_client
from src.llm.provider import LLMProvider
from src.manuscript.cohort import IncludedSetResolver
from src.models import (
    CandidatePaper,
    DecisionLogEntry,
    ExtractionRecord,
    FailureCategory,
    FallbackEventRecord,
    GateStatus,
    PrimaryStudyStatus,
    RecoveryAction,
    StepStatus,
    StudyDesign,
    WorkflowStepRecord,
)
from src.orchestration.gates import GateRunner
from src.orchestration.helpers.extraction_metrics import (
    compute_extraction_quality_metrics,
    load_fulltext_artifact_paper_ids,
)
from src.orchestration.helpers.runtime import llm_available as helper_llm_available
from src.orchestration.helpers.runtime import rc as helper_rc
from src.orchestration.helpers.runtime import rc_print as helper_rc_print
from src.orchestration.helpers.step_journal import (
    journal_step_complete as helper_journal_step_complete,
)
from src.orchestration.helpers.step_journal import (
    journal_step_start as helper_journal_step_start,
)
from src.orchestration.state import ReviewState
from src.quality import (
    CaspAssessor,
    GradeAssessor,
    MmatAssessor,
    Rob2Assessor,
    RobinsIAssessor,
    StudyRouter,
)
from src.quality.grade import _PLACEHOLDER_OUTCOME_NAMES
from src.visualization import render_rob_traffic_light
from src.writing.context_builder import sanitize_summary_text_for_writing

_log = logging.getLogger(__name__)
logger = logging.getLogger(__name__)


def _rc(state: ReviewState):
    return helper_rc(state)


def _rc_print(rc, message: object) -> None:
    helper_rc_print(rc, message)


def _llm_available(settings=None, settings_cfg=None):
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


async def _journal_step_complete(
    repo: WorkflowRepository,
    record: WorkflowStepRecord,
    *,
    status: StepStatus = StepStatus.SUCCEEDED,
    error_message: str | None = None,
    failure_category: FailureCategory | None = None,
    recovery_action: RecoveryAction | None = None,
) -> None:
    await helper_journal_step_complete(
        repo,
        record,
        status=status,
        error_message=error_message,
        failure_category=failure_category,
        recovery_action=recovery_action,
    )


def _should_exclude_low_quality_record(
    record: ExtractionRecord,
    *,
    mmat_score: int,
    mmat_minimum_score: int,
) -> bool:
    """Return True when MMAT is below threshold and findings sanitize to NR."""
    if mmat_minimum_score <= 0 or mmat_score >= mmat_minimum_score:
        return False
    summary_text = ""
    try:
        summary_text = (record.results_summary or {}).get("summary", "")
    except Exception:
        summary_text = ""
    return sanitize_summary_text_for_writing(summary_text) == "NR"


async def run_extraction_quality_node(state: ReviewState, ctx: GraphRunContext[ReviewState]) -> End[dict] | None:
    rc = _rc(state)
    assert state.review is not None
    assert state.settings is not None

    router = StudyRouter()
    grade = GradeAssessor()

    if rc and hasattr(rc, "log_status"):
        rc.log_status(f"Loading extraction records for {len(state.included_papers)} included papers...")

    _extraction_step: WorkflowStepRecord | None = None
    rob2_rows: list = []
    async with get_db(state.db_path) as db:
        repository = WorkflowRepository(db)
        canonical_included_ids = await repository.get_included_paper_ids(state.workflow_id)
        if not canonical_included_ids:
            canonical_included_ids = await repository.get_title_abstract_include_ids(state.workflow_id)
        if canonical_included_ids:
            state.included_papers = [
                paper for paper in state.deduped_papers if paper.paper_id in canonical_included_ids
            ]
        _extraction_step = await _journal_step_start(
            repository,
            state.workflow_id,
            "phase_4_extraction_quality",
            "extraction_quality_phase",
        )
        records: list[ExtractionRecord] = await repository.load_extraction_records(state.workflow_id)
        already_extracted = {r.paper_id for r in records}
        already_assessed = await repository.get_rob_assessment_ids(state.workflow_id)
        current_included_ids = {p.paper_id for p in state.included_papers}
        to_process = [p for p in state.included_papers if p.paper_id not in already_extracted]
        quality_only = [r for r in records if r.paper_id in current_included_ids and r.paper_id not in already_assessed]
        if rc:
            rc.emit_phase_start(
                "phase_4_extraction_quality",
                f"Extracting {len(to_process)} papers...",
                total=len(to_process) + len(quality_only),
            )
        gate_runner = GateRunner(repository, state.settings)
        eq_on_waiting = None
        eq_on_resolved = None
        if rc:

            def _eq_on_waiting(t: object, u: object, limit: object, waited: object = 0.0) -> None:
                rc.log_rate_limit_wait(t, u, limit, waited)  # type: ignore[union-attr]

            def _eq_on_resolved(t: object, waited: object) -> None:
                rc.log_rate_limit_resolved(t, waited)  # type: ignore[union-attr]

            eq_on_waiting = _eq_on_waiting
            eq_on_resolved = _eq_on_resolved
        provider = LLMProvider(state.settings, repository, on_waiting=eq_on_waiting, on_resolved=eq_on_resolved)
        on_classify = None
        if rc and rc.verbose:

            def _on_classify(**kw):
                rc.log_api_call(**kw)

            on_classify = _on_classify
        classifier = StudyClassifier(
            provider=provider,
            repository=repository,
            review=state.review,
            on_llm_call=on_classify,
        )
        use_llm = _llm_available(settings_cfg=state.settings) and (rc is None or not rc.offline)
        _llm_timeout = float(getattr(getattr(state.settings, "llm", None), "request_timeout_seconds", 120))
        llm_gemini = get_chat_client(timeout_seconds=_llm_timeout) if use_llm else None
        extractor = ExtractionService(
            repository=repository,
            llm_client=llm_gemini,
            settings=state.settings,
            review=state.review,
            provider=provider if use_llm else None,
        )
        rob2 = Rob2Assessor(llm_client=llm_gemini, settings=state.settings, provider=provider if use_llm else None)
        robins_i = RobinsIAssessor(
            llm_client=llm_gemini, settings=state.settings, provider=provider if use_llm else None
        )
        casp = CaspAssessor(llm_client=llm_gemini, settings=state.settings, provider=provider if use_llm else None)
        mmat = MmatAssessor(llm_client=llm_gemini, settings=state.settings, provider=provider if use_llm else None)
        cohort_resolver = IncludedSetResolver(repository, state.workflow_id)
        _non_primary_statuses = {
            PrimaryStudyStatus.SECONDARY_REVIEW,
            PrimaryStudyStatus.PROTOCOL_ONLY,
            PrimaryStudyStatus.NON_EMPIRICAL,
        }
        non_primary_paper_ids: set[str] = set()
        low_quality_paper_ids: set[str] = set()
        scope_mismatch_paper_ids: set[str] = set()
        non_primary_status_counts: dict[str, int] = {}
        not_applicable_paper_ids: list[str] = []
        _grade_pairs: list[tuple] = []

        _paper_lookup = {p.paper_id: p for p in state.included_papers}
        extraction_cfg = getattr(state.settings, "extraction", None)
        gate_cfg = getattr(state.settings, "gates", None)
        _mmat_minimum_score = max(0, int(getattr(gate_cfg, "mmat_minimum_score", 0) or 0))
        _quality_concurrency = getattr(extraction_cfg, "extraction_concurrency", 4) if extraction_cfg else 4
        _quality_sem = asyncio.Semaphore(_quality_concurrency)

        async def _assess_quality_one(qr: ExtractionRecord) -> None:
            async with _quality_sem:
                if getattr(qr, "primary_study_status", PrimaryStudyStatus.UNKNOWN) in _non_primary_statuses:
                    await cohort_resolver.persist_extraction_outcome(
                        qr.paper_id,
                        primary_study_status=getattr(qr, "primary_study_status", PrimaryStudyStatus.UNKNOWN).value,
                        extraction_failed=is_extraction_failed(qr),
                    )
                    non_primary_paper_ids.add(qr.paper_id)
                    _status = getattr(qr, "primary_study_status", PrimaryStudyStatus.UNKNOWN).value
                    non_primary_status_counts[_status] = non_primary_status_counts.get(_status, 0) + 1
                    await repository.append_decision_log(
                        DecisionLogEntry(
                            decision_type="primary_data_filter",
                            paper_id=qr.paper_id,
                            decision="exclude_non_primary",
                            rationale=(
                                f"Excluded from synthesis/writing due to primary_study_status={_status} "
                                f"(study_design={qr.study_design.value})."
                            ),
                            actor="quality_assessment",
                            phase="phase_4_extraction_quality",
                        )
                    )
                    return
                _src_paper = _paper_lookup.get(qr.paper_id)
                full_text = (_src_paper.abstract or _src_paper.title or "").strip() if _src_paper else ""
                if _src_paper and extraction_cfg is not None:
                    ft_result = None
                    try:
                        from src.extraction.table_extraction import fetch_full_text

                        ft_result = await fetch_full_text(
                            doi=_src_paper.doi,
                            url=_src_paper.url,
                            pmid=getattr(_src_paper, "pmid", None),
                            use_sciencedirect=getattr(extraction_cfg, "sciencedirect_full_text", True),
                            use_unpaywall=getattr(extraction_cfg, "unpaywall_full_text", True),
                            use_pmc=getattr(extraction_cfg, "pmc_full_text", True),
                            use_core=getattr(extraction_cfg, "core_full_text", True),
                            use_europepmc=getattr(extraction_cfg, "europepmc_full_text", True),
                            use_semanticscholar=getattr(extraction_cfg, "semanticscholar_full_text", True),
                            use_arxiv_pdf=getattr(extraction_cfg, "arxiv_full_text", True),
                            use_biorxiv_medrxiv=getattr(extraction_cfg, "biorxiv_medrxiv_full_text", True),
                            use_openalex_content=getattr(extraction_cfg, "openalex_content_full_text", False),
                            use_crossref_links=getattr(extraction_cfg, "crossref_links_full_text", True),
                        )
                    except Exception as _ft_err:
                        logger.warning(
                            "ExtractionQualityNode: full-text fetch failed for quality-only paper %s (%s)",
                            qr.paper_id,
                            _ft_err,
                        )
                    min_chars = getattr(extraction_cfg, "full_text_min_chars", 500)
                    if ft_result and ft_result.text and len(ft_result.text) >= min_chars:
                        full_text = ft_result.text
                    elif ft_result and ft_result.pdf_bytes and len(ft_result.pdf_bytes) > 1000:
                        try:
                            from src.search.pdf_retrieval import _parse_pdf_bytes

                            full_text = await asyncio.to_thread(_parse_pdf_bytes, ft_result.pdf_bytes)
                        except Exception as exc:
                            logger.warning("Phase 4 retry PDF parse failed for %s: %s", qr.paper_id, exc)
                            full_text = (_src_paper.abstract or _src_paper.title or "").strip()
                await cohort_resolver.persist_extraction_outcome(
                    qr.paper_id,
                    primary_study_status=getattr(qr, "primary_study_status", PrimaryStudyStatus.UNKNOWN).value,
                    extraction_failed=is_extraction_failed(qr),
                )
                _scope_mismatch, _scope_evidence = detect_scope_mismatch(qr, state.review)
                if _scope_mismatch:
                    scope_mismatch_paper_ids.add(qr.paper_id)
                    await cohort_resolver.persist_extraction_outcome(
                        qr.paper_id,
                        primary_study_status=getattr(qr, "primary_study_status", PrimaryStudyStatus.UNKNOWN).value,
                        extraction_failed=False,
                        scope_mismatch=True,
                        exclusion_reason_code="wrong_intervention",
                    )
                    await repository.append_decision_log(
                        DecisionLogEntry(
                            decision_type="scope_filter",
                            paper_id=qr.paper_id,
                            decision="exclude_scope_mismatch",
                            rationale=(
                                "Excluded from synthesis/writing because the extracted intervention text "
                                f"explicitly contradicted the review intervention scope ({_scope_evidence or 'explicit mismatch'})."
                            ),
                            actor="quality_assessment",
                            phase="phase_4_extraction_quality",
                        )
                    )
                    return
                try:
                    tool = router.route_tool(qr)
                    if tool == "rob2":
                        assessment = await rob2.assess(qr, full_text=full_text)
                        await repository.save_rob2_assessment(state.workflow_id, assessment)
                        if getattr(assessment, "fallback_used", False):
                            await repository.save_fallback_event(
                                FallbackEventRecord(
                                    workflow_id=state.workflow_id,
                                    phase="phase_4_extraction_quality",
                                    module="quality.rob2",
                                    fallback_type="heuristic_assessment",
                                    reason=getattr(assessment, "overall_rationale", "heuristic fallback"),
                                    paper_id=qr.paper_id,
                                )
                            )
                    elif tool == "robins_i":
                        assessment = await robins_i.assess(qr, full_text=full_text)
                        await repository.save_robins_i_assessment(state.workflow_id, assessment)
                        if getattr(assessment, "fallback_used", False):
                            await repository.save_fallback_event(
                                FallbackEventRecord(
                                    workflow_id=state.workflow_id,
                                    phase="phase_4_extraction_quality",
                                    module="quality.robins_i",
                                    fallback_type="heuristic_assessment",
                                    reason=getattr(assessment, "overall_rationale", "heuristic fallback"),
                                    paper_id=qr.paper_id,
                                )
                            )
                    elif tool == "casp":
                        assessment = await casp.assess(qr, full_text=full_text)
                        await repository.save_casp_assessment(state.workflow_id, qr.paper_id, assessment)
                        if getattr(assessment, "fallback_used", False):
                            await repository.save_fallback_event(
                                FallbackEventRecord(
                                    workflow_id=state.workflow_id,
                                    phase="phase_4_extraction_quality",
                                    module="quality.casp",
                                    fallback_type="heuristic_assessment",
                                    reason=getattr(assessment, "overall_summary", "heuristic fallback"),
                                    paper_id=qr.paper_id,
                                )
                            )
                        await repository.append_decision_log(
                            DecisionLogEntry(
                                decision_type="casp_assessment",
                                paper_id=qr.paper_id,
                                decision="completed",
                                rationale=assessment.overall_summary,
                                actor="quality_assessment",
                                phase="phase_4_extraction_quality",
                            )
                        )
                    elif tool == "mmat":
                        mmat_result = await mmat.assess(qr, full_text=full_text)
                        await repository.save_mmat_assessment(state.workflow_id, qr.paper_id, mmat_result)
                        if getattr(mmat_result, "fallback_used", False):
                            await repository.save_fallback_event(
                                FallbackEventRecord(
                                    workflow_id=state.workflow_id,
                                    phase="phase_4_extraction_quality",
                                    module="quality.mmat",
                                    fallback_type="heuristic_assessment",
                                    reason=getattr(mmat_result, "overall_summary", "heuristic fallback"),
                                    paper_id=qr.paper_id,
                                )
                            )
                        await repository.append_decision_log(
                            DecisionLogEntry(
                                decision_type="mmat_assessment",
                                paper_id=qr.paper_id,
                                decision="completed",
                                rationale=mmat_result.overall_summary,
                                actor="quality_assessment",
                                phase="phase_4_extraction_quality",
                            )
                        )
                        if _should_exclude_low_quality_record(
                            qr,
                            mmat_score=int(getattr(mmat_result, "overall_score", 0) or 0),
                            mmat_minimum_score=_mmat_minimum_score,
                        ):
                            low_quality_paper_ids.add(qr.paper_id)
                            await cohort_resolver.persist_extraction_outcome(
                                qr.paper_id,
                                primary_study_status=getattr(
                                    qr, "primary_study_status", PrimaryStudyStatus.UNKNOWN
                                ).value,
                                extraction_failed=False,
                                low_quality=True,
                                exclusion_reason_code="low_quality_mmat",
                            )
                            await repository.append_decision_log(
                                DecisionLogEntry(
                                    decision_type="quality_exclusion",
                                    paper_id=qr.paper_id,
                                    decision="exclude_low_quality",
                                    rationale=(
                                        "Excluded from synthesis/writing due to "
                                        f"MMAT score {mmat_result.overall_score}/5 with no reportable findings."
                                    ),
                                    actor="quality_assessment",
                                    phase="phase_4_extraction_quality",
                                )
                            )
                            return
                    else:
                        not_applicable_paper_ids.append(qr.paper_id)
                    _qr_outcomes = [
                        o.name.strip()
                        for o in qr.outcomes
                        if o.name.strip()
                        and o.name.strip().lower()
                        not in {
                            "primary_outcome",
                            "secondary_outcome",
                            "not_reported",
                            "",
                        }
                    ]
                    _qr_outcome_name = _qr_outcomes[0] if _qr_outcomes else "primary_outcome"
                    _grade_pairs.append((qr, None, _qr_outcome_name))
                except Exception as exc:
                    await repository.append_decision_log(
                        DecisionLogEntry(
                            decision_type="quality_retry_error",
                            paper_id=qr.paper_id,
                            decision="error",
                            rationale=f"Quality-only retry error: {type(exc).__name__}: {exc}",
                            actor="workflow_run",
                            phase="phase_4_extraction_quality",
                        )
                    )

        await asyncio.gather(
            *[_assess_quality_one(qr) for qr in quality_only],
            return_exceptions=True,
        )

        _extract_concurrency = getattr(extraction_cfg, "extraction_concurrency", 4) if extraction_cfg else 4
        _extract_sem = asyncio.Semaphore(_extract_concurrency)
        _manifest_lock = asyncio.Lock()
        _extract_done_count: list[int] = [0]

        async def _extract_one_paper(paper: CandidatePaper) -> None:
            async with _extract_sem:
                if rc and rc.verbose:
                    _rc_print(rc, f"  Extracting {paper.paper_id[:12]}...")

                ft_result = None
                if use_llm and extraction_cfg is not None:
                    if rc and hasattr(rc, "log_status"):
                        paper_num = _extract_done_count[0] + 1
                        title_snippet = (paper.title or paper.paper_id[:12] or "")[:50]
                        rc.log_status(f"Fetching full text [{paper_num}/{len(to_process)}]: {title_snippet}...")
                    try:
                        from src.extraction.table_extraction import fetch_full_text

                        ft_result = await fetch_full_text(
                            doi=paper.doi,
                            url=paper.url,
                            pmid=getattr(paper, "pmid", None),
                            use_sciencedirect=getattr(extraction_cfg, "sciencedirect_full_text", True),
                            use_unpaywall=getattr(extraction_cfg, "unpaywall_full_text", True),
                            use_pmc=getattr(extraction_cfg, "pmc_full_text", True),
                            use_core=getattr(extraction_cfg, "core_full_text", True),
                            use_europepmc=getattr(extraction_cfg, "europepmc_full_text", True),
                            use_semanticscholar=getattr(extraction_cfg, "semanticscholar_full_text", True),
                            use_arxiv_pdf=getattr(extraction_cfg, "arxiv_full_text", True),
                            use_biorxiv_medrxiv=getattr(extraction_cfg, "biorxiv_medrxiv_full_text", True),
                            use_openalex_content=getattr(extraction_cfg, "openalex_content_full_text", False),
                            use_crossref_links=getattr(extraction_cfg, "crossref_links_full_text", True),
                        )
                    except Exception as _ft_err:
                        logger.warning(
                            "ExtractionNode: full-text fetch failed for %s (%s) -- using abstract",
                            paper.paper_id,
                            _ft_err,
                        )

                min_chars = getattr(extraction_cfg, "full_text_min_chars", 500)
                if ft_result and ft_result.text and len(ft_result.text) >= min_chars:
                    full_text = ft_result.text
                    if rc and rc.verbose:
                        _rc_print(rc, f"    [dim]full-text via {ft_result.source} ({len(full_text)} chars)[/]")
                elif ft_result and ft_result.pdf_bytes and len(ft_result.pdf_bytes) > 1000:
                    try:
                        from src.search.pdf_retrieval import _parse_pdf_bytes

                        full_text = await asyncio.to_thread(_parse_pdf_bytes, ft_result.pdf_bytes)
                        if rc and rc.verbose:
                            _rc_print(
                                rc,
                                f"    [dim]full-text via {ft_result.source} PDF ({len(full_text)} chars)[/]",
                            )
                    except Exception as exc:
                        logger.warning("Phase 4 PDF parse failed for %s: %s", paper.paper_id, exc)
                        full_text = (paper.abstract or paper.title or "").strip()
                else:
                    full_text = (paper.abstract or paper.title or "").strip()

                papers_dir_path = Path(state.artifacts.get("papers_dir", ""))
                papers_manifest_path = Path(state.artifacts.get("papers_manifest", ""))
                if papers_dir_path.name:
                    try:
                        papers_dir_path.mkdir(parents=True, exist_ok=True)
                        saved_path: str | None = None
                        if ft_result and ft_result.pdf_bytes and len(ft_result.pdf_bytes) > 1000:
                            pdf_dest = papers_dir_path / f"{paper.paper_id}.pdf"
                            pdf_dest.write_bytes(ft_result.pdf_bytes)
                            saved_path = str(pdf_dest)
                        elif full_text and ft_result and ft_result.source not in ("abstract", ""):
                            txt_dest = papers_dir_path / f"{paper.paper_id}.txt"
                            txt_dest.write_text(full_text, encoding="utf-8")
                            saved_path = str(txt_dest)
                        if papers_manifest_path.name:
                            import json as _json

                            async with _manifest_lock:
                                _manifest: dict = {}
                                if papers_manifest_path.exists():
                                    try:
                                        _manifest = _json.loads(papers_manifest_path.read_text(encoding="utf-8"))
                                    except Exception:
                                        _manifest = {}
                                _manifest[paper.paper_id] = {
                                    "title": paper.title or "",
                                    "authors": paper.authors or "",
                                    "year": paper.year,
                                    "doi": paper.doi or "",
                                    "url": paper.url or "",
                                    "source": ft_result.source if ft_result else "abstract",
                                    "file_path": saved_path,
                                    "file_type": (
                                        "pdf"
                                        if (saved_path and saved_path.endswith(".pdf"))
                                        else ("txt" if saved_path else None)
                                    ),
                                }
                                papers_manifest_path.write_text(_json.dumps(_manifest, indent=2), encoding="utf-8")
                    except Exception as _save_err:
                        logger.debug("ExtractionNode: could not save fulltext for %s: %s", paper.paper_id, _save_err)

                _is_abstract_only = not ft_result or not ft_result.text
                try:
                    try:
                        design = await classifier.classify(
                            state.workflow_id,
                            paper,
                            abstract_only=_is_abstract_only,
                        )
                    except Exception as exc:
                        design = StudyDesign.NON_RANDOMIZED
                        await repository.append_decision_log(
                            DecisionLogEntry(
                                decision_type="study_design_classification",
                                paper_id=paper.paper_id,
                                decision=design.value,
                                rationale=f"Classifier error fallback: {type(exc).__name__}: {exc}",
                                actor="workflow_run",
                                phase="phase_4_extraction_quality",
                            )
                        )
                    record = await extractor.extract(
                        workflow_id=state.workflow_id,
                        paper=paper,
                        study_design=design,
                        full_text=full_text,
                    )

                    _pdf_bytes_ok = (
                        ft_result is not None and ft_result.pdf_bytes is not None and len(ft_result.pdf_bytes) >= 1024
                    )
                    use_vision = (
                        use_llm
                        and extraction_cfg is not None
                        and getattr(extraction_cfg, "use_pdf_vision", True)
                        and _pdf_bytes_ok
                    )
                    if ft_result and ft_result.source != "abstract":
                        try:
                            record.extraction_source = ft_result.source  # type: ignore[assignment]
                        except Exception:
                            _log.warning(
                                "ExtractionNode: failed to assign extraction_source=%s for paper %s",
                                ft_result.source,
                                paper.paper_id,
                                exc_info=True,
                            )

                    if use_vision:
                        try:
                            from src.extraction.table_extraction import (
                                extract_tables_from_pdf,
                                merge_outcomes,
                            )

                            vision_model = (
                                extraction_cfg.pdf_vision_model.replace("google:", "")
                                .replace("google-cloud:", "")
                                .replace("google-gla:", "")
                                .replace("google-vertex:", "")
                            )
                            vision_outcomes = await extract_tables_from_pdf(
                                ft_result.pdf_bytes,
                                model_name=vision_model,
                                repository=repository,
                                workflow_id=state.workflow_id,
                            )
                            if vision_outcomes:
                                merged, _merge_source = merge_outcomes(list(record.outcomes), vision_outcomes)
                                record.outcomes = merged
                                try:
                                    record.extraction_source = _merge_source  # type: ignore[assignment]
                                except Exception:
                                    _log.warning(
                                        "ExtractionNode: failed to assign merged extraction_source=%s for paper %s",
                                        _merge_source,
                                        paper.paper_id,
                                        exc_info=True,
                                    )
                                logger.info(
                                    "ExtractionNode: vision extracted %d table rows for paper %s (source=%s)",
                                    len(vision_outcomes),
                                    paper.paper_id,
                                    _merge_source,
                                )
                        except Exception as _vis_err:
                            logger.warning(
                                "ExtractionNode: PDF vision failed for %s: %s",
                                paper.paper_id,
                                _vis_err,
                            )
                    await repository.save_extraction_record(state.workflow_id, record)

                    if record.primary_study_status in _non_primary_statuses:
                        await cohort_resolver.persist_extraction_outcome(
                            record.paper_id,
                            primary_study_status=record.primary_study_status.value,
                            extraction_failed=is_extraction_failed(record),
                        )
                        non_primary_paper_ids.add(record.paper_id)
                        non_primary_status_counts[record.primary_study_status.value] = (
                            non_primary_status_counts.get(record.primary_study_status.value, 0) + 1
                        )
                        await repository.append_decision_log(
                            DecisionLogEntry(
                                decision_type="primary_data_filter",
                                paper_id=record.paper_id,
                                decision="exclude_non_primary",
                                rationale=(
                                    "Excluded from synthesis/writing due to "
                                    f"primary_study_status={record.primary_study_status.value} "
                                    f"(study_design={record.study_design.value})."
                                ),
                                actor="quality_assessment",
                                phase="phase_4_extraction_quality",
                            )
                        )
                        _extract_done_count[0] += 1
                        if rc:
                            rc.advance_screening("phase_4_extraction_quality", _extract_done_count[0], len(to_process))
                            extraction_summary = (record.results_summary.get("summary") or "")[:300]
                            rc.log_extraction_paper(
                                paper_id=paper.paper_id,
                                design=f"{design.value}/{record.primary_study_status.value}",
                                extraction_summary=extraction_summary,
                                rob_judgment="filtered_non_primary",
                            )
                        return

                    _scope_mismatch, _scope_evidence = detect_scope_mismatch(record, state.review)
                    if _scope_mismatch:
                        scope_mismatch_paper_ids.add(record.paper_id)
                        await cohort_resolver.persist_extraction_outcome(
                            record.paper_id,
                            primary_study_status=record.primary_study_status.value,
                            extraction_failed=False,
                            scope_mismatch=True,
                            exclusion_reason_code="wrong_intervention",
                        )
                        await repository.append_decision_log(
                            DecisionLogEntry(
                                decision_type="scope_filter",
                                paper_id=record.paper_id,
                                decision="exclude_scope_mismatch",
                                rationale=(
                                    "Excluded from synthesis/writing because the extracted intervention text "
                                    f"explicitly contradicted the review intervention scope ({_scope_evidence or 'explicit mismatch'})."
                                ),
                                actor="quality_assessment",
                                phase="phase_4_extraction_quality",
                            )
                        )
                        _extract_done_count[0] += 1
                        if rc:
                            rc.advance_screening("phase_4_extraction_quality", _extract_done_count[0], len(to_process))
                            extraction_summary = (record.results_summary.get("summary") or "")[:300]
                            rc.log_extraction_paper(
                                paper_id=paper.paper_id,
                                design=design.value,
                                extraction_summary=extraction_summary,
                                rob_judgment="filtered_scope_mismatch",
                            )
                        return

                    records.append(record)
                    await cohort_resolver.persist_extraction_outcome(
                        record.paper_id,
                        primary_study_status=record.primary_study_status.value,
                        extraction_failed=is_extraction_failed(record),
                    )
                    _extract_done_count[0] += 1
                    if rc:
                        rc.advance_screening("phase_4_extraction_quality", _extract_done_count[0], len(to_process))

                    tool = router.route_tool(record)
                    rob_judgment = "not_applicable"
                    rob_assessment_obj = None
                    if tool == "rob2":
                        assessment = await rob2.assess(record, full_text=full_text)
                        await repository.save_rob2_assessment(state.workflow_id, assessment)
                        if getattr(assessment, "fallback_used", False):
                            await repository.save_fallback_event(
                                FallbackEventRecord(
                                    workflow_id=state.workflow_id,
                                    phase="phase_4_extraction_quality",
                                    module="quality.rob2",
                                    fallback_type="heuristic_assessment",
                                    reason=getattr(assessment, "overall_rationale", "heuristic fallback"),
                                    paper_id=record.paper_id,
                                )
                            )
                        rob_assessment_obj = assessment
                        rob_judgment = (
                            assessment.overall_judgment.value if hasattr(assessment, "overall_judgment") else "unknown"
                        )
                    elif tool == "robins_i":
                        assessment = await robins_i.assess(record, full_text=full_text)
                        await repository.save_robins_i_assessment(state.workflow_id, assessment)
                        if getattr(assessment, "fallback_used", False):
                            await repository.save_fallback_event(
                                FallbackEventRecord(
                                    workflow_id=state.workflow_id,
                                    phase="phase_4_extraction_quality",
                                    module="quality.robins_i",
                                    fallback_type="heuristic_assessment",
                                    reason=getattr(assessment, "overall_rationale", "heuristic fallback"),
                                    paper_id=record.paper_id,
                                )
                            )
                        rob_assessment_obj = assessment
                        rob_judgment = (
                            assessment.overall_judgment.value if hasattr(assessment, "overall_judgment") else "unknown"
                        )
                    elif tool == "casp":
                        assessment = await casp.assess(record, full_text=full_text)
                        rob_judgment = getattr(assessment, "overall_summary", "completed")[:80]
                        await repository.save_casp_assessment(state.workflow_id, record.paper_id, assessment)
                        if getattr(assessment, "fallback_used", False):
                            await repository.save_fallback_event(
                                FallbackEventRecord(
                                    workflow_id=state.workflow_id,
                                    phase="phase_4_extraction_quality",
                                    module="quality.casp",
                                    fallback_type="heuristic_assessment",
                                    reason=getattr(assessment, "overall_summary", "heuristic fallback"),
                                    paper_id=record.paper_id,
                                )
                            )
                        await repository.append_decision_log(
                            DecisionLogEntry(
                                decision_type="casp_assessment",
                                paper_id=record.paper_id,
                                decision="completed",
                                rationale=assessment.overall_summary,
                                actor="quality_assessment",
                                phase="phase_4_extraction_quality",
                            )
                        )
                    elif tool == "mmat":
                        mmat_result = await mmat.assess(record, full_text=full_text)
                        rob_judgment = f"MMAT score {mmat_result.overall_score}/5"
                        await repository.save_mmat_assessment(state.workflow_id, record.paper_id, mmat_result)
                        if getattr(mmat_result, "fallback_used", False):
                            await repository.save_fallback_event(
                                FallbackEventRecord(
                                    workflow_id=state.workflow_id,
                                    phase="phase_4_extraction_quality",
                                    module="quality.mmat",
                                    fallback_type="heuristic_assessment",
                                    reason=getattr(mmat_result, "overall_summary", "heuristic fallback"),
                                    paper_id=record.paper_id,
                                )
                            )
                        await repository.append_decision_log(
                            DecisionLogEntry(
                                decision_type="mmat_assessment",
                                paper_id=record.paper_id,
                                decision="completed",
                                rationale=mmat_result.overall_summary,
                                actor="quality_assessment",
                                phase="phase_4_extraction_quality",
                            )
                        )
                        if _should_exclude_low_quality_record(
                            record,
                            mmat_score=int(getattr(mmat_result, "overall_score", 0) or 0),
                            mmat_minimum_score=_mmat_minimum_score,
                        ):
                            low_quality_paper_ids.add(record.paper_id)
                            records[:] = [r for r in records if r.paper_id != record.paper_id]
                            await cohort_resolver.persist_extraction_outcome(
                                record.paper_id,
                                primary_study_status=record.primary_study_status.value,
                                extraction_failed=False,
                                low_quality=True,
                                exclusion_reason_code="low_quality_mmat",
                            )
                            await repository.append_decision_log(
                                DecisionLogEntry(
                                    decision_type="quality_exclusion",
                                    paper_id=record.paper_id,
                                    decision="exclude_low_quality",
                                    rationale=(
                                        "Excluded from synthesis/writing due to "
                                        f"MMAT score {mmat_result.overall_score}/5 with no reportable findings."
                                    ),
                                    actor="quality_assessment",
                                    phase="phase_4_extraction_quality",
                                )
                            )
                            if rc:
                                extraction_summary = (record.results_summary.get("summary") or "")[:300]
                                rc.log_extraction_paper(
                                    paper_id=paper.paper_id,
                                    design=design.value,
                                    extraction_summary=extraction_summary,
                                    rob_judgment=f"excluded_low_quality_{mmat_result.overall_score}/5",
                                )
                            return
                    else:
                        not_applicable_paper_ids.append(record.paper_id)
                        await repository.append_decision_log(
                            DecisionLogEntry(
                                decision_type="rob_not_applicable",
                                paper_id=record.paper_id,
                                decision="not_applicable",
                                rationale=(
                                    f"Study design '{record.study_design.value}' is not an "
                                    "interventional study; ROBINS-I/RoB2 assessment not applicable."
                                ),
                                actor="quality_assessment",
                                phase="phase_4_extraction_quality",
                            )
                        )

                    _grade_outcomes = [
                        o.name.strip()
                        for o in record.outcomes
                        if o.name.strip()
                        and o.name.strip().lower()
                        not in {
                            "primary_outcome",
                            "secondary_outcome",
                            "not_reported",
                            "",
                        }
                    ]
                    _grade_outcome_name = _grade_outcomes[0] if _grade_outcomes else "primary_outcome"
                    _grade_pairs.append((record, rob_assessment_obj, _grade_outcome_name))

                    if rc:
                        extraction_summary = (record.results_summary.get("summary") or "")[:300]
                        rc.log_extraction_paper(
                            paper_id=paper.paper_id,
                            design=design.value,
                            extraction_summary=extraction_summary,
                            rob_judgment=rob_judgment,
                        )
                except Exception as exc:
                    await cohort_resolver.persist_extraction_outcome(
                        paper.paper_id,
                        primary_study_status=PrimaryStudyStatus.UNKNOWN.value,
                        extraction_failed=True,
                    )
                    await repository.append_decision_log(
                        DecisionLogEntry(
                            decision_type="extraction_error",
                            paper_id=paper.paper_id,
                            decision="error",
                            rationale=f"Extraction/quality error, paper skipped: {type(exc).__name__}: {exc}",
                            actor="workflow_run",
                            phase="phase_4_extraction_quality",
                        )
                    )
                    _extract_done_count[0] += 1
                    if rc:
                        rc.advance_screening("phase_4_extraction_quality", _extract_done_count[0], len(to_process))

        await asyncio.gather(*[_extract_one_paper(p) for p in to_process], return_exceptions=True)

        _abstract_only_sources = frozenset({"text", "heuristic", "", None})
        _abstract_only_count = sum(
            1 for r in records if getattr(r, "extraction_source", "text") in _abstract_only_sources
        )
        _abstract_only_warning_threshold = float(
            getattr(getattr(state.settings, "writing", None), "abstract_only_caution_threshold", 0.80)
        )
        if records and _abstract_only_count / len(records) > _abstract_only_warning_threshold:
            _pct = int(100 * _abstract_only_count / len(records))
            _msg = (
                f"fulltext_retrieval_low: {_abstract_only_count}/{len(records)} "
                f"({_pct}%) papers extracted from abstract only. "
                f"Classification and extraction quality may be degraded."
            )
            logger.warning("ExtractionQualityNode: %s", _msg)
            await repository.append_decision_log(
                DecisionLogEntry(
                    decision_type="gate_advisory",
                    paper_id="__pipeline__",
                    decision="fulltext_retrieval_low",
                    rationale=_msg,
                    actor="extraction_quality_gate",
                    phase="phase_4_extraction_quality",
                )
            )
            if rc:
                rc.log_status(f"[yellow]WARNING:[/] {_msg}")

        state.excluded_non_primary_count = len(non_primary_paper_ids)
        if non_primary_paper_ids or low_quality_paper_ids or scope_mismatch_paper_ids:
            _before = len(state.included_papers)
            _primary_ids = {r.paper_id for r in records}
            state.included_papers = [p for p in state.included_papers if p.paper_id in _primary_ids]
            _after = len(state.included_papers)
            logger.info(
                "ExtractionQualityNode: filtered %d papers before synthesis/writing "
                "(before=%d, after=%d, breakdown=%s, low_quality=%d, scope_mismatch=%d)",
                len(non_primary_paper_ids) + len(low_quality_paper_ids) + len(scope_mismatch_paper_ids),
                _before,
                _after,
                non_primary_status_counts,
                len(low_quality_paper_ids),
                len(scope_mismatch_paper_ids),
            )
            if rc:
                rc.log_status(
                    "Primary-data filter removed "
                    f"{len(non_primary_paper_ids)} non-primary and {len(low_quality_paper_ids)} "
                    f"low-quality papers and {len(scope_mismatch_paper_ids)} scope-mismatch papers before synthesis: "
                    f"{non_primary_status_counts}"
                )

        _grade_accum: dict[str, tuple[list, list]] = {}
        for _gp_record, _gp_rob, _gp_outcome in _grade_pairs:
            if _gp_outcome not in _grade_accum:
                _grade_accum[_gp_outcome] = ([], [])
            if _gp_rob is not None:
                _grade_accum[_gp_outcome][0].append(_gp_rob)
            _grade_accum[_gp_outcome][1].append(_gp_record)
        _removed_placeholders = await repository.delete_placeholder_grade_assessments(state.workflow_id)
        if _removed_placeholders > 0:
            logger.info(
                "ExtractionQualityNode: removed %d stale placeholder GRADE row(s) before aggregation",
                _removed_placeholders,
            )
        for _gp_outcome_name, (_gp_robs, _gp_recs) in _grade_accum.items():
            try:
                if _gp_outcome_name.strip().lower() in _PLACEHOLDER_OUTCOME_NAMES:
                    continue
                if _gp_robs:
                    _agg_grade = grade.assess_from_rob(
                        outcome_name=_gp_outcome_name,
                        study_design=_gp_recs[0].study_design,
                        rob_assessments=_gp_robs,
                        extraction_records=_gp_recs,
                    )
                else:
                    _agg_grade = grade.assess_outcome(
                        outcome_name=_gp_outcome_name,
                        number_of_studies=len(_gp_recs),
                        study_design=_gp_recs[0].study_design,
                    )
                await repository.save_grade_assessment(state.workflow_id, _agg_grade)
            except Exception as _grade_err:
                logger.warning(
                    "ExtractionQualityNode: GRADE aggregation failed for outcome '%s': %s",
                    _gp_outcome_name,
                    _grade_err,
                )

        rob2_rows, robins_i_rows = await repository.load_rob_assessments(state.workflow_id)
        casp_rows = await repository.load_casp_assessments(state.workflow_id)
        mmat_rows = await repository.load_mmat_assessments(state.workflow_id)
        _heuristic_count = sum(
            1
            for r in (rob2_rows + robins_i_rows + casp_rows + mmat_rows)
            if getattr(r, "assessment_source", "llm") == "heuristic"
        )
        state.heuristic_assessment_count = _heuristic_count
        if _heuristic_count > 0:
            logger.warning(
                "ExtractionQualityNode: %d quality assessment(s) used heuristic fallback",
                _heuristic_count,
            )
        fulltext_paper_ids = load_fulltext_artifact_paper_ids(state.artifacts, state.db_path)
        completeness_ratio, weak_evidence_rate, extraction_metric_details = compute_extraction_quality_metrics(
            records,
            state.included_papers,
            fulltext_paper_ids=fulltext_paper_ids,
        )
        gr = await gate_runner.run_extraction_completeness_gate(
            workflow_id=state.workflow_id,
            phase="phase_4_extraction_quality",
            completeness_ratio=completeness_ratio,
            weak_evidence_rate=weak_evidence_rate,
            metric_details=extraction_metric_details,
        )
        if state.settings.gates.profile == "strict" and gr and gr.status == GateStatus.FAILED:
            err_msg = (
                "Extraction completeness gate failed: "
                f"{gr.actual_value or 'unknown'} "
                f"(required {gr.threshold or '?'}). Cannot proceed."
            )
            summary = {
                "workflow_id": state.workflow_id,
                "status": "failed",
                "error": err_msg,
                "gate": "extraction_completeness",
                "phase": "phase_4_extraction_quality",
            }
            Path(state.artifacts["run_summary"]).write_text(json.dumps(summary, indent=2), encoding="utf-8")
            await repository.update_workflow_status(state.workflow_id, "failed")
            await update_registry_status(state.run_root, state.workflow_id, "failed")
            if rc:
                if hasattr(rc, "log_status"):
                    rc.log_status(f"[red]ERROR:[/] {err_msg}")
            if _extraction_step:
                await _journal_step_complete(
                    repository,
                    _extraction_step,
                    status=StepStatus.FAILED,
                    error_message=err_msg,
                    failure_category=FailureCategory.TERMINAL,
                    recovery_action=RecoveryAction.ABORT,
                )
            return End(summary)

        _rob_paper_lookup = {p.paper_id: p for p in state.included_papers}
        render_rob_traffic_light(
            rob2_rows,
            robins_i_rows,
            state.artifacts["rob_traffic_light"],
            paper_lookup=_rob_paper_lookup,
            not_applicable_count=len(not_applicable_paper_ids),
            rob2_output_path=state.artifacts.get("rob2_traffic_light"),
        )
        await repository.save_checkpoint(
            state.workflow_id,
            "phase_4_extraction_quality",
            papers_processed=len(records),
        )
    state.extraction_records = records
    if rc:
        rc.emit_phase_done("phase_4_extraction_quality", {"records": len(records)})
        if rc.debug:
            rc.emit_debug_state(
                "phase_4_extraction_quality",
                {"extraction_records": len(records)},
            )

    if _extraction_step:
        try:
            async with get_db(state.db_path) as _jdb:
                await _journal_step_complete(WorkflowRepository(_jdb), _extraction_step)
        except Exception:
            _log.warning("ExtractionQualityNode: step journal write failed", exc_info=True)

    return None
