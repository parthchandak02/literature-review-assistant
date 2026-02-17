"""Base prompt patterns for all manuscript sections."""

PROHIBITED_PHRASES = (
    "NEVER use these phrases: 'Of course', 'Here is', 'As an expert', 'Certainly', "
    "'In this section', 'As mentioned above', 'It is important to note', 'It should be noted'. "
    "Do NOT begin with conversational preamble or meta-commentary. "
    "Do NOT use separator lines (***, ---). "
    "Output must be suitable for direct insertion into the manuscript."
)

CITATION_CATALOG_TEMPLATE = (
    "Use ONLY citations from the provided catalog below. "
    "Use exact citekey format: [Smith2023], [Jones2024a]. "
    "Do NOT invent or hallucinate any citations not in the catalog. "
    "Every factual claim must be supported by at least one citation."
)


def get_citation_catalog_constraint(catalog_text: str) -> str:
    """Return the citation catalog constraint block for prompts."""
    return f"{CITATION_CATALOG_TEMPLATE}\n\nCitation catalog:\n{catalog_text}"
