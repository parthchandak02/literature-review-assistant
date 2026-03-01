"""KnowledgeGraphNode: Phase 5b -- build evidence knowledge graph.

Runs after SynthesisNode, before WritingNode.
Builds a paper relationship graph, runs Louvain community detection,
and detects research gaps. Results are persisted to SQLite for the
/api/run/{run_id}/knowledge-graph endpoint to serve.
Idempotent on resume.
"""

from __future__ import annotations

import json
import logging

from pydantic_graph import BaseNode, GraphRunContext

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.knowledge_graph.builder import build_paper_graph
from src.knowledge_graph.community import detect_communities
from src.knowledge_graph.gap_detector import detect_research_gaps
from src.orchestration.state import ReviewState

logger = logging.getLogger(__name__)


class KnowledgeGraphNode(BaseNode[ReviewState]):
    """Build and persist the paper evidence knowledge graph."""

    async def run(self, ctx: GraphRunContext[ReviewState]) -> "WritingNode":  # type: ignore[name-defined]
        from src.orchestration.workflow import WritingNode  # local import to avoid circular

        state = ctx.state
        rc = state.run_context

        if rc:
            rc.emit_phase_start(
                "phase_5b_knowledge_graph",
                f"Building evidence knowledge graph ({len(state.extraction_records)} papers)...",
                total=1,
            )

        async with get_db(state.db_path) as db:
            repo = WorkflowRepository(db)

            # Check if already done (idempotent on resume)
            already_done = False
            async with db.execute(
                "SELECT COUNT(*) FROM paper_relationships WHERE workflow_id = ?",
                (state.workflow_id,),
            ) as cursor:
                row = await cursor.fetchone()
                already_done = (row[0] if row else 0) > 0

            if already_done:
                logger.info("KnowledgeGraphNode: already done; skipping")
            else:
                # Load chunk embeddings for embedding-based edges
                chunk_embeddings: dict[str, list[float]] = {}
                async with db.execute(
                    "SELECT paper_id, embedding FROM paper_chunks_meta WHERE workflow_id = ? AND embedding IS NOT NULL",
                    (state.workflow_id,),
                ) as cursor:
                    paper_vecs: dict[str, list[list[float]]] = {}
                    async for row in cursor:
                        try:
                            vec = json.loads(row[1])
                            paper_vecs.setdefault(row[0], []).append(vec)
                        except (json.JSONDecodeError, TypeError):
                            continue
                    # Average chunk embeddings to get per-paper embedding
                    for pid, vecs in paper_vecs.items():
                        if vecs:
                            dim = len(vecs[0])
                            mean_vec = [
                                sum(v[i] for v in vecs) / len(vecs)
                                for i in range(dim)
                            ]
                            chunk_embeddings[pid] = mean_vec

                # Build graph
                graph = build_paper_graph(
                    records=state.extraction_records,
                    papers=state.included_papers,
                    chunk_embeddings=chunk_embeddings if chunk_embeddings else None,
                )

                # Run community detection
                updated_nodes, communities = detect_communities(graph)

                # Detect research gaps
                gaps = detect_research_gaps(state.extraction_records)

                # Persist relationships
                for edge in graph.edges:
                    try:
                        await db.execute(
                            """
                            INSERT OR IGNORE INTO paper_relationships
                                (workflow_id, source_paper_id, target_paper_id, rel_type, weight)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (state.workflow_id, edge.source, edge.target, edge.rel_type, edge.weight),
                        )
                    except Exception:
                        pass

                # Persist communities
                for comm in communities:
                    await db.execute(
                        """
                        INSERT OR IGNORE INTO graph_communities
                            (workflow_id, community_id, paper_ids, label)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            state.workflow_id,
                            comm.community_id,
                            json.dumps(comm.paper_ids),
                            comm.label or f"Cluster {comm.community_id}",
                        ),
                    )

                # Persist research gaps
                for gap in gaps:
                    await db.execute(
                        """
                        INSERT OR IGNORE INTO research_gaps
                            (gap_id, workflow_id, description, related_paper_ids, gap_type)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            gap.gap_id,
                            state.workflow_id,
                            gap.description,
                            json.dumps(gap.related_paper_ids),
                            gap.gap_type,
                        ),
                    )

                await db.commit()
                logger.info(
                    "KnowledgeGraphNode: %d edges, %d communities, %d gaps",
                    len(graph.edges),
                    len(communities),
                    len(gaps),
                )

            await repo.save_checkpoint(
                state.workflow_id,
                "phase_5b_knowledge_graph",
                papers_processed=len(state.extraction_records),
            )

        if rc:
            rc.emit_phase_done("phase_5b_knowledge_graph", {"graphs_built": 1})

        return WritingNode()
