"""Jev listwise relevance scoring for RAG chunk reranking."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from src.llm.jev_client import ask_jev
from src.llm.provider import LLMProvider
from src.models.config import JevConfig

if TYPE_CHECKING:
    from src.db.repositories import WorkflowRepository
    from src.rag.retriever import RetrievedChunk

logger = logging.getLogger(__name__)

_MAX_CHUNKS_PER_CALL = 20

_SCORE_CRITERIA = [
    "Completely irrelevant to the query",
    "Tangential mention only",
    "Partially relevant background",
    "Clearly relevant to the query",
    "Directly supports or answers the query",
]


def _order_by_scores(chunks: list[RetrievedChunk], scores: list[float], top_k: int) -> list[RetrievedChunk]:
    ranked = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
    result: list[RetrievedChunk] = []
    for rank, idx in enumerate(ranked[:top_k]):
        chunk = chunks[idx]
        chunk.score = max(0.0, 1.0 - rank * 0.05)
        result.append(chunk)
    return result


async def jev_rerank_chunks(
    query: str,
    chunks: list[RetrievedChunk],
    *,
    top_k: int,
    jev: JevConfig,
    workflow_id: str,
    repository: WorkflowRepository | None,
    provider: LLMProvider | None,
) -> list[RetrievedChunk] | None:
    """Score chunks with one Jev fan-out call. Returns None on failure (caller uses LLM)."""
    if not chunks or len(chunks) <= 1:
        return chunks[:top_k]

    subset = chunks[:_MAX_CHUNKS_PER_CALL]
    state = {
        "query": query[:500],
        "chunks": [c.content[:400].replace("\n", " ") for c in subset],
    }
    questions = {
        f"c_{i}": {
            "type": "score",
            "instructions": (
                f"For chunk #{i}: how relevant is this text to the query? "
                "Judge only the chunk text against the query in state."
            ),
            "criteria": _SCORE_CRITERIA,
        }
        for i in range(len(subset))
    }
    try:
        result = await ask_jev(model=jev.model, state=state, questions=questions, timeout_seconds=jev.timeout_seconds)
    except Exception as exc:
        logger.warning("[jev_rerank] failed: %s", exc)
        return None

    scores: list[float] = []
    for i in range(len(subset)):
        answer = result.answers.get(f"c_{i}") or {}
        try:
            scores.append(float(answer.get("score", 0)))
        except (TypeError, ValueError):
            scores.append(0.0)

    if repository and workflow_id:
        try:
            await repository.save_jev_decision(
                workflow_id=workflow_id,
                phase="phase_6_rerank",
                surface="rag_rerank",
                paper_id=None,
                choice="score_rank",
                confidence=1.0,
                routed="jev",
                details_json=json.dumps({"n_chunks": len(subset), "top_k": top_k}, sort_keys=True),
            )
        except Exception:
            logger.debug("jev_rerank decision log skipped", exc_info=True)

    if provider is not None:
        tok_in = int(result.usage.get("input_tokens", 0))
        tok_out = int(result.usage.get("output_tokens", 0))
        cost = provider.estimate_cost(result.model or jev.model, tok_in, tok_out)
        await provider.log_cost(
            model=result.model or jev.model,
            tokens_in=tok_in,
            tokens_out=tok_out,
            cost_usd=cost,
            latency_ms=result.latency_ms,
            phase="phase_6_rerank_jev",
            workflow_id=workflow_id,
        )

    ordered = _order_by_scores(subset, scores, top_k)
    if len(chunks) > len(subset):
        return ordered + chunks[len(subset) : len(subset) + max(0, top_k - len(ordered))]
    return ordered
