"""Deterministic writing checks that prose counts match canonical grounding."""

from __future__ import annotations

from src.models import AgentConfig, SettingsConfig
from src.models.writing import SectionBlock, StructuredSectionDraft
from src.writing.context_builder import WritingGroundingData
from src.writing.section_validation import (
    _grounding_integrity_issues,
    _topic_anchor_issues,
    compute_section_quality_score,
)


def _grounding(**overrides: object) -> WritingGroundingData:
    payload: dict[str, object] = {
        "databases_searched": ["pubmed"],
        "other_methods_searched": [],
        "search_date": "2026-03-10",
        "total_identified": 40,
        "duplicates_removed": 4,
        "total_screened": 30,
        "fulltext_assessed": 12,
        "total_included": 8,
        "fulltext_excluded": 4,
        "excluded_fulltext_reasons": {},
        "study_design_counts": {"rct": 8},
        "total_participants": 400,
        "year_range": "2020-2024",
        "meta_analysis_feasible": False,
        "synthesis_direction": "mixed",
        "n_studies_synthesized": 8,
        "narrative_text": "Narrative synthesis only.",
        "key_themes": ["tutoring"],
        "study_summaries": [],
        "valid_citekeys": ["Smith2021"],
        "fulltext_retrieved_count": 8,
        "fulltext_total_count": 8,
        "fulltext_not_retrieved": 2,
        "included_studies_without_rob_mapping": 0,
        "topic_anchor_terms": ["tutoring", "learning"],
        "research_question": "How do tutoring programs affect learning outcomes?",
    }
    payload.update(overrides)
    return WritingGroundingData(**payload)


def _settings() -> SettingsConfig:
    return SettingsConfig(agents={"writing": AgentConfig(model="google:gemini-2.5-flash", temperature=0.1)})


def test_grounding_integrity_skips_when_grounding_is_missing() -> None:
    content = "The review screened 1 records and included 99 studies."
    assert _grounding_integrity_issues("results", content, None) == []


def test_grounding_integrity_accepts_matching_counts_and_ignores_omitted_counts() -> None:
    matching = (
        "The review screened 30 records. "
        "12 reports were assessed for eligibility. "
        "2 full-text reports were not retrieved. "
        "The review included 8 studies."
    )
    assert _grounding_integrity_issues("results", matching, _grounding()) == []

    omitted = "Narrative synthesis summarized outcome domains without restating flow counts."
    assert _grounding_integrity_issues("results", omitted, _grounding()) == []


def test_grounding_integrity_flags_each_stated_count_mismatch() -> None:
    content = (
        "The review screened 9 records. "
        "3 reports were assessed for eligibility. "
        "7 reports were not retrieved. "
        "In total, 2 studies were included."
    )
    issues = _grounding_integrity_issues("methods", content, _grounding())
    assert issues == [
        "grounding_count_mismatch:assessed",
        "grounding_count_mismatch:included",
        "grounding_count_mismatch:not_retrieved",
        "grounding_count_mismatch:screened",
    ]


def test_grounding_integrity_prefers_included_verb_phrase_over_later_wording() -> None:
    content = "The review included 8 studies. Later text said 2 studies were included."
    assert _grounding_integrity_issues("results", content, _grounding()) == []


def test_grounding_integrity_flags_fulltext_claim_when_retrieval_is_incomplete() -> None:
    grounding = _grounding(fulltext_retrieved_count=3, fulltext_total_count=8)
    methods_claim = "All 8 included studies had their full text retrieved before extraction."
    results_claim = "All 8 included studies had full-text reports available for synthesis."

    assert _grounding_integrity_issues("methods", methods_claim, grounding) == [
        "grounding_fulltext_retrieval_contradiction"
    ]
    assert _grounding_integrity_issues("results", results_claim, grounding) == [
        "grounding_fulltext_retrieval_contradiction"
    ]
    assert _grounding_integrity_issues("discussion", results_claim, grounding) == [
        "grounding_fulltext_retrieval_contradiction"
    ]
    assert _grounding_integrity_issues("methods", results_claim, grounding) == []
    assert _grounding_integrity_issues("introduction", methods_claim, grounding) == []


def test_grounding_integrity_allows_complete_retrieval_claim() -> None:
    claim = "All 8 included studies had their full text retrieved before extraction."
    assert _grounding_integrity_issues("methods", claim, _grounding()) == []
    assert _grounding_integrity_issues("results", claim, _grounding()) == []


def test_grounding_integrity_flags_complete_rob_claim_only_when_coverage_is_gapped() -> None:
    claim = "Risk of bias was assessed and completed for all 8 studies in the included set."
    gapped = _grounding(included_studies_without_rob_mapping=2)
    assert _grounding_integrity_issues("results", claim, gapped) == ["grounding_rob_coverage_contradiction"]
    assert _grounding_integrity_issues("methods", claim, gapped) == ["grounding_rob_coverage_contradiction"]
    assert _grounding_integrity_issues("discussion", claim, gapped) == ["grounding_rob_coverage_contradiction"]
    assert _grounding_integrity_issues("conclusion", claim, gapped) == []
    assert _grounding_integrity_issues("results", claim, _grounding()) == []

    partial = "Risk of bias was assessed for 6 of 8 studies because two records lacked appraisal rows."
    assert _grounding_integrity_issues("results", partial, gapped) == []


def test_grounding_integrity_flags_internal_identifiers() -> None:
    paper_leak = "Extraction notes referred to Paper_abc123 rather than the citekey."
    uuid_leak = "The chunk id a1b2c3d4-e5f6-7890 appeared in the results prose."
    assert _grounding_integrity_issues("results", paper_leak, _grounding()) == ["internal_identifier_leakage"]
    assert _grounding_integrity_issues("discussion", uuid_leak, _grounding()) == ["internal_identifier_leakage"]


def test_topic_anchor_issues_require_section_specific_term_coverage() -> None:
    grounding = _grounding(
        topic_anchor_terms=["tutoring", "learning", "classroom", "outcomes", "reading", "math", "ignored"],
        research_question="How do tutoring programs affect learning outcomes?",
    )
    one_term = "Tutoring improved short-term scores in the included studies."
    two_terms = "Tutoring improved learning outcomes in the included studies."

    assert _topic_anchor_issues("results", one_term, grounding) == []
    assert _topic_anchor_issues("discussion", one_term, grounding) == ["topic_anchor_terms_missing"]
    assert _topic_anchor_issues("conclusion", two_terms, grounding) == []
    assert _topic_anchor_issues("introduction", one_term, grounding) == []
    assert _topic_anchor_issues("discussion", one_term, None) == []

    only_late_term = "The ignored domain was discussed without the earlier anchors."
    assert _topic_anchor_issues("results", only_late_term, grounding) == ["topic_anchor_terms_missing"]


def test_topic_anchor_issues_flag_cross_run_bleed_unless_it_is_in_scope() -> None:
    bleed = "Tutoring and learning evidence drifted into generative conversational ai tutoring systems."
    assert _topic_anchor_issues("discussion", bleed, _grounding()) == ["cross_run_topic_bleed_phrase"]

    in_scope = _grounding(research_question="What is known about generative conversational ai tutoring?")
    anchored = "Tutoring and learning evidence does not establish generative conversational ai tutoring effects."
    assert _topic_anchor_issues("discussion", anchored, in_scope) == []


def test_quality_score_treats_count_mismatch_as_a_hard_issue() -> None:
    draft = StructuredSectionDraft(
        section_key="results",
        blocks=[
            SectionBlock(
                block_type="paragraph",
                text="The review screened 30 records and included 99 studies in the evidence base.",
            )
        ],
    )
    rendered = draft.blocks[0].text
    score, issues = compute_section_quality_score(
        section="results",
        draft=draft,
        rendered=rendered,
        outline=None,
        grounding=_grounding(),
        valid_citekeys={"Smith2021"},
        must_cite=set(),
        settings=_settings(),
        included_study_count=8,
    )

    assert "grounding_count_mismatch:included" in issues
    assert score.hard_issue_count == 1
