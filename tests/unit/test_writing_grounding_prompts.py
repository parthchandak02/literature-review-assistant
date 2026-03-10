from __future__ import annotations

from src.writing.context_builder import WritingGroundingData, format_grounding_block
from src.writing.prompts.sections import (
    get_discussion_prompt_context,
    get_methods_prompt_context,
    get_results_prompt_context,
)


def _make_grounding(**overrides) -> WritingGroundingData:
    data = WritingGroundingData(
        databases_searched=["pubmed"],
        other_methods_searched=[],
        search_date="2026-03-10",
        total_identified=10,
        duplicates_removed=1,
        total_screened=9,
        fulltext_assessed=3,
        total_included=3,
        fulltext_excluded=0,
        excluded_fulltext_reasons={},
        study_design_counts={"non randomized": 3},
        total_participants=100,
        year_range="2020-2024",
        meta_analysis_feasible=False,
        synthesis_direction="mixed",
        n_studies_synthesized=3,
        narrative_text="Narrative synthesis only.",
        key_themes=["efficiency"],
        study_summaries=[],
        valid_citekeys=["Smith2021"],
        **overrides,
    )
    return data


def test_grounding_block_includes_failed_database_disclosure_rule() -> None:
    data = _make_grounding(
        failed_databases=["web_of_science"],
    )
    out = format_grounding_block(data)
    assert "Databases attempted but failed" in out
    assert "web_of_science" in out
    assert "Do NOT silently omit failed sources" in out


def test_grounding_block_includes_kappa_subset_qualifier() -> None:
    data = _make_grounding(
        cohens_kappa=0.613,
        kappa_n=37,
        kappa_stage="title_abstract",
    )
    out = format_grounding_block(data)
    assert "Cohen's kappa" in out
    assert "subset only" in out
    assert "N=37" in out


def test_grounding_block_includes_figure_map_strict_rule() -> None:
    data = _make_grounding(
        figure_map={"prisma_diagram": 1, "timeline": 3, "geographic": 4},
    )
    out = format_grounding_block(data)
    assert "FIGURE NUMBER MAP -- CRITICAL" in out
    assert "STRICT RULE" in out
    assert "Figure 3: Publication timeline" in out


def test_results_prompt_mentions_figure_map_usage() -> None:
    prompt = get_results_prompt_context()
    assert "FIGURE NUMBER MAP" in prompt
    assert "Do NOT guess figure numbers when a map is provided." in prompt


def test_non_abstract_prompts_include_boundary_marker_rule() -> None:
    methods_prompt = get_methods_prompt_context()
    results_prompt = get_results_prompt_context()
    discussion_prompt = get_discussion_prompt_context()
    assert "SECTION_BLOCK" in methods_prompt
    assert "SECTION_BLOCK" in results_prompt
    assert "SECTION_BLOCK" in discussion_prompt
