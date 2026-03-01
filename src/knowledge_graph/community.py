"""Louvain community detection on the paper relationship graph.

Uses the python-louvain library (community package) for community detection.
Falls back to a trivial single-community assignment if the library is unavailable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.knowledge_graph.builder import PaperEdge, PaperGraph, PaperNode

logger = logging.getLogger(__name__)


@dataclass
class Community:
    """A cluster of related papers detected by Louvain."""

    community_id: int
    paper_ids: list[str]
    label: str = ""


def detect_communities(graph: PaperGraph) -> tuple[list[PaperNode], list[Community]]:
    """Run Louvain community detection on the paper graph.

    Args:
        graph: PaperGraph from build_paper_graph().

    Returns:
        (updated_nodes, communities) where each node has community_id set.
    """
    if not graph.nodes:
        return [], []

    try:
        import networkx as nx  # type: ignore[import-untyped]
        import community as community_louvain  # type: ignore[import-untyped]

        G = nx.Graph()
        for node in graph.nodes:
            G.add_node(node.paper_id)
        for edge in graph.edges:
            G.add_edge(edge.source, edge.target, weight=edge.weight)

        partition = community_louvain.best_partition(G, weight="weight", random_state=42)

        # Assign community IDs to nodes
        updated_nodes: list[PaperNode] = []
        for node in graph.nodes:
            cid = partition.get(node.paper_id, -1)
            updated_nodes.append(
                PaperNode(
                    paper_id=node.paper_id,
                    title=node.title,
                    year=node.year,
                    study_design=node.study_design,
                    community_id=cid,
                )
            )

        # Group paper IDs by community
        community_papers: dict[int, list[str]] = {}
        for paper_id, cid in partition.items():
            community_papers.setdefault(cid, []).append(paper_id)

        communities: list[Community] = [
            Community(community_id=cid, paper_ids=pids)
            for cid, pids in community_papers.items()
        ]

        logger.info(
            "Community detection: %d communities from %d papers",
            len(communities),
            len(graph.nodes),
        )
        return updated_nodes, communities

    except ImportError:
        logger.warning("python-louvain not installed; using single community fallback")
        # Fallback: all papers in one community
        updated_nodes = [
            PaperNode(
                paper_id=n.paper_id,
                title=n.title,
                year=n.year,
                study_design=n.study_design,
                community_id=0,
            )
            for n in graph.nodes
        ]
        communities = [Community(community_id=0, paper_ids=[n.paper_id for n in graph.nodes])]
        return updated_nodes, communities

    except Exception as exc:
        logger.warning("Community detection failed: %s", exc)
        updated_nodes = [
            PaperNode(
                paper_id=n.paper_id,
                title=n.title,
                year=n.year,
                study_design=n.study_design,
                community_id=0,
            )
            for n in graph.nodes
        ]
        communities = [Community(community_id=0, paper_ids=[n.paper_id for n in graph.nodes])]
        return updated_nodes, communities
