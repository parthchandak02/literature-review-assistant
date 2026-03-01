"""HyDE: Hypothetical Document Embeddings for RAG retrieval.

Generates a short hypothetical excerpt of a manuscript section
(e.g. "methods") that is specific to the review topic. This text
is then embedded in place of the bare section name, producing a
richer query vector that aligns better with extracted evidence chunks.

Reference: Gao et al. (2022) "Precise Zero-Shot Dense Retrieval without
Relevance Labels" (arXiv:2212.10496).
"""
from __future__ import annotations

import logging
from typing import Optional

from pydantic_ai import Agent

logger = logging.getLogger(__name__)

_HYDE_PROMPT = """\
You are a systematic review author. Write a 2-3 sentence excerpt that would
appear in the {section} section of a systematic review on this topic:

"{research_question}"

Requirements:
- Be specific to the topic above
- Use academic language matching published systematic reviews
- Do NOT fabricate specific study names, statistics, or citations
- Length: 100-200 words maximum
"""

_SECTION_CONTEXT: dict[str, str] = {
    "introduction": "introducing background, clinical significance, and review objectives",
    "methods": "describing the search strategy, eligibility criteria, and data extraction approach",
    "results": "summarising included study characteristics and key outcome findings",
    "discussion": "interpreting results, comparing with prior work, and discussing limitations",
    "conclusion": "stating main conclusions and implications for practice or future research",
}


async def generate_hyde_document(
    section: str,
    research_question: str,
    model: str = "google-gla:gemini-2.0-flash",
    provider: Optional[object] = None,
) -> str:
    """Generate a hypothetical document excerpt for use as a RAG query vector.

    Args:
        section: Section name, e.g. "methods", "discussion".
        research_question: The full review research question.
        model: Fast LLM model to use for generation.
        provider: Optional PydanticAI provider override (unused; reserved for future).

    Returns:
        Hypothetical text (100-200 words), or "" on any failure.
    """
    # Abstract is pre-grounded in synthesis data -- HyDE adds no value here.
    if section == "abstract":
        return ""

    section_hint = _SECTION_CONTEXT.get(section, section)
    prompt = _HYDE_PROMPT.format(
        section=f"{section} ({section_hint})",
        research_question=research_question,
    )

    try:
        agent: Agent[None, str] = Agent(model, result_type=str)
        result = await agent.run(prompt)
        text = result.data.strip()
        if len(text) < 30:
            logger.warning("HyDE output too short for section '%s': %r", section, text)
            return ""
        logger.debug("HyDE generated %d chars for section '%s'", len(text), section)
        return text
    except Exception as exc:
        logger.warning("HyDE generation failed for section '%s': %s", section, exc)
        return ""
