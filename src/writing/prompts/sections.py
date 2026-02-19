"""Section-specific prompt templates (PRISMA 2020 aligned)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.writing.context_builder import WritingGroundingData

ABSTRACT_WORD_LIMIT = 250

SECTIONS = [
    "abstract",
    "introduction",
    "methods",
    "results",
    "discussion",
    "conclusion",
]


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
    return (
        prefix
        + "Write the abstract. Use the FACTUAL DATA BLOCK above for all numbers -- "
        "do NOT invent participant counts, effect sizes, or confidence intervals. "
        "If meta-analysis was NOT feasible (see block above), do NOT report an SMD or CI. "
        "Instead describe the synthesis direction from the block. "
        "Cover: (1) Title as systematic review, "
        "(2) Objectives with PICO, (3) Eligibility criteria, (4) Information sources using exact "
        "database names from the block, (5) Risk of bias methods, (6) Exact included studies count "
        "from the block, (7) Synthesis results -- use narrative description only if meta-analysis "
        "was not feasible, (8) Key findings grounded in included studies list, (9) Strengths and "
        "limitations, (10) Funding, (11) Protocol registration if available, (12) Funding sources."
    )


def get_introduction_prompt_context(
    grounding: Optional["WritingGroundingData"] = None,
) -> str:
    """Context for introduction."""
    prefix = _grounding_prefix(grounding)
    return (
        prefix
        + "Write the introduction. Cover: Background on the topic, gap in the literature, "
        "objective of this review, and its significance. "
        "Ground specific study references in the INCLUDED STUDIES list above."
    )


def get_methods_prompt_context(
    grounding: Optional["WritingGroundingData"] = None,
) -> str:
    """Context for methods. PRISMA Items 3-16."""
    prefix = _grounding_prefix(grounding)
    return (
        prefix
        + "Write the methods section. Use the FACTUAL DATA BLOCK for all database names and dates. "
        "PRISMA Items 3-16: Eligibility criteria (PICO), information sources (list ONLY the "
        "databases shown in the block, do NOT add Scopus/Web of Science/CINAHL unless listed), "
        "search strategy (reference the search appendix), selection process (dual AI reviewer "
        "screening with automated adjudication), data collection, data items, risk of bias tools "
        "(ROBINS-I for non-randomized studies; RoB 2 for RCTs if any -- use only tools "
        "indicated by study designs in the block), effect measures, synthesis methods (narrative "
        "only if meta-analysis was NOT feasible), GRADE certainty assessment."
    )


def get_results_prompt_context(
    grounding: Optional["WritingGroundingData"] = None,
) -> str:
    """Context for results."""
    prefix = _grounding_prefix(grounding)
    return (
        prefix
        + "Write the results section. ALL counts MUST come from the FACTUAL DATA BLOCK above -- "
        "do NOT invent records identified, screened, or excluded counts. "
        "Structure: (1) Study selection using exact PRISMA numbers from the block, "
        "(2) Study characteristics -- summarize only the studies listed in INCLUDED STUDIES above, "
        "(3) Risk of bias assessment based on study designs in the block, "
        "(4) Synthesis of findings -- if meta-analysis was NOT feasible, present narrative "
        "synthesis only; do NOT report pooled SMD or confidence intervals. "
        "Reference the PRISMA flow diagram (Figure 1), RoB traffic-light (Figure 2). "
        "Cite only from the VALID CITATION KEYS list."
    )


def get_discussion_prompt_context(
    grounding: Optional["WritingGroundingData"] = None,
) -> str:
    """Context for discussion."""
    prefix = _grounding_prefix(grounding)
    return (
        prefix
        + "Write the discussion. Cover: Key findings grounded in the included studies above, "
        "comparison with prior work, strengths and limitations of this review, "
        "implications for practice and future research. "
        "Ground all specific claims in the INCLUDED STUDIES list. "
        "Cite only from the VALID CITATION KEYS list."
    )


def get_conclusion_prompt_context(
    grounding: Optional["WritingGroundingData"] = None,
) -> str:
    """Context for conclusion."""
    prefix = _grounding_prefix(grounding)
    return (
        prefix
        + "Write the conclusion. Provide a concise summary of findings grounded in the "
        "INCLUDED STUDIES list above, implications for practice and research. "
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
    """Return word limit for section, or None if no limit."""
    if section.lower() == "abstract":
        return ABSTRACT_WORD_LIMIT
    return None
