"""EmbeddingNode: Phase 4b -- chunk and embed extracted papers for RAG retrieval.

Runs after ExtractionQualityNode, before SynthesisNode.
Idempotent on resume: skips papers already in paper_chunks_meta.
All embedding calls go through the Gemini text-embedding-004 API.
"""

from __future__ import annotations

import json
import logging
import os

from pydantic_graph import BaseNode, GraphRunContext

from src.db.database import get_db
from src.orchestration.state import ReviewState
from src.rag.chunker import chunk_extraction_record
from src.rag.embedder import embed_texts

logger = logging.getLogger(__name__)

_BATCH_SIZE = 20


class EmbeddingNode(BaseNode[ReviewState]):
    """Chunk and embed all extracted papers for semantic retrieval in WritingNode."""

    async def run(self, ctx: GraphRunContext[ReviewState]) -> "SynthesisNode":  # type: ignore[name-defined]
        from src.orchestration.workflow import SynthesisNode  # local import to avoid circular

        state = ctx.state
        rc = state.run_context

        if rc:
            rc.emit_phase_start(
                "phase_4b_embedding",
                f"Embedding {len(state.extraction_records)} extracted papers...",
                total=len(state.extraction_records),
            )

        api_key = os.environ.get("GEMINI_API_KEY", "")

        async with get_db(state.db_path) as db:
            # Load already-embedded paper_ids for idempotent resume
            already_done: set[str] = set()
            async with db.execute(
                "SELECT DISTINCT paper_id FROM paper_chunks_meta WHERE workflow_id = ?",
                (state.workflow_id,),
            ) as cursor:
                async for row in cursor:
                    already_done.add(row[0])

            to_embed = [
                r for r in state.extraction_records
                if r.paper_id not in already_done
            ]

            if not to_embed:
                logger.info(
                    "EmbeddingNode: all %d papers already embedded; skipping",
                    len(state.extraction_records),
                )
            else:
                # Chunk all records
                all_chunks = []
                for record in to_embed:
                    chunks = chunk_extraction_record(record)
                    all_chunks.extend(chunks)

                if all_chunks:
                    texts = [c.content for c in all_chunks]
                    embeddings = await embed_texts(texts, api_key=api_key, batch_size=_BATCH_SIZE)

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
