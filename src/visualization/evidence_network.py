"""Evidence network figure renderer.

Loads the knowledge graph from SQLite and renders it to PNG + SVG using
networkx (layout) and matplotlib (drawing). Intended to be called from
KnowledgeGraphNode after the graph is persisted.

Layout: Kamada-Kawai for <= 30 nodes (aesthetically optimal for small
academic graphs), spring layout fallback for larger ones.

Node colors match the frontend COMMUNITY_COLORS palette.
Edge colors match the frontend EDGE_COLORS palette.
Gap-related papers are highlighted with an outer amber ring.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Match frontend COMMUNITY_COLORS exactly
_COMMUNITY_COLORS = [
    "#7c3aed", "#2563eb", "#059669", "#d97706", "#dc2626",
    "#0891b2", "#7c3aed", "#16a34a", "#9333ea", "#f59e0b",
]

# Match frontend EDGE_COLORS exactly
_EDGE_COLORS: dict[str, str] = {
    "shared_outcome": "#6ee7b7",
    "shared_intervention": "#93c5fd",
    "shared_population": "#fcd34d",
    "embedding_similarity": "#d8b4fe",
    "citation": "#f9a8d4",
}

_GAP_RING_COLOR = "#f59e0b"
_DEFAULT_EDGE_COLOR = "#71717a"
_BACKGROUND_COLOR = "#09090b"
_LABEL_COLOR = "#d4d4d8"
_TITLE_COLOR = "#f4f4f5"


def _truncate(text: str, max_len: int = 22) -> str:
    return text if len(text) <= max_len else text[:max_len - 2] + ".."


async def render_evidence_network(
    db_path: str,
    workflow_id: str,
    output_dir: str,
) -> tuple[str, str]:
    """Render the evidence network to PNG and SVG figures.

    Reads from paper_relationships, graph_communities, papers, and
    research_gaps tables. Returns (png_path, svg_path). Both paths point
    to files inside output_dir.

    Raises RuntimeError if the graph has no edges (nothing to render).
    """
    import aiosqlite
    import matplotlib
    matplotlib.use("Agg")  # non-interactive backend, safe in async context
    import matplotlib.pyplot as plt
    import networkx as nx

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    png_path = str(out / "fig_evidence_network.png")
    svg_path = str(out / "fig_evidence_network.svg")

    # ------------------------------------------------------------------
    # Load graph data from SQLite
    # ------------------------------------------------------------------
    nodes: dict[str, dict] = {}   # paper_id -> {title, community_id}
    edges: list[dict] = []        # {source, target, rel_type, weight}
    gap_paper_ids: set[str] = set()

    async with aiosqlite.connect(db_path) as db:
        # Nodes: papers that have extraction records
        async with db.execute(
            """
            SELECT p.paper_id, p.title, COALESCE(er.study_design, 'unknown')
            FROM papers p
            LEFT JOIN extraction_records er
              ON er.paper_id = p.paper_id AND er.workflow_id = ?
            WHERE p.paper_id IN (
                SELECT paper_id FROM extraction_records WHERE workflow_id = ?
            )
            """,
            (workflow_id, workflow_id),
        ) as cur:
            async for row in cur:
                nodes[row[0]] = {"title": row[1] or "", "community_id": -1, "study_design": row[2]}

        # Attach community IDs
        async with db.execute(
            "SELECT community_id, paper_ids FROM graph_communities WHERE workflow_id = ?",
            (workflow_id,),
        ) as cur:
            async for row in cur:
                try:
                    pids = json.loads(row[1])
                    for pid in pids:
                        if pid in nodes:
                            nodes[pid]["community_id"] = row[0]
                except (TypeError, ValueError):
                    pass

        # Edges
        async with db.execute(
            "SELECT source_paper_id, target_paper_id, rel_type, weight FROM paper_relationships WHERE workflow_id = ?",
            (workflow_id,),
        ) as cur:
            async for row in cur:
                edges.append({"source": row[0], "target": row[1], "rel_type": row[2], "weight": float(row[3] or 0.5)})

        # Gap paper IDs
        async with db.execute(
            "SELECT related_paper_ids FROM research_gaps WHERE workflow_id = ?",
            (workflow_id,),
        ) as cur:
            async for row in cur:
                try:
                    pids = json.loads(row[0]) if row[0] else []
                    gap_paper_ids.update(pids)
                except (TypeError, ValueError):
                    pass

    if not edges:
        raise RuntimeError("No edges in graph -- skipping evidence network figure")

    # ------------------------------------------------------------------
    # Build networkx graph
    # ------------------------------------------------------------------
    G = nx.Graph()
    for pid, meta in nodes.items():
        G.add_node(pid, **meta)

    for edge in edges:
        if edge["source"] in nodes and edge["target"] in nodes:
            G.add_edge(edge["source"], edge["target"], rel_type=edge["rel_type"], weight=edge["weight"])

    # Remove isolated nodes for cleaner output (keep only connected components)
    connected = set()
    for u, v in G.edges():
        connected.add(u)
        connected.add(v)
    isolated = [n for n in list(G.nodes()) if n not in connected]
    G.remove_nodes_from(isolated)

    if G.number_of_nodes() == 0:
        raise RuntimeError("Graph has no connected nodes after filtering isolated ones")

    # ------------------------------------------------------------------
    # Compute layout (VOS-style: edge weight drives proximity)
    # Use Kamada-Kawai for <= 30 nodes (distance-aware, aesthetically clean)
    # ------------------------------------------------------------------
    n_nodes = G.number_of_nodes()
    if n_nodes <= 30:
        # Kamada-Kawai with distance matrix derived from 1 - weight
        try:
            dist_map: dict[str, dict[str, float]] = {}
            for u in G.nodes():
                dist_map[u] = {}
                for v in G.nodes():
                    if u == v:
                        dist_map[u][v] = 0.0
                    elif G.has_edge(u, v):
                        w = G[u][v]["weight"]
                        dist_map[u][v] = max(0.05, 1.0 - w)
                    else:
                        dist_map[u][v] = 1.5  # unconnected = far apart
            pos = nx.kamada_kawai_layout(G, dist=dist_map)
        except Exception:
            pos = nx.spring_layout(G, seed=42, k=2.0 / max(1, n_nodes ** 0.5))
    else:
        pos = nx.spring_layout(G, seed=42, k=2.0 / max(1, n_nodes ** 0.5), weight="weight")

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------
    fig_w = max(10, min(16, n_nodes * 0.8))
    fig_h = max(8, min(12, n_nodes * 0.6))
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    fig.patch.set_facecolor(_BACKGROUND_COLOR)
    ax.set_facecolor(_BACKGROUND_COLOR)
    ax.axis("off")

    # Draw edges grouped by rel_type for legend
    drawn_rel_types: set[str] = set()
    for edge in edges:
        src, tgt = edge["source"], edge["target"]
        if src not in pos or tgt not in pos:
            continue
        color = _EDGE_COLORS.get(edge["rel_type"], _DEFAULT_EDGE_COLOR)
        label = edge["rel_type"].replace("_", " ") if edge["rel_type"] not in drawn_rel_types else None
        nx.draw_networkx_edges(
            G,
            pos,
            edgelist=[(src, tgt)],
            edge_color=[color],
            alpha=0.55,
            width=max(0.5, edge["weight"] * 2.0),
            ax=ax,
            label=label,
        )
        drawn_rel_types.add(edge["rel_type"])

    # Gap paper outer rings (drawn before nodes so nodes appear on top)
    gap_nodes_in_graph = [pid for pid in gap_paper_ids if pid in pos]
    if gap_nodes_in_graph:
        nx.draw_networkx_nodes(
            G,
            pos,
            nodelist=gap_nodes_in_graph,
            node_color=_GAP_RING_COLOR,
            node_size=520,
            ax=ax,
            alpha=0.4,
        )

    # Nodes colored by community
    node_list = list(G.nodes())
    node_colors = [
        _COMMUNITY_COLORS[G.nodes[n]["community_id"] % len(_COMMUNITY_COLORS)]
        if G.nodes[n]["community_id"] >= 0
        else "#6b7280"
        for n in node_list
    ]
    degree_map = dict(G.degree())
    node_sizes = [max(250, 150 + degree_map.get(n, 0) * 60) for n in node_list]

    nx.draw_networkx_nodes(
        G,
        pos,
        nodelist=node_list,
        node_color=node_colors,
        node_size=node_sizes,
        alpha=0.9,
        ax=ax,
    )

    # Node labels: truncated titles
    labels = {n: _truncate(G.nodes[n]["title"]) for n in node_list}
    nx.draw_networkx_labels(
        G,
        pos,
        labels=labels,
        font_size=6,
        font_color=_LABEL_COLOR,
        ax=ax,
        verticalalignment="bottom",
        bbox={"boxstyle": "round,pad=0.1", "facecolor": _BACKGROUND_COLOR, "edgecolor": "none", "alpha": 0.6},
    )

    # Legend for edge types
    legend_patches = []
    import matplotlib.patches as mpatches
    for rel_type in drawn_rel_types:
        color = _EDGE_COLORS.get(rel_type, _DEFAULT_EDGE_COLOR)
        legend_patches.append(mpatches.Patch(color=color, label=rel_type.replace("_", " ")))
    if gap_nodes_in_graph:
        legend_patches.append(mpatches.Patch(color=_GAP_RING_COLOR, alpha=0.6, label="research gap"))
    if legend_patches:
        ax.legend(
            handles=legend_patches,
            loc="lower right",
            fontsize=7,
            framealpha=0.3,
            facecolor=_BACKGROUND_COLOR,
            edgecolor="#3f3f46",
            labelcolor=_LABEL_COLOR,
        )

    ax.set_title(
        "Evidence Network of Included Studies",
        color=_TITLE_COLOR,
        fontsize=11,
        pad=10,
    )

    plt.tight_layout()
    fig.savefig(png_path, dpi=300, bbox_inches="tight", facecolor=_BACKGROUND_COLOR)
    fig.savefig(svg_path, bbox_inches="tight", facecolor=_BACKGROUND_COLOR)
    plt.close(fig)

    logger.info("Evidence network rendered: %s (%d nodes, %d edges)", png_path, n_nodes, len(edges))
    return png_path, svg_path
