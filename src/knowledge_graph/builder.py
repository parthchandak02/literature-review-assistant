"""Build a NetworkX DiGraph of paper relationships from extraction records."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

from src.models import CandidatePaper, ExtractionRecord

logger = logging.getLogger(__name__)

_WEIGHT_THRESHOLD = 0.4
_MAX_EDGES_PER_NODE = 20
_SIMILARITY_THRESHOLD = 0.6


@dataclass
class PaperNode:
    paper_id: str
    title: str
    year: Optional[int]
    study_design: str
    community_id: int = -1


@dataclass
class PaperEdge:
    source: str
    target: str
    rel_type: str
    weight: float


@dataclass
class PaperGraph:
    nodes: list[PaperNode] = field(default_factory=list)
    edges: list[PaperEdge] = field(default_factory=list)


def _jaccard_sets(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union > 0 else 0.0


def _cosine_sim(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _extract_keyword_set(text: Optional[str]) -> set[str]:
    if not text:
        return set()
    words = text.lower().split()
    stopwords = {"the", "a", "an", "and", "or", "of", "in", "for", "to", "with", "on"}
    return {w for w in words if len(w) > 3 and w not in stopwords}


def build_paper_graph(
    records: list[ExtractionRecord],
    papers: list[CandidatePaper],
    chunk_embeddings: dict[str, list[float]] | None = None,
) -> PaperGraph:
    """Build the paper relationship graph from extraction records."""
    try:
        import networkx as nx  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("networkx not installed; returning empty graph")
        return PaperGraph()

    paper_map = {p.paper_id: p for p in papers}

    nodes: list[PaperNode] = []
    for rec in records:
        paper = paper_map.get(rec.paper_id)
        title = paper.title if paper else rec.paper_id
        year = paper.year if paper else None
        nodes.append(
            PaperNode(
                paper_id=rec.paper_id,
                title=title[:100],
                year=year,
                study_design=rec.study_design.value if rec.study_design else "unknown",
            )
        )

    outcome_sets: dict[str, set[str]] = {}
    intervention_sets: dict[str, set[str]] = {}
    population_sets: dict[str, set[str]] = {}

    for rec in records:
        outcome_sets[rec.paper_id] = {
            o.get("name", "").lower().strip()
            for o in rec.outcomes
            if o.get("name", "").strip()
            and o.get("name", "").lower() not in ("primary_outcome", "secondary_outcome", "")
        }
        intervention_sets[rec.paper_id] = _extract_keyword_set(rec.intervention_description)
        population_sets[rec.paper_id] = _extract_keyword_set(rec.participant_demographics)

    raw_edges: list[PaperEdge] = []
    n = len(records)
    edge_counts: dict[str, int] = {r.paper_id: 0 for r in records}

    for i in range(n):
        for j in range(i + 1, n):
            id_a = records[i].paper_id
            id_b = records[j].paper_id

            if edge_counts[id_a] >= _MAX_EDGES_PER_NODE or edge_counts[id_b] >= _MAX_EDGES_PER_NODE:
                continue

            out_sim = _jaccard_sets(outcome_sets.get(id_a, set()), outcome_sets.get(id_b, set()))
            if out_sim >= _WEIGHT_THRESHOLD:
                raw_edges.append(PaperEdge(id_a, id_b, "shared_outcome", out_sim))
                edge_counts[id_a] += 1
                edge_counts[id_b] += 1
                continue

            int_sim = _jaccard_sets(intervention_sets.get(id_a, set()), intervention_sets.get(id_b, set()))
            if int_sim >= _WEIGHT_THRESHOLD:
                raw_edges.append(PaperEdge(id_a, id_b, "shared_intervention", int_sim))
                edge_counts[id_a] += 1
                edge_counts[id_b] += 1
                continue

            pop_sim = _jaccard_sets(population_sets.get(id_a, set()), population_sets.get(id_b, set()))
            if pop_sim >= _WEIGHT_THRESHOLD:
                raw_edges.append(PaperEdge(id_a, id_b, "shared_population", pop_sim))
                edge_counts[id_a] += 1
                edge_counts[id_b] += 1
                continue

            if chunk_embeddings and id_a in chunk_embeddings and id_b in chunk_embeddings:
                emb_sim = _cosine_sim(chunk_embeddings[id_a], chunk_embeddings[id_b])
                if emb_sim >= _SIMILARITY_THRESHOLD:
                    raw_edges.append(PaperEdge(id_a, id_b, "embedding_similarity", emb_sim))
                    edge_counts[id_a] += 1
                    edge_counts[id_b] += 1

    logger.info("Built paper graph: %d nodes, %d edges", len(nodes), len(raw_edges))
    return PaperGraph(nodes=nodes, edges=raw_edges)
