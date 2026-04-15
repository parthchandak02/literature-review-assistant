from __future__ import annotations

from src.models import AgentConfig, OutlineNode, SectionOutline, SectionQualityScore, SettingsConfig
from src.models.writing import SectionBlock, StructuredSectionDraft
from src.writing.context_builder import WritingGroundingData
from src.writing.orchestration import _draft_fingerprint, compute_section_quality_score


def _settings() -> SettingsConfig:
    return SettingsConfig(
        agents={"writing": AgentConfig(model="google-gla:gemini-2.5-flash", temperature=0.1)}
    )


def _grounding(**overrides) -> WritingGroundingData:
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


def test_section_quality_score_orders_lexicographically() -> None:
    baseline = SectionQualityScore(
        hard_issue_count=0,
        completeness_issue_count=1,
        citation_gap_count=0,
        outline_coverage_gaps=0,
        abstract_floor_gap=0,
        soft_issue_count=2,
    )
    worse_hard = baseline.model_copy(update={"hard_issue_count": 1})
    worse_soft = baseline.model_copy(update={"soft_issue_count": 3})

    assert baseline > worse_hard
    assert baseline > worse_soft
    assert worse_hard < worse_soft


def test_section_quality_score_worst_and_fingerprint_stability() -> None:
    draft = StructuredSectionDraft(
        section_key="introduction",
        blocks=[SectionBlock(block_type="paragraph", text="Grounded opening paragraph.")],
    )
    twin = StructuredSectionDraft(
        section_key="introduction",
        blocks=[SectionBlock(block_type="paragraph", text="Grounded opening paragraph.")],
    )
    changed = StructuredSectionDraft(
        section_key="introduction",
        blocks=[SectionBlock(block_type="paragraph", text="Different paragraph.")],
    )

    assert SectionQualityScore.worst() == SectionQualityScore()
    assert _draft_fingerprint(draft) == _draft_fingerprint(twin)
    assert _draft_fingerprint(draft) != _draft_fingerprint(changed)


def test_compute_section_quality_score_counts_outline_and_abstract_gap() -> None:
    draft = StructuredSectionDraft(
        section_key="abstract",
        blocks=[
            SectionBlock(block_type="paragraph", text="**Background:** Background sentence."),
            SectionBlock(block_type="paragraph", text="**Objectives:** Objective sentence."),
            SectionBlock(block_type="paragraph", text="**Methods:** Short methods sentence."),
            SectionBlock(block_type="paragraph", text="**Results:** Short results sentence."),
            SectionBlock(block_type="paragraph", text="**Conclusions:** Short conclusion sentence."),
            SectionBlock(block_type="paragraph", text="**Keywords:** ai tutor, learning."),
        ],
    )
    rendered = "\n".join(block.text for block in draft.blocks)
    outline = SectionOutline(
        section_key="abstract",
        nodes=[
            OutlineNode(
                node_id="limitations",
                heading="Limitations",
                intent="Explicitly state a limitation tied to the evidence base.",
                required_citekeys=[],
                evidence_chunk_ids=[],
            )
        ],
    )

    score, issues = compute_section_quality_score(
        section="abstract",
        draft=draft,
        rendered=rendered,
        outline=outline,
        grounding=_grounding(research_question="How do AI tutors affect learning?"),
        valid_citekeys=set(),
        must_cite=set(),
        settings=_settings(),
        included_study_count=3,
    )

    assert score.outline_coverage_gaps == 1
    assert score.abstract_floor_gap > 0
    assert "outline_coverage:limitations" in issues
