from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.manuscript.cohort import IncludedSetResolver
from src.models import CandidatePaper, ExtractionRecord, SectionBlock, SourceCategory, StructuredSectionDraft, StudyDesign
from src.models.additional import PRISMACounts
from src.writing.context_builder import build_writing_grounding, sanitize_summary_text_for_writing
from src.writing.headings import extract_markdown_heading_inventory
from src.writing.orchestration import (
    _best_effort_accept,
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
    assert grounding.study_summaries[0].key_finding == "Not reported"


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
