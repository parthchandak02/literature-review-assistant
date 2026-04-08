from __future__ import annotations

from src.models import AgentConfig, ReviewConfig, ReviewType, SettingsConfig
from src.models.writing import SectionBlock, StructuredSectionDraft
from src.writing.citation_grounding import extract_and_strip_inline_citekeys
from src.writing.orchestration import _validate_structured_section_draft
from src.writing.renderers import render_section_markdown
from src.writing.section_writer import SectionWriter


def _review() -> ReviewConfig:
    return ReviewConfig(
        research_question="Does spaced repetition improve exam performance?",
        review_type=ReviewType.SYSTEMATIC,
        pico={
            "population": "university students",
            "intervention": "spaced repetition flashcards",
            "comparison": "usual study methods",
            "outcome": "exam performance",
        },
        keywords=["spaced repetition", "flashcards", "exam performance"],
        domain="education",
        scope="systematic review scope",
        inclusion_criteria=["primary empirical studies"],
        exclusion_criteria=["secondary reviews"],
        date_range_start=2020,
        date_range_end=2026,
        target_databases=["openalex"],
    )


def _settings() -> SettingsConfig:
    return SettingsConfig(
        agents={"writing": AgentConfig(model="google-gla:gemini-2.5-flash", temperature=0.1)}
    )


def test_section_writer_prompt_and_schema_use_structured_citations_only() -> None:
    writer = SectionWriter(
        review=_review(),
        settings=_settings(),
        citation_catalog="[Smith2023] Example study (2023)\n[Jones2024] Follow-up study (2024)",
    )

    prompt = writer._build_structured_section_prompt("results", "grounding")
    schema = writer._structured_schema()

    assert "text field must contain prose only" in prompt
    assert "Store every citation only in the citations arrays and cited_keys field." in prompt
    assert schema["properties"]["cited_keys"]["items"]["enum"] == ["Smith2023", "Jones2024"]
    assert schema["properties"]["blocks"]["items"]["properties"]["citations"]["items"]["enum"] == [
        "Smith2023",
        "Jones2024",
    ]


def test_extract_and_strip_inline_citekeys_keeps_prose_clean() -> None:
    cleaned, extracted = extract_and_strip_inline_citekeys(
        "This finding remained stable [Smith2023] across cohorts [Jones2024]."
    )

    assert extracted == ["Smith2023", "Jones2024"]
    assert cleaned == "This finding remained stable across cohorts."


def test_validate_structured_section_draft_rejects_inline_citations_in_normal_path() -> None:
    draft = StructuredSectionDraft(
        section_key="results",
        blocks=[
            SectionBlock(
                block_type="paragraph",
                text="Exam performance improved [Smith2023] and was sustained [Fake2024].",
                citations=["Jones2024", "Bad2025"],
            )
        ],
    )

    validated, issues = _validate_structured_section_draft(
        "results",
        draft,
        {"Smith2023", "Jones2024"},
    )

    assert validated.blocks[0].text == "Exam performance improved and was sustained."
    assert validated.blocks[0].citations == ["Jones2024"]
    assert validated.cited_keys == ["Jones2024"]
    assert "invalid_structured_citations:1" in issues
    assert "invalid_inline_citations:2" in issues


def test_render_section_markdown_appends_structured_citations() -> None:
    section = StructuredSectionDraft(
        section_key="results",
        blocks=[
            SectionBlock(
                block_type="paragraph",
                text="Learners improved exam scores.",
                citations=["Smith2023", "Jones2024"],
            )
        ],
    )

    rendered = render_section_markdown(section)

    assert rendered == "Learners improved exam scores. [Smith2023, Jones2024]"


def test_render_section_markdown_appends_citations_to_last_bullet() -> None:
    section = StructuredSectionDraft(
        section_key="discussion",
        blocks=[
            SectionBlock(
                block_type="bullet_list",
                text="Higher retention\nBetter short-term scores",
                citations=["Smith2023"],
            )
        ],
    )

    rendered = render_section_markdown(section)

    assert rendered == "- Higher retention\n- Better short-term scores [Smith2023]"
