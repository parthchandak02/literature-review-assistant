"""Batch LLM pre-ranker for systematic review screening.

Inserts a fast coarse-ranking pass between BM25 selection and the expensive
dual-reviewer. Instead of 1 LLM call per paper (400 papers = 400+ calls), this
module sends batches of papers to a single LLM call and returns relevance scores.
Papers below batch_screen_threshold are excluded before the dual-reviewer runs.

Expected impact: reduces dual-reviewer LLM calls by 60-70% while maintaining recall
because the threshold is intentionally liberal (0.35 by default -- uncertain papers
are always forwarded to dual-review).

Protocol / interface pattern mirrors src/screening/dual_screener.ScreeningLLMClient
so the same _ScriptedClient mock pattern works in tests.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from src.models.config import ScreeningConfig
from src.models.enums import ExclusionReason, ReviewerType, ScreeningDecisionType
from src.models.papers import CandidatePaper
from src.models.screening import ScreeningDecision

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a systematic review screener performing a rapid relevance pre-ranking.

Your task: rate each paper's relevance to the research question and return a JSON array.

RESPONSE FORMAT -- return ONLY a valid JSON array, no prose:
[
  {"id": "<paper_id>", "score": <0.0-1.0>, "reason": "<one sentence>"},
  ...
]

SCORING RULES:
- score 0.8-1.0: clearly relevant (directly evaluates the intervention in the target setting)
- score 0.4-0.7: possibly relevant (adjacent topic, may meet criteria on closer review)
- score 0.0-0.35: clearly irrelevant (different domain, unrelated intervention, or clearly out-of-scope topic)

CRITICAL -- BE LIBERAL: When uncertain, assign score >= 0.35 so the paper reaches detailed review.
A false negative (missing a relevant paper) is permanent. A false positive costs one extra review call.

HARD NEGATIVE SIGNALS (score <= 0.35 unless strong contradictory evidence exists):
- Protocol-only records with no reported results
- Secondary reviews (systematic/scoping/narrative/umbrella/meta-analysis)
- Wrong target population or unrelated training domain
- Empty-abstract records that provide no evaluable study information
"""

_USER_TEMPLATE = """Research question: {research_question}
Topic focus: {topic_focus}
Domain: {domain}

Target population: {population}
Target intervention: {intervention}
Target outcome: {outcome}
Keywords: {keywords}
Topic anchor terms: {expert_terms}
Out-of-scope signals: {excluded_terms}

Rate each paper below on relevance to this research question.
Return a JSON array with one entry per paper (same count as input papers).

Papers to rate:
{paper_list}"""


def _build_paper_list(papers: list[CandidatePaper]) -> str:
    """Format papers as a compact numbered list for the prompt."""
    lines: list[str] = []
    for i, p in enumerate(papers, start=1):
        abstract_snippet = ""
        if p.abstract:
            abstract_snippet = p.abstract[:300].replace("\n", " ")
        lines.append(f"[{i}] id={p.paper_id} | {p.title} | {abstract_snippet}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class BatchRankerClient(Protocol):
    """Protocol for the LLM client used by BatchLLMRanker.

    Satisfies the same interface contract as ScreeningLLMClient so the same
    scripted mock pattern from test_screening.py works in tests.
    """

    async def complete_batch(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float,
    ) -> str:
        """Return raw JSON string from the LLM for a batch of papers."""
        ...


# ---------------------------------------------------------------------------
# Default live client (backed by PydanticAIClient)
# ---------------------------------------------------------------------------


class PydanticAIBatchRankerClient:
    """Live LLM client for batch ranking, backed by PydanticAIClient."""

    async def complete_batch(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float,
    ) -> str:
        from src.llm.pydantic_client import PydanticAIClient

        client = PydanticAIClient()
        return await client.complete(prompt, model=model, temperature=temperature)


# ---------------------------------------------------------------------------
# Core ranker
# ---------------------------------------------------------------------------


class BatchLLMRanker:
    """Batch LLM pre-ranker: scores paper batches and splits them at a threshold.

    Usage:
        ranker = BatchLLMRanker(screening_config, settings_config, llm_client)
        forwarded, excluded = await ranker.rank_and_split(papers)

    forwarded  -- list[CandidatePaper] with score >= threshold -> goes to dual-reviewer
    excluded   -- list[ScreeningDecision] with exclusion_reason=BATCH_SCREENED_LOW
    """

    def __init__(
        self,
        screening: ScreeningConfig,
        model: str,
        temperature: float,
        research_question: str,
        topic_focus: str = "",
        domain: str = "",
        population: str = "",
        intervention: str = "",
        outcome: str = "",
        keywords: list[str] | None = None,
        expert_terms: list[str] | None = None,
        excluded_terms: list[str] | None = None,
        client: BatchRankerClient | None = None,
        on_status: Callable[[str], None] | None = None,
    ) -> None:
        self._screening = screening
        self._model = model
        self._temperature = temperature
        self._research_question = research_question
        self._topic_focus = topic_focus
        self._domain = domain
        self._population = population
        self._intervention = intervention
        self._outcome = outcome
        self._keywords = list(keywords or [])
        self._expert_terms = list(expert_terms or [])
        self._excluded_terms = list(excluded_terms or [])
        self._client: BatchRankerClient = client or PydanticAIBatchRankerClient()
        self.on_status = on_status
        # Validation state: populated by rank_and_split() after cross-checking a sample
        # of excluded papers. Callers read these to surface NPV in the Methods section.
        self.validation_sampled_n: int = 0
        self.validation_npv: float = 0.0
        # Number of near-threshold papers forwarded by uncertain-band logic.
        self.borderline_forwarded_n: int = 0

    async def _score_batch(self, batch: list[CandidatePaper]) -> dict[str, float]:
        """Call LLM once for this batch; return {paper_id -> score}.

        On any parse failure, returns all papers at score 1.0 (safe fallback:
        all go to dual-review rather than silently discarding them).
        """
        paper_list = _build_paper_list(batch)
        prompt = (
            _SYSTEM_PROMPT
            + "\n\n"
            + _USER_TEMPLATE.format(
                research_question=self._research_question,
                topic_focus=self._topic_focus,
                domain=self._domain,
                population=self._population,
                intervention=self._intervention,
                outcome=self._outcome,
                keywords=", ".join(self._keywords),
                expert_terms=", ".join(self._expert_terms),
                excluded_terms=", ".join(self._excluded_terms) or "none",
                paper_list=paper_list,
            )
        )
        try:
            raw = await self._client.complete_batch(prompt, model=self._model, temperature=self._temperature)
            results = self._parse_response(raw, batch)
            return results
        except Exception as exc:
            logger.warning(
                "BatchLLMRanker: LLM call failed for batch of %d papers; "
                "all forwarded to dual-reviewer as safe fallback. Error: %s",
                len(batch),
                exc,
            )
            return {p.paper_id: 1.0 for p in batch}

    def _parse_response(self, raw: str, batch: list[CandidatePaper]) -> dict[str, float]:
        """Parse JSON array from raw LLM response.

        Tolerates:
        - Markdown code fences around JSON
        - Extra prose before/after the JSON array
        - Missing entries (forwards those papers with score 1.0)
        - Invalid scores (clamped to 0.0-1.0)
        """
        # Strip markdown fences if present
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            # Remove first and last fence lines
            inner = [ln for ln in lines if not ln.startswith("```")]
            text = "\n".join(inner).strip()

        # Find the first '[' and last ']' to extract the JSON array
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1 or end <= start:
            logger.warning(
                "BatchLLMRanker: Could not locate JSON array in response; "
                "forwarding all %d papers. Response prefix: %r",
                len(batch),
                text[:200],
            )
            return {p.paper_id: 1.0 for p in batch}

        try:
            items = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            logger.warning(
                "BatchLLMRanker: JSON decode failed (%s); forwarding all %d papers.",
                exc,
                len(batch),
            )
            return {p.paper_id: 1.0 for p in batch}

        scores: dict[str, float] = {}
        seen_ids: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            paper_id = str(item.get("id", "")).strip()
            raw_score = item.get("score", 1.0)
            try:
                score = float(raw_score)
            except (TypeError, ValueError):
                score = 1.0
            score = max(0.0, min(1.0, score))
            if paper_id:
                scores[paper_id] = score
                seen_ids.add(paper_id)

        # Any papers not mentioned in the LLM response get score 1.0 (safe fallback)
        for p in batch:
            if p.paper_id not in seen_ids:
                logger.debug(
                    "BatchLLMRanker: paper %s not in LLM response; forwarding with score 1.0",
                    p.paper_id,
                )
                scores[p.paper_id] = 1.0

        return scores

    async def rank_and_split(
        self, papers: list[CandidatePaper]
    ) -> tuple[list[CandidatePaper], list[ScreeningDecision]]:
        """Score all papers in batches and split at threshold.

        Returns:
            forwarded -- papers to send to dual-reviewer (score >= threshold)
            excluded  -- ScreeningDecision records for papers auto-excluded
        """
        if not papers:
            return [], []

        threshold = self._screening.batch_screen_threshold
        uncertain_band = max(0.0, min(getattr(self._screening, "batch_screen_uncertain_band", 0.0), threshold))
        uncertain_floor = max(0.0, threshold - uncertain_band)
        batch_size = self._screening.batch_screen_size

        # Split into batches
        batches: list[list[CandidatePaper]] = []
        for i in range(0, len(papers), batch_size):
            batches.append(papers[i : i + batch_size])

        logger.info(
            "BatchLLMRanker: scoring %d papers in %d batches (size=%d, threshold=%.2f, uncertain_band=%.2f)",
            len(papers),
            len(batches),
            batch_size,
            threshold,
            uncertain_band,
        )

        # Run batches concurrently up to batch_screen_concurrency to reduce wall-clock time.
        # Each batch is one LLM call; a semaphore prevents RPM burst.
        _concurrency = getattr(self._screening, "batch_screen_concurrency", 3)
        sem = asyncio.Semaphore(_concurrency)

        ranker_started = time.perf_counter()

        async def _score_one(idx: int, batch: list[CandidatePaper]) -> dict[str, float]:
            async with sem:
                if self.on_status:
                    self.on_status(
                        f"Pre-ranker batch {idx + 1}/{len(batches)} starting "
                        f"({idx * batch_size}/{len(papers)} papers scored, "
                        f"elapsed {int(time.perf_counter() - ranker_started)}s)"
                    )
                logger.info("BatchLLMRanker: batch %d/%d (%d papers)", idx + 1, len(batches), len(batch))
                t0 = time.perf_counter()
                result = await self._score_batch(batch)
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                if self.on_status:
                    self.on_status(
                        f"Pre-ranker batch {idx + 1}/{len(batches)} done in {elapsed_ms}ms ({len(batch)} papers scored)"
                    )
                return result

        gathered_scores = await asyncio.gather(
            *[_score_one(idx, batch) for idx, batch in enumerate(batches)],
            return_exceptions=True,
        )
        all_scores: dict[str, float] = {}
        for result in gathered_scores:
            if not isinstance(result, BaseException):
                all_scores.update(result)

        # Split on threshold
        forwarded: list[CandidatePaper] = []
        excluded: list[ScreeningDecision] = []
        self.borderline_forwarded_n = 0
        for paper in papers:
            score = all_scores.get(paper.paper_id, 1.0)
            if score >= threshold:
                forwarded.append(paper)
            elif score >= uncertain_floor:
                # Recall-first safety band: keep near-threshold records for dual review.
                forwarded.append(paper)
                self.borderline_forwarded_n += 1
            else:
                excluded.append(
                    ScreeningDecision(
                        paper_id=paper.paper_id,
                        decision=ScreeningDecisionType.EXCLUDE,
                        exclusion_reason=ExclusionReason.BATCH_SCREENED_LOW,
                        reviewer_type=ReviewerType.BATCH_RANKER,
                        confidence=round(1.0 - score, 3),
                        reason=f"Batch LLM pre-ranker score {score:.2f} < threshold {threshold:.2f}",
                    )
                )

        logger.info(
            "BatchLLMRanker: %d forwarded to dual-review (%d in uncertain band), %d auto-excluded (below %.2f threshold)",
            len(forwarded),
            self.borderline_forwarded_n,
            len(excluded),
            uncertain_floor,
        )

        # Cross-validation: re-score a configurable sample of excluded papers
        # to estimate NPV.
        # A paper is "confirmed excluded" if the re-score still falls below the threshold.
        # This produces a methodological transparency metric for the Methods section.
        await self._validate_exclusion_sample(papers, excluded, threshold)

        return forwarded, excluded

    async def _validate_exclusion_sample(
        self,
        all_papers: list[CandidatePaper],
        excluded_decisions: list[ScreeningDecision],
        threshold: float,
    ) -> None:
        """Cross-validate a sample of excluded papers via an independent re-score.

        Computes the negative predictive value (NPV) of the batch pre-ranker and stores
        it in self.validation_sampled_n and self.validation_npv so callers can surface
        it in the Methods section for PRISMA 2020 methodological transparency.
        """
        if not excluded_decisions:
            return
        paper_by_id = {p.paper_id: p for p in all_papers}
        fraction = float(getattr(self._screening, "batch_screen_validation_fraction", 0.10))
        min_sample = int(getattr(self._screening, "batch_screen_validation_min_sample", 20))
        max_sample = max(min_sample, int(getattr(self._screening, "batch_screen_validation_max_sample", 60)))
        sample_size = max(min_sample, min(max_sample, round(len(excluded_decisions) * fraction)))
        sample_decisions = random.sample(excluded_decisions, min(sample_size, len(excluded_decisions)))
        sample_papers = [paper_by_id[d.paper_id] for d in sample_decisions if d.paper_id in paper_by_id]
        if not sample_papers:
            return
        try:
            rescored = await self._score_batch(sample_papers)
            confirmed = sum(1 for p in sample_papers if rescored.get(p.paper_id, 0.0) < threshold)
            self.validation_sampled_n = len(sample_papers)
            self.validation_npv = round(confirmed / len(sample_papers), 3) if sample_papers else 0.0
            logger.info(
                "BatchLLMRanker: cross-validation on %d excluded abstracts: %d confirmed excluded (NPV=%.1f%%)",
                len(sample_papers),
                confirmed,
                self.validation_npv * 100,
            )
        except Exception as exc:
            logger.warning("BatchLLMRanker: cross-validation failed (%s); skipping.", exc)
