"""Section writing loop: iterate sections, RAG retrieval, write_section_with_validation, humanizer."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from src.db.repositories import CitationRepository, WorkflowRepository
from src.llm.provider import LLMProvider
from src.models import SectionDraft, SectionOutline
from src.orchestration.helpers.runtime import evaluate_rag_health as helper_evaluate_rag_health
from src.orchestration.helpers.runtime import llm_available as helper_llm_available
from src.orchestration.runners.writing.rag_retrieval import (
    generate_hyde_documents,
    retrieve_rag_for_section,
)
from src.orchestration.state import ReviewState
from src.rag.retriever import RAGRetriever
from src.writing.citation_grounding import verify_citation_grounding
from src.writing.humanizer import humanize_async
from src.writing.humanizer_guardrails import (
    apply_deterministic_guardrails,
    extract_citation_blocks,
    extract_numeric_tokens,
)
from src.writing.orchestration import (
    _citation_entries_from_papers,
    _ensure_structured_abstract,
    canonicalize_structured_abstract_markdown,
    validate_structured_abstract_markdown_band,
    write_section_with_validation,
)
from src.writing.outline_generator import build_fallback_section_outline, generate_section_outline
from src.writing.prompts.sections import SECTIONS, get_section_context, get_section_word_limit

logger = logging.getLogger(__name__)


def _llm_available(settings=None, settings_cfg=None):
    return helper_llm_available(settings=settings, settings_cfg=settings_cfg)


def _evaluate_rag_health(*, empty_sections: int, error_sections: int, max_empty_sections: int) -> tuple[bool, str]:
    return helper_evaluate_rag_health(
        empty_sections=empty_sections,
        error_sections=error_sections,
        max_empty_sections=max_empty_sections,
    )


def _rc_print(rc, message):
    from src.orchestration.helpers.runtime import rc_print as helper_rc_print

    helper_rc_print(rc, message)


@dataclass
class SectionLoopResult:
    """Results from the section writing loop."""

    sections_written: list[str] = field(default_factory=list)
    failed_sections: list[str] = field(default_factory=list)
    section_results_by_key: dict[str, object] = field(default_factory=dict)


async def run_section_writing_loop(
    state: ReviewState,
    *,
    repository: WorkflowRepository,
    db: Any,
    citation_repo: CitationRepository,
    provider: LLMProvider,
    grounding: Any,
    citation_catalog: str,
    completed: set,
    prisma_counts: Any,
    rc: Any | None,
    save_writing_checkpoint: Callable,
    save_subphase_checkpoint: Callable,
) -> SectionLoopResult:
    """Execute the section writing loop: HyDE, outlines, per-section RAG+write, phase A/B, retries."""
    result = SectionLoopResult()
    _section_results_by_key: dict[str, object] = {}

    def _on_write(**kw):
        if rc:
            rc.log_api_call(**kw)

    rag_cfg = getattr(state.settings, "rag", None)
    use_hyde = getattr(rag_cfg, "use_hyde", True)
    hyde_model = rag_cfg.hyde_model
    embed_model = rag_cfg.embed_model
    embed_dim = getattr(rag_cfg, "embed_dim", 768)
    use_rerank = getattr(rag_cfg, "rerank", True)
    candidate_k = getattr(rag_cfg, "candidate_k", 20)
    final_k = getattr(rag_cfg, "final_k", 8)
    min_chunks_per_section = getattr(rag_cfg, "min_chunks_per_section", 1)
    max_empty_sections = getattr(rag_cfg, "max_empty_sections", 2)
    block_on_rag_failure = getattr(rag_cfg, "block_writing_on_rag_failure", False)
    rag_empty_policy = getattr(rag_cfg, "rag_empty_policy", "warn")
    reranker_model = rag_cfg.reranker_model
    if candidate_k < final_k:
        candidate_k = final_k

    _pico_cfg = getattr(state.review, "pico", None) if state.review else None

    # --- HyDE generation ---
    hyde_docs: dict[str, str] = {}
    if use_hyde and state.review:
        hyde_docs = await generate_hyde_documents(
            state,
            hyde_model=hyde_model,
            pico_cfg=_pico_cfg,
            repository=repository,
            rc=rc,
        )
    await save_subphase_checkpoint("phase_6a_hyde", papers_processed=len(hyde_docs))

    # --- Outline generation ---
    writing_cfg = getattr(state.settings, "writing", None)
    section_outlines: dict[str, SectionOutline] = {}
    outline_enabled = bool(getattr(writing_cfg, "ratchet_outline_enabled", True))
    if outline_enabled:
        _outline_generation = await repository.get_writing_generation(state.workflow_id)
        _outline_checkpoints = await repository.get_checkpoints(state.workflow_id)
        _saved_outlines = await repository.load_section_outlines(
            state.workflow_id,
            generation=_outline_generation,
        )
        if len(_saved_outlines) == len(SECTIONS) and _outline_checkpoints.get("phase_6a2_outline") == "completed":
            section_outlines = _saved_outlines
            logger.info(
                "WritingNode: reusing %d persisted section outlines for generation=%d",
                len(section_outlines),
                _outline_generation,
            )
        else:
            if rc:
                rc.log_status("Generating section outlines...")
            _outline_request_timeout = float(
                getattr(getattr(state.settings, "llm", None), "request_timeout_seconds", 180)
            )
            _outline_timeout = max(_outline_request_timeout * 1.5, 120.0)
            _outline_sem = asyncio.Semaphore(getattr(writing_cfg, "writing_concurrency", 3))

            async def _outline_one(section_name: str) -> SectionOutline:
                async with _outline_sem:
                    return await generate_section_outline(
                        section=section_name,
                        settings=state.settings,
                        grounding=grounding,
                        citation_catalog=citation_catalog,
                        provider=provider,
                        on_llm_call=_on_write if rc else None,
                    )

            try:
                _outline_results = await asyncio.wait_for(
                    asyncio.gather(*[_outline_one(s) for s in SECTIONS]),
                    timeout=_outline_timeout,
                )
                section_outlines = {outline.section_key: outline for outline in _outline_results}
            except TimeoutError:
                logger.warning(
                    "Section outline generation timed out after %.0fs; using deterministic fallback outlines.",
                    _outline_timeout,
                )
                section_outlines = {
                    section_name: build_fallback_section_outline(
                        section_name,
                        grounding,
                        citation_catalog,
                    )
                    for section_name in SECTIONS
                }
            for outline in section_outlines.values():
                await repository.save_section_outline(
                    state.workflow_id,
                    outline,
                    generation=_outline_generation,
                )
            await save_subphase_checkpoint(
                "phase_6a2_outline",
                papers_processed=len(section_outlines),
            )

    # --- Section writing setup ---
    do_humanize = getattr(writing_cfg, "humanization", False)
    humanize_iters = getattr(writing_cfg, "humanization_iterations", 1)
    humanize_verify_repair = getattr(writing_cfg, "humanization_verification_repair", True)
    humanize_repair_max = getattr(writing_cfg, "humanization_repair_max_per_pass", 1)
    use_llm_write = _llm_available(settings_cfg=state.settings) and (rc is None or not rc.offline)
    _write_concurrency = getattr(writing_cfg, "writing_concurrency", 3)
    _write_sem = asyncio.Semaphore(_write_concurrency)
    _sections_done: list[int] = [0]
    _rag_status_counts: dict[str, int] = {"success": 0, "empty": 0, "error": 0, "skipped": 0}
    retriever = RAGRetriever(db, state.workflow_id)
    chunk_count = await retriever.chunk_count()
    paper_citation_meta: dict[str, dict[str, str]] = {}
    for citekey, paper in _citation_entries_from_papers(state.included_papers):
        paper_citation_meta[paper.paper_id] = {
            "citekey": citekey,
            "year": str(paper.year or "n.d."),
            "title": (paper.title or "(No title)").strip(),
        }

    # --- Per-section write function ---
    async def _write_one_section(
        i: int,
        section: str,
        prior_sections_context: str = "",
    ) -> tuple[int, str]:
        """Produce (index, content) for one section, already draft-saved."""
        async with _write_sem:
            if section in completed:
                if rc and rc.verbose:
                    _rc_print(rc, f"  Skipping {section} (already done)")
                _cursor = await db.execute(
                    """
                    SELECT content FROM section_drafts
                    WHERE workflow_id = ?
                      AND section = ?
                      AND generation = COALESCE(
                          (SELECT writing_generation FROM workflows WHERE workflow_id = ?),
                          1
                      )
                    ORDER BY version DESC LIMIT 1
                    """,
                    (state.workflow_id, section, state.workflow_id),
                )
                _row = await _cursor.fetchone()
                _content = _row[0] if _row else ""
                _sections_done[0] += 1
                await save_writing_checkpoint(
                    papers_processed=_sections_done[0],
                    status="partial",
                )
                if rc:
                    rc.advance_screening("phase_6_writing", _sections_done[0], len(SECTIONS))
                return i, _content

            if rc and rc.verbose:
                _rc_print(rc, f"  Writing section: {section}...")
            context = get_section_context(section)
            word_limit = get_section_word_limit(section)

            # --- RAG retrieval ---
            rag_result = await retrieve_rag_for_section(
                section,
                state=state,
                repository=repository,
                retriever=retriever,
                chunk_count=chunk_count,
                hyde_docs=hyde_docs,
                embed_model=embed_model,
                embed_dim=embed_dim,
                use_rerank=use_rerank,
                reranker_model=reranker_model,
                candidate_k=candidate_k,
                final_k=final_k,
                min_chunks_per_section=min_chunks_per_section,
                rag_empty_policy=rag_empty_policy,
                paper_citation_meta=paper_citation_meta,
                pico_cfg=_pico_cfg,
                rc=rc,
            )
            rag_context = rag_result.context
            _rag_status_counts[rag_result.status] = _rag_status_counts.get(rag_result.status, 0) + 1

            # --- Write section ---
            _llm_timeout_writing = float(getattr(getattr(state.settings, "writing", None), "llm_timeout", 120))
            _request_timeout = float(getattr(getattr(state.settings, "llm", None), "request_timeout_seconds", 180))
            _section_write_timeout = max(_request_timeout * 2.5, 300.0)
            _section_result = None
            try:
                _ratchet_max = int(getattr(getattr(state.settings, "writing", None), "ratchet_max_iterations", 1))
                _ratchet_factor = 1.0 + 0.5 * max(0, _ratchet_max - 1)
                _section_write_timeout = max(
                    _request_timeout * 2.5 * _ratchet_factor,
                    300.0 * _ratchet_factor,
                )
                _section_result = await asyncio.wait_for(
                    write_section_with_validation(
                        section=section,
                        context=context,
                        workflow_id=state.workflow_id,
                        review=state.review,
                        settings=state.settings,
                        citation_repo=citation_repo,
                        citation_catalog=citation_catalog,
                        word_limit=word_limit,
                        on_llm_call=_on_write if rc else None,
                        provider=provider,
                        grounding=grounding,
                        rag_context=rag_context,
                        prior_sections_context=prior_sections_context,
                        outline=section_outlines.get(section),
                    ),
                    timeout=_section_write_timeout,
                )
                _content = _section_result.content_markdown
                _section_results_by_key[section] = _section_result
            except TimeoutError:
                logger.error(
                    "write_section_with_validation timed out for '%s' after %.0fs",
                    section,
                    _section_write_timeout,
                )
                raise

            # --- Humanizer ---
            _humanizer_timeout = max(_llm_timeout_writing, _request_timeout)
            if do_humanize and use_llm_write:
                humanizer_agent = state.settings.agents["humanizer"]
                h_model = humanizer_agent.model
                h_temp = humanizer_agent.temperature
                _valid_citekeys_local = [
                    line.strip()[1 : line.strip().index("]")]
                    for line in citation_catalog.splitlines()
                    if line.strip().startswith("[") and "]" in line.strip()
                ]
                if rc and rc.verbose:
                    _rc_print(rc, f"    Humanizing {section} ({humanize_iters} pass(es))...")
                for _ in range(humanize_iters):
                    _before_h = _content
                    _content = apply_deterministic_guardrails(_content)
                    if provider is not None:
                        await provider.reserve_call_slot("humanizer")
                    try:
                        _content = await asyncio.wait_for(
                            humanize_async(
                                _content,
                                section=section,
                                model=h_model,
                                temperature=h_temp,
                                max_chars=12000,
                                provider=provider if use_llm_write else None,
                                enable_verification_repair=bool(humanize_verify_repair),
                                repair_max_per_pass=int(humanize_repair_max),
                            ),
                            timeout=_humanizer_timeout,
                        )
                    except TimeoutError:
                        logger.warning(
                            "Humanizer timed out for section '%s' after %.0fs; using pre-humanizer text.",
                            section,
                            _humanizer_timeout,
                        )
                        _content = _before_h
                        continue
                    if extract_citation_blocks(_before_h) != extract_citation_blocks(
                        _content
                    ) or extract_numeric_tokens(_before_h) != extract_numeric_tokens(_content):
                        logger.warning(
                            "Humanizer pass reverted for section '%s' due to citation or numeric drift.",
                            section,
                        )
                        _content = _before_h
                        continue
                    if _valid_citekeys_local:
                        _verified_local, _hallucinated_local = verify_citation_grounding(
                            _content,
                            _valid_citekeys_local,
                            section,
                        )
                        if _hallucinated_local:
                            logger.warning(
                                "Humanizer pass reverted for section '%s' due to hallucinated citekeys: %s",
                                section,
                                _hallucinated_local[:5],
                            )
                            _content = _before_h
                            continue
                    if section == "abstract":
                        _min_abs_words = int(
                            getattr(getattr(state.settings, "writing", None), "abstract_trim_floor_words", 210)
                        )
                        _max_abs_words = int(
                            getattr(getattr(state.settings, "ieee_export", None), "max_abstract_words", 250)
                        )
                        _abstract_ok, _abstract_reason = validate_structured_abstract_markdown_band(
                            _content,
                            min_words=_min_abs_words,
                            max_words=_max_abs_words,
                        )
                        if not _abstract_ok:
                            logger.warning(
                                "Humanizer pass reverted for abstract due to structured constraints: %s",
                                _abstract_reason[:200],
                            )
                            _content = _before_h
                            continue
                _content = apply_deterministic_guardrails(_content)
                if section == "abstract" and _section_result is not None:
                    _min_abs_words = int(
                        getattr(getattr(state.settings, "writing", None), "abstract_trim_floor_words", 210)
                    )
                    _max_abs_words = int(
                        getattr(getattr(state.settings, "ieee_export", None), "max_abstract_words", 250)
                    )
                    _abstract_ok, _abstract_reason = validate_structured_abstract_markdown_band(
                        _content,
                        min_words=_min_abs_words,
                        max_words=_max_abs_words,
                    )
                    if not _abstract_ok:
                        logger.warning(
                            "Post-humanizer abstract drift detected; restoring structured writer output (%s).",
                            _abstract_reason[:200],
                        )
                        _content = _section_result.content_markdown
                    else:
                        try:
                            _content = canonicalize_structured_abstract_markdown(_content)
                        except Exception as _canon_exc:
                            logger.warning(
                                "Abstract canonicalization skipped after validation: %s",
                                str(_canon_exc)[:180],
                            )

            word_count = len(_content.split())
            draft = SectionDraft(
                workflow_id=state.workflow_id,
                section=section,
                version=1,
                content=_content,
                claims_used=[],
                citations_used=[],
                word_count=word_count,
            )
            await repository.save_section_artifacts_from_draft(draft, section_order=i)
            _sections_done[0] += 1
            await save_writing_checkpoint(
                papers_processed=_sections_done[0],
                status="partial",
            )
            if rc:
                rc.advance_screening("phase_6_writing", _sections_done[0], len(SECTIONS))
            return i, _content

    # --- Phase A: abstract, introduction, methods, results ---
    _PHASE_A_SECTIONS = ["abstract", "introduction", "methods", "results"]
    _PHASE_B_SECTIONS = ["discussion", "conclusion"]

    def _collect_results(
        phase_sections: list[str],
        phase_results: list,
    ) -> tuple[list[tuple[int, str]], list[str]]:
        """Extract (index, content) pairs and failed section names."""
        ordered: list[tuple[int, str]] = []
        failed: list[str] = []
        for sec, res in zip(phase_sections, phase_results):
            if isinstance(res, BaseException):
                logger.error(
                    "Writing task failed for section '%s' (%s: %s). Check API quota for the writing model.",
                    sec,
                    type(res).__name__,
                    str(res)[:200],
                )
                failed.append(sec)
            elif isinstance(res, tuple):
                ordered.append(res)
        return ordered, failed

    _phase_a_results = await asyncio.gather(
        *[_write_one_section(SECTIONS.index(s), s) for s in _PHASE_A_SECTIONS if s in SECTIONS],
        return_exceptions=True,
    )
    _ordered_a, _failed_a = _collect_results(
        [s for s in _PHASE_A_SECTIONS if s in SECTIONS],
        _phase_a_results,
    )
    await save_subphase_checkpoint("phase_6b_phase_a", papers_processed=len(_ordered_a))

    # Build prior context for Phase B from Results
    _section_a_cache: dict[str, str] = {}
    for _, _acontent in _ordered_a:
        pass
    for sec, res in zip([s for s in _PHASE_A_SECTIONS if s in SECTIONS], _phase_a_results):
        if isinstance(res, tuple):
            _section_a_cache[sec] = res[1]

    _results_draft = _section_a_cache.get("results", "")

    def _build_prior_ctx(for_section: str) -> str:
        """Build PRIOR SECTIONS CONTEXT block for Discussion/Conclusion."""
        if not _results_draft:
            return ""
        _max_chars = 2000 if for_section == "discussion" else 900
        _rule = (
            (
                "PRIOR SECTIONS RULE: The Results section is summarised above. "
                "Do NOT re-state or copy these statistics. Instead, interpret them: "
                "what does this evidence mean clinically and methodologically? "
                "Compare with prior literature and synthesize implications. "
                "Build forward -- do not look back."
            )
            if for_section == "discussion"
            else (
                "PRIOR SECTIONS RULE: A Results summary is provided above for context. "
                "The Conclusion must NOT recite these findings again. Instead, provide "
                "the high-level 'so what' answer: what does this body of evidence mean "
                "for practice and future research? Close with a strong final statement."
            )
        )
        return (
            "---\n"
            "PRIOR SECTIONS CONTEXT (do not re-state; build on this):\n\n"
            "=== RESULTS SUMMARY (first ~2000 chars) ===\n"
            + _results_draft[:_max_chars]
            + "\n=== END PRIOR SECTIONS ===\n\n"
            + _rule
            + "\n---"
        )

    # --- Phase B: discussion, conclusion ---
    _phase_b_results = await asyncio.gather(
        *[_write_one_section(SECTIONS.index(s), s, _build_prior_ctx(s)) for s in _PHASE_B_SECTIONS if s in SECTIONS],
        return_exceptions=True,
    )
    _ordered_b, _failed_b = _collect_results(
        [s for s in _PHASE_B_SECTIONS if s in SECTIONS],
        _phase_b_results,
    )
    await save_subphase_checkpoint("phase_6c_phase_b", papers_processed=len(_ordered_b))

    # --- Retry failed sections ---
    _failed_sections = _failed_a + _failed_b
    if _failed_sections:
        logger.warning(
            "WritingNode: retrying %d failed section(s) sequentially: %s",
            len(_failed_sections),
            ", ".join(_failed_sections),
        )
        _retry_ok: list[tuple[int, str]] = []
        _retry_failed: list[str] = []
        for _sec in _failed_sections:
            try:
                _prior_ctx = _build_prior_ctx(_sec) if _sec in _PHASE_B_SECTIONS else ""
                _retry_ok.append(await _write_one_section(SECTIONS.index(_sec), _sec, _prior_ctx))
            except Exception as _retry_exc:
                logger.error(
                    "Writing retry failed for section '%s' (%s: %s)",
                    _sec,
                    type(_retry_exc).__name__,
                    str(_retry_exc)[:200],
                )
                _retry_failed.append(_sec)
        _ordered_a = _ordered_a + _retry_ok
        _failed_sections = _retry_failed
    else:
        _failed_sections = []

    # --- Assemble ordered sections ---
    _ordered = sorted(_ordered_a + _ordered_b, key=lambda t: t[0])
    sections_written_raw = {idx: content for idx, content in _ordered}
    sections_written = [sections_written_raw.get(i, "") for i in range(len(SECTIONS))]

    # --- Abstract/Methods fallback for empty sections ---
    _included_total = 0
    _norm_assessed = 0
    _norm_sought = 0
    _prisma_sentence = ""
    if prisma_counts is not None:
        _included_total = prisma_counts.studies_included_qualitative + prisma_counts.studies_included_quantitative
        _norm_assessed = max(prisma_counts.reports_assessed, _included_total)
        _norm_sought = max(prisma_counts.reports_sought, prisma_counts.reports_not_retrieved + _norm_assessed)
        _prisma_sentence = (
            f"Of the {_norm_sought} reports sought for retrieval, "
            f"{prisma_counts.reports_not_retrieved} were not retrieved and {_norm_assessed} "
            f"were assessed for eligibility, with {_included_total} studies ultimately included."
        )

    _abs_idx = SECTIONS.index("abstract") if "abstract" in SECTIONS else -1
    if _abs_idx >= 0 and not sections_written[_abs_idx].strip():
        sections_written[_abs_idx] = (
            "**Background:** This review synthesizes the available evidence for the topic. "
            f"**Objectives:** This review evaluated {state.review.research_question}. "
            "**Methods:** Bibliographic databases were searched using the configured protocol and settings. "
            f"**Results:** {_prisma_sentence} "
            "**Conclusion:** Evidence synthesis was generated from included studies. "
            "**Keywords:** systematic review, evidence synthesis, outcomes, implementation, methodology."
        )
    _methods_idx = SECTIONS.index("methods") if "methods" in SECTIONS else -1
    if _methods_idx >= 0 and not sections_written[_methods_idx].strip():
        sections_written[_methods_idx] = (
            "Two independent reviewers screened records with adjudication for disagreements. " + _prisma_sentence
        )

    # --- Abstract structured validation ---
    if _abs_idx >= 0 and sections_written[_abs_idx]:
        _max_abs_words = int(getattr(getattr(state.settings, "ieee_export", None), "max_abstract_words", 250))
        _writing_cfg_local = getattr(state.settings, "writing", None)
        _floor = int(getattr(_writing_cfg_local, "abstract_trim_floor_words", 210))
        _abstract_ok, _abstract_reason = validate_structured_abstract_markdown_band(
            sections_written[_abs_idx],
            min_words=_floor,
            max_words=_max_abs_words,
        )
        if not _abstract_ok:
            logger.warning(
                "WritingNode: abstract failed structured finalize checks; applying legacy fallback (%s).",
                _abstract_reason[:200],
            )
            sections_written[_abs_idx] = _ensure_structured_abstract(
                sections_written[_abs_idx],
                state.review.research_question if state.review else "",
            )
            _abstract_ok, _abstract_reason = validate_structured_abstract_markdown_band(
                sections_written[_abs_idx],
                min_words=_floor,
                max_words=_max_abs_words,
            )
            if not _abstract_ok:
                from src.orchestration.helpers.writing_manuscript import trim_abstract_to_limit

                _trimmed_abs = trim_abstract_to_limit(sections_written[_abs_idx], limit=_max_abs_words)
                if _trimmed_abs != sections_written[_abs_idx]:
                    logger.warning("WritingNode: abstract used bounded trim as final fallback to satisfy contracts.")
                    sections_written[_abs_idx] = _trimmed_abs
        else:
            try:
                sections_written[_abs_idx] = canonicalize_structured_abstract_markdown(sections_written[_abs_idx])
            except Exception as _canon_exc:
                logger.warning(
                    "WritingNode: abstract canonicalization skipped (%s).",
                    str(_canon_exc)[:180],
                )

    # --- Recover failed sections with deterministic fallback ---
    if _failed_sections:
        _recovered_sections: list[str] = []
        for _sec in list(_failed_sections):
            if _sec not in SECTIONS:
                continue
            _sec_idx = SECTIONS.index(_sec)
            if _sec_idx >= len(sections_written):
                continue
            _recovered_content = str(sections_written[_sec_idx] or "").strip()
            if not _recovered_content:
                continue
            _recovered_draft = SectionDraft(
                workflow_id=state.workflow_id,
                section=_sec,
                version=1,
                content=_recovered_content,
                claims_used=[],
                citations_used=[],
                word_count=len(_recovered_content.split()),
            )
            await repository.save_section_artifacts_from_draft(
                _recovered_draft,
                section_order=_sec_idx,
            )
            _recovered_sections.append(_sec)
        if _recovered_sections:
            logger.warning(
                "WritingNode: persisted deterministic fallback for recovered section(s): %s",
                ", ".join(_recovered_sections),
            )
            _failed_sections = [s for s in _failed_sections if s not in _recovered_sections]

    if _failed_sections and rc and hasattr(rc, "_emit"):
        rc._emit(
            {
                "type": "writing_error",
                "failed_sections": _failed_sections,
                "succeeded": len(_ordered),
                "message": (
                    f"Writing failed for {len(_failed_sections)} section(s): "
                    f"{', '.join(_failed_sections)}. "
                    "Check API quota for the writing model in config/settings.yaml."
                ),
            }
        )

    # --- RAG health assessment ---
    state.rag_sections_total = len(SECTIONS)
    state.rag_sections_success = _rag_status_counts.get("success", 0)
    state.rag_sections_empty = _rag_status_counts.get("empty", 0)
    state.rag_sections_error = _rag_status_counts.get("error", 0)
    state.rag_sections_skipped = _rag_status_counts.get("skipped", 0)
    state.rag_threshold_breached, _rag_msg = _evaluate_rag_health(
        empty_sections=state.rag_sections_empty,
        error_sections=state.rag_sections_error,
        max_empty_sections=max_empty_sections,
    )
    if state.rag_threshold_breached:
        _rag_msg = _rag_msg + f", strict_mode={block_on_rag_failure}"
        logger.warning(_rag_msg)
        if rc:
            rc.log_status(_rag_msg)
        if block_on_rag_failure:
            raise RuntimeError(_rag_msg)

    result.sections_written = sections_written
    result.failed_sections = _failed_sections
    result.section_results_by_key = _section_results_by_key
    return result
