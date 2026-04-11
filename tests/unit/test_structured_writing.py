from __future__ import annotations

from src.models.writing import SectionBlock, StructuredSectionDraft
from src.writing.orchestration import (
    _build_deterministic_section_fallback,
    _extract_valid_citekeys,
    _patch_abstract_grounding,
    _post_render_completeness_issues,
    _section_completeness_issues,
    _validate_structured_section_draft,
)
from src.writing.renderers import render_section_latex, render_section_markdown
from src.writing.section_writer import SectionWriter


def test_render_section_markdown_and_latex_from_ir() -> None:
    draft = StructuredSectionDraft(
        section_key="methods",
        blocks=[
            SectionBlock(block_type="subheading", text="Eligibility Criteria", level=3),
            SectionBlock(block_type="paragraph", text="We defined eligibility using PICO [Page2021]."),
            SectionBlock(block_type="bullet_list", text="Population\nIntervention\nOutcomes"),
        ],
    )
    md = render_section_markdown(draft)
    tex = render_section_latex(draft)

    assert "### Eligibility Criteria" in md
    assert "- Population" in md
    assert "\\subsection{Eligibility Criteria}" in tex
    assert "\\begin{itemize}" in tex


def test_validate_structured_section_filters_citations_and_sets_required_subsections() -> None:
    valid = _extract_valid_citekeys("[Page2021] PRISMA\n[Smith2024] Included study")
    draft = StructuredSectionDraft(
        section_key="methods",
        blocks=[
            SectionBlock(
                block_type="paragraph",
                text="We followed prisma_guideline and screening_process metrics [BadKey].",
                citations=["BadKey", "Page2021"],
            )
        ],
    )

    out, issues = _validate_structured_section_draft("methods", draft, valid)
    paras = [b.text for b in out.blocks if b.block_type == "paragraph"]

    assert issues == ["invalid_structured_citations:1"]
    assert "Eligibility Criteria" in out.required_subsections
    assert "Information Sources" in out.required_subsections
    assert "prisma guideline" in paras[0]
    assert out.cited_keys == ["Page2021"]


def test_validate_structured_abstract_strips_inline_and_structured_citations() -> None:
    draft = StructuredSectionDraft(
        section_key="abstract",
        blocks=[
            SectionBlock(
                block_type="paragraph",
                text="**Methods:** Searches were completed [Page2021].",
                citations=["Page2021"],
            ),
            SectionBlock(
                block_type="paragraph",
                text="**Results:** Effects were mixed [Smith2024].",
            ),
        ],
    )
    normalized, issues = _validate_structured_section_draft("abstract", draft, {"Page2021", "Smith2024"})
    assert issues == []
    assert normalized.blocks[0].citations == []
    assert normalized.blocks[1].citations == []
    assert "[Page2021]" not in normalized.blocks[0].text
    assert "[Smith2024]" not in normalized.blocks[1].text
    assert normalized.cited_keys == []


def test_validate_structured_section_merges_inline_citekeys_with_structured_citations() -> None:
    valid = {"Page2021", "Smith2024"}
    draft = StructuredSectionDraft(
        section_key="discussion",
        blocks=[
            SectionBlock(
                block_type="paragraph",
                text="Interpretation remained cautious [Smith2024].",
                citations=["Page2021"],
            )
        ],
    )
    normalized, issues = _validate_structured_section_draft("discussion", draft, valid)
    assert issues == []
    assert normalized.blocks[0].citations == ["Page2021", "Smith2024"]
    assert "[Smith2024]" not in normalized.blocks[0].text


def test_section_writer_fallback_parses_markdown_like_text_into_blocks() -> None:
    raw = "### Study Selection\n\nThe search identified records.\n\n### Synthesis\nNarrative synthesis was used."
    out = SectionWriter._fallback_structured_from_text("results", raw)
    kinds = [b.block_type for b in out.blocks]
    texts = [b.text for b in out.blocks]
    assert kinds.count("subheading") == 2
    assert "Study Selection" in texts
    assert "The search identified records." in texts


def test_section_completeness_detects_trailing_fragment() -> None:
    draft = StructuredSectionDraft(
        section_key="discussion",
        blocks=[
            SectionBlock(block_type="subheading", text="Principal Findings", level=3),
            SectionBlock(
                block_type="paragraph",
                text="This section summarizes educational efficacy, user experience, and",
            ),
        ],
    )
    issues = _section_completeness_issues("discussion", draft)
    assert any("trailing_fragment" in issue for issue in issues)


def test_section_completeness_allows_abstract_field_lines_without_terminal_punctuation() -> None:
    draft = StructuredSectionDraft(
        section_key="abstract",
        blocks=[
            SectionBlock(
                block_type="paragraph",
                text="**Keywords:** qr code vaccine record, digital vaccine passport, dvp",
            )
        ],
    )
    issues = _section_completeness_issues("abstract", draft)
    assert "trailing_fragment_punctuation" not in issues


def test_deterministic_methods_fallback_includes_prisma_sought_and_not_retrieved() -> None:
    class _Grounding:
        fulltext_sought = 66
        fulltext_not_retrieved = 33
        fulltext_assessed = 33
        total_included = 10
        total_screened = 1996

    draft = _build_deterministic_section_fallback("methods", _Grounding(), {"Page2021"})
    text = render_section_markdown(draft)
    assert "66 reports were sought for full-text retrieval" in text
    assert "33 reports were not retrieved" in text


def test_deterministic_discussion_fallback_uses_topic_scope() -> None:
    class _Grounding:
        research_question = "the impact of simulation training on clinical skill acquisition"
        review_topic = ""

    draft = _build_deterministic_section_fallback("discussion", _Grounding(), {"Page2021"})
    text = render_section_markdown(draft)
    assert "simulation training on clinical skill acquisition" in text
    assert "generative conversational AI tutoring" not in text


def test_deterministic_abstract_fallback_contains_structured_fields() -> None:
    class _Grounding:
        research_question = "the impact of simulation training on clinical skill acquisition"
        review_topic = ""
        databases_searched = ["OpenAlex", "PubMed"]
        total_screened = 120
        fulltext_assessed = 14
        fulltext_not_retrieved = 2
        total_included = 6
        synthesis_direction = "mixed"
        search_eligibility_window = "2015-2026"

    draft = _build_deterministic_section_fallback("abstract", _Grounding(), {"Page2021"})
    text = render_section_markdown(draft)
    assert "**Background:**" in text
    assert "**Objectives:**" in text
    assert "**Methods:**" in text
    assert "**Results:**" in text
    assert "**Conclusions:**" in text
    assert "**Keywords:**" in text
    assert len(text.split()) >= 150
    assert "digital vaccine records" not in text.lower()


def test_patch_abstract_grounding_appends_keywords_terminal_punctuation() -> None:
    class _Grounding:
        databases_searched = ["OpenAlex", "PubMed"]
        search_date = "2026-04-08"
        search_eligibility_window = "2015-2026"
        total_screened = 120
        total_included = 6
        fulltext_assessed = 14
        synthesis_direction = "mixed"

    class _Review:
        research_question = "What is the effect?"
        keywords = ["digital vaccine records", "qr codes"]

    content = (
        "**Background:** Background.\n"
        "**Objectives:** Objective.\n"
        "**Methods:** Placeholder.\n"
        "**Results:** Placeholder.\n"
        "**Conclusions:** Conclusion.\n"
        "**Keywords:** digital vaccine records, qr codes"
    )
    patched = _patch_abstract_grounding(content, _Grounding(), _Review())
    assert "**Keywords:** digital vaccine records, qr codes." in patched


def test_section_completeness_detects_missing_discussion_required_subheadings() -> None:
    draft = StructuredSectionDraft(
        section_key="discussion",
        blocks=[
            SectionBlock(block_type="subheading", text="Principal Findings", level=3),
            SectionBlock(
                block_type="paragraph",
                text="This section provides interpretation of findings and contextual caveats with adequate detail.",
            ),
        ],
    )
    issues = _section_completeness_issues("discussion", draft)
    assert any(issue == "missing_required_subheadings" for issue in issues)


def test_post_render_completeness_flags_truncated_discussion_tail() -> None:
    content = (
        "### Principal Findings\n\n"
        "The evidence base indicates benefits in selected contexts and suggests implementation caveats.\n\n"
        "### Comparison with Prior Work\n\n"
        "Findings align with prior systematic reviews and"
    )
    issues = _post_render_completeness_issues("discussion", content)
    assert any("post_trailing_fragment" in issue for issue in issues)

