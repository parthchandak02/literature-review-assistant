"""Dual-reviewer screening workflow with adjudication."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

_log = logging.getLogger(__name__)

from pydantic import ValidationError

from src.db.repositories import WorkflowRepository
from src.llm.provider import LLMProvider
from src.models import (
    BatchScreeningItemPayload,
    BatchScreeningResponsePayload,
    CandidatePaper,
    DecisionLogEntry,
    ExclusionReason,
    ReviewConfig,
    ReviewerType,
    ScreeningDecision,
    ScreeningDecisionType,
    ScreeningResponsePayload,
    SettingsConfig,
)
from src.screening.heuristics import (
    DEFAULT_TITLE_ONLY_ABSTRACT_WORD_THRESHOLD,
    enforce_fulltext_exclusion_reason,
    has_intervention_anchor_match,
    is_insufficient_content,
    is_protocol_only,
)
from src.screening.persistence import (
    persist_insufficient_content_exclusion,
    persist_no_fulltext_exclusion,
    persist_protocol_exclusion,
)
from src.screening.prompts import (
    adjudicator_prompt,
    reviewer_a_prompt,
    reviewer_b_prompt,
)
from src.search.pdf_retrieval import FullTextCoverageSummary, PDFRetrievalResult, PDFRetriever

ScreeningResponse = ScreeningResponsePayload
_BatchScreeningItem = BatchScreeningItemPayload
_BatchScreeningEnvelope = BatchScreeningResponsePayload


class ScreeningLLMClient(Protocol):
    async def complete_json(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
    ) -> str:
        """Return a JSON string matching ScreeningResponse."""

    async def complete_screening_response_with_usage(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
    ) -> tuple[ScreeningResponse, int, int, int, int]:
        """Return a typed screening payload plus usage."""

    async def complete_batch_screening_with_usage(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
        item_schema: dict[str, object],
    ) -> tuple[_BatchScreeningEnvelope, int, int, int, int]:
        """Return a typed batch payload plus usage."""


class HeuristicScreeningClient:
    """Test-only stub. Returns deterministic fake decisions. Use PydanticAIScreeningClient for real runs."""

    async def complete_json(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
    ) -> str:
        lower = prompt.lower()
        if "no full text" in lower or "not retrieved" in lower:
            payload = ScreeningResponse(
                decision=ScreeningDecisionType.EXCLUDE,
                confidence=0.95,
                short_reason="No full text available",
                reasoning="Full text is unavailable for full-text screening.",
                exclusion_reason=ExclusionReason.NO_FULL_TEXT,
            )
        elif "exclude" in lower and "stage: fulltext" in lower and "conference abstract" in lower:
            payload = ScreeningResponse(
                decision=ScreeningDecisionType.EXCLUDE,
                confidence=0.9,
                short_reason="Conference abstract, not peer-reviewed",
                reasoning="Exclusion criterion applies.",
                exclusion_reason=ExclusionReason.NOT_PEER_REVIEWED,
            )
        elif "reviewer b" in lower:
            payload = ScreeningResponse(
                decision=ScreeningDecisionType.UNCERTAIN,
                confidence=0.6,
                short_reason="Borderline, needs adjudication",
                reasoning="Borderline evidence requires adjudication.",
            )
        else:
            payload = ScreeningResponse(
                decision=ScreeningDecisionType.INCLUDE,
                confidence=0.9,
                short_reason="Inclusion criteria met",
                reasoning="Inclusion criteria are plausibly met.",
            )
        return payload.model_dump_json()

    async def complete_screening_response_with_usage(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
    ) -> tuple[ScreeningResponse, int, int, int, int]:
        raw = await self.complete_json(
            prompt,
            agent_name=agent_name,
            model=model,
            temperature=temperature,
        )
        parsed = ScreeningResponse.model_validate_json(raw)
        return parsed, max(1, len(prompt.split())), max(1, len(raw.split())), 0, 0

    async def complete_batch_screening_with_usage(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
        item_schema: dict[str, object],
    ) -> tuple[_BatchScreeningEnvelope, int, int, int, int]:
        _ = item_schema
        raw = await self.complete_json(
            prompt,
            agent_name=agent_name,
            model=model,
            temperature=temperature,
        )
        single = ScreeningResponse.model_validate_json(raw)
        payload = _BatchScreeningEnvelope(
            decisions=[
                _BatchScreeningItem(
                    paper_id="paper-1",
                    decision=single.decision,
                    confidence=single.confidence,
                    short_reason=single.short_reason,
                    reasoning=single.reasoning,
                    exclusion_reason=single.exclusion_reason,
                )
            ]
        )
        return payload, max(1, len(prompt.split())), max(1, len(raw.split())), 0, 0


@dataclass(frozen=True)
class ReviewerSpec:
    agent_name: str
    reviewer_type: ReviewerType


class DualReviewerScreener:
    def __init__(
        self,
        repository: WorkflowRepository,
        provider: LLMProvider,
        review: ReviewConfig,
        settings: SettingsConfig,
        llm_client: ScreeningLLMClient | None = None,
        on_llm_call: Callable[..., None] | None = None,
        on_progress: Callable[[str, int, int], None] | None = None,
        on_prompt: Callable[[str, str, str | None], None] | None = None,
        should_proceed_with_partial: Callable[[], bool] | None = None,
        on_screening_decision: Callable[[str, str, str, str | None, float | None], None] | None = None,
        on_status: Callable[[str], None] | None = None,
    ):
        self.repository = repository
        self.provider = provider
        self.review = review
        self.settings = settings
        self.llm_client = llm_client or HeuristicScreeningClient()
        self.on_llm_call = on_llm_call
        self.on_progress = on_progress
        self.on_prompt = on_prompt
        self.should_proceed_with_partial = should_proceed_with_partial
        self.on_screening_decision = on_screening_decision
        self.on_status = on_status
        # Accumulates DualScreeningResult objects where both reviewers participated.
        # Used by the workflow to compute Cohen's kappa after screening completes.
        self._dual_results: list = []
        # Screening diagnostics surfaced in phase summaries.
        self.fast_path_include_count: int = 0
        self.fast_path_exclude_count: int = 0
        self.cross_review_count: int = 0
        self.batch_parse_degraded_count: int = 0
        self.batch_id_mismatch_count: int = 0
        self.batch_missing_fallback_count: int = 0
        self.contract_violation_count: int = 0

    def _has_intervention_anchor_match(self, paper: CandidatePaper, full_text: str | None = None) -> bool:
        return has_intervention_anchor_match(self.review, paper, full_text)

    async def screen_title_abstract(self, workflow_id: str, paper: CandidatePaper) -> ScreeningDecision:
        result = await self._screen_one(
            workflow_id=workflow_id,
            paper=paper,
            stage="title_abstract",
            full_text=None,
        )
        return result

    async def screen_full_text(self, workflow_id: str, paper: CandidatePaper, full_text: str) -> ScreeningDecision:
        result = await self._screen_one(
            workflow_id=workflow_id,
            paper=paper,
            stage="fulltext",
            full_text=full_text,
        )
        return result

    def reset_partial_flag(self) -> None:
        """Consume any prior partial-proceed signal so the next screen_batch runs to completion.

        Call this between stage 1 and stage 2 so that a Ctrl+C during stage 1
        does not immediately abort stage 2.  A fresh Ctrl+C during stage 2 will
        still be honoured because the callback itself is not altered -- only the
        one-shot 'ignore' gate is cleared on the next reset.
        """
        self._partial_flag_consumed = True

    def _check_partial(self) -> bool:
        """Return True only when the partial-proceed signal is live and unconsumed."""
        if getattr(self, "_partial_flag_consumed", False):
            return False
        return bool(self.should_proceed_with_partial and self.should_proceed_with_partial())

    def _is_insufficient_content(self, paper: CandidatePaper) -> bool:
        return is_insufficient_content(self.settings, paper)

    def _is_protocol_only(self, paper: CandidatePaper) -> bool:
        return is_protocol_only(paper)

    async def screen_batch_for_calibration(
        self,
        workflow_id: str,
        papers: Sequence[CandidatePaper],
        on_progress: object = None,
    ) -> list:
        """Screen papers for calibration, always running both reviewers.

        Unlike screen_batch, this method bypasses the fast-path (single-reviewer
        shortcut) to ensure both reviewers produce a decision for every paper.
        Returns list[DualScreeningResult] so calibrate_threshold can compute
        Cohen's kappa correctly.

        Uses an in-memory DB no-op repository to avoid polluting the real
        workflow's decision log with calibration passes.

        on_progress: optional callable(phase, current, total) called after each
        paper completes so the UI shows live calibration progress instead of
        appearing frozen.
        """
        from src.models import DualScreeningResult

        results: list[DualScreeningResult] = []
        sem = asyncio.Semaphore(self.settings.screening.screening_concurrency)
        total = len(papers)
        completed: list[int] = [0]

        async def _calibrate_one(paper: CandidatePaper) -> DualScreeningResult | None:
            async with sem:
                await self.repository.save_paper(paper)
                # Skip heuristic pre-exclusions: calibration needs both reviewers.
                reviewer_a = await self._run_reviewer(
                    workflow_id=workflow_id,
                    paper=paper,
                    stage="title_abstract",
                    full_text=None,
                    spec=ReviewerSpec(
                        agent_name="screening_reviewer_a",
                        reviewer_type=ReviewerType.REVIEWER_A,
                    ),
                )
                reviewer_b = await self._run_reviewer(
                    workflow_id=workflow_id,
                    paper=paper,
                    stage="title_abstract",
                    full_text=None,
                    spec=ReviewerSpec(
                        agent_name="screening_reviewer_b",
                        reviewer_type=ReviewerType.REVIEWER_B,
                    ),
                    other_reviewer_decision=reviewer_a.decision,
                )
                agreement = reviewer_a.decision == reviewer_b.decision
                result = DualScreeningResult(
                    paper_id=paper.paper_id,
                    reviewer_a=reviewer_a,
                    reviewer_b=reviewer_b,
                    agreement=agreement,
                    final_decision=reviewer_a.decision if agreement else reviewer_b.decision,
                )
                completed[0] += 1
                if callable(on_progress):
                    on_progress("screening_calibration", completed[0], total)
                return result

        raw = await asyncio.gather(*[_calibrate_one(p) for p in papers], return_exceptions=True)
        for item in raw:
            if isinstance(item, DualScreeningResult):
                results.append(item)
            elif isinstance(item, BaseException):
                _log.warning("Calibration screening failed for one paper: %s", item)
        return results

    async def screen_batch(
        self,
        workflow_id: str,
        stage: str,
        papers: Sequence[CandidatePaper],
        full_text_by_paper: dict[str, str] | None = None,
        retriever: PDFRetriever | None = None,
        coverage_report_path: str | None = None,
        on_pdf_progress: Callable[[int, int], None] | None = None,
        on_pdf_result: Callable[[str, str, str, bool, str | None], None] | None = None,
    ) -> list[ScreeningDecision]:
        # Clear consumed flag at the start of every new batch so subsequent
        # Ctrl+C events (after a reset) are still honoured.
        self._partial_flag_consumed = False
        self.last_fulltext_coverage: FullTextCoverageSummary | None = None

        # Determine which papers still need processing BEFORE fetching PDFs so
        # we do not re-download full text for papers that already have a decision
        # saved from an interrupted prior run.  On a fresh run to_process == papers
        # and behaviour is identical; on resume, only the truly unfinished subset
        # is returned and PDF retrieval is scoped to that subset alone.
        processed = await self.repository.get_processed_paper_ids(workflow_id, stage)
        to_process = [p for p in papers if p.paper_id not in processed]

        if stage == "fulltext":
            if full_text_by_paper is None:
                active_retriever = retriever or PDFRetriever()
                _pdf_concurrency = self.settings.screening.pdf_retrieval_concurrency
                _pdf_timeout = self.settings.screening.pdf_retrieval_per_paper_timeout
                if to_process:
                    total_fulltext = len(to_process)
                    full_text_by_paper = {}
                    processed_so_far = 0
                    # Process retrieval in chunks so a single non-cooperative provider call
                    # cannot block the entire phase indefinitely.
                    chunk_size = max(1, _pdf_concurrency)
                    for chunk_start in range(0, total_fulltext, chunk_size):
                        chunk = to_process[chunk_start : chunk_start + chunk_size]
                        chunk_len = len(chunk)
                        chunk_timeout_s = max(
                            float(_pdf_timeout + 15),
                            (float(_pdf_timeout) * float(chunk_len) / float(max(1, _pdf_concurrency))) + 15.0,
                        )

                        def _chunk_progress(done: int, _chunk_total: int) -> None:
                            if on_pdf_progress:
                                on_pdf_progress(processed_so_far + done, total_fulltext)

                        chunk_results: dict[str, PDFRetrievalResult] = {}
                        try:
                            chunk_results, _ = await asyncio.wait_for(
                                active_retriever.retrieve_batch(
                                    chunk,
                                    on_progress=_chunk_progress if on_pdf_progress else None,
                                    concurrency=_pdf_concurrency,
                                    per_paper_timeout=_pdf_timeout,
                                    on_result=on_pdf_result,
                                ),
                                timeout=chunk_timeout_s,
                            )
                        except TimeoutError:
                            _log.warning(
                                "PDF retrieval chunk timed out after %.1fs for workflow %s (%d papers). "
                                "Marking chunk as timeout and continuing.",
                                chunk_timeout_s,
                                workflow_id,
                                chunk_len,
                            )
                            for idx, paper in enumerate(chunk, start=1):
                                chunk_results[paper.paper_id] = PDFRetrievalResult(
                                    paper_id=paper.paper_id,
                                    reason_code="timeout",
                                    success=False,
                                    error=f"chunk timeout after {chunk_timeout_s:.1f}s",
                                )
                                if on_pdf_result:
                                    on_pdf_result(
                                        paper.paper_id,
                                        paper.title,
                                        "abstract",
                                        False,
                                        "timeout",
                                    )
                                if on_pdf_progress:
                                    on_pdf_progress(processed_so_far + idx, total_fulltext)

                        for paper_id, result in chunk_results.items():
                            if result.success and result.full_text.strip():
                                full_text_by_paper[paper_id] = result.full_text
                        processed_so_far += chunk_len

                    coverage = self._coverage_from_map(to_process, full_text_by_paper)
                    skip_no_pdf = self.settings.screening.skip_fulltext_if_no_pdf
                    if not skip_no_pdf:
                        for paper in to_process:
                            if paper.paper_id not in full_text_by_paper:
                                fallback = (paper.abstract or paper.title or "").strip()
                                full_text_by_paper[paper.paper_id] = fallback
                else:
                    coverage = self._coverage_from_map([], {})
                    full_text_by_paper = {}
            else:
                coverage = self._coverage_from_map(to_process, full_text_by_paper)
            self.last_fulltext_coverage = coverage
            await self._persist_fulltext_coverage(
                workflow_id=workflow_id,
                stage=stage,
                coverage=coverage,
                coverage_report_path=coverage_report_path,
            )

        # ------------------------------------------------------------------
        # Batch-mode dispatch: when reviewer_batch_size > 0 send N papers per
        # LLM call instead of one call per paper.
        # ------------------------------------------------------------------
        batch_size = self.settings.screening.reviewer_batch_size
        if batch_size > 0 and to_process:
            return await self._screen_batch_mode(
                workflow_id=workflow_id,
                stage=stage,
                papers=to_process,
                full_texts=full_text_by_paper,
            )

        total = len(to_process)
        concurrency = self.settings.screening.screening_concurrency
        sem = asyncio.Semaphore(concurrency)
        completed_count = 0

        async def _process_one(paper: CandidatePaper) -> ScreeningDecision | None:
            nonlocal completed_count
            async with sem:
                if self._check_partial():
                    return None
                if stage == "fulltext":
                    text = (full_text_by_paper or {}).get(paper.paper_id, "")
                    skip_no_pdf = self.settings.screening.skip_fulltext_if_no_pdf
                    if skip_no_pdf and not text.strip():
                        # Ensure FK integrity: papers table must have a row before
                        # screening_decisions (which has a FK on papers.paper_id).
                        await self.repository.save_paper(paper)
                        result = await persist_no_fulltext_exclusion(
                            self.repository,
                            workflow_id=workflow_id,
                            stage=stage,
                            paper_id=paper.paper_id,
                            on_screening_decision=self.on_screening_decision,
                        )
                    else:
                        result = await self.screen_full_text(workflow_id, paper, text)
                else:
                    result = await self.screen_title_abstract(workflow_id, paper)
                completed_count += 1
                if self.on_progress:
                    self.on_progress("phase_3_screening", completed_count, total)
                return result

        raw_results = await asyncio.gather(*[_process_one(p) for p in to_process], return_exceptions=True)
        decisions: list[ScreeningDecision] = []
        for paper, outcome in zip(to_process, raw_results):
            if isinstance(outcome, BaseException):
                _log.warning(
                    "Screening failed for paper %s (%s): %s -- skipping",
                    paper.paper_id,
                    (paper.title or "")[:60],
                    outcome,
                )
            elif outcome is not None:
                decisions.append(outcome)
        return decisions

    @staticmethod
    def _coverage_from_map(
        papers: Sequence[CandidatePaper],
        full_text_by_paper: dict[str, str],
    ) -> FullTextCoverageSummary:
        attempted = len(papers)
        succeeded_ids = [
            paper.paper_id for paper in papers if (full_text_by_paper.get(paper.paper_id, "").strip() != "")
        ]
        succeeded = len(succeeded_ids)
        failed_ids = [paper.paper_id for paper in papers if paper.paper_id not in set(succeeded_ids)]
        failed = len(failed_ids)
        success_rate = float(succeeded) / float(attempted) if attempted else 0.0
        return FullTextCoverageSummary(
            attempted=attempted,
            succeeded=succeeded,
            failed=failed,
            success_rate=success_rate,
            failed_paper_ids=failed_ids,
        )

    async def _persist_fulltext_coverage(
        self,
        workflow_id: str,
        stage: str,
        coverage: FullTextCoverageSummary,
        coverage_report_path: str | None,
    ) -> None:
        decision = "passed" if coverage.failed == 0 else "partial"
        summary = (
            f"attempted={coverage.attempted}, succeeded={coverage.succeeded}, "
            f"failed={coverage.failed}, success_rate={coverage.success_rate:.2f}"
        )
        await self.repository.append_decision_log(
            DecisionLogEntry(
                decision_type="fulltext_retrieval_coverage",
                paper_id=None,
                decision=decision,
                rationale=summary,
                actor="pdf_retriever",
                phase="phase_3_screening",
            )
        )
        if coverage_report_path is None:
            return
        report = Path(coverage_report_path)
        report.parent.mkdir(parents=True, exist_ok=True)
        failed = ", ".join(coverage.failed_paper_ids) if coverage.failed_paper_ids else "none"
        report.write_text(
            "\n".join(
                [
                    "# Full-Text Retrieval Coverage Report",
                    "",
                    f"- Stage: {stage}",
                    f"- Attempted: {coverage.attempted}",
                    f"- Succeeded: {coverage.succeeded}",
                    f"- Failed: {coverage.failed}",
                    f"- Success rate: {coverage.success_rate:.2f}",
                    f"- Failed paper IDs: {failed}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    async def _screen_one(
        self,
        workflow_id: str,
        paper: CandidatePaper,
        stage: str,
        full_text: str | None,
    ) -> ScreeningDecision:
        # Ensure FK integrity before writing screening decisions.
        await self.repository.save_paper(paper)

        # Protocol-only heuristic pre-check: auto-exclude before any LLM call.
        # Protocols registered on ClinicalTrials.gov/PROSPERO with no results
        # cannot contribute outcome data and must not be counted as included studies.
        if self._is_protocol_only(paper):
            _log.info("Protocol-only heuristic: auto-excluding %s (%s)", paper.paper_id, paper.title)
            proto_decision = await persist_protocol_exclusion(
                self.repository,
                workflow_id=workflow_id,
                stage=stage,
                paper_id=paper.paper_id,
                on_screening_decision=self.on_screening_decision,
            )
            return proto_decision

        # Title-only / insufficient-content heuristic: papers with no extractable abstract
        # cannot be meaningfully screened or have data extracted -- auto-exclude.
        if stage == "title_abstract" and self._is_insufficient_content(paper):
            _abstract_word_count = len((paper.abstract or "").split())
            _log.info(
                "Insufficient-content heuristic: auto-excluding %s (%s) -- abstract word count: %d",
                paper.paper_id,
                paper.title,
                _abstract_word_count,
            )
            _threshold = getattr(
                self.settings.screening,
                "insufficient_content_min_words",
                DEFAULT_TITLE_ONLY_ABSTRACT_WORD_THRESHOLD,
            )
            insuf_decision = await persist_insufficient_content_exclusion(
                self.repository,
                workflow_id=workflow_id,
                stage=stage,
                paper_id=paper.paper_id,
                abstract_word_count=_abstract_word_count,
                min_words_threshold=_threshold,
                on_screening_decision=self.on_screening_decision,
            )
            return insuf_decision

        include_thresh = self.settings.screening.stage1_include_threshold
        exclude_thresh = self.settings.screening.stage1_exclude_threshold

        reviewer_a = await self._run_reviewer(
            workflow_id=workflow_id,
            paper=paper,
            stage=stage,
            full_text=full_text,
            spec=ReviewerSpec(
                agent_name="screening_reviewer_a",
                reviewer_type=ReviewerType.REVIEWER_A,
            ),
        )

        # Confidence fast-path: skip reviewer B when reviewer A is sufficiently certain.
        # Applies to title/abstract only -- full-text screening requires dual review
        # for each study per Cochrane MECIR C39.
        if stage == "fulltext":
            fast_path = False
        else:
            anchor_matched = self._has_intervention_anchor_match(paper, full_text)
            include_fast_path = (
                anchor_matched
                and reviewer_a.confidence >= include_thresh
                and reviewer_a.decision == ScreeningDecisionType.INCLUDE
            )
            exclude_fast_path = (
                reviewer_a.confidence >= exclude_thresh and reviewer_a.decision == ScreeningDecisionType.EXCLUDE
            )
            require_dual_for_exclude = getattr(self.settings.screening, "exclude_fast_path_requires_dual", False)
            fast_path = include_fast_path or (exclude_fast_path and not require_dual_for_exclude)

        if fast_path:
            final_decision = reviewer_a
            adjudication_needed = False
            agreement = True
            if final_decision.decision == ScreeningDecisionType.INCLUDE:
                self.fast_path_include_count += 1
            else:
                self.fast_path_exclude_count += 1
        else:
            reviewer_b = await self._run_reviewer(
                workflow_id=workflow_id,
                paper=paper,
                stage=stage,
                full_text=full_text,
                spec=ReviewerSpec(
                    agent_name="screening_reviewer_b",
                    reviewer_type=ReviewerType.REVIEWER_B,
                ),
                other_reviewer_decision=reviewer_a.decision,
            )
            agreement = reviewer_a.decision == reviewer_b.decision
            from src.models import DualScreeningResult

            self._dual_results.append(
                DualScreeningResult(
                    paper_id=paper.paper_id,
                    reviewer_a=reviewer_a,
                    reviewer_b=reviewer_b,
                    agreement=agreement,
                    final_decision=reviewer_a.decision if agreement else reviewer_b.decision,
                )
            )
            if agreement:
                final_decision = reviewer_a
                adjudication_needed = False
            else:
                adjudication = await self._run_adjudicator(
                    workflow_id=workflow_id,
                    paper=paper,
                    stage=stage,
                    full_text=full_text,
                    reviewer_a=reviewer_a,
                    reviewer_b=reviewer_b,
                )
                final_decision = adjudication
                adjudication_needed = True
            self.cross_review_count += 1

        if stage == "fulltext" and final_decision.decision == ScreeningDecisionType.EXCLUDE:
            final_decision = self._enforce_fulltext_exclusion_reason(final_decision)

        await self.repository.save_dual_screening_result(
            workflow_id=workflow_id,
            paper_id=paper.paper_id,
            stage=stage,
            agreement=agreement,
            final_decision=final_decision.decision,
            adjudication_needed=adjudication_needed,
        )
        await self.repository.append_decision_log(
            DecisionLogEntry(
                decision_type="dual_screening_final",
                paper_id=paper.paper_id,
                decision=final_decision.decision.value,
                rationale=final_decision.reason or "Final decision from dual-review workflow.",
                actor="dual_screener",
                phase="phase_3_screening",
            )
        )
        if self.on_screening_decision is not None:
            self.on_screening_decision(
                paper.paper_id,
                stage,
                final_decision.decision.value,
                final_decision.reason,
                final_decision.confidence,
            )
        return final_decision

    # ------------------------------------------------------------------
    # Batch reviewer helpers
    # ------------------------------------------------------------------

    _BATCH_SYSTEM_PROMPT = (
        "You are a systematic review screener. Screen each paper below.\n"
        "\n"
        "MANDATORY DATA QUALITY EXCLUSION CRITERIA (apply first, before topic relevance):\n"
        "EXCLUDE with exclusion_reason=insufficient_data if ANY apply:\n"
        "- No authors listed; editorial/letter/opinion with no empirical data\n"
        "- Conference abstract only; purely theoretical; no measurable outcomes\n"
        "EXCLUDE with exclusion_reason=protocol_only if paper is a registered protocol\n"
        "with no reported results.\n"
        "\n"
        "Return ONLY valid JSON with this exact object shape:\n"
        "{\n"
        '  "decisions": [\n'
        "    {\n"
        '      "paper_id": "<id>",\n'
        '      "decision": "include|exclude|uncertain",\n'
        '      "confidence": 0.0,\n'
        '      "short_reason": "<max 80 chars>",\n'
        '      "reasoning": "<justification>",\n'
        '      "exclusion_reason": "<code or null>"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "\n"
        "Allowed exclusion_reason values: wrong_population, wrong_intervention, "
        "wrong_comparator, wrong_outcome, wrong_study_design, not_peer_reviewed, "
        "duplicate, insufficient_data, wrong_language, no_full_text, protocol_only, other.\n"
        "Use null when decision is include or uncertain."
    )

    def _build_batch_prompt(
        self,
        papers: list[CandidatePaper],
        stage: str,
        full_texts: dict[str, str],
        spec: ReviewerSpec,
    ) -> str:
        """Build a single prompt that asks the LLM to screen all papers in one call."""
        from src.screening.prompts import _topic_header

        role = (
            "Reviewer A (recall-biased)"
            if spec.reviewer_type == ReviewerType.REVIEWER_A
            else "Reviewer B (precision-biased)"
        )
        goal = f"Screen papers for inclusion in a systematic review on: {self.review.research_question}"
        backstory = f"Domain: {self.review.domain}. Favour recall when uncertain."

        header = _topic_header(self.review, role, goal, backstory)
        lines = [header, self._BATCH_SYSTEM_PROMPT, "", "Papers to screen:"]
        allowed_ids: list[str] = []
        for paper in papers:
            text = full_texts.get(paper.paper_id, "") if stage == "fulltext" else ""
            content = (text[:1200] if text else (paper.abstract or ""))[:600].replace("\n", " ")
            lines.append(f"paper_id={paper.paper_id} | {paper.title} | {content}")
            allowed_ids.append(paper.paper_id)
        lines.extend(
            [
                "",
                "CONSTRAINT: Return decisions ONLY for the exact paper_id values listed below.",
                "Any decision for an unlisted paper_id will be ignored and retried individually.",
                "Allowed paper_ids:",
                ", ".join(allowed_ids),
            ]
        )
        return "\n".join(lines)

    def _parse_batch_response(
        self,
        raw: str,
        papers: list[CandidatePaper],
        spec: ReviewerSpec,
        stage: str,
        allowed_paper_ids: set[str] | None = None,
    ) -> tuple[dict[str, ScreeningDecision], dict[str, int]]:
        """Parse a JSON batch response into a paper_id -> ScreeningDecision map.

        Returns only the paper_ids that were successfully parsed. Missing or
        unparseable papers are handled by the caller (fallback to individual call).
        """
        stats = {
            "returned_items": 0,
            "normalized_items": 0,
            "validated_items": 0,
            "out_of_chunk_items": 0,
            "schema_mismatch": 0,
            "json_parse_failed": 0,
        }
        s = raw.strip()
        parsed_payload: object | None = None
        try:
            parsed_payload = json.loads(s)
        except json.JSONDecodeError:
            parsed_payload = None

        if parsed_payload is None:
            stats["json_parse_failed"] = 1
            return {}, stats

        items: object = parsed_payload
        if isinstance(parsed_payload, dict):
            try:
                items = _BatchScreeningEnvelope.model_validate(parsed_payload).decisions
            except Exception:
                items = parsed_payload.get("decisions")
        if not isinstance(items, list):
            stats["schema_mismatch"] = 1
            return {}, stats

        result: dict[str, ScreeningDecision] = {}
        index_to_paper_id = {str(i): paper.paper_id for i, paper in enumerate(papers, start=1)}
        for item in items:
            if hasattr(item, "model_dump"):
                item = item.model_dump()
            if not isinstance(item, dict):
                continue
            stats["returned_items"] += 1
            normalized = self._normalize_batch_item(
                item,
                index_to_paper_id=index_to_paper_id,
                allowed_paper_ids=allowed_paper_ids,
            )
            if normalized is None:
                continue
            stats["normalized_items"] += 1
            try:
                parsed = _BatchScreeningItem.model_validate(normalized)
            except Exception as exc:
                _log.warning("Batch screening item validation failed: %s | item=%s", exc, normalized)
                continue
            stats["validated_items"] += 1
            if allowed_paper_ids is not None and parsed.paper_id not in allowed_paper_ids:
                stats["out_of_chunk_items"] += 1
                continue
            decision = ScreeningDecision(
                paper_id=parsed.paper_id,
                decision=parsed.decision,
                reason=parsed.reasoning,
                exclusion_reason=parsed.exclusion_reason,
                reviewer_type=spec.reviewer_type,
                confidence=parsed.confidence,
            )
            if stage == "fulltext" and decision.decision == ScreeningDecisionType.EXCLUDE:
                decision = self._enforce_fulltext_exclusion_reason(decision)
            result[parsed.paper_id] = decision
        return result, stats

    @staticmethod
    def _normalize_batch_item(
        item: dict[str, object],
        *,
        index_to_paper_id: dict[str, str] | None = None,
        allowed_paper_ids: set[str] | None = None,
    ) -> dict[str, object] | None:
        """Normalize a loose batch item into _BatchScreeningItem-compatible keys.

        Keeps decision and exclusion_reason strongly typed while tolerating
        common output drift (id key variants, missing confidence/reasoning).
        """

        def _coerce_pid(value: object) -> str | None:
            if isinstance(value, bool) or value is None:
                return None
            if isinstance(value, (int, float)):
                token = str(int(value))
            elif isinstance(value, str):
                token = value.strip()
            else:
                return None
            if not token:
                return None
            if allowed_paper_ids is not None and token in allowed_paper_ids:
                return token
            if index_to_paper_id:
                if token in index_to_paper_id:
                    return index_to_paper_id[token]
                if token.startswith("[") and token.endswith("]"):
                    inner = token[1:-1].strip()
                    if inner.isdigit() and 1 <= len(inner) <= 3:
                        mapped = index_to_paper_id.get(inner)
                        if mapped:
                            return mapped
                normalized = token.lower().replace("_", "").replace("-", "").replace(":", "").replace(" ", "")
                for prefix in ("paper", "item", "idx", "index"):
                    if normalized.startswith(prefix):
                        suffix = normalized[len(prefix) :]
                        if suffix.isdigit() and 1 <= len(suffix) <= 3:
                            mapped = index_to_paper_id.get(suffix)
                            if mapped:
                                return mapped
                if token.isdigit() and token in index_to_paper_id:
                    mapped = index_to_paper_id.get(token)
                    if mapped:
                        return mapped
            return token

        pid = _coerce_pid(item.get("paper_id") or item.get("paperId") or item.get("id"))
        if pid is None:
            pid = _coerce_pid(item.get("index") or item.get("paper_index") or item.get("idx"))
        if pid is None:
            return None

        raw_decision = item.get("decision") or item.get("final_decision")
        if not isinstance(raw_decision, str):
            return None
        decision = raw_decision.strip().lower()

        confidence_value = item.get("confidence", item.get("score", 0.5))
        try:
            confidence = float(confidence_value)
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))

        short_reason = item.get("short_reason")
        if short_reason is None:
            short_reason = item.get("reason")
        if short_reason is not None:
            short_reason = str(short_reason)

        reasoning_value = item.get("reasoning")
        if reasoning_value is None:
            reasoning_value = item.get("reason")
        if reasoning_value is None:
            reasoning = "Batch response omitted reasoning."
        else:
            reasoning = str(reasoning_value)

        normalized: dict[str, object] = {
            "paper_id": pid.strip(),
            "decision": decision,
            "confidence": confidence,
            "short_reason": short_reason,
            "reasoning": reasoning,
        }

        raw_exclusion = item.get("exclusion_reason")
        if isinstance(raw_exclusion, str):
            exclusion_candidate = raw_exclusion.strip().lower()
            valid_reasons = {reason.value for reason in ExclusionReason}
            normalized["exclusion_reason"] = exclusion_candidate if exclusion_candidate in valid_reasons else None
        else:
            normalized["exclusion_reason"] = None
        return normalized

    async def _batch_run_reviewer(
        self,
        workflow_id: str,
        papers: list[CandidatePaper],
        stage: str,
        full_texts: dict[str, str],
        spec: ReviewerSpec,
    ) -> dict[str, ScreeningDecision]:
        """Send N papers to the LLM in one call; return paper_id -> ScreeningDecision.

        Papers missing from the response are NOT included in the returned dict.
        The caller is responsible for falling back to individual _run_reviewer()
        for any paper whose paper_id is absent.
        """
        if not papers:
            return {}
        prompt = self._build_batch_prompt(papers, stage, full_texts, spec)
        allowed_paper_ids = {paper.paper_id for paper in papers}
        item_schema = _BatchScreeningItem.model_json_schema()
        # Enforce an explicit paper_id allow-list in schema so the model cannot
        # invent or drift to non-chunk identifiers.
        properties = item_schema.get("properties")
        if isinstance(properties, dict):
            paper_id_schema = properties.get("paper_id")
            if isinstance(paper_id_schema, dict):
                paper_id_schema["enum"] = sorted(allowed_paper_ids)
        if self.on_prompt:
            self.on_prompt(spec.agent_name, prompt, None)
        runtime = await self.provider.reserve_call_slot(spec.agent_name)
        started = time.perf_counter()
        try:
            parsed_batch: _BatchScreeningEnvelope | None = None
            if hasattr(self.llm_client, "complete_json_with_usage"):
                if hasattr(self.llm_client, "complete_batch_screening_with_usage"):
                    (
                        parsed_batch,
                        tokens_in,
                        tokens_out,
                        cache_write,
                        cache_read,
                    ) = await self.llm_client.complete_batch_screening_with_usage(
                        prompt,
                        agent_name=spec.agent_name,
                        model=runtime.model,
                        temperature=runtime.temperature,
                        item_schema=item_schema,
                    )
                    raw = parsed_batch.model_dump_json()
                elif hasattr(self.llm_client, "complete_json_array_with_usage"):
                    (
                        raw,
                        tokens_in,
                        tokens_out,
                        cache_write,
                        cache_read,
                    ) = await self.llm_client.complete_json_array_with_usage(
                        prompt,
                        agent_name=spec.agent_name,
                        model=runtime.model,
                        temperature=runtime.temperature,
                        item_schema=item_schema,
                    )
                else:
                    (
                        raw,
                        tokens_in,
                        tokens_out,
                        cache_write,
                        cache_read,
                    ) = await self.llm_client.complete_json_with_usage(
                        prompt,
                        agent_name=spec.agent_name,
                        model=runtime.model,
                        temperature=runtime.temperature,
                    )
            else:
                raw = await self.llm_client.complete_json(
                    prompt,
                    agent_name=spec.agent_name,
                    model=runtime.model,
                    temperature=runtime.temperature,
                )
                tokens_in = max(1, len(prompt.split()))
                tokens_out = max(1, len(raw.split()))
                cache_write = cache_read = 0
        except Exception as exc:
            _log.warning(
                "Batch reviewer call failed (%s) -- all %d papers fall back to individual calls", exc, len(papers)
            )
            return {}
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        cost_usd = self.provider.estimate_cost(runtime.model, tokens_in, tokens_out, cache_write, cache_read)
        await self.provider.log_cost(
            model=runtime.model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            latency_ms=elapsed_ms,
            phase="phase_3_screening",
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
        )
        if self.on_llm_call:
            self.on_llm_call(
                source=spec.agent_name,
                status="success",
                phase="phase_3_screening",
                call_type=f"batch_reviewer_{len(papers)}p",
                model=runtime.model,
                latency_ms=elapsed_ms,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost_usd,
            )
        parsed_map, parse_stats = self._parse_batch_response(
            raw,
            papers,
            spec,
            stage,
            allowed_paper_ids=allowed_paper_ids,
        )
        parsed_count = len(parsed_map)
        fallback_count = max(0, len(papers) - parsed_count)
        out_of_chunk_count = parse_stats["out_of_chunk_items"]
        if out_of_chunk_count > 0:
            self.batch_id_mismatch_count += out_of_chunk_count
            _log.warning(
                "Batch %s returned %d out-of-chunk paper_ids; ignored",
                spec.reviewer_type.value,
                out_of_chunk_count,
            )
            if self.on_status:
                self.on_status(
                    f"Batch {spec.reviewer_type.value} id mismatch: ignored {out_of_chunk_count} out-of-chunk paper_ids"
                )
            await self.repository.append_decision_log(
                DecisionLogEntry(
                    decision_type="screening_batch_id_mismatch",
                    paper_id=None,
                    decision=f"ignored_{out_of_chunk_count}_out_of_chunk_ids",
                    rationale=(
                        f"returned_items={parse_stats['returned_items']}, "
                        f"normalized_items={parse_stats['normalized_items']}, "
                        f"validated_items={parse_stats['validated_items']}, "
                        f"stage={stage}, reviewer={spec.reviewer_type.value}"
                    ),
                    actor=spec.reviewer_type.value,
                    phase="phase_3_screening",
                )
            )
        if fallback_count > 0:
            self.batch_parse_degraded_count += fallback_count
            _log.warning(
                "Batch %s parse coverage degraded: parsed %d/%d; %d papers require fallback "
                "(parse_failed=%d schema_mismatch=%d out_of_chunk=%d)",
                spec.reviewer_type.value,
                parsed_count,
                len(papers),
                fallback_count,
                parse_stats["json_parse_failed"],
                parse_stats["schema_mismatch"],
                out_of_chunk_count,
            )
            if self.on_status:
                self.on_status(
                    f"Batch {spec.reviewer_type.value} parse degraded: parsed {parsed_count}/{len(papers)}; "
                    f"fallback {fallback_count} "
                    f"(parse_failed={parse_stats['json_parse_failed']} "
                    f"schema_mismatch={parse_stats['schema_mismatch']} "
                    f"out_of_chunk={out_of_chunk_count})"
                )
            await self.repository.append_decision_log(
                DecisionLogEntry(
                    decision_type="screening_batch_parse_coverage",
                    paper_id=None,
                    decision=f"parsed_{parsed_count}_of_{len(papers)}",
                    rationale=(
                        f"fallback_count={fallback_count}, "
                        f"out_of_chunk_count={out_of_chunk_count}, "
                        f"parse_failed={parse_stats['json_parse_failed']}, "
                        f"schema_mismatch={parse_stats['schema_mismatch']}, "
                        f"stage={stage}, reviewer={spec.reviewer_type.value}"
                    ),
                    actor=spec.reviewer_type.value,
                    phase="phase_3_screening",
                )
            )
        # Persist decisions + decision log for papers that were parsed.
        for paper in papers:
            decision = parsed_map.get(paper.paper_id)
            if decision is None:
                continue
            await self.repository.save_screening_decision(workflow_id=workflow_id, stage=stage, decision=decision)
            await self.repository.append_decision_log(
                DecisionLogEntry(
                    decision_type="screening_reviewer_decision",
                    paper_id=paper.paper_id,
                    decision=decision.decision.value,
                    rationale=decision.reason or "Batch reviewer decision.",
                    actor=decision.reviewer_type.value,
                    phase="phase_3_screening",
                )
            )
        return parsed_map

    async def _screen_batch_mode(
        self,
        workflow_id: str,
        stage: str,
        papers: list[CandidatePaper],
        full_texts: dict[str, str] | None,
    ) -> list[ScreeningDecision]:
        """Screen papers in batches: one LLM call per chunk for Reviewer A,
        then one call per uncertain-remainder chunk for Reviewer B.
        Adjudication and DB writes are handled per-paper.

        Preserves the fast-path (high-confidence A decisions skip Reviewer B),
        all on_progress / on_screening_decision callbacks, and DB write semantics
        identical to the per-paper path.
        """
        from src.models import DualScreeningResult

        batch_size = self.settings.screening.reviewer_batch_size
        ft = full_texts or {}
        include_thresh = self.settings.screening.stage1_include_threshold
        exclude_thresh = self.settings.screening.stage1_exclude_threshold

        spec_a = ReviewerSpec(agent_name="screening_reviewer_a", reviewer_type=ReviewerType.REVIEWER_A)
        spec_b = ReviewerSpec(agent_name="screening_reviewer_b", reviewer_type=ReviewerType.REVIEWER_B)

        # Heuristic pre-filters (no-full-text, protocol-only, insufficient-content) still run
        # per-paper before any LLM call, identical to the per-paper path.
        skip_no_pdf = self.settings.screening.skip_fulltext_if_no_pdf
        heuristic_decisions: dict[str, ScreeningDecision] = {}
        llm_candidates: list[CandidatePaper] = []
        for paper in papers:
            await self.repository.save_paper(paper)
            # Gate: if full-text screening and no PDF was retrieved, auto-exclude.
            # Must mirror the _process_one path so skip_fulltext_if_no_pdf is enforced
            # regardless of whether batch mode or per-paper mode is active.
            if stage == "fulltext" and skip_no_pdf and not ft.get(paper.paper_id, "").strip():
                d = await persist_no_fulltext_exclusion(
                    self.repository,
                    workflow_id=workflow_id,
                    stage=stage,
                    paper_id=paper.paper_id,
                    on_screening_decision=self.on_screening_decision,
                )
                heuristic_decisions[paper.paper_id] = d
                continue
            if self._is_protocol_only(paper):
                d = await persist_protocol_exclusion(
                    self.repository,
                    workflow_id=workflow_id,
                    stage=stage,
                    paper_id=paper.paper_id,
                    on_screening_decision=self.on_screening_decision,
                )
                heuristic_decisions[paper.paper_id] = d
                continue
            if stage == "title_abstract" and self._is_insufficient_content(paper):
                wc = len((paper.abstract or "").split())
                _threshold = getattr(
                    self.settings.screening,
                    "insufficient_content_min_words",
                    DEFAULT_TITLE_ONLY_ABSTRACT_WORD_THRESHOLD,
                )
                d = await persist_insufficient_content_exclusion(
                    self.repository,
                    workflow_id=workflow_id,
                    stage=stage,
                    paper_id=paper.paper_id,
                    abstract_word_count=wc,
                    min_words_threshold=_threshold,
                    on_screening_decision=self.on_screening_decision,
                )
                heuristic_decisions[paper.paper_id] = d
                continue
            llm_candidates.append(paper)

        # ------------------------------------------------------------------
        # Phase 1: Reviewer A -- chunked batch calls
        # ------------------------------------------------------------------
        reviewer_a_map: dict[str, ScreeningDecision] = {}
        chunks = [llm_candidates[i : i + batch_size] for i in range(0, len(llm_candidates), batch_size)]
        n_chunks = len(chunks)
        phase_started = time.perf_counter()
        for chunk_idx, chunk in enumerate(chunks):
            papers_done = len(heuristic_decisions) + chunk_idx * batch_size
            if self.on_status:
                self.on_status(
                    f"Reviewer A: batch {chunk_idx + 1}/{n_chunks} starting "
                    f"({papers_done}/{len(papers)} papers done, "
                    f"phase elapsed {int(time.perf_counter() - phase_started)}s)"
                )
            batch_start = time.perf_counter()
            batch_result = await self._batch_run_reviewer(workflow_id, chunk, stage, ft, spec_a)
            batch_elapsed_ms = int((time.perf_counter() - batch_start) * 1000)
            reviewer_a_map.update(batch_result)
            # Fallback: any paper missing from the batch response is individually reviewed.
            for paper in chunk:
                if paper.paper_id not in reviewer_a_map:
                    self.batch_missing_fallback_count += 1
                    _log.warning("Batch A missing paper %s -- falling back to individual call", paper.paper_id)
                    if self.on_status:
                        self.on_status(f"Batch A missing paper {paper.paper_id} -- falling back to individual call")
                    d = await self._run_reviewer(workflow_id, paper, stage, ft.get(paper.paper_id), spec_a)
                    reviewer_a_map[paper.paper_id] = d
            papers_done_after = len(heuristic_decisions) + (chunk_idx + 1) * batch_size
            if self.on_status:
                self.on_status(
                    f"Reviewer A: batch {chunk_idx + 1}/{n_chunks} done in {batch_elapsed_ms}ms "
                    f"({min(papers_done_after, len(papers))}/{len(papers)} papers, "
                    f"phase elapsed {int(time.perf_counter() - phase_started)}s)"
                )

        # ------------------------------------------------------------------
        # Phase 2: Apply fast-path; collect uncertain papers for Reviewer B
        # ------------------------------------------------------------------
        fast_path_decisions: dict[str, ScreeningDecision] = {}
        uncertain_papers: list[CandidatePaper] = []
        uncertain_reviewer_a: dict[str, ScreeningDecision] = {}
        require_dual_for_exclude = getattr(self.settings.screening, "exclude_fast_path_requires_dual", False)
        for paper in llm_candidates:
            a = reviewer_a_map[paper.paper_id]
            # Fast-path applies to title/abstract only.
            # Full-text screening requires dual review for all papers (Cochrane MECIR C39).
            if stage == "fulltext":
                is_fast = False
            else:
                anchor_matched = self._has_intervention_anchor_match(paper, ft.get(paper.paper_id))
                include_fast = (
                    anchor_matched and a.confidence >= include_thresh and a.decision == ScreeningDecisionType.INCLUDE
                )
                exclude_fast = a.confidence >= exclude_thresh and a.decision == ScreeningDecisionType.EXCLUDE
                is_fast = include_fast or (exclude_fast and not require_dual_for_exclude)
            if is_fast:
                fast_path_decisions[paper.paper_id] = a
            else:
                uncertain_papers.append(paper)
                uncertain_reviewer_a[paper.paper_id] = a

        # ------------------------------------------------------------------
        # Phase 3: Reviewer B -- batched for uncertain papers only
        # ------------------------------------------------------------------
        reviewer_b_map: dict[str, ScreeningDecision] = {}
        if uncertain_papers:
            b_chunks = [uncertain_papers[i : i + batch_size] for i in range(0, len(uncertain_papers), batch_size)]
            n_b_chunks = len(b_chunks)
            if self.on_status:
                self.on_status(
                    f"Reviewer B: {len(uncertain_papers)} uncertain papers need cross-review ({n_b_chunks} batches)"
                )
            for b_idx, chunk in enumerate(b_chunks):
                if self.on_status:
                    self.on_status(
                        f"Reviewer B: batch {b_idx + 1}/{n_b_chunks} starting "
                        f"({b_idx * batch_size}/{len(uncertain_papers)} cross-reviewed, "
                        f"phase elapsed {int(time.perf_counter() - phase_started)}s)"
                    )
                b_batch_start = time.perf_counter()
                batch_result = await self._batch_run_reviewer(workflow_id, chunk, stage, ft, spec_b)
                b_batch_elapsed_ms = int((time.perf_counter() - b_batch_start) * 1000)
                reviewer_b_map.update(batch_result)
                for paper in chunk:
                    if paper.paper_id not in reviewer_b_map:
                        self.batch_missing_fallback_count += 1
                        _log.warning("Batch B missing paper %s -- falling back to individual call", paper.paper_id)
                        if self.on_status:
                            self.on_status(f"Batch B missing paper {paper.paper_id} -- falling back to individual call")
                        d = await self._run_reviewer(
                            workflow_id,
                            paper,
                            stage,
                            ft.get(paper.paper_id),
                            spec_b,
                            other_reviewer_decision=uncertain_reviewer_a[paper.paper_id].decision,
                        )
                        reviewer_b_map[paper.paper_id] = d
                if self.on_status:
                    self.on_status(
                        f"Reviewer B: batch {b_idx + 1}/{n_b_chunks} done in {b_batch_elapsed_ms}ms "
                        f"({min((b_idx + 1) * batch_size, len(uncertain_papers))}/{len(uncertain_papers)} cross-reviewed, "
                        f"phase elapsed {int(time.perf_counter() - phase_started)}s)"
                    )
        else:
            if self.on_status and stage != "fulltext":
                self.on_status(
                    f"Reviewer B: skipped for title/abstract stage -- all {len(fast_path_decisions)} "
                    f"papers had high-confidence Reviewer A decisions "
                    f"(thresholds: include>={round(include_thresh * 100)}%, "
                    f"exclude>={round(exclude_thresh * 100)}%)"
                )

        # ------------------------------------------------------------------
        # Phase 4: Adjudication, dual_screening_results, callbacks -- all per-paper
        # ------------------------------------------------------------------
        if self.on_status:
            n_fast = len(fast_path_decisions)
            n_uncertain = len(uncertain_papers)
            self.on_status(f"Adjudicating {len(papers)} papers: {n_fast} fast-path, {n_uncertain} needed cross-review")
        self.fast_path_include_count += sum(
            1 for d in fast_path_decisions.values() if d.decision == ScreeningDecisionType.INCLUDE
        )
        self.fast_path_exclude_count += sum(
            1 for d in fast_path_decisions.values() if d.decision == ScreeningDecisionType.EXCLUDE
        )
        self.cross_review_count += len(uncertain_papers)
        final_decisions: list[ScreeningDecision] = []
        completed = [0]
        total = len(papers)

        async def _finalize_heuristic(paper: CandidatePaper) -> ScreeningDecision:
            d = heuristic_decisions[paper.paper_id]
            await self.repository.save_dual_screening_result(
                workflow_id=workflow_id,
                paper_id=paper.paper_id,
                stage=stage,
                agreement=True,
                final_decision=d.decision,
                adjudication_needed=False,
            )
            completed[0] += 1
            if self.on_progress:
                self.on_progress("phase_3_screening", completed[0], total)
            return d

        async def _finalize_fast_path(paper: CandidatePaper) -> ScreeningDecision:
            d = fast_path_decisions[paper.paper_id]
            await self.repository.save_dual_screening_result(
                workflow_id=workflow_id,
                paper_id=paper.paper_id,
                stage=stage,
                agreement=True,
                final_decision=d.decision,
                adjudication_needed=False,
            )
            await self.repository.append_decision_log(
                DecisionLogEntry(
                    decision_type="dual_screening_final",
                    paper_id=paper.paper_id,
                    decision=d.decision.value,
                    rationale=d.reason or "Fast-path: Reviewer A high-confidence decision.",
                    actor="dual_screener",
                    phase="phase_3_screening",
                )
            )
            if self.on_screening_decision is not None:
                self.on_screening_decision(paper.paper_id, stage, d.decision.value, d.reason, d.confidence)
            completed[0] += 1
            if self.on_progress:
                self.on_progress("phase_3_screening", completed[0], total)
            return d

        async def _finalize_dual(paper: CandidatePaper) -> ScreeningDecision:
            a = uncertain_reviewer_a[paper.paper_id]
            b = reviewer_b_map[paper.paper_id]
            agreement = a.decision == b.decision
            self._dual_results.append(
                DualScreeningResult(
                    paper_id=paper.paper_id,
                    reviewer_a=a,
                    reviewer_b=b,
                    agreement=agreement,
                    final_decision=a.decision if agreement else b.decision,
                )
            )
            if agreement:
                final = a
                adjudication_needed = False
            else:
                final = await self._run_adjudicator(
                    workflow_id=workflow_id,
                    paper=paper,
                    stage=stage,
                    full_text=ft.get(paper.paper_id),
                    reviewer_a=a,
                    reviewer_b=b,
                )
                adjudication_needed = True
            if stage == "fulltext" and final.decision == ScreeningDecisionType.EXCLUDE:
                final = self._enforce_fulltext_exclusion_reason(final)
            await self.repository.save_dual_screening_result(
                workflow_id=workflow_id,
                paper_id=paper.paper_id,
                stage=stage,
                agreement=agreement,
                final_decision=final.decision,
                adjudication_needed=adjudication_needed,
            )
            await self.repository.append_decision_log(
                DecisionLogEntry(
                    decision_type="dual_screening_final",
                    paper_id=paper.paper_id,
                    decision=final.decision.value,
                    rationale=final.reason or "Final decision from dual-review workflow.",
                    actor="dual_screener",
                    phase="phase_3_screening",
                )
            )
            if self.on_screening_decision is not None:
                self.on_screening_decision(paper.paper_id, stage, final.decision.value, final.reason, final.confidence)
            completed[0] += 1
            if self.on_progress:
                self.on_progress("phase_3_screening", completed[0], total)
            return final

        for paper in papers:
            if paper.paper_id in heuristic_decisions:
                final_decisions.append(await _finalize_heuristic(paper))
            elif paper.paper_id in fast_path_decisions:
                final_decisions.append(await _finalize_fast_path(paper))
            else:
                final_decisions.append(await _finalize_dual(paper))

        return final_decisions

    async def _run_reviewer(
        self,
        workflow_id: str,
        paper: CandidatePaper,
        stage: str,
        full_text: str | None,
        spec: ReviewerSpec,
        other_reviewer_decision: ScreeningDecisionType | None = None,
    ) -> ScreeningDecision:
        if spec.reviewer_type == ReviewerType.REVIEWER_A:
            prompt = reviewer_a_prompt(self.review, paper, stage, full_text)
        else:
            prompt = reviewer_b_prompt(self.review, paper, stage, full_text)
        decision = await self._request_decision(
            prompt=prompt,
            spec=spec,
            workflow_id=workflow_id,
            paper_id=paper.paper_id,
            other_reviewer_decision=other_reviewer_decision,
        )
        if stage == "fulltext" and decision.decision == ScreeningDecisionType.EXCLUDE:
            decision = self._enforce_fulltext_exclusion_reason(decision)
        await self.repository.save_screening_decision(workflow_id=workflow_id, stage=stage, decision=decision)
        await self.repository.append_decision_log(
            DecisionLogEntry(
                decision_type="screening_reviewer_decision",
                paper_id=paper.paper_id,
                decision=decision.decision.value,
                rationale=decision.reason or "Reviewer decision generated.",
                actor=decision.reviewer_type.value,
                phase="phase_3_screening",
            )
        )
        return decision

    async def _run_adjudicator(
        self,
        workflow_id: str,
        paper: CandidatePaper,
        stage: str,
        full_text: str | None,
        reviewer_a: ScreeningDecision,
        reviewer_b: ScreeningDecision,
    ) -> ScreeningDecision:
        prompt = adjudicator_prompt(self.review, paper, stage, reviewer_a, reviewer_b, full_text)
        decision = await self._request_decision(
            prompt=prompt,
            spec=ReviewerSpec(
                agent_name="screening_adjudicator",
                reviewer_type=ReviewerType.ADJUDICATOR,
            ),
            workflow_id=workflow_id,
            paper_id=paper.paper_id,
        )
        await self.repository.save_screening_decision(workflow_id=workflow_id, stage=stage, decision=decision)
        await self.repository.append_decision_log(
            DecisionLogEntry(
                decision_type="screening_adjudication",
                paper_id=paper.paper_id,
                decision=decision.decision.value,
                rationale=decision.reason or "Adjudication decision generated.",
                actor=ReviewerType.ADJUDICATOR.value,
                phase="phase_3_screening",
            )
        )
        return decision

    async def _request_decision(
        self,
        prompt: str,
        spec: ReviewerSpec,
        workflow_id: str,
        paper_id: str,
        other_reviewer_decision: ScreeningDecisionType | None = None,
    ) -> ScreeningDecision:
        if self.on_prompt:
            self.on_prompt(spec.agent_name, prompt, paper_id)
        runtime = await self.provider.reserve_call_slot(spec.agent_name)
        started = time.perf_counter()
        if hasattr(self.llm_client, "complete_json_with_usage"):
            if hasattr(self.llm_client, "complete_screening_response_with_usage"):
                (
                    parsed,
                    tokens_in,
                    tokens_out,
                    cache_write,
                    cache_read,
                ) = await self.llm_client.complete_screening_response_with_usage(
                    prompt,
                    agent_name=spec.agent_name,
                    model=runtime.model,
                    temperature=runtime.temperature,
                )
                raw = parsed.model_dump_json()
            else:
                raw, tokens_in, tokens_out, cache_write, cache_read = await self.llm_client.complete_json_with_usage(
                    prompt,
                    agent_name=spec.agent_name,
                    model=runtime.model,
                    temperature=runtime.temperature,
                )
                parsed = self._parse_response(raw)
        else:
            raw = await self.llm_client.complete_json(
                prompt,
                agent_name=spec.agent_name,
                model=runtime.model,
                temperature=runtime.temperature,
            )
            tokens_in = max(1, len(prompt.split()))
            tokens_out = max(1, len(raw.split()))
            cache_write = cache_read = 0
            parsed = self._parse_response(raw)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        cost_usd = self.provider.estimate_cost(runtime.model, tokens_in, tokens_out, cache_write, cache_read)
        if parsed.short_reason in {"Invalid JSON", "Invalid schema"}:
            self.contract_violation_count += 1
            await self.repository.append_decision_log(
                DecisionLogEntry(
                    workflow_id=workflow_id,
                    decision_type="screening_contract_violation",
                    paper_id=paper_id,
                    decision=parsed.decision.value,
                    rationale=parsed.reasoning,
                    actor=spec.reviewer_type.value,
                    phase="phase_3_screening",
                )
            )
        if self.on_llm_call:
            self.on_llm_call(
                spec.agent_name,
                "success",
                f"{paper_id[:12]} {parsed.decision.value}",
                None,
                raw_response=raw,
                latency_ms=elapsed_ms,
                model=runtime.model,
                paper_id=paper_id,
                phase="phase_3_screening",
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost_usd,
                other_reviewer_decision=other_reviewer_decision,
            )
        await self.provider.log_cost(
            model=runtime.model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            latency_ms=elapsed_ms,
            phase="phase_3_screening",
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
        )
        return ScreeningDecision(
            paper_id=paper_id,
            decision=parsed.decision,
            reason=parsed.reasoning,
            exclusion_reason=parsed.exclusion_reason,
            reviewer_type=spec.reviewer_type,
            confidence=parsed.confidence,
        )

    @staticmethod
    def _parse_response(raw: str) -> ScreeningResponse:
        s = raw.strip()
        try:
            payload = json.loads(s)
        except json.JSONDecodeError:
            return ScreeningResponse(
                decision=ScreeningDecisionType.UNCERTAIN,
                confidence=0.0,
                short_reason="Invalid JSON",
                reasoning="Model output was not valid JSON.",
            )
        try:
            return ScreeningResponse.model_validate(payload)
        except ValidationError:
            return ScreeningResponse(
                decision=ScreeningDecisionType.UNCERTAIN,
                confidence=0.0,
                short_reason="Invalid schema",
                reasoning="Model output did not match expected schema.",
            )

    @staticmethod
    def _enforce_fulltext_exclusion_reason(decision: ScreeningDecision) -> ScreeningDecision:
        return enforce_fulltext_exclusion_reason(decision)
