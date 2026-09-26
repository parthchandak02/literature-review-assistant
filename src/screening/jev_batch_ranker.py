"""Jev relevance pre-ranking for batch screening."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.llm.jev_client import (
    JevAskResult,
    ask_jev,
    bounded_gather,
    jev_cost_phase,
    log_jev_cost,
    record_jev_decision,
)
from src.llm.provider import LLMProvider
from src.models.config import JevConfig
from src.models.papers import CandidatePaper

if TYPE_CHECKING:
    from src.db.repositories import WorkflowRepository

logger = logging.getLogger(__name__)

_MAX_PAPERS = 15
_PHASE = "screening_batch_ranker"
SURFACE = "batch_pre_rank"

_CRITERIA = [
    "Clearly irrelevant to the review question",
    "Mostly off-topic; unlikely to meet inclusion",
    "Possibly relevant; uncertain without full review",
    "Likely relevant to population/intervention/outcome",
    "Clearly relevant primary study for this review",
]


@dataclass
class JevBatchScores:
    scores: dict[str, float] = field(default_factory=dict)
    results: list[JevAskResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return bool(self.errors)


def _score_to_unit(score_0_4: float) -> float:
    return max(0.0, min(1.0, float(score_0_4) / 4.0))


def _chunk_state_and_questions(
    subset: list[CandidatePaper], research_question: str, population: str, intervention: str, outcome: str
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    state = {
        "research_question": research_question[:400],
        "population": population[:200],
        "intervention": intervention[:200],
        "outcome": outcome[:200],
        "papers": [
            {
                "id": p.paper_id,
                "title": (p.title or "")[:200],
                "abstract": (p.abstract or "")[:350].replace("\n", " "),
            }
            for p in subset
        ],
    }
    questions = {
        f"p_{i}": {
            "type": "score",
            "instructions": (
                f"For paper #{i} (id={subset[i].paper_id}): relevance to the review "
                "question and PICO in state. Be liberal when uncertain."
            ),
            "criteria": _CRITERIA,
        }
        for i in range(len(subset))
    }
    return state, questions


async def jev_score_papers(
    *,
    papers: list[CandidatePaper],
    research_question: str,
    population: str,
    intervention: str,
    outcome: str,
    jev: JevConfig,
) -> JevBatchScores:
    """Score every paper via anchored fan-outs of <= _MAX_PAPERS. Never raises."""
    out = JevBatchScores()
    chunks = [papers[i : i + _MAX_PAPERS] for i in range(0, len(papers), _MAX_PAPERS)]

    async def _one(subset: list[CandidatePaper]) -> tuple[list[CandidatePaper], JevAskResult | None, str | None]:
        state, questions = _chunk_state_and_questions(subset, research_question, population, intervention, outcome)
        try:
            result = await asyncio.wait_for(
                ask_jev(model=jev.model, state=state, questions=questions, timeout_seconds=jev.timeout_seconds),
                timeout=jev.timeout_seconds + 5.0,
            )
            return subset, result, None
        except Exception as exc:
            return subset, None, f"{type(exc).__name__}: {str(exc)[:200]}"

    for subset, result, error in await bounded_gather((_one(c) for c in chunks), jev.shadow_concurrency):
        if result is None:
            out.errors.append(error or "unknown")
            continue
        out.results.append(result)
        for i, paper in enumerate(subset):
            answer = result.answers.get(f"p_{i}") or {}
            try:
                out.scores[paper.paper_id] = _score_to_unit(float(answer.get("score", 2)))
            except (TypeError, ValueError):
                out.scores[paper.paper_id] = 1.0
    return out


async def jev_batch_relevance_scores(
    *,
    papers: list[CandidatePaper],
    research_question: str,
    population: str,
    intervention: str,
    outcome: str,
    jev: JevConfig,
    workflow_id: str,
    repository: WorkflowRepository | None,
    provider: LLMProvider | None,
) -> dict[str, float] | None:
    """Live path: paper_id -> relevance in [0,1], or None to escalate to the LLM batch ranker."""
    _ = provider
    if not papers:
        return {}
    scored = await jev_score_papers(
        papers=papers,
        research_question=research_question,
        population=population,
        intervention=intervention,
        outcome=outcome,
        jev=jev,
    )
    cost = 0.0
    for result in scored.results:
        cost += await log_jev_cost(
            repository, jev=jev, result=result, phase=jev_cost_phase(_PHASE, "live"), workflow_id=workflow_id
        )
    await record_jev_decision(
        repository,
        workflow_id=workflow_id,
        phase="phase_3_screening",
        surface=SURFACE,
        paper_id=None,
        choice="score_batch",
        confidence=1.0,
        routed="escalate" if scored.failed else "jev",
        mode="live",
        cost_usd=cost,
        details={
            "n_papers": len(papers),
            "n_calls": len(scored.results),
            "latency_ms": max((r.latency_ms for r in scored.results), default=0),
            "errors": scored.errors,
            "jev_scores": scored.scores,
        },
    )
    if scored.failed:
        logger.warning("jev_batch_ranker failed: %s", "; ".join(scored.errors))
        return None
    return scored.scores


async def record_batch_rank_shadow(
    repository: WorkflowRepository | None,
    *,
    jev: JevConfig,
    workflow_id: str,
    shadow: JevBatchScores,
    llm_scores: dict[str, float],
    threshold: float,
) -> None:
    """Persist one shadow row per batch with both score maps. Never raises."""
    try:
        cost = 0.0
        for result in shadow.results:
            cost += await log_jev_cost(
                repository, jev=jev, result=result, phase=jev_cost_phase(_PHASE, "shadow"), workflow_id=workflow_id
            )
        common = [pid for pid in shadow.scores if pid in llm_scores]
        agree = sum(1 for pid in common if (shadow.scores[pid] >= threshold) == (llm_scores[pid] >= threshold))
        await record_jev_decision(
            repository,
            workflow_id=workflow_id,
            phase="phase_3_screening",
            surface=SURFACE,
            paper_id=None,
            choice="score_batch",
            confidence=1.0,
            routed="shadow_error" if shadow.failed and not shadow.results else "shadow",
            mode="shadow",
            cost_usd=cost,
            details={
                "n_papers": len(llm_scores),
                "n_calls": len(shadow.results),
                "latency_ms": max((r.latency_ms for r in shadow.results), default=0),
                "tokens_in": sum(int(r.usage.get("input_tokens", 0)) for r in shadow.results),
                "tokens_out": sum(int(r.usage.get("output_tokens", 0)) for r in shadow.results),
                "errors": shadow.errors,
                "threshold": threshold,
                "forward_agreement": (agree / len(common)) if common else None,
                "jev_scores": shadow.scores,
                "llm_scores": llm_scores,
            },
        )
    except Exception:
        logger.debug("jev batch rank shadow record skipped", exc_info=True)
