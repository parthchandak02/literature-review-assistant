"""Deterministic diagram style profiles for concept figures."""

from __future__ import annotations

import pytest

from src.models.diagrams import (
    DiagramStyleProfile,
    FlowchartDiagramInput,
    FlowchartPhase,
    FrameworkDiagramInput,
    TaxonomyCategory,
    TaxonomyDiagramInput,
    diagram_style_profile_from_seed,
)
from src.visualization.concept_diagrams import (
    _build_flowchart_mermaid_prompt,
    _build_framework_dot_prompt,
    _build_taxonomy_dot_prompt,
)


def _taxonomy_spec() -> TaxonomyDiagramInput:
    return TaxonomyDiagramInput(
        title="Taxonomy",
        root_label="Root",
        categories=[TaxonomyCategory(label="CatA", items=["a", "b"])],
        review_topic="Topic",
    )


def _framework_spec() -> FrameworkDiagramInput:
    return FrameworkDiagramInput(
        title="Framework",
        population="Pop",
        interventions=["Int"],
        outcomes=["Out"],
        study_count=3,
        review_topic="Topic",
    )


def _flow_spec() -> FlowchartDiagramInput:
    return FlowchartDiagramInput(
        title="Flow",
        phases=[
            FlowchartPhase(label="A", count=1),
            FlowchartPhase(label="B", count=2),
        ],
        review_topic="Topic",
    )


def test_diagram_style_profile_from_seed_stable() -> None:
    a = diagram_style_profile_from_seed("wf-test|topic-one")
    b = diagram_style_profile_from_seed("wf-test|topic-one")
    assert a.model_dump() == b.model_dump()


def test_diagram_style_profile_from_seed_differs_across_workflows() -> None:
    x = diagram_style_profile_from_seed("wf-aaa|same topic")
    y = diagram_style_profile_from_seed("wf-bbb|same topic")
    assert x.taxonomy_root_fill != y.taxonomy_root_fill or x.taxonomy_rankdir != y.taxonomy_rankdir


def test_taxonomy_prompt_contains_style_tokens() -> None:
    style = diagram_style_profile_from_seed("seed-xyz")
    prompt = _build_taxonomy_dot_prompt(_taxonomy_spec(), style)
    assert f"rankdir={style.taxonomy_rankdir}" in prompt
    assert style.taxonomy_root_fill in prompt
    assert f"splines={style.taxonomy_splines}" in prompt


def test_framework_prompt_contains_style_tokens() -> None:
    style = diagram_style_profile_from_seed("seed-xyz")
    prompt = _build_framework_dot_prompt(_framework_spec(), style)
    assert f"rankdir={style.framework_rankdir}" in prompt
    assert style.framework_pop_fill in prompt
    assert style.framework_theme_shape in prompt


def test_flowchart_prompt_respects_mermaid_direction() -> None:
    style_td = diagram_style_profile_from_seed("force-td-seed")
    # Fixed seeds may still be LR; assert prompt matches model field
    p = _build_flowchart_mermaid_prompt(_flow_spec(), style_td)
    assert f"flowchart {style_td.mermaid_direction}" in p
    if style_td.mermaid_title_shape == "stadium":
        assert "stadium" in p or "([" in p
    else:
        assert "rectangle" in p.lower()


def test_diagram_style_profile_rejects_bad_hex() -> None:
    with pytest.raises(ValueError, match="taxonomy_root_fill"):
        DiagramStyleProfile(
            taxonomy_rankdir="TB",
            taxonomy_splines="ortho",
            taxonomy_nodesep=0.5,
            taxonomy_ranksep=0.8,
            taxonomy_root_fill="not-a-color",
            taxonomy_category_fill="#3498db",
            taxonomy_leaf_fill="#ecf0f1",
            taxonomy_leaf_fontcolor="#2c3e50",
            taxonomy_leaf_shape="ellipse",
            taxonomy_category_rounded=True,
            framework_rankdir="LR",
            framework_splines="curved",
            framework_nodesep=0.6,
            framework_ranksep=1.0,
            framework_pop_fill="#1a5276",
            framework_int_fill="#1e8449",
            framework_out_fill="#7d6608",
            framework_theme_fill="#6c3483",
            framework_theme_shape="diamond",
            framework_cluster_style="rounded",
            mermaid_direction="TD",
            mermaid_title_shape="stadium",
        )
