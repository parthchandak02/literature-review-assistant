from __future__ import annotations

from src.models import SectionBlock, StructuredSectionDraft
from src.writing.context_builder import StudySummary, WritingGroundingData
from src.writing.evidence_assembler import (
    build_results_evidence_pack,
    build_results_section_fallback,
    normalize_results_section_draft,
    render_results_evidence_context,
)


def _grounding() -> WritingGroundingData:
    return WritingGroundingData(
        databases_searched=["OpenAlex"],
        other_methods_searched=[],
        search_date="2026-04-08",
        total_identified=10,
        duplicates_removed=1,
        total_screened=9,
        fulltext_assessed=3,
        total_included=3,
        fulltext_excluded=0,
        excluded_fulltext_reasons={},
        study_design_counts={"randomized controlled trial": 2, "qualitative": 1},
        total_participants=120,
        year_range="2020-2024",
        meta_analysis_feasible=False,
        synthesis_direction="predominantly_positive",
        n_studies_synthesized=3,
        narrative_text="Most studies reported improved learning outcomes.",
        key_themes=["improved engagement", "better retention"],
        study_summaries=[
            StudySummary(
                paper_id="p1",
                title="AI tutor outcomes in higher education",
                year=2024,
                study_design="randomized controlled trial",
                participant_count=50,
                key_finding="Improved examination performance compared with controls.",
            ),
            StudySummary(
                paper_id="p2",
                title="Adaptive tutoring and retention",
                year=2023,
                study_design="randomized controlled trial",
                participant_count=40,
                key_finding="Improved retention after eight weeks.",
            ),
            StudySummary(
                paper_id="p3",
                title="Learner perceptions of AI tutoring",
                year=2022,
                study_design="qualitative",
                participant_count=30,
                key_finding="Students described higher engagement and clearer feedback.",
            ),
        ],
        valid_citekeys=["Smith2024", "Jones2023", "Lee2022"],
        included_study_citekeys=["Smith2024", "Jones2023", "Lee2022"],
        citekey_title_map={
            "Smith2024": "AI tutor outcomes in higher education",
            "Jones2023": "Adaptive tutoring and retention",
            "Lee2022": "Learner perceptions of AI tutoring",
        },
        fulltext_sought=3,
        fulltext_not_retrieved=0,
    )


def test_build_results_evidence_pack_matches_citekeys_to_studies() -> None:
    pack = build_results_evidence_pack(_grounding())
    assert "screened 9 records" in pack.study_selection_sentence
    assert len(pack.studies) == 3
    assert [study.citekey for study in pack.studies] == ["Smith2024", "Jones2023", "Lee2022"]


def test_render_results_evidence_context_includes_study_roster() -> None:
    pack = build_results_evidence_pack(_grounding())
    context = render_results_evidence_context(pack)
    assert "RESULTS EVIDENCE PLAN" in context
    assert "[Smith2024] AI tutor outcomes in higher education" in context
    assert "improved engagement" in context


def test_results_section_fallback_uses_structured_study_citations() -> None:
    pack = build_results_evidence_pack(_grounding())
    draft = build_results_section_fallback(
        pack,
        required_subsections=["Study Selection", "Study Characteristics", "Synthesis of Findings"],
        fallback_citations=[],
    )
    assert draft.section_key == "results"
    assert draft.cited_keys == ["Jones2023", "Lee2022", "Smith2024"]
    assert any(block.citations for block in draft.blocks if block.block_type == "paragraph")


def test_results_section_fallback_rewrites_not_reported_findings() -> None:
    grounding = _grounding()
    grounding.key_themes = ["implementation_barriers", "student_engagement"]
    grounding.study_summaries[0].key_finding = "Not reported"
    pack = build_results_evidence_pack(grounding)
    assert "Theme 1: implementation barriers." in pack.theme_sentences
    draft = build_results_section_fallback(
        pack,
        required_subsections=["Study Selection", "Study Characteristics", "Synthesis of Findings"],
        fallback_citations=[],
    )
    paragraph_text = "\n".join(block.text for block in draft.blocks if block.block_type == "paragraph")
    assert "reported the following key finding: Not reported" not in paragraph_text
    assert "No quantitative outcomes were reported." in paragraph_text


def test_results_section_fallback_avoids_truncated_study_findings() -> None:
    grounding = _grounding()
    grounding.study_summaries[0].key_finding = "The intervention improved reporting timeliness but left administrat"
    pack = build_results_evidence_pack(grounding)
    draft = build_results_section_fallback(
        pack,
        required_subsections=["Study Selection", "Study Characteristics", "Synthesis of Findings"],
        fallback_citations=[],
    )
    paragraph_text = "\n".join(block.text for block in draft.blocks if block.block_type == "paragraph")
    assert "left administrat" not in paragraph_text
    assert "contributed evidence to this review." in paragraph_text


def test_normalize_results_section_draft_materializes_required_subsections() -> None:
    grounding = _grounding()
    pack = build_results_evidence_pack(grounding)
    draft = normalize_results_section_draft(
        draft=StructuredSectionDraft(
            section_key="results",
            blocks=[
                SectionBlock(block_type="subheading", text="Study Selection", level=3),
                SectionBlock(block_type="paragraph", text=pack.study_selection_sentence),
            ],
        ),
        pack=pack,
        fallback_citations=[],
    )
    headings = [block.text for block in draft.blocks if block.block_type == "subheading"]
    assert headings == ["Study Selection", "Study Characteristics", "Synthesis of Findings"]
    paragraph_text = "\n".join(block.text for block in draft.blocks if block.block_type == "paragraph")
    assert "Most studies reported improved learning outcomes." in paragraph_text
