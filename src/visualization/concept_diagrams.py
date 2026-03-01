"""Programmatic concept diagram generation for systematic review papers.

Produces up to three publication-quality SVG diagram files per review:
  1. fig_concept_taxonomy.svg  -- study design / intervention taxonomy tree (Graphviz)
  2. fig_conceptual_framework.svg -- PICO conceptual framework (Graphviz)
  3. fig_methodology_flow.svg  -- review methodology flowchart (Mermaid -> Kroki API)

Rendering pipeline per diagram type:
  - Taxonomy / Framework: LLM generates Graphviz DOT code -> graphviz.Source.pipe(svg)
  - Flowchart: LLM generates Mermaid syntax -> POST https://kroki.io/mermaid/svg -> SVG bytes

DOT code is used instead of raw SVG because LLMs reliably produce valid DOT (~10 lines);
Graphviz then handles all layout math deterministically. Mermaid is used for flowcharts
because its linear sequential syntax is trivial for an LLM to generate correctly.
"""

from __future__ import annotations

import asyncio
import logging
import re
import textwrap
from pathlib import Path
from typing import Optional

import aiohttp

from src.llm.pydantic_client import PydanticAIClient
from src.models.diagrams import (
    FlowchartDiagramInput,
    FrameworkDiagramInput,
    TaxonomyDiagramInput,
)

logger = logging.getLogger(__name__)

_LLM_MODEL = "google-gla:gemini-2.5-flash"
_LLM_TEMPERATURE = 0.3
_KROKI_URL = "https://kroki.io/mermaid/svg"
_KROKI_TIMEOUT_S = 30


# ---------------------------------------------------------------------------
# Internal: LLM helpers
# ---------------------------------------------------------------------------

def _extract_code_block(text: str, language: str) -> str:
    """Extract fenced code block content, falling back to raw text."""
    pattern = rf"```{language}\s*(.*?)```"
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m2 = re.search(r"```\s*(.*?)```", text, re.DOTALL)
    if m2:
        return m2.group(1).strip()
    return text.strip()


async def _llm_generate(prompt: str) -> str:
    client = PydanticAIClient()
    return await client.complete(prompt, model=_LLM_MODEL, temperature=_LLM_TEMPERATURE)


# ---------------------------------------------------------------------------
# Internal: Graphviz renderer
# ---------------------------------------------------------------------------

def _render_dot_to_svg(dot_source: str, out_path: Path) -> Path:
    """Render a DOT string to SVG via the graphviz Python library."""
    import graphviz  # type: ignore[import-untyped]

    src = graphviz.Source(dot_source, format="svg")
    rendered = src.pipe(encoding="utf-8")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# Internal: Kroki renderer (Mermaid -> SVG via REST API)
# ---------------------------------------------------------------------------

async def _render_mermaid_via_kroki(mermaid_source: str, out_path: Path) -> Optional[Path]:
    """POST Mermaid source to Kroki and write the SVG response to out_path.

    Returns None on network failure so the caller can skip without crashing.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                _KROKI_URL,
                json={"diagram_source": mermaid_source},
                timeout=aiohttp.ClientTimeout(total=_KROKI_TIMEOUT_S),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning("Kroki API returned %s: %s", resp.status, body[:200])
                    return None
                svg_bytes = await resp.read()
        out_path.write_bytes(svg_bytes)
        return out_path
    except Exception as exc:  # noqa: BLE001
        logger.warning("Kroki render failed (%s); skipping flowchart diagram.", exc)
        return None


# ---------------------------------------------------------------------------
# Taxonomy tree renderer
# ---------------------------------------------------------------------------

def _build_taxonomy_dot_prompt(spec: TaxonomyDiagramInput) -> str:
    categories_text = []
    for cat in spec.categories:
        items_str = ", ".join(f'"{it}"' for it in cat.items) if cat.items else "(none)"
        sub_str = ""
        if cat.subcategories:
            sub_str = " subcategories: " + ", ".join(
                f'"{s.label}"' for s in cat.subcategories
            )
        categories_text.append(f'  - "{cat.label}": items=[{items_str}]{sub_str}')

    categories_block = "\n".join(categories_text)

    return textwrap.dedent(f"""
        You are a scientific figure generator. Produce ONLY a valid Graphviz DOT digraph
        representing a taxonomy tree for the following systematic review data.

        Review topic: {spec.review_topic}
        Diagram title: {spec.title}
        Root node: {spec.root_label}

        Categories and their leaf items:
        {categories_block}

        Requirements:
        - Use digraph with rankdir=TB (top to bottom)
        - Root node shape: rectangle, fillcolor="#2c3e50", fontcolor=white, style=filled
        - Category nodes: rounded rectangle, fillcolor="#3498db", fontcolor=white, style=filled
        - Leaf nodes: ellipse, fillcolor="#ecf0f1", fontcolor="#2c3e50", style=filled
        - Edges: plain arrows from root to categories, then categories to leaves
        - No node IDs with spaces -- use underscores
        - Set graph [splines=ortho, nodesep=0.5, ranksep=0.8]
        - Set fontname="Helvetica" on all nodes and edges
        - Keep labels concise (max 4 words per node)
        - If a category has subcategories, chain them before leaves

        Return ONLY the DOT code inside a ```dot code block. No explanation.
    """).strip()


async def render_taxonomy_diagram(
    spec: TaxonomyDiagramInput, out_path: Path
) -> Optional[Path]:
    """Generate a taxonomy tree SVG via LLM -> DOT -> Graphviz."""
    prompt = _build_taxonomy_dot_prompt(spec)
    try:
        raw = await _llm_generate(prompt)
        dot_source = _extract_code_block(raw, "dot")
        if not dot_source.startswith("digraph") and not dot_source.startswith("graph"):
            logger.warning("LLM taxonomy DOT output does not look like DOT; skipping.")
            return None
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, _render_dot_to_svg, dot_source, out_path
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Taxonomy diagram generation failed (%s); skipping.", exc)
        return None


# ---------------------------------------------------------------------------
# Conceptual framework renderer
# ---------------------------------------------------------------------------

def _build_framework_dot_prompt(spec: FrameworkDiagramInput) -> str:
    interventions = "\n".join(f"  - {i}" for i in spec.interventions)
    outcomes = "\n".join(f"  - {o}" for o in spec.outcomes)
    themes = (
        "\n".join(f"  - {t}" for t in spec.key_themes)
        if spec.key_themes
        else "  - (none identified)"
    )
    comparator_line = f"Comparator: {spec.comparator}" if spec.comparator else ""

    return textwrap.dedent(f"""
        You are a scientific figure generator. Produce ONLY a valid Graphviz DOT digraph
        representing a PICO conceptual framework for a systematic review.

        Review topic: {spec.review_topic}
        Diagram title: {spec.title}
        Number of included studies: {spec.study_count}
        Population: {spec.population}
        {comparator_line}

        Interventions:
        {interventions}

        Outcomes:
        {outcomes}

        Key synthesis themes:
        {themes}

        Requirements:
        - Use digraph with rankdir=LR (left to right)
        - Population node: leftmost, shape=box, fillcolor="#1a5276", fontcolor=white, style=filled
        - Intervention nodes: shape=box, fillcolor="#1e8449", fontcolor=white, style=filled
        - Outcome nodes: rightmost, shape=box, fillcolor="#7d6608", fontcolor=white, style=filled
        - Theme nodes: shape=diamond, fillcolor="#6c3483", fontcolor=white, style=filled
        - Edges: Population -> Interventions -> Outcomes; Themes connect to relevant Outcomes
        - Use subgraph clusters for Interventions and Outcomes groups with light borders
        - Set fontname="Helvetica" on graph, all nodes and edges
        - No node IDs with spaces -- use underscores
        - Set graph [splines=curved, nodesep=0.6, ranksep=1.0]
        - Keep labels concise (max 5 words per node)

        Return ONLY the DOT code inside a ```dot code block. No explanation.
    """).strip()


async def render_framework_diagram(
    spec: FrameworkDiagramInput, out_path: Path
) -> Optional[Path]:
    """Generate a PICO conceptual framework SVG via LLM -> DOT -> Graphviz."""
    prompt = _build_framework_dot_prompt(spec)
    try:
        raw = await _llm_generate(prompt)
        dot_source = _extract_code_block(raw, "dot")
        if not dot_source.startswith("digraph") and not dot_source.startswith("graph"):
            logger.warning("LLM framework DOT output does not look like DOT; skipping.")
            return None
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, _render_dot_to_svg, dot_source, out_path
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Framework diagram generation failed (%s); skipping.", exc)
        return None


# ---------------------------------------------------------------------------
# Methodology flowchart renderer
# ---------------------------------------------------------------------------

def _build_flowchart_mermaid_prompt(spec: FlowchartDiagramInput) -> str:
    phases_text = []
    for i, phase in enumerate(spec.phases):
        count_str = f" (n={phase.count})" if phase.count is not None else ""
        sub_str = f" -- {phase.sublabel}" if phase.sublabel else ""
        phases_text.append(f"  Phase {i + 1}: {phase.label}{count_str}{sub_str}")
    phases_block = "\n".join(phases_text)

    return textwrap.dedent(f"""
        You are a scientific figure generator. Produce ONLY valid Mermaid flowchart syntax
        representing a systematic review methodology flow.

        Review topic: {spec.review_topic}
        Diagram title: {spec.title}

        Sequential phases (in order):
        {phases_block}

        Requirements:
        - Use "flowchart TD" (top-down)
        - Each phase is a rectangle node with a short label (include count if present)
        - Connect phases sequentially with arrows
        - Use descriptive node IDs (no spaces, e.g. A, B, step1)
        - The first node should use a stadium shape for the title: title(["{spec.title}"])
        - Wrap labels longer than 30 chars using <br/> inside the node label
        - Do NOT include any styling, classDef, or style blocks

        Return ONLY the Mermaid code inside a ```mermaid code block. No explanation.
    """).strip()


async def render_flowchart_diagram(
    spec: FlowchartDiagramInput, out_path: Path
) -> Optional[Path]:
    """Generate a methodology flowchart SVG via LLM -> Mermaid -> Kroki API."""
    prompt = _build_flowchart_mermaid_prompt(spec)
    try:
        raw = await _llm_generate(prompt)
        mermaid_source = _extract_code_block(raw, "mermaid")
        if not mermaid_source.startswith("flowchart") and not mermaid_source.startswith("graph"):
            logger.warning("LLM flowchart output does not look like Mermaid; skipping.")
            return None
        return await _render_mermaid_via_kroki(mermaid_source, out_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Flowchart diagram generation failed (%s); skipping.", exc)
        return None


# ---------------------------------------------------------------------------
# Public API: render all concept diagrams
# ---------------------------------------------------------------------------

async def render_concept_diagrams(
    taxonomy_spec: Optional[TaxonomyDiagramInput],
    framework_spec: Optional[FrameworkDiagramInput],
    flowchart_spec: Optional[FlowchartDiagramInput],
    out_dir: Path,
) -> dict[str, Optional[Path]]:
    """Render all three concept diagrams concurrently.

    Each renderer fails gracefully: if generation fails, the corresponding
    entry in the returned dict is None and a warning is logged.

    Returns a dict with keys:
      "taxonomy"   -> Path to fig_concept_taxonomy.svg or None
      "framework"  -> Path to fig_conceptual_framework.svg or None
      "flowchart"  -> Path to fig_methodology_flow.svg or None
    """
    taxonomy_path = out_dir / "fig_concept_taxonomy.svg"
    framework_path = out_dir / "fig_conceptual_framework.svg"
    flowchart_path = out_dir / "fig_methodology_flow.svg"

    async def _noop() -> None:
        return None

    taxonomy_coro = (
        render_taxonomy_diagram(taxonomy_spec, taxonomy_path)
        if taxonomy_spec is not None
        else _noop()
    )
    framework_coro = (
        render_framework_diagram(framework_spec, framework_path)
        if framework_spec is not None
        else _noop()
    )
    flowchart_coro = (
        render_flowchart_diagram(flowchart_spec, flowchart_path)
        if flowchart_spec is not None
        else _noop()
    )

    raw = await asyncio.gather(
        taxonomy_coro, framework_coro, flowchart_coro, return_exceptions=True
    )

    def _to_path(result: object) -> Optional[Path]:
        if isinstance(result, BaseException):
            logger.warning("Concept sub-diagram failed: %s", result)
            return None
        return result  # type: ignore[return-value]

    return {
        "taxonomy": _to_path(raw[0]),
        "framework": _to_path(raw[1]),
        "flowchart": _to_path(raw[2]),
    }
