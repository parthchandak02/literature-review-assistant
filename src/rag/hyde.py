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
import time
from typing import TYPE_CHECKING

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from src.llm.provider import LLMProvider
from src.llm.pydantic_client import _run_with_retry
from src.models.additional import CostRecord

if TYPE_CHECKING:
    from src.db.repositories import WorkflowRepository

logger = logging.getLogger(__name__)

_HYDE_PROMPT = """\
You are a systematic review author. Write a 2-3 sentence excerpt that would
appear in the {section} section of a systematic review on this topic:

"{research_question}"
{pico_block}
Requirements:
- Be specific to the topic above
- Use academic language matching published systematic reviews
- Do NOT fabricate specific study names, statistics, or citations
- Length: 100-200 words maximum
"""

_SECTION_CONTEXT: dict[str, str] = {
    "introduction": "introducing background, research significance, and review objectives",
    "methods": "describing the search strategy, eligibility criteria, and data extraction approach",
    "results": "summarising included study characteristics and key outcome findings",
    "discussion": "interpreting results, comparing with prior work, and discussing limitations",
    "conclusion": "stating main conclusions and implications for practice or future research",
}


def _build_pico_block(pico: object | None) -> str:
    """Build a PICO context block to inject into the HyDE prompt.

    Returns "" when pico is None or all fields are empty.
    """
    if pico is None:
        return ""
    parts: list[str] = []
    for label, attr in (
        ("Population", "population"),
        ("Intervention", "intervention"),
        ("Comparison", "comparison"),
        ("Outcome", "outcome"),
    ):
        val = getattr(pico, attr, "") or ""
        if val.strip():
            parts.append(f"  {label}: {val.strip()}")
    if not parts:
        return ""
    return "\nPICO framework for this review:\n" + "\n".join(parts) + "\n"


async def generate_hyde_document(
    section: str,
    research_question: str,
    model: str = "google-gla:gemini-3.1-flash-lite-preview",
    pico: object | None = None,
    provider: object | None = None,
    repository: WorkflowRepository | None = None,
) -> str:
    """Generate a hypothetical document excerpt for use as a RAG query vector.

    Args:
        section: Section name, e.g. "methods", "discussion".
        research_question: The full review research question.
        model: Fast LLM model to use for generation.
        pico: Optional PICOConfig object; when provided, PICO terms are injected
            into the prompt to anchor the hypothetical text to the review topic.
        provider: Optional PydanticAI provider override (unused; reserved for future).
        repository: Optional WorkflowRepository; when provided, cost is logged to DB.

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
        pico_block=_build_pico_block(pico),
    )

    try:
        t0 = time.monotonic()
        agent: Agent[None, str] = Agent(model, output_type=str)
        result = await _run_with_retry(agent, prompt, model_settings=ModelSettings(temperature=0.7))
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        text = result.output.strip()
        if len(text) < 30:
            logger.warning("HyDE output too short for section '%s': %r", section, text)
            return ""
        logger.debug("HyDE generated %d chars for section '%s'", len(text), section)

        if repository:
            usage = result.usage()
            tokens_in = usage.input_tokens or 0
            tokens_out = usage.output_tokens or 0
            cost_usd = LLMProvider.estimate_cost_usd(model, tokens_in, tokens_out)
            await repository.save_cost_record(
                CostRecord(
                    model=model,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=cost_usd,
                    latency_ms=elapsed_ms,
                    phase="phase_6_hyde",
                )
            )
        return text
    except Exception as exc:
        logger.warning("HyDE generation failed for section '%s': %s", section, exc)
        return ""
