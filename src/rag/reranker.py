"""Listwise reranker for RAG retrieval using Gemini Flash.

After hybrid BM25+dense retrieval produces a top-k candidate set, this
reranker prompts an LLM to order the chunks by relevance to the query.
A single LLM call handles all candidates -- no local model download needed.

This approach uses the existing PydanticAI + Gemini infrastructure and adds
zero new package dependencies.

Design: listwise reranking (single call, all chunks ranked together) is more
accurate than pointwise (per-chunk scores) and cheaper than pairwise.
"""
from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from src.llm.provider import LLMProvider
from src.llm.pydantic_client import _run_with_retry
from src.models.additional import CostRecord

if TYPE_CHECKING:
    from src.db.repositories import WorkflowRepository
    from src.rag.retriever import RetrievedChunk

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "google-gla:gemini-2.0-flash"

_RERANK_PROMPT = """\
You are a relevance-ranking assistant for a systematic literature review.

QUERY: {query}

Below are {n} text chunks from research papers. Rank them by relevance to the
query above. The most relevant chunk should come first.

{chunks_text}

Return ONLY a JSON array of the chunk indices (0-based) in descending relevance
order. Include all {n} indices. Example for 5 chunks: [2, 0, 4, 1, 3]
"""


class _RerankOutput(BaseModel):
    indices: list[int]


async def rerank_chunks(
    query: str,
    chunks: list[RetrievedChunk],
    top_k: int = 8,
    model: str = _DEFAULT_MODEL,
    repository: WorkflowRepository | None = None,
) -> list[RetrievedChunk]:
    """Rerank chunks by relevance using Gemini listwise ranking.

    A single LLM call receives all candidate chunks and returns their indices
    in descending relevance order. The top_k best are returned with their
    scores replaced by a position-based rank score.

    Args:
        query: The retrieval query (HyDE text or BM25 query).
        chunks: Candidate chunks from hybrid retriever (top_k=20 recommended).
        top_k: Number of chunks to return after reranking.
        model: Fast LLM model for listwise scoring.
        repository: Optional WorkflowRepository; when provided, cost is logged to DB.

    Returns:
        Up to top_k chunks, ordered by reranker relevance (best first).
        Falls back to original order on any failure.
    """
    if not chunks or len(chunks) <= 1:
        return chunks[:top_k]

    # Truncate each chunk to 400 chars so the prompt stays within token budget.
    chunk_lines = "\n".join(
        f"[{i}] {c.content[:400].replace(chr(10), ' ')}"
        for i, c in enumerate(chunks)
    )
    prompt = _RERANK_PROMPT.format(
        query=query[:500],
        n=len(chunks),
        chunks_text=chunk_lines,
    )

    t0 = time.monotonic()
    try:
        agent: Agent[None, str] = Agent(model, output_type=str)
        result = await _run_with_retry(
            agent, prompt, model_settings=ModelSettings(temperature=0.0)
        )
        raw = result.output.strip()

        # Extract JSON array from the response (handle prose wrapping).
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start == -1 or end == 0:
            raise ValueError(f"No JSON array found in response: {raw[:100]!r}")

        indices: list[int] = json.loads(raw[start:end])
        if not isinstance(indices, list):
            raise ValueError(f"Expected list, got {type(indices)}")

        # Validate and deduplicate indices within bounds.
        valid = []
        seen: set[int] = set()
        for idx in indices:
            if isinstance(idx, int) and 0 <= idx < len(chunks) and idx not in seen:
                valid.append(idx)
                seen.add(idx)

        # Append any missing indices at the end (safety net).
        for i in range(len(chunks)):
            if i not in seen:
                valid.append(i)

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "[reranker] ranked %d chunks in %d ms via %s",
            len(chunks),
            elapsed_ms,
            model,
        )

        if repository:
            usage = result.usage()
            tokens_in = usage.input_tokens or 0
            tokens_out = usage.output_tokens or 0
            cost_usd = LLMProvider.estimate_cost_usd(model, tokens_in, tokens_out)
            await repository.save_cost_record(
                CostRecord(
                    model=model,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=cost_usd,
                    latency_ms=elapsed_ms,
                    phase="phase_6_rerank",
                )
            )

        # Assign descending rank scores (1.0, 0.95, ...) for transparency.
        result_chunks = []
        for rank, idx in enumerate(valid[:top_k]):
            chunk = chunks[idx]
            chunk.score = max(0.0, 1.0 - rank * 0.05)
            result_chunks.append(chunk)
        return result_chunks

    except Exception as exc:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.warning(
            "[reranker] failed after %d ms: %s -- using original RRF order",
            elapsed_ms,
            exc,
        )
        return chunks[:top_k]
