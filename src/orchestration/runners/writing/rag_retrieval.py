"""RAG retrieval for writing: HyDE generation, embedding lookup, reranking, diagnostics."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

from src.db.repositories import WorkflowRepository
from src.models import FallbackEventRecord, RagRetrievalDiagnostic
from src.orchestration.state import ReviewState
from src.rag.embedder import embed_query as rag_embed_query
from src.rag.hyde import generate_hyde_document
from src.rag.reranker import rerank_chunks
from src.rag.retriever import RAGRetriever
from src.writing.prompts.sections import SECTIONS

logger = logging.getLogger(__name__)


@dataclass
class RagResult:
    """Result of RAG retrieval for a single section."""

    context: str = ""
    status: str = "skipped"
    latency_ms: int | None = None
    selected_chunks_json: str = "[]"
    query_type: str = "none"
    retrieved_count: int = 0
    error: str | None = None


async def generate_hyde_documents(
    state: ReviewState,
    *,
    hyde_model: str,
    pico_cfg: Any | None,
    repository: WorkflowRepository,
    rc: Any | None,
) -> dict[str, str]:
    """Pre-generate HyDE documents for all manuscript sections in parallel."""
    hyde_docs: dict[str, str] = {}
    if not state.review:
        return hyde_docs

    _hyde_total = len(SECTIONS)
    _hyde_done: list[int] = [0]
    if rc:
        rc.log_status(f"Pre-generating HyDE retrieval documents for {_hyde_total} manuscript sections (parallel)...")

    async def _hyde_one(s: str) -> str | Exception:
        try:
            result = await generate_hyde_document(
                section=s,
                research_question=state.review.research_question,  # type: ignore[union-attr]
                model=hyde_model,
                pico=pico_cfg,
                repository=repository,
                workflow_id=state.workflow_id,
            )
            _hyde_done[0] += 1
            if rc and hasattr(rc, "log_status"):
                rc.log_status(f"HyDE ready: '{s}' ({_hyde_done[0]}/{_hyde_total} sections)")
            return result
        except Exception as _e:
            _hyde_done[0] += 1
            if rc and hasattr(rc, "log_status"):
                rc.log_status(f"HyDE skipped: '{s}' ({_hyde_done[0]}/{_hyde_total} sections)")
            return _e

    try:
        _hyde_results = await asyncio.gather(
            *[_hyde_one(s) for s in SECTIONS],
            return_exceptions=True,
        )
        for s, res in zip(SECTIONS, _hyde_results):
            if isinstance(res, str) and res:
                hyde_docs[s] = res
        logger.info(
            "HyDE pre-generated %d/%d section docs (PICO=%s)",
            len(hyde_docs),
            len(SECTIONS),
            pico_cfg is not None,
        )
    except Exception as _hyde_err:
        logger.warning("HyDE batch failed: %s -- falling back to bare embed_query", _hyde_err)

    return hyde_docs


async def retrieve_rag_for_section(
    section: str,
    *,
    state: ReviewState,
    repository: WorkflowRepository,
    retriever: RAGRetriever,
    chunk_count: int,
    hyde_docs: dict[str, str],
    embed_model: str,
    embed_dim: int,
    use_rerank: bool,
    reranker_model: str,
    candidate_k: int,
    final_k: int,
    min_chunks_per_section: int,
    rag_empty_policy: str,
    paper_citation_meta: dict[str, dict[str, str]],
    pico_cfg: Any | None,
    rc: Any | None,
) -> RagResult:
    """Perform RAG retrieval for a single section: embed, search, rerank, log diagnostics."""
    result = RagResult()

    try:
        if chunk_count > 0:
            _rag_t0 = asyncio.get_running_loop().time()
            hyde_text = hyde_docs.get(section, "")
            result.query_type = "hyde" if hyde_text else "section_fallback"
            query_vec = await rag_embed_query(
                hyde_text if hyde_text else section,
                model=embed_model,
                dim=embed_dim,
            )
            if hyde_text:
                logger.debug("RAG: HyDE embedding used for section '%s'", section)

            _pico_terms = (
                " ".join(
                    filter(
                        None,
                        [
                            getattr(pico_cfg, "population", "") or "",
                            getattr(pico_cfg, "intervention", "") or "",
                            getattr(pico_cfg, "comparison", "") or "",
                            getattr(pico_cfg, "outcome", "") or "",
                        ],
                    )
                ).strip()
                if pico_cfg
                else ""
            )
            bm25_query = " ".join(
                filter(
                    None,
                    [
                        state.review.research_question,
                        _pico_terms,
                        section,
                    ],
                )
            )
            _section_terms = {
                "methods": "search strategy eligibility criteria risk of bias grade prisma",
                "results": "study characteristics outcome effect size confidence interval p value",
                "discussion": "interpretation limitations certainty grade implications",
            }
            if section in _section_terms:
                bm25_query = f"{bm25_query} {_section_terms[section]}"

            candidate_top_k = candidate_k if use_rerank else final_k
            chunks = await retriever.search(
                query_vec,
                top_k=candidate_top_k,
                query_text=bm25_query,
            )

            if use_rerank and chunks:
                rerank_query = hyde_text if hyde_text else bm25_query
                chunks = await rerank_chunks(
                    rerank_query,
                    chunks,
                    top_k=final_k,
                    model=reranker_model,
                    repository=repository,
                    workflow_id=state.workflow_id,
                )
            elif chunks:
                chunks = chunks[:final_k]

            if chunks:
                _diag_rows: list[str] = []
                _selected_chunks: list[dict[str, str | float | int]] = []
                _rag_lines: list[str] = []
                for c in chunks:
                    _meta = paper_citation_meta.get(c.paper_id, {})
                    _citekey = _meta.get("citekey", "unknown")
                    _year = _meta.get("year", "n.d.")
                    _title = _meta.get("title", "").replace("\n", " ").strip()
                    _title_snippet = _title[:80] if _title else "(No title)"
                    _diag_rows.append(f"{c.chunk_id}|paper={c.paper_id}|citekey={_citekey}|score={c.score:.4f}")
                    _selected_chunks.append(
                        {
                            "chunk_id": c.chunk_id,
                            "paper_id": c.paper_id,
                            "citekey": _citekey,
                            "score": float(c.score),
                        }
                    )
                    _rag_lines.append(
                        f"[Chunk {c.chunk_id} | Paper {c.paper_id} | Citekey {_citekey} | Year {_year} | Title {_title_snippet} | Score {c.score:.4f}]\n{c.content}"
                    )
                result.context = "\n\n".join(_rag_lines)
                result.status = "success"
                result.retrieved_count = len(chunks)
                result.selected_chunks_json = json.dumps(_selected_chunks)
            else:
                result.status = "empty"
                result.retrieved_count = 0

            result.latency_ms = int((asyncio.get_running_loop().time() - _rag_t0) * 1000)
            if rc:
                _diag_model = f"{embed_model} | {('rerank:' + reranker_model) if use_rerank else 'rerank:off'}"
                rc.log_api_call(
                    source="writing",
                    status="success" if result.status in ("success", "empty") else result.status,
                    details=f"RAG retrieval for {section}",
                    records=result.retrieved_count,
                    call_type="rag_retrieval",
                    raw_response="\n".join(_diag_rows) if result.status == "success" else None,
                    latency_ms=result.latency_ms,
                    model=_diag_model,
                    phase="phase_6_writing",
                    section_name=section,
                )
        else:
            result.status = "skipped"
            result.query_type = "none"
    except Exception as _rag_exc:
        logger.warning("RAG retrieval failed for section '%s': %s", section, _rag_exc)
        result.status = "error"
        result.error = str(_rag_exc)
        result.retrieved_count = 0
        if rc:
            rc.log_api_call(
                source="writing",
                status="error",
                details=f"RAG retrieval failed for {section}: {_rag_exc}",
                records=0,
                call_type="rag_retrieval",
                raw_response=None,
                model=embed_model,
                phase="phase_6_writing",
                section_name=section,
            )
    finally:
        await repository.save_rag_retrieval_diagnostic(
            RagRetrievalDiagnostic(
                workflow_id=state.workflow_id,
                section=section,
                query_type=result.query_type,
                rerank_enabled=use_rerank,
                candidate_k=candidate_k,
                final_k=final_k,
                retrieved_count=result.retrieved_count,
                status=result.status,
                selected_chunks_json=result.selected_chunks_json,
                error_message=result.error,
                latency_ms=result.latency_ms,
            )
        )
        if result.status in {"empty", "error"}:
            await repository.save_fallback_event(
                FallbackEventRecord(
                    workflow_id=state.workflow_id,
                    phase="phase_6_writing",
                    module="rag.retrieval",
                    fallback_type=("empty_retrieval_context" if result.status == "empty" else "rag_retrieval_error"),
                    reason=result.error or f"section={section}; retrieved={result.retrieved_count}",
                )
            )
        if result.retrieved_count < min_chunks_per_section and rc:
            rc.log_status(
                f"RAG warning [{section}]: status={result.status}, retrieved={result.retrieved_count}, "
                f"minimum={min_chunks_per_section}"
            )

    if result.status == "empty" and rag_empty_policy == "block":
        raise RuntimeError(f"RAG returned zero chunks for section '{section}' and rag_empty_policy=block")

    return result
