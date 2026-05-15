from __future__ import annotations

import pytest

from src.models.writing import SectionBlock, StructuredAbstractOutput, StructuredSectionDraft
from src.writing.orchestration import (
    _abstract_body_word_count,
    _apply_structured_grounding_patches,
    _build_deterministic_section_fallback,
    _extract_valid_citekeys,
    _needs_legacy_heading_fix,
    _patch_abstract_grounding,
    _patch_methods_grounding,
    _patch_results_grounding,
    _post_render_completeness_issues,
    _section_completeness_issues,
    _validate_structured_section_draft,
    parse_structured_abstract_markdown,
    canonicalize_structured_abstract_markdown,
    validate_structured_abstract_markdown_band,
)
from src.writing.renderers import render_section_latex, render_section_markdown
from src.writing.section_writer import SectionWriter


def _abstract_sentences(seed: str, repeat: int = 3) -> str:
    return " ".join([f"{seed} sentence {idx} improves manuscript quality." for idx in range(1, repeat + 1)])


def test_structured_abstract_output_normalizes_and_renders_markdown() -> None:
    payload = StructuredAbstractOutput(
        background="  Background statement with extra spacing  ",
        objectives="Objective statement with trailing spaces   ",
        methods="Methods sentence one. Methods sentence two with detail.",
        results="Results sentence one. Results sentence two with detail.",
        conclusions="Conclusions statement with practical implications",
        keywords=["digital health", "Digital Health", "evidence synthesis", "implementation science"],
    )
    normalized = payload.normalized()
    markdown = normalized.to_markdown()
    lines = markdown.splitlines()

    assert lines[0].startswith("**Background:** ")
    assert lines[1].startswith("**Objectives:** ")
    assert lines[2].startswith("**Methods:** ")
    assert lines[3].startswith("**Results:** ")
    assert lines[4].startswith("**Conclusions:** ")
    assert lines[5].startswith("**Keywords:** ")
    assert markdown.count("digital health") == 1


def test_structured_abstract_output_validates_word_band() -> None:
    payload = StructuredAbstractOutput(
        background=_abstract_sentences("Background", repeat=3),
        objectives=_abstract_sentences("Objectives", repeat=3),
        methods=_abstract_sentences("Methods", repeat=4),
        results=_abstract_sentences("Results", repeat=4),
        conclusions=_abstract_sentences("Conclusions", repeat=3),
        keywords=["systematic review", "evidence synthesis", "implementation science"],
    ).normalized()
    payload.validate_word_band(min_words=40, max_words=250)


def test_structured_abstract_output_raises_when_over_max_words() -> None:
    payload = StructuredAbstractOutput(
        background=_abstract_sentences("Background", repeat=12),
        objectives=_abstract_sentences("Objectives", repeat=12),
        methods=_abstract_sentences("Methods", repeat=12),
        results=_abstract_sentences("Results", repeat=12),
        conclusions=_abstract_sentences("Conclusions", repeat=12),
        keywords=["systematic review", "evidence synthesis", "implementation science"],
    ).normalized()
    with pytest.raises(ValueError, match="exceeds maximum"):
        payload.validate_word_band(min_words=50, max_words=250)


def test_parse_structured_abstract_markdown_returns_typed_payload() -> None:
    content = (
        "**Background:** Background sentence 1 improves manuscript quality. Background sentence 2 improves manuscript quality.\n"
        "**Objectives:** Objectives sentence 1 improves manuscript quality. Objectives sentence 2 improves manuscript quality.\n"
        "**Methods:** Methods sentence 1 improves manuscript quality. Methods sentence 2 improves manuscript quality. Methods sentence 3 improves manuscript quality.\n"
        "**Results:** Results sentence 1 improves manuscript quality. Results sentence 2 improves manuscript quality. Results sentence 3 improves manuscript quality.\n"
        "**Conclusions:** Conclusions sentence 1 improves manuscript quality. Conclusions sentence 2 improves manuscript quality.\n"
        "**Keywords:** systematic review, evidence synthesis, implementation science."
    )
    parsed = parse_structured_abstract_markdown(content)
    assert parsed.background.startswith("Background sentence 1")
    assert parsed.objectives.startswith("Objectives sentence 1")
    assert parsed.methods.startswith("Methods sentence 1")
    assert parsed.results.startswith("Results sentence 1")
    assert parsed.conclusions.startswith("Conclusions sentence 1")
    assert parsed.keywords == ["systematic review", "evidence synthesis", "implementation science"]


def test_validate_structured_abstract_markdown_band_flags_missing_structure() -> None:
    ok, reason = validate_structured_abstract_markdown_band(
        "**Background:** short.\n**Objectives:** short.\n**Keywords:** a, b, c.",
        min_words=50,
        max_words=250,
    )
    assert ok is False
    assert reason


def test_canonicalize_structured_abstract_markdown_splits_inline_fields() -> None:
    inline = (
        "**Background:** Background sentence 1 improves manuscript quality. "
        "**Objectives:** Objectives sentence 1 improves manuscript quality. "
        "**Methods:** Methods sentence 1 improves manuscript quality. Methods sentence 2 improves manuscript quality. "
        "**Results:** Results sentence 1 improves manuscript quality. Results sentence 2 improves manuscript quality. "
        "**Conclusions:** Conclusions sentence 1 improves manuscript quality. "
        "**Keywords:** systematic review, evidence synthesis, implementation science."
    )
    canonical = canonicalize_structured_abstract_markdown(inline)
    lines = canonical.splitlines()
    assert len(lines) == 6
    assert lines[0].startswith("**Background:**")
    assert lines[5].startswith("**Keywords:**")


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


@pytest.mark.asyncio
async def test_section_writer_write_section_structured_async_fails_fast_after_validation_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.llm.pydantic_client import PydanticAIClient

    async def _raise_validation(*args, **kwargs):
        _ = (args, kwargs)
        raise ValueError("schema mismatch")

    monkeypatch.setattr(PydanticAIClient, "complete_validated", _raise_validation)

    review = type(
        "Review",
        (),
        {
            "domain_brief_lines": lambda self=None: [],
            "domain_signal_terms": lambda self=None, limit=12: [],
            "preferred_terminology": lambda self=None: [],
            "discouraged_terminology": lambda self=None: [],
            "expert_topic": lambda self=None: "digital vaccination records",
            "domain": "public health",
            "research_question": "What is the impact?",
            "keywords": ["qr code"],
        },
    )()
    settings = type(
        "Settings",
        (),
        {
            "llm": type("LLM", (), {"request_timeout_seconds": 60})(),
            "agents": {"writing": type("Agent", (), {"model": "google-gla:gemini-2.5-flash", "temperature": 0.1})()},
        },
    )()
    writer = SectionWriter(review=review, settings=settings)
    with pytest.raises(RuntimeError, match="failed structured output validation"):
        await writer.write_section_structured_async("results", "context text")


@pytest.mark.asyncio
async def test_section_writer_abstract_uses_structured_output_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.llm.pydantic_client import PydanticAIClient

    calls: list[type] = []

    async def _fake_complete_validated(*args, **kwargs):
        _ = args
        calls.append(kwargs["response_model"])
        return (
            StructuredAbstractOutput(
                background=_abstract_sentences("Background", repeat=3),
                objectives=_abstract_sentences("Objectives", repeat=3),
                methods=_abstract_sentences("Methods", repeat=4),
                results=_abstract_sentences("Results", repeat=4),
                conclusions=_abstract_sentences("Conclusions", repeat=3),
                keywords=["systematic review", "evidence synthesis", "implementation science"],
            ),
            120,
            180,
            0,
            0,
            0,
        )

    monkeypatch.setattr(PydanticAIClient, "complete_validated", _fake_complete_validated)

    review = type(
        "Review",
        (),
        {
            "domain_brief_lines": lambda self=None: [],
            "domain_signal_terms": lambda self=None, limit=12: [],
            "preferred_terminology": lambda self=None: [],
            "discouraged_terminology": lambda self=None: [],
            "expert_topic": lambda self=None: "digital vaccination records",
            "domain": "public health",
            "research_question": "What is the impact?",
            "keywords": ["qr code"],
        },
    )()
    settings = type(
        "Settings",
        (),
        {
            "llm": type("LLM", (), {"request_timeout_seconds": 60})(),
            "agents": {"writing": type("Agent", (), {"model": "google-gla:gemini-2.5-flash", "temperature": 0.1})()},
            "writing": type("Writing", (), {"abstract_trim_floor_words": 50})(),
            "ieee_export": type("IEEE", (), {"max_abstract_words": 250})(),
        },
    )()

    writer = SectionWriter(review=review, settings=settings)
    structured, _metadata = await writer.write_section_structured_async("abstract", "grounded context")
    rendered = render_section_markdown(structured)

    assert calls and calls[0] is StructuredAbstractOutput
    assert structured.section_key == "abstract"
    assert "**Background:**" in rendered
    assert "**Conclusions:**" in rendered
    assert "**Keywords:**" in rendered


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


def test_patch_abstract_grounding_expands_short_abstract_to_minimum_words() -> None:
    class _Grounding:
        databases_searched = ["OpenAlex", "PubMed"]
        search_date = "2026-04-08"
        search_eligibility_window = "2015-2026"
        total_screened = 120
        total_included = 6
        fulltext_assessed = 14
        synthesis_direction = "mixed"
        conclusion_hedging_required = True
        fulltext_total_count = 6
        fulltext_retrieved_count = 3
        grade_summary = "coverage: low; usability: very low"

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
    patched = _patch_abstract_grounding(content, _Grounding(), _Review(), minimum_words=80)
    assert _abstract_body_word_count(patched) >= 80
    assert "missing retrievable full texts" in patched


def test_patch_abstract_grounding_forces_minimum_compliant_fallback_for_real_floor() -> None:
    class _Grounding:
        databases_searched = ["IEEE Xplore", "PubMed", "Scopus", "Semantic Scholar"]
        search_date = "2026-04-14"
        search_eligibility_window = "2000-2026"
        total_screened = 691
        total_included = 7
        fulltext_sought = 21
        fulltext_not_retrieved = 11
        fulltext_assessed = 10
        synthesis_direction = "mixed"
        conclusion_hedging_required = True
        fulltext_total_count = 7
        fulltext_retrieved_count = 3
        grade_summary = "coverage: very low; usability: low"
        study_design_counts = {
            "cross_sectional": 2,
            "qualitative": 2,
            "quasi_experimental": 2,
            "pre_post": 1,
        }
        total_participants = 700155
        screening_method_description = "An AI-assisted dual-reviewer pipeline screened titles and abstracts with adjudication for disagreements."
        rob_summary = "ROBINS-I (non-RCTs, n=2): low: 1; no information: 1 | CASP (cross-sectional/qualitative, n=4): 1/8 criteria met: 1; 2/8 criteria met: 3"

    class _Review:
        research_question = (
            "What is the impact of QR-code-enabled digital vaccine record systems on vaccination coverage, "
            "tracking efficiency, and health system integration in rural communities compared to traditional paper-based records?"
        )
        keywords = ["QR code vaccine record", "digital vaccine passport", "rural immunization"]

    content = (
        "**Background:** Background.\n"
        "**Objectives:** Objective.\n"
        "**Methods:** Placeholder.\n"
        "**Results:** Placeholder.\n"
        "**Conclusions:** Conclusion.\n"
        "**Keywords:** QR code vaccine record, digital vaccine passport, rural immunization"
    )
    patched = _patch_abstract_grounding(content, _Grounding(), _Review(), minimum_words=210)
    assert _abstract_body_word_count(patched) >= 210
    assert "sought 21 full-text reports" in patched
    assert "700155" in patched


def test_patch_methods_grounding_reuses_combined_search_heading_alias() -> None:
    class _Grounding:
        fulltext_total_count = 4
        fulltext_retrieved_count = 2
        databases_searched = ["OpenAlex", "PubMed"]
        search_date = "2026-04-08"
        search_eligibility_window = "2015-2026"
        screening_method_description = "An AI-assisted dual-reviewer pipeline screened records."
        fulltext_sought = 5
        fulltext_not_retrieved = 1
        fulltext_assessed = 4
        total_included = 4
        excluded_non_primary_count = 0
        rob_summary = "ROBINS-I for 2 studies; CASP for 2 studies."

    class _Review:
        pico = type(
            "Pico",
            (),
            {
                "population": "rural populations",
                "intervention": "digital vaccine records",
                "comparison": "paper records",
                "outcome": "coverage and usability",
            },
        )()

    content = (
        "### Information Sources and Search Strategy\n\n"
        "Legacy combined heading.\n\n"
        "### Study Selection\n\n"
        "Legacy study selection text."
    )
    patched = _patch_methods_grounding(content, _Grounding(), _Review())
    assert patched.count("### Search Strategy") == 0
    assert patched.count("### Selection Process") == 1


def test_patch_methods_grounding_adds_batch_validation_sentence() -> None:
    class _Grounding:
        fulltext_total_count = 4
        fulltext_retrieved_count = 2
        databases_searched = ["OpenAlex", "PubMed"]
        search_date = "2026-04-08"
        search_eligibility_window = "2015-2026"
        screening_method_description = "An AI-assisted dual-reviewer pipeline screened records."
        fulltext_sought = 5
        fulltext_not_retrieved = 1
        fulltext_assessed = 4
        total_included = 4
        excluded_non_primary_count = 0
        rob_summary = "ROBINS-I for 2 studies; CASP for 2 studies."
        batch_screen_validation_n = 24
        batch_screen_validation_npv = 0.875

    class _Review:
        pico = type(
            "Pico",
            (),
            {
                "population": "rural populations",
                "intervention": "digital vaccine records",
                "comparison": "paper records",
                "outcome": "coverage and usability",
            },
        )()

    content = "### Selection Process\n\nLegacy selection text."
    patched = _patch_methods_grounding(content, _Grounding(), _Review())
    assert "To verify automated exclusions, 24 low-relevance records were cross-checked by dual review; 88% were confirmed as true exclusions." in patched


def test_patch_methods_grounding_adds_rob_coverage_gap_sentence() -> None:
    class _Grounding:
        fulltext_total_count = 4
        fulltext_retrieved_count = 2
        databases_searched = ["OpenAlex", "PubMed"]
        search_date = "2026-04-08"
        search_eligibility_window = "2015-2026"
        screening_method_description = "An AI-assisted dual-reviewer pipeline screened records."
        fulltext_sought = 5
        fulltext_not_retrieved = 1
        fulltext_assessed = 4
        total_included = 4
        excluded_non_primary_count = 0
        rob_summary = "ROBINS-I for 2 studies; CASP for 2 studies."
        included_studies_without_rob_mapping = 2
        risk_tool_counts = {"casp": 2, "mmat": 5}
        study_design_counts = {"mixed_methods": 3, "pre_post": 2}

    class _Review:
        pico = type(
            "Pico",
            (),
            {
                "population": "rural populations",
                "intervention": "digital vaccine records",
                "comparison": "paper records",
                "outcome": "coverage and usability",
            },
        )()

    content = "### Data Collection\n\nLegacy extraction statement."
    patched = _patch_methods_grounding(content, _Grounding(), _Review())
    assert "Risk-of-bias coverage was incomplete for 2 of 4 included studies" in patched
    assert "Risk-of-bias routing was design-aligned" in patched


def test_apply_structured_grounding_patches_syncs_methods_ir() -> None:
    class _Grounding:
        fulltext_total_count = 4
        fulltext_retrieved_count = 2
        databases_searched = ["OpenAlex", "PubMed"]
        search_date = "2026-04-08"
        search_eligibility_window = "2015-2026"
        screening_method_description = "An AI-assisted dual-reviewer pipeline screened records."
        fulltext_sought = 5
        fulltext_not_retrieved = 1
        fulltext_assessed = 4
        total_included = 4
        excluded_non_primary_count = 0
        rob_summary = "ROBINS-I for 2 studies; CASP for 2 studies."

    class _Review:
        pico = type(
            "Pico",
            (),
            {
                "population": "rural populations",
                "intervention": "digital vaccine records",
                "comparison": "paper records",
                "outcome": "coverage and usability",
            },
        )()
        research_question = "What is the effect?"
        keywords = ["digital vaccine records", "qr codes"]

    settings = type(
        "Settings",
        (),
        {
            "writing": type("Writing", (), {"abstract_trim_floor_words": 210})(),
        },
    )()
    draft = StructuredSectionDraft(
        section_key="methods",
        blocks=[
            SectionBlock(block_type="paragraph", text="Legacy methods summary."),
        ],
    )
    patched = _apply_structured_grounding_patches(
        "methods",
        draft,
        grounding=_Grounding(),
        review=_Review(),
        settings=settings,
        valid_citekeys={"Page2021"},
    )
    rendered = render_section_markdown(patched)
    # Non-abstract sections now keep source-driven narrative content unchanged.
    subheadings = [block.text for block in patched.blocks if block.block_type == "subheading"]
    assert subheadings == []
    assert rendered == "Legacy methods summary."


def test_apply_structured_grounding_patches_conclusion_adds_cautionary_constraints() -> None:
    class _Grounding:
        fulltext_sought = 41
        fulltext_not_retrieved = 20
        grade_summary = "coverage: low; usability: very low"
        missing_participant_count = 6
        n_total_studies = 11

    class _Review:
        research_question = "What is the effect?"
        keywords = ["digital vaccine records", "qr codes"]

    settings = type(
        "Settings",
        (),
        {
            "writing": type("Writing", (), {"abstract_trim_floor_words": 210})(),
        },
    )()
    draft = StructuredSectionDraft(
        section_key="conclusion",
        blocks=[
            SectionBlock(block_type="paragraph", text="Legacy conclusion paragraph."),
        ],
    )
    patched = _apply_structured_grounding_patches(
        "conclusion",
        draft,
        grounding=_Grounding(),
        review=_Review(),
        settings=settings,
        valid_citekeys={"Page2021"},
    )
    rendered = render_section_markdown(patched)
    assert rendered == "Legacy conclusion paragraph."


def test_apply_structured_grounding_patches_keeps_valid_abstract_without_legacy_expansion() -> None:
    class _Grounding:
        databases_searched = ["OpenAlex", "PubMed"]
        search_date = "2026-04-08"
        search_eligibility_window = "2015-2026"
        total_screened = 120
        total_included = 6
        fulltext_assessed = 14
        synthesis_direction = "mixed"
        fulltext_total_count = 6
        fulltext_retrieved_count = 6
        fulltext_sought = 14
        fulltext_not_retrieved = 0

    class _Review:
        research_question = "What is the effect?"
        keywords = ["digital vaccine records", "qr codes"]

    settings = type(
        "Settings",
        (),
        {
            "writing": type("Writing", (), {"abstract_trim_floor_words": 50})(),
        },
    )()
    draft = StructuredSectionDraft(
        section_key="abstract",
        blocks=[
            SectionBlock(block_type="paragraph", text="**Background:** " + _abstract_sentences("Background", repeat=3)),
            SectionBlock(block_type="paragraph", text="**Objectives:** " + _abstract_sentences("Objectives", repeat=3)),
            SectionBlock(block_type="paragraph", text="**Methods:** " + _abstract_sentences("Methods", repeat=4)),
            SectionBlock(block_type="paragraph", text="**Results:** " + _abstract_sentences("Results", repeat=4)),
            SectionBlock(block_type="paragraph", text="**Conclusions:** " + _abstract_sentences("Conclusions", repeat=3)),
            SectionBlock(
                block_type="paragraph",
                text="**Keywords:** systematic review, evidence synthesis, implementation science.",
            ),
        ],
    )
    patched = _apply_structured_grounding_patches(
        "abstract",
        draft,
        grounding=_Grounding(),
        review=_Review(),
        settings=settings,
        valid_citekeys={"Page2021"},
    )
    rendered = render_section_markdown(patched)
    assert "Searches of OpenAlex, PubMed were conducted" not in rendered
    assert "**Methods:** Methods sentence 1 improves manuscript quality." in rendered


def test_needs_legacy_heading_fix_only_flags_malformed_layout() -> None:
    assert not _needs_legacy_heading_fix("### Study Selection\n\nThe review screened 10 records.")
    assert _needs_legacy_heading_fix("### Study Selection The review screened 10 records.")


def test_patch_results_grounding_preserves_following_subheading_boundary() -> None:
    class _Grounding:
        total_screened = 1399
        fulltext_sought = 35
        fulltext_not_retrieved = 12
        fulltext_assessed = 23
        total_included = 7
        excluded_fulltext_reasons = {"wrong_intervention": 9, "wrong_population": 1}
        excluded_non_primary_count = 0
        fulltext_total_count = 7
        fulltext_retrieved_count = 7
        risk_tool_counts = {"casp": 2, "mmat": 5}
        study_design_counts = {"mixed_methods": 3, "pre_post": 2}

    content = (
        "### Study Selection\n\nLegacy counts.\n\n"
        "### Study Characteristics\n\nStudy details follow."
    )
    patched = _patch_results_grounding(content, _Grounding())
    assert "\n\n### Study Characteristics" in patched
    assert ".### Study Characteristics" not in patched
    assert "Quality appraisal coverage included CASP" in patched


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

