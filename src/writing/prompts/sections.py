"""Section-specific prompt templates (PRISMA 2020 aligned)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.writing.context_builder import WritingGroundingData


def _get_abstract_word_limit() -> int:
    """Read max_abstract_words from settings.ieee_export; fall back to 250 (IEEE max)."""
    try:
        from src.config.loader import load_configs

        _, _settings = load_configs(settings_path="config/settings.yaml")
        return int(getattr(getattr(_settings, "ieee_export", None), "max_abstract_words", 250))
    except Exception:
        return 250


ABSTRACT_WORD_LIMIT = _get_abstract_word_limit()

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
    "STRUCTURE RULE: Do NOT write the section name as a heading at the top. "
    "Do NOT write '## Introduction', '## Methods', '## Results', '## Discussion', "
    "'### Results', '### **Results**', '### Discussion', '### **Discussion**', "
    "or any variant of the section name as a heading. "
    "The section heading is inserted automatically by the assembly pipeline. "
    "Begin directly with the first sentence of the section content. "
    "Sub-headings within the section (e.g. '### Study Selection') are allowed."
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


def _grounding_prefix(grounding: WritingGroundingData | None) -> str:
    """Return the formatted grounding block if available, else empty string."""
    if grounding is None:
        return ""
    from src.writing.context_builder import format_grounding_block

    return format_grounding_block(grounding) + "\n\n" + _PROSE_QUALITY_RULE + "\n\n"


def get_abstract_prompt_context(
    grounding: WritingGroundingData | None = None,
) -> str:
    """Context for abstract. Must cover 12 PRISMA abstract items."""
    prefix = _grounding_prefix(grounding)

    # Build a hard meta-analysis constraint based on actual grounding data.
    # meta_analysis_ran=True means pooling succeeded and a result is available.
    # meta_analysis_feasible=True but meta_analysis_ran=False means feasibility check
    # passed but actual float parsing failed -- still narrative synthesis only.
    meta_ran = getattr(grounding, "meta_analysis_ran", False) if grounding else False
    if grounding is not None and not (grounding.meta_analysis_feasible and meta_ran):
        meta_constraint = (
            "CRITICAL -- META-ANALYSIS CONSTRAINT: A meta-analysis was NOT performed "
            "in this review. In the Results field of the abstract "
            "you MUST write ONLY a narrative description such as: "
            "'A narrative synthesis was conducted; the overall direction of evidence "
            "was predominantly positive.' "
            "Do NOT write 'a meta-analysis showed', 'pooled analysis', 'SMD', 'CI', "
            "or any phrase implying quantitative pooling was performed. "
            "This is a hard constraint -- violating it produces a factually incorrect abstract."
        )
    else:
        poolable = getattr(grounding, "poolable_outcomes", []) if grounding else []
        outcomes_str = ", ".join(poolable) if poolable else "the feasible outcome(s)"
        meta_constraint = (
            f"Meta-analysis was performed for: {outcomes_str}. "
            "Report the pooled direction and effect size in the Results field "
            "using the values from the FACTUAL DATA BLOCK. "
            "Do NOT claim meta-analysis for outcomes not listed above."
        )

    # Build kappa framing instruction if kappa data is present in grounding
    kappa_instruction = ""
    if grounding is not None and getattr(grounding, "cohens_kappa", None) is not None:
        kappa_val = f"{grounding.cohens_kappa:.3f}"
        kappa_n = getattr(grounding, "kappa_n", 0)
        n_str = f" (N={kappa_n})" if kappa_n > 0 else ""
        kappa_instruction = (
            f"CRITICAL -- kappa abstract framing: If you mention inter-rater reliability "
            f"in the Methods field, you MUST use the subset qualifier. Write: "
            f"'Inter-rater reliability for the subset of ambiguous papers requiring dual "
            f"review{n_str} was Cohen's kappa = {kappa_val}.' "
            f"Do NOT report this as overall screening agreement. "
            f"The majority of screening decisions were high-confidence single-reviewer "
            f"classifications that are excluded from this kappa calculation.\n\n"
        )

    return (
        prefix
        + meta_constraint
        + "\n\n"
        + kappa_instruction
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
    grounding: WritingGroundingData | None = None,
) -> str:
    """Context for introduction."""
    prefix = _grounding_prefix(grounding)
    return (
        prefix + _NO_HEADING_RULE + "\n\n" + "Write a thorough introduction of approximately 700 words. "
        "Do not truncate findings or provide a superficial overview. "
        "Cover: (1) Background on the topic and its significance and relevance, "
        "(2) Current state of the literature and the evidence gap, "
        "(3) Objective of this systematic review and its scope. "
        "Ground specific study references in the INCLUDED STUDIES list above."
    )


def get_methods_prompt_context(
    grounding: WritingGroundingData | None = None,
) -> str:
    """Context for methods. PRISMA Items 3-16."""
    prefix = _grounding_prefix(grounding)
    return (
        prefix + _NO_HEADING_RULE + "\n\n" + "Write a thorough methods section of approximately 750 words. "
        "Do not truncate or summarise -- describe each step fully. "
        "Use the FACTUAL DATA BLOCK for all database names and dates. "
        "PRISMA Items 3-16: "
        "(1) Eligibility criteria using explicit PICO framework, "
        "(2) Information sources: list the 'Bibliographic databases searched' from the block. "
        "If the block includes a 'Search limitation' line, incorporate that statement verbatim "
        "(e.g. 'Searches were limited to Scopus to align with institutional access.'). "
        "If multiple databases were searched but only one returned records, state explicitly: "
        "'We searched X, Y, Z; only [database name] returned records.' "
        "Any sources listed under 'Other methods' (e.g. perplexity_web, AI discovery tools) must be "
        "described separately as 'Other Methods' per PRISMA 2020 item 7, NOT as bibliographic databases. "
        "Do NOT add Scopus/Web of Science/CINAHL unless listed in the block as searched or as failed. "
        "If the block lists 'Databases attempted but failed', MUST include a sentence disclosing each "
        "failed database verbatim (e.g. 'Web of Science was searched but could not be queried due to an "
        "API error and returned no records for this review.'). Per PRISMA 2020 item 5, failed sources "
        "must be reported. Do NOT omit them even if they returned no results. "
        "If inter-rater reliability (Cohen's kappa) is present in the block, report it in this section. "
        "(3) Search strategy (reference the search appendix), "
        "(4) Selection process: use the 'Screening method' text from the FACTUAL DATA BLOCK verbatim. "
        "Use neutral phrasing such as 'two independent reviewers' or 'two reviewers'. "
        "Do NOT specify whether reviewers were human or AI -- do not write 'large language models', "
        "'AI reviewers', 'AI adjudicator', 'human reviewers', or 'two independent researchers'. "
        "The block contains the exact approved neutral description. "
        "If Cohen's kappa is present in the block, include it in this sub-section with the subset qualifier. "
        "(5) Data collection process and data items extracted, "
        "(6) Risk of bias tools (ROBINS-I for non-randomized studies; RoB 2 for RCTs -- "
        "use only the tools indicated by study designs in the block), "
        "(7) Synthesis methods: check the 'Meta-analysis:' line in the FACTUAL DATA BLOCK. "
        "If it says 'NARRATIVE SYNTHESIS ONLY' or 'NOT feasible', write ONLY narrative synthesis -- "
        "do NOT write 'we conducted a meta-analysis', 'pooled effect sizes', 'SMD', or 'confidence intervals'. "
        "If it says 'PERFORMED on outcome(s):', report meta-analysis ONLY for those specific outcomes and "
        "use narrative synthesis for all other outcomes. "
        "Never generalize or expand the pooled outcomes beyond what the block explicitly lists. "
        "If the FACTUAL DATA BLOCK contains a 'SWIM NARRATIVE SYNTHESIS REQUIREMENT' instruction, "
        "follow it EXACTLY: name the outcome domains used to group studies, state the "
        "direction-of-effect (vote-counting) approach, and organise the Results synthesis "
        "subsection by these domains. Do NOT mix all outcomes into a single generic paragraph. "
        "(8) GRADE certainty assessment, "
        "(9) Protocol registration: use EXACTLY the wording shown in 'Protocol registration' "
        "in the FACTUAL DATA BLOCK -- do NOT invent or contradict it. "
        "If the block says 'NOT PROSPECTIVELY REGISTERED', write the OSF post-hoc registration "
        "statement verbatim from the block. "
        "NEVER write 'registration is planned on PROSPERO' or 'will be registered'. "
        "NEVER write 'registered prospectively' unless the block explicitly says YES. "
        "If the FACTUAL DATA BLOCK contains a 'LLM SCREENING TRANSPARENCY' instruction, "
        "include the full batch pre-ranker disclosure paragraph verbatim in this section. "
        "If the FACTUAL DATA BLOCK contains a 'FULL-TEXT RETRIEVAL EFFORT' instruction, "
        "include the retrieval pathways paragraph in this section. "
        "Use the subsection style of PRISMA 2020: each item is a distinct sub-paragraph."
    )


def get_results_prompt_context(
    grounding: WritingGroundingData | None = None,
) -> str:
    """Context for results."""
    prefix = _grounding_prefix(grounding)
    return (
        prefix + _NO_HEADING_RULE + "\n\n" + "Write a thorough results section of approximately 900 words. "
        "ALL counts MUST come from the FACTUAL DATA BLOCK above -- "
        "do NOT invent records identified, screened, or excluded counts. "
        "Begin immediately with '### Study Selection' as the first line -- "
        "do NOT add a parent 'Results' heading before it. "
        "Structure with explicit sub-headings:\n"
        "### Study Selection\n"
        "Report exact PRISMA numbers from the block. Refer to Figure 1 (PRISMA flow diagram). "
        "If full-text articles were excluded, report the primary exclusion reasons from "
        "'Primary exclusion reasons' in the FACTUAL DATA BLOCK.\n"
        "### Study Characteristics\n"
        "Summarise the included studies: design distribution, date range, geographic spread, "
        "participant characteristics. Reference Appendix B (study characteristics table). "
        "You MUST include explicit in-text references to the figures: "
        "'Figure 3 shows the publication timeline of included studies.' and "
        "'Figure 4 shows the geographic distribution of included studies.' "
        "These sentences are REQUIRED -- do NOT omit them. "
        "Base descriptions ONLY on the INCLUDED STUDIES list.\n"
        "### Risk of Bias Assessment\n"
        "Summarise RoB findings from the block. Reference Figure 2 (RoB traffic-light plot).\n"
        "### Synthesis of Findings\n"
        "If meta-analysis was NOT feasible, present narrative synthesis only -- "
        "do NOT report pooled SMD or confidence intervals. "
        "If the FACTUAL DATA BLOCK contains a 'SWIM NARRATIVE SYNTHESIS REQUIREMENT' instruction, "
        "follow it EXACTLY: organise findings by the pre-specified outcome domains listed in the "
        "block (e.g., dispensing accuracy, operational efficiency, patient outcomes, barriers/facilitators). "
        "Within each domain, state the direction of effect: how many studies reported improvement, "
        "no change, or worsening. Label each subsection with a heading matching the outcome domain. "
        "Do NOT write a single undifferentiated narrative paragraph. "
        "Cite only from the VALID CITATION KEYS list."
    )


def get_discussion_prompt_context(
    grounding: WritingGroundingData | None = None,
) -> str:
    """Context for discussion."""
    prefix = _grounding_prefix(grounding)
    return (
        prefix + _NO_HEADING_RULE + "\n\n" + "Write a thorough discussion section of approximately 850 words. "
        "Do not truncate. "
        "Begin immediately with '### Principal Findings' as the first line -- "
        "do NOT add a parent 'Discussion' heading before it. "
        "Use explicit sub-headings:\n"
        "### Principal Findings\n"
        "Summarise the main results and their implications.\n"
        "### Comparison with Prior Work\n"
        "Compare findings to earlier reviews and the broader literature. "
        "Ground all claims in the INCLUDED STUDIES list. "
        "If the FACTUAL DATA BLOCK contains a 'SOCIO-TECHNICAL VARIABILITY' instruction, "
        "follow it EXACTLY: explain WHY effect sizes vary across studies, address the "
        "Implementation Dip phenomenon for any studies reporting initial efficiency loss, "
        "and connect variability to socio-technical factors (system maturity, EMR integration, "
        "pharmacy volume, staff training). Do NOT write a generic 'findings align with prior work' "
        "sentence -- provide academic analysis of the variability.\n"
        "### Strengths and Limitations\n"
        "Discuss methodological strengths and limitations of this review explicitly. "
        "The limitations paragraph MUST acknowledge ALL of the following that apply: "
        "(a) language restriction -- state if searches were limited to English-language publications; "
        "(b) absence of citation chasing -- note that reference lists of included studies were not "
        "screened for additional eligible studies (snowball search); "
        "(c) absence of grey literature -- note that trial registries, dissertations, and "
        "unpublished reports were not systematically searched; "
        "(d) reliance on observational and non-randomized study designs; "
        "(e) heterogeneous outcome reporting that precluded meta-analysis (if applicable); "
        "(f) missing sample sizes in included studies (if applicable). "
        "Do NOT collapse all limitations into a single vague sentence. "
        "If the FACTUAL DATA BLOCK contains a 'ROBINS-I/GRADE IMPACT ON CONCLUSIONS' instruction, "
        "follow it EXACTLY: write a dedicated paragraph explicitly connecting the predominant "
        "risk-of-bias judgment (serious/moderate) to the reliability of specific stated effect "
        "estimates, and state the implication of VERY LOW GRADE certainty for the conclusions. "
        "This paragraph must be specific and analytical -- NOT a generic 'limitations exist' sentence. "
        "Do NOT write 'most studies demonstrated moderate to serious risk of bias' without "
        "explaining which specific conclusions are therefore less reliable and why.\n"
        "### Implications for Practice and Future Research\n"
        "Translate findings into concrete recommendations. "
        "Cite only from the VALID CITATION KEYS list."
    )


def get_conclusion_prompt_context(
    grounding: WritingGroundingData | None = None,
) -> str:
    """Context for conclusion."""
    prefix = _grounding_prefix(grounding)
    return (
        prefix + _NO_HEADING_RULE + "\n\n" + "Write a concise conclusion of approximately 350 words. "
        "Provide a clear summary of findings grounded in the INCLUDED STUDIES list, "
        "key implications for practice and future research, and a closing statement. "
        "Do NOT introduce new statistics. Cite only from the VALID CITATION KEYS list."
    )


def get_section_context(
    section: str,
    grounding: WritingGroundingData | None = None,
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
