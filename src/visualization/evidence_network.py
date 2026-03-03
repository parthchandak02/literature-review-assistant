"""Evidence network figure renderer.

Loads the knowledge graph from SQLite and renders it to PNG + SVG using
networkx (layout) and matplotlib (drawing). Intended to be called from
KnowledgeGraphNode after the graph is persisted.

Layout: Kamada-Kawai for <= 30 nodes (aesthetically optimal for small
academic graphs), spring layout fallback for larger ones.

Print-quality output (white background, 600 DPI) suitable for direct
embedding in manuscript DOCX and LaTeX PDF.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Node community colors -- vivid enough to pop on a white background
_COMMUNITY_COLORS = [
    "#6d28d9",
    "#1d4ed8",
    "#047857",
    "#b45309",
    "#b91c1c",
    "#0e7490",
    "#7c3aed",
    "#15803d",
    "#7e22ce",
    "#d97706",
]

# Edge colors -- saturated/dark enough to be legible on white paper
_EDGE_COLORS: dict[str, str] = {
    "shared_outcome": "#059669",  # teal-green
    "shared_intervention": "#2563eb",  # blue
    "shared_population": "#d97706",  # amber
    "embedding_similarity": "#7c3aed",  # violet
    "citation": "#db2777",  # pink
}

_GAP_RING_COLOR = "#f59e0b"
_DEFAULT_EDGE_COLOR = "#9ca3af"  # neutral gray -- visible on white
_BACKGROUND_COLOR = "#ffffff"  # white -- print/DOCX friendly
_AXES_COLOR = "#f9fafb"  # very light gray axes background
_LABEL_COLOR = "#111827"  # near-black
_TITLE_COLOR = "#111827"
_LEGEND_FACE = "#f3f4f6"  # light gray legend box


def _truncate(text: str, max_len: int = 24) -> str:
    return text if len(text) <= max_len else text[: max_len - 2] + ".."


async def render_evidence_network(
    db_path: str,
    workflow_id: str,
    output_dir: str,
) -> tuple[str, str]:
    """Render the evidence network to PNG and SVG figures.

    Reads from paper_relationships, graph_communities, papers, and
    research_gaps tables. Returns (png_path, svg_path). Both paths point
    to files inside output_dir.

    PNG is saved at 600 DPI with a white background for manuscript/DOCX
    embedding. SVG is saved at the same white background for LaTeX/PDF.

    Raises RuntimeError if the graph has no edges (nothing to render).
    """
    import aiosqlite
    import matplotlib

    matplotlib.use("Agg")  # non-interactive backend, safe in async context
    import matplotlib.patches as mpatches
    import matplotlib.pyplot as plt
    import networkx as nx

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    png_path = str(out / "fig_evidence_network.png")
    svg_path = str(out / "fig_evidence_network.svg")

    # ------------------------------------------------------------------
    # Load graph data from SQLite
    # ------------------------------------------------------------------
    nodes: dict[str, dict] = {}  # paper_id -> {title, community_id, study_design}
    edges: list[dict] = []  # {source, target, rel_type, weight}
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
                edges.append(
                    {
                        "source": row[0],
                        "target": row[1],
                        "rel_type": row[2],
                        "weight": float(row[3] or 0.5),
                    }
                )

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
            G.add_edge(
                edge["source"],
                edge["target"],
                rel_type=edge["rel_type"],
                weight=edge["weight"],
            )

    # Keep only connected nodes for cleaner output
    connected = {u for u, v in G.edges()} | {v for u, v in G.edges()}
    G.remove_nodes_from([n for n in list(G.nodes()) if n not in connected])

    if G.number_of_nodes() == 0:
        raise RuntimeError("Graph has no connected nodes after filtering isolated ones")

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    n_nodes = G.number_of_nodes()
    if n_nodes <= 30:
        try:
            dist_map: dict[str, dict[str, float]] = {}
            for u in G.nodes():
                dist_map[u] = {}
                for v in G.nodes():
                    if u == v:
                        dist_map[u][v] = 0.0
                    elif G.has_edge(u, v):
                        dist_map[u][v] = max(0.05, 1.0 - G[u][v]["weight"])
                    else:
                        dist_map[u][v] = 1.5
            pos = nx.kamada_kawai_layout(G, dist=dist_map)
        except Exception:
            pos = nx.spring_layout(G, seed=42, k=2.0 / max(1, n_nodes**0.5))
    else:
        pos = nx.spring_layout(G, seed=42, k=2.0 / max(1, n_nodes**0.5), weight="weight")

    # ------------------------------------------------------------------
    # Figure setup -- white background, generous size for label legibility
    # ------------------------------------------------------------------
    fig_w = max(12, min(18, n_nodes * 0.9))
    fig_h = max(9, min(14, n_nodes * 0.65))
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    fig.patch.set_facecolor(_BACKGROUND_COLOR)
    ax.set_facecolor(_AXES_COLOR)
    ax.axis("off")

    # Thin border around axes to frame the graph cleanly
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_edgecolor("#d1d5db")
        spine.set_linewidth(0.8)

    # ------------------------------------------------------------------
    # Draw edges
    # ------------------------------------------------------------------
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
            alpha=0.6,
            width=max(0.8, edge["weight"] * 2.5),
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
            node_size=580,
            ax=ax,
            alpha=0.35,
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
    node_sizes = [max(300, 180 + degree_map.get(n, 0) * 70) for n in node_list]

    nx.draw_networkx_nodes(
        G,
        pos,
        nodelist=node_list,
        node_color=node_colors,
        node_size=node_sizes,
        alpha=0.92,
        ax=ax,
        linewidths=0.8,
        edgecolors="#ffffff",  # white outline improves separation on light bg
    )

    # Node labels: truncated titles, dark text on white label box
    labels = {n: _truncate(G.nodes[n]["title"]) for n in node_list}
    nx.draw_networkx_labels(
        G,
        pos,
        labels=labels,
        font_size=8,  # up from 6 -- legible at 600 DPI
        font_color=_LABEL_COLOR,
        ax=ax,
        verticalalignment="bottom",
        bbox={
            "boxstyle": "round,pad=0.15",
            "facecolor": "#ffffff",
            "edgecolor": "#e5e7eb",
            "alpha": 0.85,
        },
    )

    # ------------------------------------------------------------------
    # Legend
    # ------------------------------------------------------------------
    legend_patches = []
    for rel_type in sorted(drawn_rel_types):
        color = _EDGE_COLORS.get(rel_type, _DEFAULT_EDGE_COLOR)
        legend_patches.append(mpatches.Patch(color=color, label=rel_type.replace("_", " ")))
    if gap_nodes_in_graph:
        legend_patches.append(mpatches.Patch(color=_GAP_RING_COLOR, alpha=0.5, label="research gap"))
    if legend_patches:
        ax.legend(
            handles=legend_patches,
            loc="lower right",
            fontsize=8,
            framealpha=0.9,
            facecolor=_LEGEND_FACE,
            edgecolor="#d1d5db",
            labelcolor=_LABEL_COLOR,
            title="Relationship type",
            title_fontsize=8,
        )

    ax.set_title(
        f"Evidence Network of Included Studies ({n_nodes} studies)",
        color=_TITLE_COLOR,
        fontsize=12,
        fontweight="bold",
        pad=12,
    )

    plt.tight_layout(pad=1.2)

    # PNG at 600 DPI -- publication-quality for DOCX and print
    fig.savefig(
        png_path,
        dpi=600,
        bbox_inches="tight",
        pad_inches=0.15,
        facecolor=_BACKGROUND_COLOR,
    )
    # SVG -- vector for LaTeX / PDF workflows
    fig.savefig(
        svg_path,
        bbox_inches="tight",
        pad_inches=0.15,
        facecolor=_BACKGROUND_COLOR,
    )
    plt.close(fig)

    logger.info(
        "Evidence network rendered: %s (%d nodes, %d edges)",
        png_path,
        n_nodes,
        len(edges),
    )
    return png_path, svg_path
