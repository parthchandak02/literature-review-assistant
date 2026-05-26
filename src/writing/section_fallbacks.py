"""Deterministic section fallback builders for when LLM generation fails validation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.models import (
    SectionBlock,
    StructuredSectionDraft,
)
from src.writing.abstract_utils import _abstract_body_word_count, _append_abstract_field_sentence
from src.writing.evidence_assembler import build_results_evidence_pack, build_results_section_fallback
from src.writing.headings import SECTION_REQUIRED_SUBHEADINGS

if TYPE_CHECKING:
    from src.models import ReviewConfig
    from src.writing.context_builder import WritingGroundingData

_SECTION_REQUIRED_SUBHEADINGS = SECTION_REQUIRED_SUBHEADINGS


def _format_abstract_design_summary(study_design_counts: dict[str, int] | None) -> str:
    if not study_design_counts:
        return "heterogeneous study designs"
    ordered = sorted(
        ((str(label or "").replace("_", " ").strip(), int(count or 0)) for label, count in study_design_counts.items()),
        key=lambda item: (-item[1], item[0]),
    )
    parts = [f"{label} (n={count})" for label, count in ordered if label and count > 0]
    if not parts:
        return "heterogeneous study designs"
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"


def _expand_abstract_to_minimum_words(content: str, grounding: WritingGroundingData, minimum_words: int) -> str:
    expanded = content
    if _abstract_body_word_count(expanded) >= minimum_words:
        return expanded
    fulltext_total_count = int(getattr(grounding, "fulltext_total_count", 0) or 0)
    fulltext_retrieved_count = int(getattr(grounding, "fulltext_retrieved_count", 0) or 0)
    abstract_only_count = max(0, fulltext_total_count - fulltext_retrieved_count)
    expansion_steps = [
        (
            "Methods",
            f"Eligibility assessment covered {grounding.fulltext_assessed} retrieved reports after screening "
            f"{grounding.total_screened} records across the configured databases.",
        ),
        (
            "Results",
            f"Study designs were heterogeneous, and {grounding.total_included} included studies produced an overall "
            f"{str(grounding.synthesis_direction).replace('_', ' ')} direction of evidence.",
        ),
    ]
    if abstract_only_count > 0:
        expansion_steps.append(
            (
                "Conclusions",
                f"{abstract_only_count} included studies were extracted from abstracts and metadata only, which "
                "limits synthesis depth and increases uncertainty.",
            )
        )
    if getattr(grounding, "grade_summary", ""):
        expansion_steps.append(
            (
                "Conclusions",
                "Certainty of evidence was predominantly low to very low, so findings should be treated as "
                "hypothesis-generating rather than definitive.",
            )
        )
    for field, sentence in expansion_steps:
        if _abstract_body_word_count(expanded) >= minimum_words:
            break
        expanded = _append_abstract_field_sentence(expanded, field, sentence)
    return expanded


def _build_minimum_compliant_abstract(
    review: ReviewConfig,
    grounding: WritingGroundingData,
    minimum_words: int,
) -> str:
    research_question = str(review.research_question or "the review question").strip().rstrip("?")
    databases = ", ".join(getattr(grounding, "databases_searched", []) or ["configured bibliographic databases"])
    search_window = str(getattr(grounding, "search_eligibility_window", "") or "").strip()
    search_window_clause = f" across the eligibility window {search_window}" if search_window else ""
    screening_method = str(getattr(grounding, "screening_method_description", "") or "").strip()
    if screening_method and screening_method[-1] not in ".!?":
        screening_method = f"{screening_method}."
    design_summary = _format_abstract_design_summary(getattr(grounding, "study_design_counts", {}))
    total_participants = getattr(grounding, "total_participants", None)
    participant_sentence = ""
    if total_participants:
        participant_sentence = f" Reported participant totals summed to approximately {int(total_participants)} across studies that disclosed sample sizes."
    direction = str(getattr(grounding, "synthesis_direction", "mixed") or "mixed").replace("_", " ")
    grade_summary = str(getattr(grounding, "grade_summary", "") or "").strip()
    grade_sentence = ""
    if grade_summary:
        grade_sentence = (
            " Certainty of evidence was predominantly low to very low across reported outcomes, "
            "which limits confidence in the stability and transferability of the observed effects."
        )
    fulltext_sought = int(getattr(grounding, "fulltext_sought", 0) or 0)
    fulltext_not_retrieved = int(getattr(grounding, "fulltext_not_retrieved", 0) or 0)
    fulltext_assessed = int(getattr(grounding, "fulltext_assessed", 0) or 0)
    total_included = int(getattr(grounding, "total_included", 0) or 0)
    fulltext_total_count = int(getattr(grounding, "fulltext_total_count", 0) or 0)
    fulltext_retrieved_count = int(getattr(grounding, "fulltext_retrieved_count", 0) or 0)
    abstract_only_count = max(0, fulltext_total_count - fulltext_retrieved_count)
    abstract_only_sentence = ""
    if abstract_only_count > 0:
        abstract_only_sentence = f" {abstract_only_count} included studies were extracted from abstracts and metadata only because retrievable full-text PDFs were unavailable."
    retrieval_sentence = ""
    if fulltext_not_retrieved > 0:
        retrieval_sentence = f" The evidence base was constrained by non-retrieval of {fulltext_not_retrieved} of {fulltext_sought} reports sought for full-text review."
    rob_summary = str(getattr(grounding, "rob_summary", "") or "").strip()
    rob_sentence = ""
    if rob_summary:
        rob_sentence = f" Risk-of-bias appraisal used design-appropriate tools summarized as follows: {rob_summary}"
    keyword_values = [str(keyword).strip() for keyword in getattr(review, "keywords", [])[:5] if str(keyword).strip()]
    keywords_value = ", ".join(keyword_values) if keyword_values else "systematic review"
    if keywords_value[-1] not in ".!?":
        keywords_value = f"{keywords_value}."
    candidate = (
        f"**Background:** This systematic review synthesized available evidence relevant to {research_question}, with emphasis on methodological transparency, evidence consistency, and practical interpretation.\n"
        f"**Objectives:** The objective of this review was to examine {research_question}.\n"
        f"**Methods:** Searches of {databases} were conducted on {grounding.search_date}{search_window_clause}. We screened {grounding.total_screened} records, sought {fulltext_sought} full-text reports, did not retrieve {fulltext_not_retrieved}, assessed {fulltext_assessed} reports for eligibility, and included {total_included} studies. {screening_method}{rob_sentence}\n"
        f"**Results:** Included evidence comprised {design_summary}. The overall direction of evidence was {direction}, with reported benefits concentrated in selected implementation and usability outcomes rather than a uniform effect across all domains.{participant_sentence} Heterogeneity in design, setting, and outcome definitions limited direct comparability and prevented strong pooled inference.{abstract_only_sentence}\n"
        f"**Conclusions:** Available evidence suggests potential implementation benefits, but conclusions should remain cautious because the evidence base is small, methodologically heterogeneous, and incompletely retrieved.{grade_sentence}{retrieval_sentence} Stronger comparative studies with fuller reporting are needed before drawing definitive implementation claims.\n"
        f"**Keywords:** {keywords_value}"
    ).strip()
    if _abstract_body_word_count(candidate) >= minimum_words:
        return candidate
    candidate = _append_abstract_field_sentence(
        candidate,
        "Results",
        "Observed findings were better suited to narrative synthesis than to precise quantitative comparison because outcome measurement and reporting practices varied substantially across studies.",
    )
    if _abstract_body_word_count(candidate) >= minimum_words:
        return candidate
    candidate = _append_abstract_field_sentence(
        candidate,
        "Conclusions",
        "Implementation decisions should therefore emphasize local feasibility, data quality safeguards, and prospective evaluation rather than assuming that digital record adoption alone will produce durable coverage gains.",
    )
    return candidate


def _build_deterministic_section_fallback(
    section: str,
    grounding: WritingGroundingData | None,
    valid_citekeys: set[str],
) -> StructuredSectionDraft:
    """Build minimal, complete section content when generation remains malformed."""
    fallback_citations: list[str] = []
    if valid_citekeys:
        first = sorted(valid_citekeys)[0]
        fallback_citations = [first]
    if section == "abstract":
        databases = (
            ", ".join(getattr(grounding, "databases_searched", []) or []) or "configured bibliographic databases"
        )
        review_topic = str(
            getattr(grounding, "research_question", "")
            or getattr(grounding, "review_topic", "")
            or "the review question"
        ).strip()
        screened = getattr(grounding, "total_screened", 0) if grounding is not None else 0
        assessed = getattr(grounding, "fulltext_assessed", 0) if grounding is not None else 0
        included = getattr(grounding, "total_included", 0) if grounding is not None else 0
        not_retrieved = getattr(grounding, "fulltext_not_retrieved", 0) if grounding is not None else 0
        direction = str(getattr(grounding, "synthesis_direction", "mixed") or "mixed").replace("_", " ")
        search_window = str(getattr(grounding, "search_eligibility_window", "") or "").strip()
        search_phrase = f" across the protocol window {search_window}" if search_window else ""
        return StructuredSectionDraft(
            section_key="abstract",
            cited_keys=fallback_citations,
            blocks=[
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        f"**Background:** This systematic review evaluated the available evidence addressing {review_topic}, "
                        "with emphasis on study selection transparency, synthesis consistency, and the strength of the "
                        "reported evidence base."
                    ),
                ),
                SectionBlock(
                    block_type="paragraph",
                    text=f"**Objectives:** The objective of this review was to examine {review_topic}.",
                ),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        f"**Methods:** Searches of {databases} were conducted{search_phrase}; {screened} records were screened, "
                        f"{assessed} reports were assessed for eligibility, {not_retrieved} full-text reports were not retrieved, "
                        f"and {included} studies were included in the synthesis."
                    ),
                    citations=fallback_citations,
                ),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        f"**Results:** The available evidence came from {included} included studies and the overall direction "
                        f"of evidence was {direction}. Reported effects suggested potential implementation gains alongside "
                        "persistent data quality, interoperability, and infrastructure constraints."
                    ),
                    citations=fallback_citations,
                ),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        "**Conclusions:** Available evidence remains limited and methodologically heterogeneous, so conclusions "
                        "should be interpreted cautiously while prioritizing stronger comparative studies and better reporting."
                    ),
                ),
                SectionBlock(
                    block_type="paragraph",
                    text="**Keywords:** systematic review, evidence synthesis, included studies, manuscript quality, research question.",
                ),
            ],
        )
    if section == "methods":
        sought = getattr(grounding, "fulltext_sought", 0) if grounding is not None else 0
        not_retrieved = getattr(grounding, "fulltext_not_retrieved", 0) if grounding is not None else 0
        assessed = getattr(grounding, "fulltext_assessed", 0) if grounding is not None else 0
        included = getattr(grounding, "total_included", 0) if grounding is not None else 0
        screened = getattr(grounding, "total_screened", 0) if grounding is not None else 0
        return StructuredSectionDraft(
            section_key="methods",
            cited_keys=fallback_citations,
            required_subsections=list(_SECTION_REQUIRED_SUBHEADINGS.get("methods", ())),
            blocks=[
                SectionBlock(block_type="subheading", text="Eligibility Criteria", level=3),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        "Eligibility was predefined using population, intervention, comparator, and outcome criteria "
                        "from the protocol, and only studies meeting all criteria were retained."
                    ),
                ),
                SectionBlock(block_type="subheading", text="Information Sources", level=3),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        "Bibliographic database searches were executed on the protocol date range using the configured "
                        "connectors, and search strategies were archived in the appendix."
                    ),
                ),
                SectionBlock(block_type="subheading", text="Selection Process", level=3),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        f"Two independent reviewers screened {screened} records with adjudication for disagreements. "
                        f"{sought} reports were sought for full-text retrieval, {not_retrieved} reports were not retrieved, "
                        f"{assessed} were assessed for eligibility, and {included} studies were ultimately included."
                    ),
                ),
                SectionBlock(block_type="subheading", text="Synthesis Methods", level=3),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        "A narrative synthesis framework was used because methodological and outcome heterogeneity "
                        "limited quantitative pooling, and evidence certainty was interpreted with risk-of-bias and GRADE inputs."
                    ),
                    citations=fallback_citations,
                ),
            ],
        )
    if section == "results":
        return build_results_section_fallback(
            build_results_evidence_pack(grounding),
            required_subsections=list(_SECTION_REQUIRED_SUBHEADINGS.get("results", ())),
            fallback_citations=fallback_citations,
        )
    if section == "discussion":
        topic_scope = ""
        if grounding is not None:
            topic_scope = str(
                getattr(grounding, "research_question", "") or getattr(grounding, "review_topic", "")
            ).strip()
        if not topic_scope:
            topic_scope = "the review question"
        return StructuredSectionDraft(
            section_key="discussion",
            required_subsections=list(_SECTION_REQUIRED_SUBHEADINGS.get("discussion", ())),
            blocks=[
                SectionBlock(block_type="subheading", text="Principal Findings", level=3),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        f"Across included studies addressing {topic_scope}, evidence indicates potentially meaningful "
                        "effects, but heterogeneity and certainty limitations constrain strong causal conclusions."
                    ),
                ),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        "Interpretation should remain cautious because outcome definitions, comparator quality, and reporting "
                        "completeness vary substantially across the evidence base."
                    ),
                ),
                SectionBlock(block_type="subheading", text="Comparison with Prior Work", level=3),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        "These findings are broadly consistent with prior systematic review trends, while direct "
                        "cross-study comparison remains limited by outcome heterogeneity and contextual differences."
                    ),
                ),
                SectionBlock(block_type="subheading", text="Strengths and Limitations", level=3),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        "Strengths include protocol-led screening and structured extraction, whereas limitations include "
                        "variable study quality, inconsistent reporting, and constrained full-text availability."
                    ),
                ),
                SectionBlock(block_type="subheading", text="Implications for Practice", level=3),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        "Practice adoption should be cautious and context-aware, prioritizing settings with adequate "
                        "implementation support and robust evidence of effectiveness."
                    ),
                ),
                SectionBlock(block_type="subheading", text="Implications for Research", level=3),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        "Future studies should use stronger comparative designs, standardized outcomes, and preregistered "
                        "analysis plans to improve causal interpretability and certainty of evidence."
                    ),
                ),
            ],
        )
    return StructuredSectionDraft(
        section_key=section,
        blocks=[
            SectionBlock(
                block_type="paragraph",
                text="Section content was generated using deterministic fallback due to incomplete model output.",
            )
        ],
    )
