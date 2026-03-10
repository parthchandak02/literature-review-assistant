"""Dual-reviewer screening workflow with adjudication."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

_log = logging.getLogger(__name__)

from pydantic import BaseModel, Field, ValidationError

from src.db.repositories import WorkflowRepository
from src.llm.provider import LLMProvider
from src.models import (
    CandidatePaper,
    DecisionLogEntry,
    ExclusionReason,
    ReviewConfig,
    ReviewerType,
    ScreeningDecision,
    ScreeningDecisionType,
    SettingsConfig,
)
from src.screening.prompts import (
    adjudicator_prompt,
    reviewer_a_prompt,
    reviewer_b_prompt,
)
from src.search.pdf_retrieval import FullTextCoverageSummary, PDFRetriever


class ScreeningResponse(BaseModel):
    decision: ScreeningDecisionType
    confidence: float = Field(ge=0.0, le=1.0)
    short_reason: str | None = Field(default=None, description="One-line summary, max 80 chars")
    reasoning: str
    exclusion_reason: ExclusionReason | None = None


class _BatchScreeningItem(BaseModel):
    """One paper's decision within a batch LLM response array."""

    paper_id: str
    decision: ScreeningDecisionType
    confidence: float = Field(ge=0.0, le=1.0)
    short_reason: str | None = None
    reasoning: str
    exclusion_reason: ExclusionReason | None = None


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

    _PROTOCOL_TITLE_PATTERNS: tuple[str, ...] = (
        "protocol for",
        "protocol of",
        "study protocol",
        "trial protocol",
        "research protocol",
        "protocol paper",
        "protocol article",
        ": a protocol",
        "- a protocol",
        "design and methods",
        "study design and",
        "rationale and design",
        "prospero registration",
        "trial registration",
    )

    # Abstract phrases that strongly signal the record is title-only with no retrievable data
    _TITLE_ONLY_ABSTRACT_PHRASES: tuple[str, ...] = (
        "title only",
        "title-only",
        "[no abstract]",
        "no abstract available",
        "abstract not available",
        "abstract unavailable",
        "[abstract not available]",
    )

    # Retained as a fallback default; the live value is read from settings.screening.insufficient_content_min_words
    _TITLE_ONLY_ABSTRACT_WORD_THRESHOLD: int = 5

    def _is_insufficient_content(self, paper: CandidatePaper) -> bool:
        """Return True when the paper has no usable abstract content.

        Fires when:
        - The abstract is absent AND settings.screening.insufficient_content_min_words > 0.
          When min_words is 0, empty-abstract papers are forwarded to the LLM for title-only
          evaluation (PRISMA 2020 guidance: advance to full-text when abstract is absent).
        - The abstract has fewer than insufficient_content_min_words words (stub/title-only).
        - The abstract text explicitly signals it is a title-only record.

        Setting insufficient_content_min_words: 0 disables all stub-abstract auto-exclusions
        and delegates every record to the LLM dual-screener, which can exclude on title alone.
        """
        abstract = (paper.abstract or "").strip()
        title = (paper.title or "").strip()

        # Read threshold first so the empty-abstract guard can respect it.
        min_words = getattr(
            getattr(getattr(self, "settings", None), "screening", None),
            "insufficient_content_min_words",
            self._TITLE_ONLY_ABSTRACT_WORD_THRESHOLD,
        )

        # No abstract at all: only auto-exclude when the threshold requires content.
        # When min_words=0, forward to LLM for title-only evaluation.
        if not abstract:
            return min_words > 0

        # Abstract is just the title repeated (some databases duplicate title as abstract)
        if abstract.lower() == title.lower():
            return True

        # Explicit "title only" signals
        abstract_lower = abstract.lower()
        if any(phrase in abstract_lower for phrase in self._TITLE_ONLY_ABSTRACT_PHRASES):
            return True

        # Stub abstract: fewer than configured threshold words
        word_count = len(abstract.split())
        if word_count < min_words:
            return True

        return False

    def _is_protocol_only(self, paper: CandidatePaper) -> bool:
        """Return True when title/abstract strongly indicate a protocol with no results.

        This heuristic acts as a post-LLM safety net. It is conservative: it
        only fires when the title unambiguously marks the paper as a protocol,
        or when the abstract explicitly states no results are yet available.
        """
        title_lower = (paper.title or "").lower()
        abstract_lower = (paper.abstract or "").lower()

        # Title-based signal: explicit protocol markers
        if any(pat in title_lower for pat in self._PROTOCOL_TITLE_PATTERNS):
            return True

        # Abstract-based signal: phrases that confirm no results exist
        no_results_phrases = (
            "no results are available",
            "results will be reported",
            "results are not yet available",
            "trial is ongoing",
            "study is ongoing",
            "data collection is underway",
            "data collection has not",
        )
        if any(ph in abstract_lower for ph in no_results_phrases):
            return True

        return False

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
        on_pdf_result: Callable[[str, str, str, bool], None] | None = None,
    ) -> list[ScreeningDecision]:
        # Clear consumed flag at the start of every new batch so subsequent
        # Ctrl+C events (after a reset) are still honoured.
        self._partial_flag_consumed = False

        if stage == "fulltext":
            if full_text_by_paper is None:
                active_retriever = retriever or PDFRetriever()
                _pdf_concurrency = self.settings.screening.pdf_retrieval_concurrency
                _pdf_timeout = self.settings.screening.pdf_retrieval_per_paper_timeout
                retrieval_results, coverage = await active_retriever.retrieve_batch(
                    papers,
                    on_progress=on_pdf_progress,
                    concurrency=_pdf_concurrency,
                    per_paper_timeout=_pdf_timeout,
                    on_result=on_pdf_result,
                )
                full_text_by_paper = {
                    paper_id: result.full_text for paper_id, result in retrieval_results.items() if result.success
                }
                # Abstract fallback for papers without full text (when not excluding for no-PDF)
                skip_no_pdf = self.settings.screening.skip_fulltext_if_no_pdf
                if not skip_no_pdf:
                    for paper in papers:
                        if paper.paper_id not in full_text_by_paper:
                            fallback = (paper.abstract or paper.title or "").strip()
                            full_text_by_paper[paper.paper_id] = fallback
            else:
                coverage = self._coverage_from_map(papers, full_text_by_paper)
            await self._persist_fulltext_coverage(
                workflow_id=workflow_id,
                stage=stage,
                coverage=coverage,
                coverage_report_path=coverage_report_path,
            )

        processed = await self.repository.get_processed_paper_ids(workflow_id, stage)
        to_process = [p for p in papers if p.paper_id not in processed]

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
                        no_ft_decision = ScreeningDecision(
                            paper_id=paper.paper_id,
                            decision=ScreeningDecisionType.EXCLUDE,
                            confidence=1.0,
                            reason="Full text not retrievable.",
                            reviewer_type=ReviewerType.ADJUDICATOR,
                            exclusion_reason=ExclusionReason.NO_FULL_TEXT,
                        )
                        await self.repository.save_screening_decision(
                            workflow_id=workflow_id, stage=stage, decision=no_ft_decision
                        )
                        await self.repository.save_dual_screening_result(
                            workflow_id=workflow_id,
                            paper_id=paper.paper_id,
                            stage=stage,
                            agreement=True,
                            final_decision=ScreeningDecisionType.EXCLUDE,
                            adjudication_needed=False,
                        )
                        await self.repository.append_decision_log(
                            DecisionLogEntry(
                                decision_type="screening_no_fulltext",
                                paper_id=paper.paper_id,
                                decision=ScreeningDecisionType.EXCLUDE.value,
                                rationale="Full text not retrievable; excluded per skip_fulltext_if_no_pdf.",
                                actor=ReviewerType.ADJUDICATOR.value,
                                phase="phase_3_screening",
                            )
                        )
                        if self.on_screening_decision:
                            self.on_screening_decision(
                                paper.paper_id, stage, "exclude", "fulltext_no_pdf_heuristic", 1.0
                            )
                        result = no_ft_decision
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
            proto_decision = ScreeningDecision(
                paper_id=paper.paper_id,
                decision=ScreeningDecisionType.EXCLUDE,
                confidence=0.95,
                reason="Protocol-only heuristic: title or abstract indicates a study protocol with no reported results.",
                reviewer_type=ReviewerType.KEYWORD_FILTER,
                exclusion_reason=ExclusionReason.PROTOCOL_ONLY,
            )
            await self.repository.save_screening_decision(workflow_id=workflow_id, stage=stage, decision=proto_decision)
            await self.repository.append_decision_log(
                DecisionLogEntry(
                    decision_type="screening_protocol_heuristic",
                    paper_id=paper.paper_id,
                    decision=ScreeningDecisionType.EXCLUDE.value,
                    rationale="Protocol-only auto-exclusion (no results available).",
                    actor=ReviewerType.KEYWORD_FILTER.value,
                    phase="phase_3_screening",
                )
            )
            if self.on_screening_decision:
                self.on_screening_decision(paper.paper_id, stage, "exclude", "protocol_only_heuristic", 0.95)
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
            insuf_decision = ScreeningDecision(
                paper_id=paper.paper_id,
                decision=ScreeningDecisionType.EXCLUDE,
                confidence=0.90,
                reason="Insufficient content: abstract absent, too short, or title-only stub -- no data extractable.",
                reviewer_type=ReviewerType.KEYWORD_FILTER,
                exclusion_reason=ExclusionReason.INSUFFICIENT_DATA,
            )
            await self.repository.save_screening_decision(workflow_id=workflow_id, stage=stage, decision=insuf_decision)
            await self.repository.append_decision_log(
                DecisionLogEntry(
                    decision_type="screening_insufficient_content_heuristic",
                    paper_id=paper.paper_id,
                    decision=ScreeningDecisionType.EXCLUDE.value,
                    rationale=(
                        f"Abstract absent or stub ({_abstract_word_count} words). "
                        f"Threshold: fewer than "
                        f"{getattr(getattr(getattr(self, 'settings', None), 'screening', None), 'insufficient_content_min_words', self._TITLE_ONLY_ABSTRACT_WORD_THRESHOLD)} "
                        f"words or explicit no-abstract marker."
                    ),
                    actor=ReviewerType.KEYWORD_FILTER.value,
                    phase="phase_3_screening",
                )
            )
            if self.on_screening_decision:
                # Encode word count in reason with pipe delimiter so the SSE consumer
                # can display it: "insufficient_content_heuristic|3w" -> "(3w)" in UI.
                self.on_screening_decision(
                    paper.paper_id,
                    stage,
                    "exclude",
                    f"insufficient_content_heuristic|{_abstract_word_count}w",
                    0.90,
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
            fast_path = (
                reviewer_a.confidence >= include_thresh and reviewer_a.decision == ScreeningDecisionType.INCLUDE
            ) or (reviewer_a.confidence >= exclude_thresh and reviewer_a.decision == ScreeningDecisionType.EXCLUDE)

        if fast_path:
            final_decision = reviewer_a
            adjudication_needed = False
            agreement = True
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
        "Return ONLY a valid JSON array, one entry per paper (same count as input):\n"
        "[\n"
        "  {\n"
        '    "paper_id": "<id>",\n'
        '    "decision": "include|exclude|uncertain",\n'
        '    "confidence": 0.0,\n'
        '    "short_reason": "<max 80 chars>",\n'
        '    "reasoning": "<justification>",\n'
        '    "exclusion_reason": "<code or null>"\n'
        "  }\n"
        "]\n"
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
        for i, paper in enumerate(papers, start=1):
            text = full_texts.get(paper.paper_id, "") if stage == "fulltext" else ""
            content = (text[:1200] if text else (paper.abstract or ""))[:600].replace("\n", " ")
            lines.append(f"[{i}] paper_id={paper.paper_id} | {paper.title} | {content}")
        return "\n".join(lines)

    def _parse_batch_response(
        self,
        raw: str,
        papers: list[CandidatePaper],
        spec: ReviewerSpec,
        stage: str,
    ) -> dict[str, ScreeningDecision]:
        """Parse a JSON array response into a paper_id -> ScreeningDecision map.

        Returns only the paper_ids that were successfully parsed. Missing or
        unparseable papers are handled by the caller (fallback to individual call).
        """
        s = raw.strip()
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
        s = s.strip()
        first = s.find("[")
        last = s.rfind("]")
        if first < 0 or last <= first:
            return {}
        s = s[first : last + 1]
        try:
            items = json.loads(s)
        except json.JSONDecodeError:
            return {}
        if not isinstance(items, list):
            return {}
        result: dict[str, ScreeningDecision] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                parsed = _BatchScreeningItem.model_validate(item)
            except Exception:
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
        return result

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
        if self.on_prompt:
            self.on_prompt(spec.agent_name, prompt, None)
        runtime = await self.provider.reserve_call_slot(spec.agent_name)
        started = time.perf_counter()
        try:
            if hasattr(self.llm_client, "complete_json_with_usage"):
                raw, tokens_in, tokens_out, cache_write, cache_read = await self.llm_client.complete_json_with_usage(
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
        parsed_map = self._parse_batch_response(raw, papers, spec, stage)
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
                d = ScreeningDecision(
                    paper_id=paper.paper_id,
                    decision=ScreeningDecisionType.EXCLUDE,
                    confidence=1.0,
                    reason="Full text not retrievable.",
                    reviewer_type=ReviewerType.ADJUDICATOR,
                    exclusion_reason=ExclusionReason.NO_FULL_TEXT,
                )
                await self.repository.save_screening_decision(workflow_id=workflow_id, stage=stage, decision=d)
                await self.repository.save_dual_screening_result(
                    workflow_id=workflow_id,
                    paper_id=paper.paper_id,
                    stage=stage,
                    agreement=True,
                    final_decision=ScreeningDecisionType.EXCLUDE,
                    adjudication_needed=False,
                )
                await self.repository.append_decision_log(
                    DecisionLogEntry(
                        decision_type="screening_no_fulltext",
                        paper_id=paper.paper_id,
                        decision=ScreeningDecisionType.EXCLUDE.value,
                        rationale="Full text not retrievable; excluded per skip_fulltext_if_no_pdf.",
                        actor=ReviewerType.ADJUDICATOR.value,
                        phase="phase_3_screening",
                    )
                )
                if self.on_screening_decision:
                    self.on_screening_decision(paper.paper_id, stage, "exclude", "fulltext_no_pdf_heuristic", 1.0)
                heuristic_decisions[paper.paper_id] = d
                continue
            if self._is_protocol_only(paper):
                d = ScreeningDecision(
                    paper_id=paper.paper_id,
                    decision=ScreeningDecisionType.EXCLUDE,
                    confidence=0.95,
                    reason="Protocol-only heuristic: title or abstract indicates a study protocol with no reported results.",
                    reviewer_type=ReviewerType.KEYWORD_FILTER,
                    exclusion_reason=ExclusionReason.PROTOCOL_ONLY,
                )
                await self.repository.save_screening_decision(workflow_id=workflow_id, stage=stage, decision=d)
                await self.repository.append_decision_log(
                    DecisionLogEntry(
                        decision_type="screening_protocol_heuristic",
                        paper_id=paper.paper_id,
                        decision=ScreeningDecisionType.EXCLUDE.value,
                        rationale="Protocol-only auto-exclusion.",
                        actor=ReviewerType.KEYWORD_FILTER.value,
                        phase="phase_3_screening",
                    )
                )
                if self.on_screening_decision:
                    self.on_screening_decision(paper.paper_id, stage, "exclude", "protocol_only_heuristic", 0.95)
                heuristic_decisions[paper.paper_id] = d
                continue
            if stage == "title_abstract" and self._is_insufficient_content(paper):
                wc = len((paper.abstract or "").split())
                d = ScreeningDecision(
                    paper_id=paper.paper_id,
                    decision=ScreeningDecisionType.EXCLUDE,
                    confidence=0.90,
                    reason="Insufficient content: abstract absent, too short, or title-only stub.",
                    reviewer_type=ReviewerType.KEYWORD_FILTER,
                    exclusion_reason=ExclusionReason.INSUFFICIENT_DATA,
                )
                await self.repository.save_screening_decision(workflow_id=workflow_id, stage=stage, decision=d)
                await self.repository.append_decision_log(
                    DecisionLogEntry(
                        decision_type="screening_insufficient_content_heuristic",
                        paper_id=paper.paper_id,
                        decision=ScreeningDecisionType.EXCLUDE.value,
                        rationale=f"Abstract absent or stub ({wc} words).",
                        actor=ReviewerType.KEYWORD_FILTER.value,
                        phase="phase_3_screening",
                    )
                )
                if self.on_screening_decision:
                    self.on_screening_decision(
                        paper.paper_id,
                        stage,
                        "exclude",
                        f"insufficient_content_heuristic|{wc}w",
                        0.90,
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
                    _log.warning("Batch A missing paper %s -- falling back to individual call", paper.paper_id)
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
        for paper in llm_candidates:
            a = reviewer_a_map[paper.paper_id]
            # Fast-path applies to title/abstract only.
            # Full-text screening requires dual review for all papers (Cochrane MECIR C39).
            if stage == "fulltext":
                is_fast = False
            else:
                is_fast = (a.confidence >= include_thresh and a.decision == ScreeningDecisionType.INCLUDE) or (
                    a.confidence >= exclude_thresh and a.decision == ScreeningDecisionType.EXCLUDE
                )
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
                        _log.warning("Batch B missing paper %s -- falling back to individual call", paper.paper_id)
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
        paper_id: str,
        other_reviewer_decision: ScreeningDecisionType | None = None,
    ) -> ScreeningDecision:
        if self.on_prompt:
            self.on_prompt(spec.agent_name, prompt, paper_id)
        runtime = await self.provider.reserve_call_slot(spec.agent_name)
        started = time.perf_counter()
        if hasattr(self.llm_client, "complete_json_with_usage"):
            raw, tokens_in, tokens_out, cache_write, cache_read = await self.llm_client.complete_json_with_usage(
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
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        cost_usd = self.provider.estimate_cost(runtime.model, tokens_in, tokens_out, cache_write, cache_read)
        parsed = self._parse_response(raw)
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
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
        s = s.strip()
        first = s.find("{")
        last = s.rfind("}")
        if first >= 0 and last > first:
            s = s[first : last + 1]
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
        if decision.exclusion_reason is not None:
            return decision
        return decision.model_copy(update={"exclusion_reason": ExclusionReason.OTHER})
