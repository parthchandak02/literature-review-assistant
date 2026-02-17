"""Section-specific prompt templates (PRISMA 2020 aligned)."""

ABSTRACT_WORD_LIMIT = 250

SECTIONS = [
    "abstract",
    "introduction",
    "methods",
    "results",
    "discussion",
    "conclusion",
]


def get_abstract_prompt_context() -> str:
    """Context for abstract. Must cover 12 PRISMA abstract items."""
    return (
        "Write the abstract. Cover: (1) Title as systematic review/meta-analysis, "
        "(2) Objectives with PICO, (3) Eligibility criteria, (4) Information sources with dates, "
        "(5) Risk of bias methods, (6) Included studies count/characteristics, "
        "(7) Synthesis results with CIs, (8) Key findings, (9) Strengths and limitations, "
        "(10) Registration/funding, (11) Protocol registration number, (12) Funding sources."
    )


def get_introduction_prompt_context() -> str:
    """Context for introduction."""
    return "Write the introduction. Cover: Background, gap in literature, objective, significance."


def get_methods_prompt_context() -> str:
    """Context for methods. PRISMA Items 3-16."""
    return (
        "Write the methods. Cover: Eligibility criteria (PICO), information sources, "
        "search strategy (reference appendix), selection process (dual reviewer + kappa), "
        "data collection, data items, RoB tools, effect measures, synthesis methods, GRADE."
    )


def get_results_prompt_context() -> str:
    """Context for results."""
    return (
        "Write the results. Reference: PRISMA diagram, study characteristics table, "
        "RoB traffic-light figure, forest plot, GRADE SoF table."
    )


def get_discussion_prompt_context() -> str:
    """Context for discussion."""
    return (
        "Write the discussion. Cover: Key findings, comparison with prior work, "
        "strengths, limitations, implications."
    )


def get_conclusion_prompt_context() -> str:
    """Context for conclusion."""
    return "Write the conclusion. Summary, implications for practice/research."


def get_section_context(section: str) -> str:
    """Return prompt context for section."""
    lookup = {
        "abstract": get_abstract_prompt_context,
        "introduction": get_introduction_prompt_context,
        "methods": get_methods_prompt_context,
        "results": get_results_prompt_context,
        "discussion": get_discussion_prompt_context,
        "conclusion": get_conclusion_prompt_context,
    }
    fn = lookup.get(section.lower(), get_introduction_prompt_context)
    return fn()


def get_section_word_limit(section: str) -> int | None:
    """Return word limit for section, or None if no limit."""
    if section.lower() == "abstract":
        return ABSTRACT_WORD_LIMIT
    return None
