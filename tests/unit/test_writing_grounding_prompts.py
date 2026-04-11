from __future__ import annotations

from src.models.additional import PRISMACounts
from src.writing.context_builder import WritingGroundingData, build_writing_grounding, format_grounding_block
from src.writing.prompts.sections import (
    get_conclusion_prompt_context,
    get_discussion_prompt_context,
    get_methods_prompt_context,
    get_results_prompt_context,
)


def _make_grounding(**overrides) -> WritingGroundingData:
    payload = {
        "databases_searched": ["pubmed"],
        "other_methods_searched": [],
        "search_date": "2026-03-10",
        "total_identified": 10,
        "duplicates_removed": 1,
        "total_screened": 9,
        "fulltext_assessed": 3,
        "total_included": 3,
        "fulltext_excluded": 0,
        "excluded_fulltext_reasons": {},
        "study_design_counts": {"non randomized": 3},
        "total_participants": 100,
        "year_range": "2020-2024",
        "meta_analysis_feasible": False,
        "synthesis_direction": "mixed",
        "n_studies_synthesized": 3,
        "narrative_text": "Narrative synthesis only.",
        "key_themes": ["efficiency"],
        "study_summaries": [],
        "valid_citekeys": ["Smith2021"],
    }
    payload.update(overrides)
    return WritingGroundingData(**payload)


def test_grounding_block_includes_failed_database_disclosure_rule() -> None:
    data = _make_grounding(
        failed_databases=["web_of_science"],
    )
    out = format_grounding_block(data)
    assert "Databases attempted but failed" in out
    assert "web_of_science" in out
    assert "Do NOT silently omit failed sources" in out


def test_grounding_block_includes_topic_anchor_rule() -> None:
    data = _make_grounding(
        research_question="What is the impact of simulation and AI on undergraduate medical education outcomes?",
        topic_anchor_terms=["simulation", "medical", "education"],
    )
    out = format_grounding_block(data)
    assert "Research question:" in out
    assert "TOPIC ANCHOR TERMS" in out
    assert "TOPIC CONSISTENCY RULE" in out


def test_grounding_block_includes_domain_brief_terminology_rules() -> None:
    data = _make_grounding(
        domain_brief_lines=[
            "Expert role: Education evidence reviewer",
            "Preferred terminology: intelligent tutoring system, learning gain",
        ],
        preferred_terminology=["intelligent tutoring system", "learning gain"],
        discouraged_terminology=["clinical endpoint"],
    )
    out = format_grounding_block(data)
    assert "DOMAIN EXPERT BRIEF" in out
    assert "PREFERRED TERMINOLOGY" in out
    assert "clinical endpoint" in out


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


def test_discussion_prompt_includes_topic_anchor_when_grounding_present() -> None:
    data = _make_grounding(
        research_question="How does simulation training affect skill acquisition?",
        topic_anchor_terms=["simulation", "skill", "acquisition"],
    )
    prompt = get_discussion_prompt_context(data)
    assert "TOPIC ANCHOR RULE" in prompt
    assert "How does simulation training affect skill acquisition?" in prompt


def test_methods_prompt_blocks_unsupported_claims() -> None:
    prompt = get_methods_prompt_context()
    assert "Do NOT claim medical librarian consultation" in prompt
    assert "RoB 2, ROBINS-I, CASP, MMAT" in prompt


def test_conclusion_prompt_enforces_hedging_when_required() -> None:
    data = _make_grounding(
        conclusion_hedging_required=True,
        conclusion_hedging_reason="low or very low GRADE certainty",
    )
    prompt = get_conclusion_prompt_context(data)
    assert "CERTAINTY HEDGING RULE" in prompt
    assert "low or very low GRADE certainty" in prompt


def test_build_writing_grounding_zeros_automation_when_screened_gap_is_zero() -> None:
    prisma = PRISMACounts(
        databases_records={"pubmed": 100},
        other_sources_records={},
        total_identified_databases=100,
        total_identified_other=0,
        duplicates_removed=0,
        automation_excluded=83,
        records_screened=100,
        records_excluded_screening=85,
        reports_sought=15,
        reports_not_retrieved=0,
        reports_assessed=15,
        reports_excluded_with_reasons={},
        studies_included_qualitative=15,
        studies_included_quantitative=0,
        arithmetic_valid=True,
    )
    grounding = build_writing_grounding(
        prisma_counts=prisma,
        extraction_records=[],
        included_papers=[],
        narrative=None,
        citation_catalog="",
    )
    assert grounding.records_after_deduplication == 100
    assert grounding.automation_excluded == 83
    assert grounding.total_screened == 17


def test_grounding_block_mentions_overlapping_fulltext_reasons() -> None:
    data = _make_grounding(
        excluded_fulltext_reasons={"wrong_intervention": 6, "wrong_language": 1},
    )
    out = format_grounding_block(data)
    assert "categories may overlap" in out
    assert "do NOT present reason counts as separate article totals" in out


def test_build_writing_grounding_sets_conclusion_hedging_for_high_nonretrieval() -> None:
    prisma = PRISMACounts(
        databases_records={"pubmed": 20},
        other_sources_records={},
        total_identified_databases=20,
        total_identified_other=0,
        duplicates_removed=2,
        automation_excluded=0,
        records_screened=18,
        records_excluded_screening=8,
        reports_sought=10,
        reports_not_retrieved=5,
        reports_assessed=5,
        reports_excluded_with_reasons={},
        studies_included_qualitative=3,
        studies_included_quantitative=0,
        arithmetic_valid=True,
    )
    grounding = build_writing_grounding(
        prisma_counts=prisma,
        extraction_records=[],
        included_papers=[],
        narrative=None,
        citation_catalog="",
    )
    assert grounding.conclusion_hedging_required is True
    assert "high full-text non-retrieval" in grounding.conclusion_hedging_reason


def test_grounding_block_flags_validation_sample_floor_violation() -> None:
    data = _make_grounding(
        batch_screen_forwarded=30,
        batch_screen_excluded=20,
        batch_screen_threshold=0.2,
        batch_screen_validation_n=8,
        batch_screen_validation_npv=0.875,
        batch_screen_validation_min_n=20,
    )
    out = format_grounding_block(data)
    assert "VALIDATION SAMPLE FLOOR" in out
    assert "required minimum is 20" in out
