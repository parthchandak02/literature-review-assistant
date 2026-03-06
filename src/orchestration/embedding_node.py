"""EmbeddingNode: Phase 4b -- chunk and embed extracted papers for RAG retrieval.

Runs after ExtractionQualityNode, before SynthesisNode.
Idempotent on resume: skips papers already in paper_chunks_meta.
Embedding calls go through pydantic_ai.embeddings.Embedder (Gemini gemini-embedding-001).
Auth is handled by PydanticAI via the GEMINI_API_KEY environment variable.
"""

from __future__ import annotations

import json
import logging

from pydantic_graph import BaseNode, GraphRunContext

from src.db.database import get_db
from src.orchestration.state import ReviewState
from src.rag.chunker import chunk_extraction_record, chunk_table_outcomes
from src.rag.embedder import embed_texts

logger = logging.getLogger(__name__)

_BATCH_SIZE = 20


class EmbeddingNode(BaseNode[ReviewState]):
    """Chunk and embed all extracted papers for semantic retrieval in WritingNode."""

    async def run(self, ctx: GraphRunContext[ReviewState]) -> SynthesisNode:  # type: ignore[name-defined]  # noqa: F821
        from src.orchestration.workflow import SynthesisNode  # local import to avoid circular

        state = ctx.state
        rc = state.run_context

        if rc:
            rc.emit_phase_start(
                "phase_4b_embedding",
                f"Embedding {len(state.extraction_records)} extracted papers...",
                total=len(state.extraction_records),
            )

        rag_cfg = state.settings.rag
        embed_model = rag_cfg.embed_model
        embed_dim = rag_cfg.embed_dim
        embed_batch_size = rag_cfg.embed_batch_size
        chunk_max_words = rag_cfg.chunk_max_words
        chunk_overlap_sentences = rag_cfg.chunk_overlap_sentences

        async with get_db(state.db_path) as db:
            # Load already-embedded paper_ids for idempotent resume
            already_done: set[str] = set()
            async with db.execute(
                "SELECT DISTINCT paper_id FROM paper_chunks_meta WHERE workflow_id = ?",
                (state.workflow_id,),
            ) as cursor:
                async for row in cursor:
                    already_done.add(row[0])

            to_embed = [r for r in state.extraction_records if r.paper_id not in already_done]

            if not to_embed:
                logger.info(
                    "EmbeddingNode: all %d papers already embedded; skipping",
                    len(state.extraction_records),
                )
                if rc:
                    rc.log_status(f"All {len(state.extraction_records)} papers already embedded; skipping.")
            else:
                if rc:
                    rc.log_status(
                        f"Chunking {len(to_embed)} extracted papers into RAG segments..."
                    )
                # Chunk all records -- text chunks + vision-extracted table rows
                all_chunks = []
                for record in to_embed:
                    text_chunks = chunk_extraction_record(
                        record,
                        max_words=chunk_max_words,
                        overlap_sentences=chunk_overlap_sentences,
                    )
                    all_chunks.extend(text_chunks)
                    # Also embed any vision-extracted table outcomes as structured chunks
                    table_outcomes = [o for o in (record.outcomes or []) if o.effect_size or o.p_value or o.ci_lower]
                    if table_outcomes:
                        table_chunks = chunk_table_outcomes(
                            paper_id=record.paper_id,
                            outcomes=table_outcomes,
                            start_index=len(text_chunks),
                        )
                        all_chunks.extend(table_chunks)
                        logger.debug(
                            "EmbeddingNode: added %d table chunks for paper %s",
                            len(table_chunks),
                            record.paper_id,
                        )

                if all_chunks:
                    if rc:
                        rc.log_status(
                            f"Calling embedding API: {len(all_chunks)} chunks from {len(to_embed)} papers "
                            f"(batch_size={embed_batch_size})..."
                        )
                    texts = [c.content for c in all_chunks]
                    embeddings = await embed_texts(
                        texts,
                        batch_size=embed_batch_size,
                        model=embed_model,
                        dim=embed_dim,
                    )

                    if rc:
                        rc.log_status(
                            f"Persisting {len(all_chunks)} embedded chunks to database..."
                        )
                    # Persist chunks with embeddings
                    for chunk, embedding in zip(all_chunks, embeddings):
                        await db.execute(
                            """
                            INSERT OR IGNORE INTO paper_chunks_meta
                                (chunk_id, workflow_id, paper_id, chunk_index, content, embedding)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                chunk.chunk_id,
                                state.workflow_id,
                                chunk.paper_id,
                                chunk.chunk_index,
                                chunk.content,
                                json.dumps(embedding),
                            ),
                        )
                    await db.commit()
                    logger.info(
                        "EmbeddingNode: embedded %d chunks from %d papers",
                        len(all_chunks),
                        len(to_embed),
                    )

            # Save checkpoint
            from src.db.repositories import WorkflowRepository

            repo = WorkflowRepository(db)
            await repo.save_checkpoint(
                state.workflow_id,
                "phase_4b_embedding",
                papers_processed=len(state.extraction_records),
            )

        if rc:
            rc.emit_phase_done(
                "phase_4b_embedding",
                {"chunks_embedded": len(state.extraction_records)},
            )

        return SynthesisNode()
