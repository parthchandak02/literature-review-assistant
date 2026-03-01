"""Typed input models for programmatic concept diagram generation.

These models are consumed by src/visualization/concept_diagrams.py and are
constructed from synthesis-phase outputs (NarrativeSynthesisResult, PRISMACounts,
ReviewConfig) before being passed to the diagram renderers.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class TaxonomyCategory(BaseModel):
    """A single branch in a taxonomy tree: one label with leaf items."""

    label: str = Field(..., min_length=1)
    items: list[str] = Field(default_factory=list)
    subcategories: list["TaxonomyCategory"] = Field(default_factory=list)


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
    label: Optional[str] = None


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
    comparator: Optional[str] = None
    study_count: int = Field(..., ge=1)
    review_topic: str
    diagram_type: Literal["framework"] = "framework"


class FlowchartPhase(BaseModel):
    """A single phase box in a methodology flowchart."""

    label: str
    count: Optional[int] = None
    sublabel: Optional[str] = None


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
