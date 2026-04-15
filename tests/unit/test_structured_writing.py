from __future__ import annotations

from src.models.writing import SectionBlock, StructuredSectionDraft
from src.writing.orchestration import (
    _apply_structured_grounding_patches,
    _abstract_body_word_count,
    _build_deterministic_section_fallback,
    _extract_valid_citekeys,
    _needs_legacy_heading_fix,
    _patch_abstract_grounding,
    _patch_methods_grounding,
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
    subheadings = [block.text for block in patched.blocks if block.block_type == "subheading"]
    assert "Selection Process" in subheadings
    assert "Data Collection" in subheadings
    assert "### Selection Process" in rendered
    assert "### Data Collection" in rendered


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

    content = (
        "### Study Selection\n\nLegacy counts.\n\n"
        "### Study Characteristics\n\nStudy details follow."
    )
    patched = _patch_results_grounding(content, _Grounding())
    assert "primary reason category.\n\n### Study Characteristics" in patched
    assert "primary reason category.### Study Characteristics" not in patched


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

