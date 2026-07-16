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

from src.llm.provider import LLMProvider
from src.models.config import ScreeningConfig
from src.models.enums import ExclusionReason, ReviewerType, ScreeningDecisionType
from src.models.papers import CandidatePaper
from src.models.screening import BatchRankerResponsePayload, ScreeningDecision

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a systematic review screener performing a rapid relevance pre-ranking.

Your task: rate each paper's relevance to the research question and return JSON matching the schema.

RESPONSE FORMAT -- return ONLY valid JSON matching this exact schema, no prose:
{"ratings": [{"id": "<paper_id>", "score": <0.0-1.0>, "reason": "<one sentence>"}, ...]}

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
Intervention anchor terms: {anchor_terms}
Related context terms: {related_terms}
Out-of-scope signals: {excluded_terms}

Scoring guidance:
- Intervention anchor terms define the specific mechanism of interest.
- Related context terms are supportive context only and do NOT by themselves establish intervention alignment.
- Score <= 0.35 when a paper evaluates only a broader adjacent digital system, registry, workflow tool, or policy without the intervention anchors or a clear synonym.

Rate each paper below on relevance to this research question.
Return one ratings entry per input paper (same count as input papers).

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


def _batch_ranker_json_schema() -> dict[str, object]:
    """Build provider-safe object schema for batch ranker structured output."""
    embedded_item_schema = dict(BatchRankerResponsePayload.model_json_schema()["$defs"]["BatchRankerItemPayload"])
    object_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "ratings": {
                "type": "array",
                "items": embedded_item_schema,
            }
        },
        "required": ["ratings"],
        "additionalProperties": False,
    }
    shared_defs = BatchRankerResponsePayload.model_json_schema().get("$defs")
    if isinstance(shared_defs, dict) and shared_defs:
        object_schema["$defs"] = shared_defs
    return object_schema


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
    ) -> str | BatchRankerResponsePayload | tuple[str | BatchRankerResponsePayload, int, int, int, int]:
        """Return raw JSON, validated payload, or (payload/json, in, out, cache_write, cache_read)."""
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
    ) -> tuple[BatchRankerResponsePayload, int, int, int, int]:
        from src.llm.factory import get_chat_client

        client = get_chat_client()
        parsed, tok_in, tok_out, cw, cr, _retries = await client.complete_validated(
            prompt,
            model=model,
            temperature=temperature,
            response_model=BatchRankerResponsePayload,
            json_schema=_batch_ranker_json_schema(),
        )
        return parsed, tok_in, tok_out, cw, cr


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
        anchor_terms: list[str] | None = None,
        related_terms: list[str] | None = None,
        excluded_terms: list[str] | None = None,
        client: BatchRankerClient | None = None,
        on_status: Callable[[str], None] | None = None,
        provider: LLMProvider | None = None,
        workflow_id: str = "",
        reserve_agent: str = "batch_screener",
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
        self._anchor_terms = list(anchor_terms or [])
        self._related_terms = list(related_terms or [])
        self._excluded_terms = list(excluded_terms or [])
        self._client: BatchRankerClient = client or PydanticAIBatchRankerClient()
        self.on_status = on_status
        self._provider = provider
        self._workflow_id = workflow_id
        self._reserve_agent = reserve_agent
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
                anchor_terms=", ".join(self._anchor_terms),
                related_terms=", ".join(self._related_terms),
                excluded_terms=", ".join(self._excluded_terms) or "none",
                paper_list=paper_list,
            )
        )
        try:
            t0 = time.perf_counter()
            if self._provider is not None:
                await self._provider.reserve_call_slot(self._reserve_agent)
            raw_response = await self._client.complete_batch(
                prompt,
                model=self._model,
                temperature=self._temperature,
            )
            tok_in = tok_out = cw = cr = 0
            payload: BatchRankerResponsePayload | str
            if isinstance(raw_response, tuple):
                payload, tok_in, tok_out, cw, cr = raw_response
            else:
                payload = raw_response
            if self._provider is not None and self._workflow_id and tok_in >= 0 and tok_out >= 0:
                latency_ms = int((time.perf_counter() - t0) * 1000)
                cost = self._provider.estimate_cost_usd(self._model, tok_in, tok_out, cw, cr)
                await self._provider.log_cost(
                    self._model,
                    tok_in,
                    tok_out,
                    cost,
                    latency_ms,
                    phase="screening_batch_ranker",
                    cache_read_tokens=cr,
                    cache_write_tokens=cw,
                )
            results = self._scores_from_response(payload, batch)
            return results
        except Exception as exc:
            logger.warning(
                "BatchLLMRanker: LLM call failed for batch of %d papers; "
                "all forwarded to dual-reviewer as safe fallback. Error: %s",
                len(batch),
                exc,
            )
            return {p.paper_id: 1.0 for p in batch}

    def _scores_from_response(
        self,
        response: str | BatchRankerResponsePayload,
        batch: list[CandidatePaper],
    ) -> dict[str, float]:
        """Convert validated payload or legacy JSON text into {paper_id -> score}."""
        if isinstance(response, BatchRankerResponsePayload):
            return self._scores_from_payload(response, batch)
        return self._parse_response(str(response), batch)

    def _scores_from_payload(
        self,
        payload: BatchRankerResponsePayload,
        batch: list[CandidatePaper],
    ) -> dict[str, float]:
        scores: dict[str, float] = {}
        seen_ids: set[str] = set()
        for item in payload.ratings:
            paper_id = str(item.id or "").strip()
            if not paper_id:
                continue
            score = max(0.0, min(1.0, float(item.score)))
            scores[paper_id] = score
            seen_ids.add(paper_id)

        for p in batch:
            if p.paper_id not in seen_ids:
                logger.debug(
                    "BatchLLMRanker: paper %s not in LLM response; forwarding with score 1.0",
                    p.paper_id,
                )
                scores[p.paper_id] = 1.0
        return scores

    def _parse_response(self, raw: str, batch: list[CandidatePaper]) -> dict[str, float]:
        """Parse JSON from raw LLM response (legacy array or ratings envelope).

        Tolerates:
        - Markdown code fences around JSON
        - Extra prose before/after the JSON payload
        - Legacy top-level JSON arrays
        - Missing entries (forwards those papers with score 1.0)
        - Invalid scores (clamped to 0.0-1.0)
        """
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            inner = [ln for ln in lines if not ln.startswith("```")]
            text = "\n".join(inner).strip()

        payload: BatchRankerResponsePayload | None = None
        object_start = text.find("{")
        object_end = text.rfind("}")
        if object_start != -1 and object_end > object_start:
            try:
                payload = BatchRankerResponsePayload.model_validate_json(text[object_start : object_end + 1])
            except Exception:
                payload = None

        if payload is not None:
            return self._scores_from_payload(payload, batch)

        array_start = text.find("[")
        array_end = text.rfind("]")
        if array_start == -1 or array_end == -1 or array_end <= array_start:
            logger.warning(
                "BatchLLMRanker: Could not locate JSON payload in response; "
                "forwarding all %d papers. Response prefix: %r",
                len(batch),
                text[:200],
            )
            return {p.paper_id: 1.0 for p in batch}

        try:
            items = json.loads(text[array_start : array_end + 1])
        except json.JSONDecodeError as exc:
            logger.warning(
                "BatchLLMRanker: JSON decode failed (%s); forwarding all %d papers.",
                exc,
                len(batch),
            )
            return {p.paper_id: 1.0 for p in batch}

        if not isinstance(items, list):
            logger.warning(
                "BatchLLMRanker: Expected ratings array in response; forwarding all %d papers.",
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

        forwarded: list[CandidatePaper] = []
        excluded: list[ScreeningDecision] = []
        self.borderline_forwarded_n = 0
        for paper in papers:
            score = all_scores.get(paper.paper_id, 1.0)
            if score >= threshold:
                forwarded.append(paper)
            elif score >= uncertain_floor:
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
