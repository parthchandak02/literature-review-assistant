"""Jev listwise relevance scoring for RAG chunk reranking."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.llm.jev_client import JevAskResult, ask_jev, jev_cost_phase, log_jev_cost, record_jev_decision
from src.llm.provider import LLMProvider
from src.models.config import JevConfig

if TYPE_CHECKING:
    from src.db.repositories import WorkflowRepository
    from src.rag.retriever import RetrievedChunk

logger = logging.getLogger(__name__)

_MAX_CHUNKS_PER_CALL = 20
_PHASE = "phase_6_rerank"
SURFACE = "rag_rerank"

_SCORE_CRITERIA = [
    "Completely irrelevant to the query",
    "Tangential mention only",
    "Partially relevant background",
    "Clearly relevant to the query",
    "Directly supports or answers the query",
]


@dataclass(frozen=True)
class JevChunkScores:
    chunk_ids: list[str]
    scores: list[float]
    result: JevAskResult | None = None
    error: str | None = None


def _order_by_scores(chunks: list[RetrievedChunk], scores: list[float], top_k: int) -> list[RetrievedChunk]:
    ranked = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
    result: list[RetrievedChunk] = []
    for rank, idx in enumerate(ranked[:top_k]):
        chunk = chunks[idx]
        chunk.score = max(0.0, 1.0 - rank * 0.05)
        result.append(chunk)
    return result


def _top_ids(chunk_ids: list[str], scores: list[float], top_k: int) -> list[str]:
    ranked = sorted(range(len(chunk_ids)), key=lambda i: scores[i], reverse=True)
    return [chunk_ids[i] for i in ranked[:top_k]]


async def jev_score_chunks(query: str, chunks: list[RetrievedChunk], *, jev: JevConfig) -> JevChunkScores:
    """Score up to _MAX_CHUNKS_PER_CALL chunks in one fan-out. Never raises; never mutates chunks."""
    subset = chunks[:_MAX_CHUNKS_PER_CALL]
    ids = [c.chunk_id for c in subset]
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
        result = await asyncio.wait_for(
            ask_jev(model=jev.model, state=state, questions=questions, timeout_seconds=jev.timeout_seconds),
            timeout=jev.timeout_seconds + 5.0,
        )
    except Exception as exc:
        return JevChunkScores(chunk_ids=ids, scores=[], error=f"{type(exc).__name__}: {str(exc)[:200]}")
    scores: list[float] = []
    for i in range(len(subset)):
        answer = result.answers.get(f"c_{i}") or {}
        try:
            scores.append(float(answer.get("score", 0)))
        except (TypeError, ValueError):
            scores.append(0.0)
    return JevChunkScores(chunk_ids=ids, scores=scores, result=result)


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
    """Live path: score chunks with one Jev fan-out call. Returns None on failure (caller uses LLM)."""
    _ = provider
    if not chunks or len(chunks) <= 1:
        return chunks[:top_k]

    scored = await jev_score_chunks(query, chunks, jev=jev)
    cost: float | None = None
    if scored.result is not None:
        cost = await log_jev_cost(
            repository, jev=jev, result=scored.result, phase=jev_cost_phase(_PHASE, "live"), workflow_id=workflow_id
        )
    await record_jev_decision(
        repository,
        workflow_id=workflow_id,
        phase=_PHASE,
        surface=SURFACE,
        paper_id=None,
        choice="score_rank",
        confidence=1.0,
        routed="jev" if scored.result is not None else "error",
        mode="live",
        result=scored.result,
        cost_usd=cost,
        details={"n_chunks": len(scored.chunk_ids), "top_k": top_k, "error": scored.error},
    )
    if scored.result is None:
        logger.warning("[jev_rerank] failed: %s", scored.error)
        return None

    subset = chunks[:_MAX_CHUNKS_PER_CALL]
    ordered = _order_by_scores(subset, scored.scores, top_k)
    if len(chunks) > len(subset):
        return ordered + chunks[len(subset) : len(subset) + max(0, top_k - len(ordered))]
    return ordered


async def record_rerank_shadow(
    repository: WorkflowRepository | None,
    *,
    jev: JevConfig,
    workflow_id: str,
    shadow: JevChunkScores,
    input_ids: list[str],
    llm_top_ids: list[str],
    top_k: int,
) -> None:
    """Persist the shadow Jev order next to the LLM order. Never raises."""
    try:
        cost: float | None = None
        if shadow.result is not None:
            cost = await log_jev_cost(
                repository, jev=jev, result=shadow.result, phase=jev_cost_phase(_PHASE, "shadow"), workflow_id=workflow_id
            )
        jev_top = _top_ids(shadow.chunk_ids, shadow.scores, top_k) if shadow.scores else []
        overlap = len(set(jev_top) & set(llm_top_ids)) / max(1, min(top_k, len(llm_top_ids))) if jev_top else None
        await record_jev_decision(
            repository,
            workflow_id=workflow_id,
            phase=_PHASE,
            surface=SURFACE,
            paper_id=None,
            choice="score_rank",
            confidence=1.0,
            routed="shadow" if shadow.result is not None else "shadow_error",
            mode="shadow",
            result=shadow.result,
            cost_usd=cost,
            details={
                "top_k": top_k,
                "error": shadow.error,
                "input_ids": input_ids,
                "jev_top_ids": jev_top,
                "llm_top_ids": llm_top_ids,
                "overlap_at_k": overlap,
            },
        )
    except Exception:
        logger.debug("jev_rerank shadow record skipped", exc_info=True)
