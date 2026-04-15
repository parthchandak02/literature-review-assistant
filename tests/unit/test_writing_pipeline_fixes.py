from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.extraction.extractor import detect_scope_mismatch
from src.extraction.inference_utils import result_not_extractable_text
from src.manuscript.cohort import IncludedSetResolver
from src.models import (
    CandidatePaper,
    ExtractionRecord,
    SectionBlock,
    SourceCategory,
    StructuredSectionDraft,
    StudyDesign,
)
from src.models.additional import PRISMACounts
from src.writing.context_builder import build_writing_grounding, sanitize_summary_text_for_writing
from src.writing.headings import extract_markdown_heading_inventory, normalize_subsection_heading_layout
from src.writing.orchestration import (
    _best_effort_accept,
    _patch_methods_grounding,
    _patch_results_grounding,
    _post_render_completeness_issues,
    _sanitize_prose,
    _validate_structured_section_draft,
)
from src.writing.renderers import collect_section_heading_inventory, render_section_markdown


def _prisma_counts() -> PRISMACounts:
    return PRISMACounts(
        databases_records={"openalex": 1},
        other_sources_records={},
        total_identified_databases=1,
        total_identified_other=0,
        duplicates_removed=0,
        records_screened=1,
        records_excluded_screening=0,
        reports_sought=1,
        reports_not_retrieved=0,
        reports_assessed=1,
        reports_excluded_with_reasons={},
        studies_included_qualitative=1,
        studies_included_quantitative=0,
        arithmetic_valid=True,
        records_after_deduplication=1,
        total_included=1,
    )


def _paper() -> CandidatePaper:
    return CandidatePaper(
        paper_id="p1",
        title="AI tutor outcomes in higher education",
        authors=["Smith"],
        year=2024,
        source_database="openalex",
        source_category=SourceCategory.DATABASE,
    )


def test_best_effort_accept_prefers_richer_generated_draft() -> None:
    generated = StructuredSectionDraft(
        section_key="discussion",
        blocks=[
            SectionBlock(block_type="paragraph", text=" ".join(["substantive"] * 45) + "."),
            SectionBlock(block_type="paragraph", text=" ".join(["evidence"] * 38) + "."),
        ],
    )
    fallback = StructuredSectionDraft(
        section_key="discussion",
        blocks=[
            SectionBlock(
                block_type="paragraph",
                text="Section content was generated using deterministic fallback due to incomplete model output.",
            )
        ],
    )
    assert _best_effort_accept(
        "discussion",
        generated,
        fallback,
        ["topic_anchor_terms_missing"],
        included_study_count=8,
    )


def test_key_finding_sanitization_becomes_not_reported() -> None:
    record = ExtractionRecord(
        paper_id="p1",
        study_design=StudyDesign.CROSS_SECTIONAL,
        intervention_description="",
        outcomes=[],
        results_summary={"summary": "The provided text does not contain the requested outcomes."},
    )
    grounding = build_writing_grounding(
        prisma_counts=_prisma_counts(),
        extraction_records=[record],
        included_papers=[_paper()],
        narrative=None,
    )
    assert sanitize_summary_text_for_writing(record.results_summary["summary"]) == "NR"
    assert grounding.study_summaries[0].key_finding == result_not_extractable_text()


def test_key_finding_sanitization_strips_excerpt_artifacts() -> None:
    record = ExtractionRecord(
        paper_id="p1",
        study_design=StudyDesign.CROSS_SECTIONAL,
        intervention_description="",
        outcomes=[],
        extraction_source="text",
        results_summary={"summary": "Specific findings are not presented in the available excerpt."},
    )
    grounding = build_writing_grounding(
        prisma_counts=_prisma_counts(),
        extraction_records=[record],
        included_papers=[_paper()],
        narrative=None,
    )
    assert sanitize_summary_text_for_writing(record.results_summary["summary"]) == "NR"
    assert grounding.study_summaries[0].key_finding == result_not_extractable_text()
    assert grounding.nonextractable_result_count == 1
    assert grounding.abstract_only_result_gap_count == 1


def test_build_writing_grounding_replaces_internal_study_ids_in_titles() -> None:
    record = ExtractionRecord(
        paper_id="p1",
        study_design=StudyDesign.CROSS_SECTIONAL,
        intervention_description="",
        outcomes=[],
        results_summary={"summary": "Outcome improved."},
    )
    paper = CandidatePaper(
        paper_id="p1",
        title="Paper_abcdef",
        authors=["Smith"],
        year=2024,
        source_database="openalex",
        source_category=SourceCategory.DATABASE,
    )
    grounding = build_writing_grounding(
        prisma_counts=_prisma_counts(),
        extraction_records=[record],
        included_papers=[paper],
        narrative=None,
    )
    assert grounding.study_summaries[0].title == "Included study"


def test_build_writing_grounding_filters_off_topic_themes() -> None:
    record = ExtractionRecord(
        paper_id="p1",
        study_design=StudyDesign.CROSS_SECTIONAL,
        intervention_description="Digital immunization registry deployment in rural clinics.",
        outcomes=[],
        results_summary={"summary": "Registry adoption improved reporting completeness and coverage."},
    )
    review = SimpleNamespace(
        research_question="How do digital immunization registries affect vaccine coverage in rural clinics?",
        topic="digital immunization registries",
    )
    grounding = build_writing_grounding(
        prisma_counts=_prisma_counts(),
        extraction_records=[record],
        included_papers=[_paper()],
        narrative={
            "feasibility": {},
            "narrative": {
                "effect_direction_summary": "predominantly_positive",
                "n_studies": 1,
                "narrative_text": "Coverage improved after registry deployment.",
                "key_themes": [
                    "vaccine_coverage",
                    "reporting_completeness",
                    "average_hash_delay",
                ],
            },
        },
        review_config=review,
    )
    assert grounding.key_themes == ["vaccine coverage", "reporting completeness"]


def test_build_writing_grounding_prefers_extracted_country_for_study_summary() -> None:
    record = ExtractionRecord(
        paper_id="p1",
        study_design=StudyDesign.CROSS_SECTIONAL,
        intervention_description="Registry deployment",
        outcomes=[],
        results_summary={"summary": "Coverage improved."},
        country="Kenya",
    )
    paper = _paper().model_copy(update={"country": None})
    grounding = build_writing_grounding(
        prisma_counts=_prisma_counts(),
        extraction_records=[record],
        included_papers=[paper],
        narrative=None,
    )
    assert grounding.study_summaries[0].country == "Kenya"


def test_build_writing_grounding_infers_country_from_abstract_when_missing() -> None:
    record = ExtractionRecord(
        paper_id="p1",
        study_design=StudyDesign.CROSS_SECTIONAL,
        intervention_description="Registry deployment",
        outcomes=[],
        results_summary={"summary": "Coverage improved in district facilities."},
        country=None,
    )
    paper = _paper().model_copy(
        update={
            "country": None,
            "title": "District registry performance study",
            "abstract": "This cross-sectional study evaluated registry performance in Kenya across six clinics.",
        }
    )
    grounding = build_writing_grounding(
        prisma_counts=_prisma_counts(),
        extraction_records=[record],
        included_papers=[paper],
        narrative=None,
    )
    assert grounding.study_summaries[0].country == "Kenya"


def test_build_writing_grounding_normalizes_standalone_criterion_years() -> None:
    record = ExtractionRecord(
        paper_id="p1",
        study_design=StudyDesign.CROSS_SECTIONAL,
        intervention_description="Registry deployment",
        outcomes=[],
        results_summary={"summary": "Coverage improved."},
    )
    review = SimpleNamespace(
        date_range_start=2000,
        date_range_end=2026,
        inclusion_criteria=["Studies published after 2010 were eligible."],
        exclusion_criteria=["Exclude reports published since 2027."],
        protocol=SimpleNamespace(registered=False, registration_number=""),
        author_name="",
    )
    grounding = build_writing_grounding(
        prisma_counts=_prisma_counts(),
        extraction_records=[record],
        included_papers=[_paper()],
        narrative=None,
        review_config=review,
    )
    assert grounding.eligibility_inclusion_criteria == ["Studies published after 2000-2026 were eligible."]
    assert grounding.eligibility_exclusion_criteria == ["Exclude reports published since 2000-2026."]


def test_build_writing_grounding_uses_only_canonical_included_records() -> None:
    included_record = ExtractionRecord(
        paper_id="p1",
        study_design=StudyDesign.CROSS_SECTIONAL,
        intervention_description="QR registry in rural clinics.",
        outcomes=[],
        results_summary={"summary": "Coverage improved."},
    )
    excluded_record = ExtractionRecord(
        paper_id="p2",
        study_design=StudyDesign.NARRATIVE_REVIEW,
        intervention_description="Narrative overview.",
        outcomes=[],
        results_summary={"summary": "Not primary evidence."},
    )
    grounding = build_writing_grounding(
        prisma_counts=_prisma_counts(),
        extraction_records=[included_record, excluded_record],
        included_papers=[_paper()],
        narrative=None,
    )
    assert grounding.study_design_counts == {"cross sectional": 1}
    assert [summary.paper_id for summary in grounding.study_summaries] == ["p1"]


def test_snake_case_post_render_is_sanitized() -> None:
    sanitized = _sanitize_prose("The study_design_counts field supported the primary_outcome summary.")
    assert "study design counts" in sanitized
    assert "primary outcome" in sanitized
    assert "_" not in sanitized


def test_post_render_completeness_ignores_terminal_citations() -> None:
    content = "\n".join(
        [
            "### Study Selection",
            "",
            "The review screened 10 records and included 5 studies. [Page2021]",
            "",
            "### Study Characteristics",
            "",
            "Study designs included mixed methods and qualitative evaluations. [Adeoye2026]",
            "",
            "### Synthesis of Findings",
            "",
            "The evidence direction was mixed, with improvements in reporting timeliness but uneven integration. [Shichijo2026]",
        ]
    )
    issues = _post_render_completeness_issues("results", content, included_study_count=5)
    assert "post_trailing_fragment_punctuation" not in issues
    assert "post_missing_subheading:synthesis of findings" not in issues


def test_normalize_subsection_heading_layout_splits_punctuation_joined_heading() -> None:
    raw = (
        "Full-text PDFs were retrieved for 13 studies.### Study Characteristics\n\n"
        "Study details follow."
    )
    normalized = normalize_subsection_heading_layout(raw)
    assert "Full-text PDFs were retrieved for 13 studies.\n\n### Study Characteristics" in normalized


def test_normalize_subsection_heading_layout_merges_connector_split_heading() -> None:
    raw = "### Risk of\n\nBias and Critical Appraisal\n\nStructured assessment text."
    normalized = normalize_subsection_heading_layout(raw)
    assert "### Risk of Bias and Critical Appraisal" in normalized
    assert "\n\nStructured assessment text." in normalized


def test_valid_inline_citekeys_are_promoted_to_structured_citations() -> None:
    draft = StructuredSectionDraft(
        section_key="methods",
        blocks=[
            SectionBlock(
                block_type="paragraph",
                text="The review followed PRISMA guidance [Page2021] and used GRADE [Guyatt2011].",
            )
        ],
    )
    normalized, issues = _validate_structured_section_draft("methods", draft, {"Page2021", "Guyatt2011"})
    assert issues == []
    assert normalized.blocks[0].citations == ["Page2021", "Guyatt2011"]
    assert "[Page2021]" not in normalized.blocks[0].text


def test_shared_heading_inventory_matches_rendered_markdown() -> None:
    draft = StructuredSectionDraft(
        section_key="discussion",
        blocks=[
            SectionBlock(block_type="subheading", level=3, text="Comparison with Prior Work [Page2021]"),
            SectionBlock(
                block_type="paragraph",
                text="This paragraph compares the review findings against prior literature in a grounded way.",
            ),
        ],
    )
    rendered = render_section_markdown(draft)
    assert collect_section_heading_inventory(draft) == extract_markdown_heading_inventory(rendered, min_level=3, max_level=4)


def test_grounding_patches_replace_conflicting_selection_and_fulltext_sentences() -> None:
    grounding = SimpleNamespace(
        databases_searched=["IEEE Xplore", "PubMed"],
        search_date="2026-04-11",
        search_eligibility_window="2000-2026",
        screening_method_description="Two independent reviewers screened records with adjudication for disagreements.",
        rob_summary="ROBINS-I; CASP; MMAT",
        fulltext_sought=45,
        fulltext_not_retrieved=0,
        fulltext_assessed=45,
        total_screened=1358,
        total_included=19,
        fulltext_retrieved_count=13,
        fulltext_total_count=19,
        excluded_non_primary_count=7,
        excluded_fulltext_reasons={"wrong_intervention": 17, "insufficient_data": 1},
    )
    review = SimpleNamespace(
        pico=SimpleNamespace(
            population="rural communities",
            intervention="QR-code-enabled digital vaccine record systems",
            comparison="paper-based records",
            outcome="vaccination coverage and tracking efficiency",
        )
    )
    methods_input = (
        "### Selection Process\n\nLegacy wording with inconsistent counts.### Data Collection Process\n\n"
        "All 19 included studies had their full text retrieved."
    )
    methods_output = _patch_methods_grounding(methods_input, grounding, review)
    assert "Following title and abstract screening, 45 reports were sought for full-text retrieval" in methods_output
    assert "retrievable full-text PDFs were available for only 13 of the 19 included studies" in methods_output
    assert "All 19 included studies had their full text retrieved" not in methods_output
    assert "### Data Collection" in methods_output
    assert "### Data Collection Process" not in methods_output

    results_input = "### Study Selection\n\nThe review screened 1300 records and assessed 39 reports."
    results_output = _patch_results_grounding(results_input, grounding)
    assert "The review screened 1358 records" in results_output
    assert "sought 45 full-text reports" in results_output
    assert "All 45 reports were retrieved for eligibility assessment" in results_output
    assert "each excluded report was assigned one primary reason category" in results_output


@pytest.mark.asyncio
async def test_mmat_quality_gate_marks_low_quality_membership(tmp_path) -> None:
    db_path = str(tmp_path / "quality_gate.db")
    async with get_db(db_path) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-low-quality", "topic", "hash")
        await repo.save_paper(_paper())
        resolver = IncludedSetResolver(repo, "wf-low-quality")
        await resolver.persist_extraction_outcome(
            "p1",
            primary_study_status="primary",
            extraction_failed=False,
            low_quality=True,
            exclusion_reason_code="low_quality_mmat",
        )
        cursor = await db.execute(
            """
            SELECT synthesis_eligibility, exclusion_reason_code
            FROM study_cohort_membership
            WHERE workflow_id = ? AND paper_id = ?
            """,
            ("wf-low-quality", "p1"),
        )
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] == "excluded_low_quality"
    assert row[1] == "low_quality_mmat"


def test_detect_scope_mismatch_requires_explicit_contradiction() -> None:
    record = ExtractionRecord(
        paper_id="p1",
        study_design=StudyDesign.CROSS_SECTIONAL,
        intervention_description="This study does not describe a QR-code-enabled digital vaccine record system.",
        outcomes=[],
        results_summary={"summary": "The intervention was outside the QR-enabled registry scope."},
        source_spans={"title": "Childhood immunization rates in rural clinics"},
    )
    review = SimpleNamespace(
        pico=SimpleNamespace(intervention="QR-code-enabled digital vaccine record system"),
        preferred_terminology=lambda limit=12: ["digital vaccine record", "QR code"],
        domain_signal_terms=lambda limit=18: ["digital vaccine record", "QR code vaccination"],
    )
    mismatch, evidence = detect_scope_mismatch(record, review)
    assert mismatch is True
    assert evidence is not None
    assert "digital vaccine record" in evidence or "code" in evidence


@pytest.mark.asyncio
async def test_scope_mismatch_marks_cohort_membership(tmp_path) -> None:
    db_path = str(tmp_path / "scope_gate.db")
    async with get_db(db_path) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-scope", "topic", "hash")
        await repo.save_paper(_paper())
        resolver = IncludedSetResolver(repo, "wf-scope")
        await resolver.persist_extraction_outcome(
            "p1",
            primary_study_status="primary",
            extraction_failed=False,
            scope_mismatch=True,
            exclusion_reason_code="wrong_intervention",
        )
        cursor = await db.execute(
            """
            SELECT synthesis_eligibility, exclusion_reason_code
            FROM study_cohort_membership
            WHERE workflow_id = ? AND paper_id = ?
            """,
            ("wf-scope", "p1"),
        )
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] == "excluded_scope_mismatch"
    assert row[1] == "wrong_intervention"
