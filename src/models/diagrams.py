"""Typed input models for programmatic concept diagram generation.

These models are consumed by src/visualization/concept_diagrams.py and are
constructed from synthesis-phase outputs (NarrativeSynthesisResult, PRISMACounts,
ReviewConfig) before being passed to the diagram renderers.
"""

from __future__ import annotations

import hashlib
import re
from typing import Literal

from pydantic import BaseModel, Field

_HEX6 = re.compile(r"^#[0-9A-Fa-f]{6}$")

_TAXONOMY_PALETTES: list[tuple[str, str, str, str]] = [
    ("#2c3e50", "#3498db", "#ecf0f1", "#2c3e50"),
    ("#1b2631", "#2874a6", "#eaf2f8", "#1c2833"),
    ("#4a235a", "#884ea0", "#f4ecf7", "#512e5f"),
    ("#145a32", "#28b463", "#eafaf1", "#145a32"),
    ("#78281f", "#cb4335", "#fdedec", "#78281f"),
    ("#1b4f72", "#5dade2", "#ebf5fb", "#154360"),
]

_FRAMEWORK_PALETTES: list[tuple[str, str, str, str]] = [
    ("#1a5276", "#1e8449", "#7d6608", "#6c3483"),
    ("#2874a6", "#148f77", "#b7950b", "#884ea0"),
    ("#154360", "#117864", "#9a7d0a", "#512e5f"),
    ("#1f618d", "#239b56", "#b9770e", "#7d3c98"),
    ("#2471a3", "#17a589", "#ca6f1e", "#884ea0"),
    ("#2e86c1", "#229954", "#d68910", "#af7ac5"),
]

_SPLINES_ORDER: tuple[str, ...] = ("ortho", "curved", "polyline", "line", "spline")
_RANKDIR_TAX: tuple[str, ...] = ("TB", "LR", "BT")
_RANKDIR_FW: tuple[str, ...] = ("LR", "RL", "TB")


class DiagramStyleProfile(BaseModel):
    """Deterministic visual theme for LLM-authored DOT/Mermaid concept figures."""

    taxonomy_rankdir: Literal["TB", "LR", "BT"]
    taxonomy_splines: Literal["ortho", "curved", "polyline", "line", "spline"]
    taxonomy_nodesep: float = Field(ge=0.35, le=0.95)
    taxonomy_ranksep: float = Field(ge=0.55, le=1.45)
    taxonomy_root_fill: str
    taxonomy_category_fill: str
    taxonomy_leaf_fill: str
    taxonomy_leaf_fontcolor: str
    taxonomy_leaf_shape: Literal["ellipse", "box"]
    taxonomy_category_rounded: bool

    framework_rankdir: Literal["LR", "RL", "TB"]
    framework_splines: Literal["ortho", "curved", "polyline", "line", "spline"]
    framework_nodesep: float = Field(ge=0.45, le=1.05)
    framework_ranksep: float = Field(ge=0.65, le=1.55)
    framework_pop_fill: str
    framework_int_fill: str
    framework_out_fill: str
    framework_theme_fill: str
    framework_theme_shape: Literal["diamond", "hexagon", "ellipse"]
    framework_cluster_style: Literal["rounded", "solid"]

    mermaid_direction: Literal["TD", "LR"]
    mermaid_title_shape: Literal["stadium", "rectangle"]

    def model_post_init(self, __context: object) -> None:
        for name, val in (
            ("taxonomy_root_fill", self.taxonomy_root_fill),
            ("taxonomy_category_fill", self.taxonomy_category_fill),
            ("taxonomy_leaf_fill", self.taxonomy_leaf_fill),
            ("taxonomy_leaf_fontcolor", self.taxonomy_leaf_fontcolor),
            ("framework_pop_fill", self.framework_pop_fill),
            ("framework_int_fill", self.framework_int_fill),
            ("framework_out_fill", self.framework_out_fill),
            ("framework_theme_fill", self.framework_theme_fill),
        ):
            if not _HEX6.match(val):
                raise ValueError(f"{name} must be a #RRGGBB hex color, got {val!r}")


def diagram_style_profile_from_seed(seed: str) -> DiagramStyleProfile:
    """Build a reproducible style profile from an arbitrary UTF-8 seed string."""
    digest = hashlib.sha256(seed.encode("utf-8")).digest()

    txi = digest[0] % len(_TAXONOMY_PALETTES)
    fwi = digest[1] % len(_FRAMEWORK_PALETTES)
    tr, tc, tl, tlf = _TAXONOMY_PALETTES[txi]
    fp, f_int, fo, ft = _FRAMEWORK_PALETTES[fwi]

    taxonomy_rankdir = _RANKDIR_TAX[digest[2] % len(_RANKDIR_TAX)]  # type: ignore[arg-type]
    taxonomy_splines = _SPLINES_ORDER[digest[3] % len(_SPLINES_ORDER)]  # type: ignore[arg-type]
    taxonomy_nodesep = round(0.38 + (digest[4] % 9) * 0.06, 2)
    taxonomy_ranksep = round(0.58 + (digest[5] % 11) * 0.07, 2)

    framework_rankdir = _RANKDIR_FW[digest[6] % len(_RANKDIR_FW)]  # type: ignore[arg-type]
    framework_splines = _SPLINES_ORDER[digest[7] % len(_SPLINES_ORDER)]  # type: ignore[arg-type]
    framework_nodesep = round(0.48 + (digest[8] % 10) * 0.06, 2)
    framework_ranksep = round(0.72 + (digest[9] % 12) * 0.07, 2)

    leaf_shape: Literal["ellipse", "box"] = "ellipse" if digest[10] % 2 == 0 else "box"
    cat_rounded = digest[11] % 2 == 0

    theme_shape_pool: tuple[Literal["diamond", "hexagon", "ellipse"], ...] = ("diamond", "hexagon", "ellipse")
    fw_theme_shape = theme_shape_pool[digest[12] % 3]

    cluster_style: Literal["rounded", "solid"] = "rounded" if digest[13] % 2 == 0 else "solid"

    mermaid_direction: Literal["TD", "LR"] = "TD" if digest[14] % 2 == 0 else "LR"
    mermaid_title_shape: Literal["stadium", "rectangle"] = "stadium" if digest[15] % 2 == 0 else "rectangle"

    return DiagramStyleProfile(
        taxonomy_rankdir=taxonomy_rankdir,  # type: ignore[arg-type]
        taxonomy_splines=taxonomy_splines,  # type: ignore[arg-type]
        taxonomy_nodesep=taxonomy_nodesep,
        taxonomy_ranksep=taxonomy_ranksep,
        taxonomy_root_fill=tr,
        taxonomy_category_fill=tc,
        taxonomy_leaf_fill=tl,
        taxonomy_leaf_fontcolor=tlf,
        taxonomy_leaf_shape=leaf_shape,
        taxonomy_category_rounded=cat_rounded,
        framework_rankdir=framework_rankdir,  # type: ignore[arg-type]
        framework_splines=framework_splines,  # type: ignore[arg-type]
        framework_nodesep=framework_nodesep,
        framework_ranksep=framework_ranksep,
        framework_pop_fill=fp,
        framework_int_fill=f_int,
        framework_out_fill=fo,
        framework_theme_fill=ft,
        framework_theme_shape=fw_theme_shape,
        framework_cluster_style=cluster_style,
        mermaid_direction=mermaid_direction,
        mermaid_title_shape=mermaid_title_shape,
    )


class TaxonomyCategory(BaseModel):
    """A single branch in a taxonomy tree: one label with leaf items."""

    label: str = Field(..., min_length=1)
    items: list[str] = Field(default_factory=list)
    subcategories: list[TaxonomyCategory] = Field(default_factory=list)


class TaxonomyDiagramInput(BaseModel):
    """Input for a hierarchical taxonomy tree diagram.

    Rendered via LLM -> Graphviz DOT -> SVG.  Typically derived from the
    NarrativeSynthesisResult themes or study-design classification counts.
    """

    title: str
    root_label: str
    categories: list[TaxonomyCategory] = Field(..., min_length=1)
    review_topic: str
    diagram_type: Literal["taxonomy"] = "taxonomy"


class FrameworkNode(BaseModel):
    """A single node in a conceptual framework graph."""

    id: str = Field(..., min_length=1)
    label: str
    node_type: Literal["population", "intervention", "comparator", "outcome", "theme", "other"] = "other"


class FrameworkEdge(BaseModel):
    """A directed edge between two framework nodes."""

    source_id: str
    target_id: str
    label: str | None = None


class FrameworkDiagramInput(BaseModel):
    """Input for a PICO conceptual framework diagram.

    Rendered via LLM -> Graphviz DOT -> SVG.  Nodes represent PICO elements
    and key synthesis themes; edges represent conceptual relationships.
    """

    title: str
    population: str
    interventions: list[str] = Field(..., min_length=1)
    outcomes: list[str] = Field(..., min_length=1)
    key_themes: list[str] = Field(default_factory=list)
    comparator: str | None = None
    study_count: int = Field(..., ge=1)
    review_topic: str
    diagram_type: Literal["framework"] = "framework"


class FlowchartPhase(BaseModel):
    """A single phase box in a methodology flowchart."""

    label: str
    count: int | None = None
    sublabel: str | None = None


class FlowchartDiagramInput(BaseModel):
    """Input for a methodology flowchart diagram.

    Rendered via LLM -> Mermaid syntax -> Kroki API -> SVG.  Phases are
    sequential steps in the review methodology (search, screen, extract, etc.)
    derived from PRISMACounts and ReviewConfig.
    """

    title: str
    phases: list[FlowchartPhase] = Field(..., min_length=2)
    review_topic: str
    diagram_type: Literal["flowchart"] = "flowchart"


ConceptDiagramInput = TaxonomyDiagramInput | FrameworkDiagramInput | FlowchartDiagramInput
