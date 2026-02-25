"""Section-specific prompt templates (PRISMA 2020 aligned)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.writing.context_builder import WritingGroundingData

ABSTRACT_WORD_LIMIT = 300

SECTION_WORD_LIMITS: dict[str, int] = {
    "abstract": ABSTRACT_WORD_LIMIT,
    "introduction": 700,
    "methods": 750,
    "results": 900,
    "discussion": 850,
    "conclusion": 350,
}

SECTIONS = [
    "abstract",
    "introduction",
    "methods",
    "results",
    "discussion",
    "conclusion",
]

# Instruction added to every non-abstract section to prevent the LLM from
# writing its own duplicate heading (the assembly pipeline adds headings).
_NO_HEADING_RULE = (
    "STRUCTURE RULE: Do NOT begin the text with a section heading "
    "(e.g. '## Introduction', '## Methods'). "
    "The heading is inserted automatically by the assembly pipeline. "
    "Begin directly with the first sentence of the section content."
)

_PROSE_QUALITY_RULE = (
    "PROSE QUALITY RULES (mandatory):\n"
    "1. Write in natural academic English prose throughout.\n"
    "2. Never copy raw field names, snake_case identifiers, or enum values "
    "into the manuscript text. Paraphrase all directional findings and "
    "synthesis descriptions in your own words (e.g. write "
    "'predominantly positive' not 'predominantly_positive').\n"
    "3. Never invent statistics, effect sizes, or counts not present in "
    "the FACTUAL DATA BLOCK.\n"
    "4. Use ONLY the citation keys listed in VALID CITATION KEYS. "
    "Do not invent citekeys.\n"
)


def _grounding_prefix(grounding: Optional["WritingGroundingData"]) -> str:
    """Return the formatted grounding block if available, else empty string."""
    if grounding is None:
        return ""
    from src.writing.context_builder import format_grounding_block
    return format_grounding_block(grounding) + "\n\n" + _PROSE_QUALITY_RULE + "\n\n"


def get_abstract_prompt_context(
    grounding: Optional["WritingGroundingData"] = None,
) -> str:
    """Context for abstract. Must cover 12 PRISMA abstract items."""
    prefix = _grounding_prefix(grounding)

    # Build a hard meta-analysis constraint based on actual grounding data.
    if grounding is not None and not grounding.meta_analysis_feasible:
        meta_constraint = (
            "CRITICAL -- META-ANALYSIS CONSTRAINT: A meta-analysis was NOT performed "
            "in this review due to heterogeneity. In the Results field of the abstract "
            "you MUST write ONLY a narrative description such as: "
            "'A narrative synthesis was conducted; the overall direction of evidence "
            "was predominantly positive.' "
            "Do NOT write 'a meta-analysis showed', 'pooled analysis', 'SMD', 'CI', "
            "or any phrase implying quantitative pooling was performed. "
            "This is a hard constraint -- violating it produces a factually incorrect abstract."
        )
    else:
        meta_constraint = (
            "If meta-analysis was performed, report the pooled direction and effect "
            "size in the Results field using the values from the FACTUAL DATA BLOCK."
        )

    return (
        prefix
        + meta_constraint + "\n\n"
        + "Write the structured abstract. Format it with bold field labels on separate lines: "
        "**Objectives:**, **Methods:**, **Results:**, **Conclusion:**, **Keywords:**\n\n"
        "Use the FACTUAL DATA BLOCK above for all numbers -- "
        "do NOT invent participant counts, effect sizes, or confidence intervals. "
        "Cover: (1) Objectives with PICO, (2) Eligibility criteria, "
        "(3) Information sources using exact database names from the block, "
        "(4) Risk of bias methods, (5) Exact included studies count from the block, "
        "(6) Synthesis results (narrative only -- see constraint above), "
        "(7) Key findings grounded in included studies list, "
        "(8) Limitations and funding.\n\n"
        "After the Conclusion field, add: "
        "'**Keywords:** [5-7 comma-separated keywords drawn from the research topic]'"
    )


def get_introduction_prompt_context(
    grounding: Optional["WritingGroundingData"] = None,
) -> str:
    """Context for introduction."""
    prefix = _grounding_prefix(grounding)
    return (
        prefix
        + _NO_HEADING_RULE + "\n\n"
        + "Write a thorough introduction of approximately 700 words. "
        "Do not truncate findings or provide a superficial overview. "
        "Cover: (1) Background on the topic and its clinical/educational significance, "
        "(2) Current state of the literature and the evidence gap, "
        "(3) Objective of this systematic review and its scope. "
        "Ground specific study references in the INCLUDED STUDIES list above."
    )


def get_methods_prompt_context(
    grounding: Optional["WritingGroundingData"] = None,
) -> str:
    """Context for methods. PRISMA Items 3-16."""
    prefix = _grounding_prefix(grounding)
    return (
        prefix
        + _NO_HEADING_RULE + "\n\n"
        + "Write a thorough methods section of approximately 750 words. "
        "Do not truncate or summarise -- describe each step fully. "
        "Use the FACTUAL DATA BLOCK for all database names and dates. "
        "PRISMA Items 3-16: "
        "(1) Eligibility criteria using explicit PICO framework, "
        "(2) Information sources: list ONLY the 'Bibliographic databases searched' from the block. "
        "Any sources listed under 'Other methods' (e.g. perplexity_web, AI discovery tools) must be "
        "described separately as 'Other Methods' per PRISMA 2020 item 7, NOT as bibliographic databases. "
        "Do NOT add Scopus/Web of Science/CINAHL unless listed in the block. "
        "If inter-rater reliability (Cohen's kappa) is present in the block, report it in this section. "
        "(3) Search strategy (reference the search appendix), "
        "(4) Selection process: clearly state 'two independent AI reviewers screened titles and abstracts "
        "using large language models, with disagreements resolved by an automated AI adjudicator.' "
        "Do NOT describe AI reviewers as human reviewers. "
        "If full-text assessment was also performed by AI reviewers, state this explicitly. "
        "(5) Data collection process and data items extracted, "
        "(6) Risk of bias tools (ROBINS-I for non-randomized studies; RoB 2 for RCTs -- "
        "use only the tools indicated by study designs in the block), "
        "(7) Synthesis methods (narrative synthesis only -- do NOT describe meta-analysis "
        "procedures if meta-analysis was NOT feasible), "
        "(8) GRADE certainty assessment. "
        "Use the subsection style of PRISMA 2020: each item is a distinct sub-paragraph."
    )


def get_results_prompt_context(
    grounding: Optional["WritingGroundingData"] = None,
) -> str:
    """Context for results."""
    prefix = _grounding_prefix(grounding)
    return (
        prefix
        + _NO_HEADING_RULE + "\n\n"
        + "Write a thorough results section of approximately 900 words. "
        "ALL counts MUST come from the FACTUAL DATA BLOCK above -- "
        "do NOT invent records identified, screened, or excluded counts. "
        "Structure with explicit sub-headings:\n"
        "### Study Selection\n"
        "Report exact PRISMA numbers from the block. Refer to Figure 1 (PRISMA flow diagram).\n"
        "### Study Characteristics\n"
        "Summarise the included studies: design distribution, date range, geographic spread, "
        "participant characteristics. Reference Appendix A (study characteristics table). "
        "Base descriptions ONLY on the INCLUDED STUDIES list.\n"
        "### Risk of Bias Assessment\n"
        "Summarise RoB findings from the block. Reference Figure 2 (RoB traffic-light plot).\n"
        "### Synthesis of Findings\n"
        "If meta-analysis was NOT feasible, present narrative synthesis only -- "
        "do NOT report pooled SMD or confidence intervals. "
        "Organise by outcome themes. Cite only from the VALID CITATION KEYS list."
    )


def get_discussion_prompt_context(
    grounding: Optional["WritingGroundingData"] = None,
) -> str:
    """Context for discussion."""
    prefix = _grounding_prefix(grounding)
    return (
        prefix
        + _NO_HEADING_RULE + "\n\n"
        + "Write a thorough discussion section of approximately 850 words. "
        "Do not truncate. Use explicit sub-headings:\n"
        "### Principal Findings\n"
        "Summarise the main results and their implications.\n"
        "### Comparison with Prior Work\n"
        "Compare findings to earlier reviews and the broader literature. "
        "Ground all claims in the INCLUDED STUDIES list.\n"
        "### Strengths and Limitations\n"
        "Discuss methodological strengths and limitations of this review explicitly.\n"
        "### Implications for Practice and Future Research\n"
        "Translate findings into concrete recommendations. "
        "Cite only from the VALID CITATION KEYS list."
    )


def get_conclusion_prompt_context(
    grounding: Optional["WritingGroundingData"] = None,
) -> str:
    """Context for conclusion."""
    prefix = _grounding_prefix(grounding)
    return (
        prefix
        + _NO_HEADING_RULE + "\n\n"
        + "Write a concise conclusion of approximately 350 words. "
        "Provide a clear summary of findings grounded in the INCLUDED STUDIES list, "
        "key implications for practice and future research, and a closing statement. "
        "Do NOT introduce new statistics. Cite only from the VALID CITATION KEYS list."
    )


def get_section_context(
    section: str,
    grounding: Optional["WritingGroundingData"] = None,
) -> str:
    """Return prompt context for section, optionally injecting grounding data."""
    lookup = {
        "abstract": get_abstract_prompt_context,
        "introduction": get_introduction_prompt_context,
        "methods": get_methods_prompt_context,
        "results": get_results_prompt_context,
        "discussion": get_discussion_prompt_context,
        "conclusion": get_conclusion_prompt_context,
    }
    fn = lookup.get(section.lower(), get_introduction_prompt_context)
    return fn(grounding=grounding)


def get_section_word_limit(section: str) -> int | None:
    """Return target word count for section, or None if unset."""
    return SECTION_WORD_LIMITS.get(section.lower())
