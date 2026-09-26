"""Jev relevance pre-ranking for batch screening."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from src.llm.jev_client import ask_jev
from src.llm.provider import LLMProvider
from src.models.config import JevConfig
from src.models.papers import CandidatePaper

if TYPE_CHECKING:
    from src.db.repositories import WorkflowRepository

logger = logging.getLogger(__name__)

_MAX_PAPERS = 15


def _score_to_unit(score_0_4: float) -> float:
    return max(0.0, min(1.0, float(score_0_4) / 4.0))


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
    """Return paper_id -> relevance in [0,1], or None to escalate to LLM batch ranker."""
    if not papers:
        return {}
    subset = papers[:_MAX_PAPERS]
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
    criteria = [
        "Clearly irrelevant to the review question",
        "Mostly off-topic; unlikely to meet inclusion",
        "Possibly relevant; uncertain without full review",
        "Likely relevant to population/intervention/outcome",
        "Clearly relevant primary study for this review",
    ]
    questions = {
        f"p_{i}": {
            "type": "score",
            "instructions": (
                f"For paper #{i} (id={subset[i].paper_id}): relevance to the review "
                "question and PICO in state. Be liberal when uncertain."
            ),
            "criteria": criteria,
        }
        for i in range(len(subset))
    }
    try:
        result = await ask_jev(model=jev.model, state=state, questions=questions, timeout_seconds=jev.timeout_seconds)
    except Exception as exc:
        logger.warning("jev_batch_ranker failed: %s", exc)
        return None

    scores: dict[str, float] = {}
    for i, paper in enumerate(subset):
        answer = result.answers.get(f"p_{i}") or {}
        try:
            scores[paper.paper_id] = _score_to_unit(float(answer.get("score", 2)))
        except (TypeError, ValueError):
            scores[paper.paper_id] = 1.0

    for paper in papers[len(subset) :]:
        scores[paper.paper_id] = 1.0

    if repository and workflow_id:
        try:
            await repository.save_jev_decision(
                workflow_id=workflow_id,
                phase="phase_3_screening",
                surface="batch_pre_rank",
                paper_id=None,
                choice="score_batch",
                confidence=1.0,
                routed="jev",
                details_json=json.dumps({"n_papers": len(subset)}, sort_keys=True),
            )
        except Exception:
            logger.debug("jev batch rank decision log skipped", exc_info=True)

    if provider is not None:
        tok_in = int(result.usage.get("input_tokens", 0))
        tok_out = int(result.usage.get("output_tokens", 0))
        await provider.log_cost(
            model=result.model or jev.model,
            tokens_in=tok_in,
            tokens_out=tok_out,
            cost_usd=provider.estimate_cost(result.model or jev.model, tok_in, tok_out),
            latency_ms=result.latency_ms,
            phase="screening_batch_ranker_jev",
            workflow_id=workflow_id,
        )
    return scores
