"""Second-pass LLM refinement to improve academic tone and naturalness."""

from __future__ import annotations

import logging

from src.llm.pydantic_client import PydanticAIClient

logger = logging.getLogger(__name__)

_HUMANIZE_PROMPT_TEMPLATE = """\
You are an expert academic editor specialising in systematic review manuscripts.

Revise the following manuscript section to sound more natural and human-authored.
Do NOT change the factual content, statistics, or citation keys (text inside square
brackets like [AuthorYear] must be preserved exactly).
Do NOT add or remove citations.
Do NOT change section structure or headings.

Improvements to make:
- Vary sentence length and structure for natural rhythm
- Replace mechanical or repetitive academic boilerplate with precise, direct prose
- Eliminate AI-sounding filler phrases (e.g. "It is worth noting that", "Furthermore,
  it is important to mention")
- Maintain formal academic register throughout
- Keep all numerical values and statistical results unchanged

Section text:

{text}

Return ONLY the revised section text. Do not include any commentary or explanation.
"""


def humanize(text: str, max_chars: int = 4_000) -> str:
    """Synchronous pass-through stub for offline/test usage."""
    _ = max_chars
    return text


async def humanize_async(
    text: str,
    model: str = "google-gla:gemini-2.5-pro",
    temperature: float = 0.3,
    max_chars: int = 4_000,
) -> str:
    """Refine AI-generated text for academic naturalness using Gemini Pro.

    Truncates input to max_chars before sending. Falls back to returning the
    original text if the LLM call fails.
    """
    truncated = text[:max_chars]
    prompt = _HUMANIZE_PROMPT_TEMPLATE.format(text=truncated)
    client = PydanticAIClient()
    try:
        refined = await client.complete(prompt, model=model, temperature=temperature)
        # Preserve any text beyond max_chars that was truncated
        if len(text) > max_chars:
            refined = refined + "\n" + text[max_chars:]
        return refined
    except Exception as exc:
        logger.warning(
            "Humanizer LLM call failed (%s); returning original text.", type(exc).__name__
        )
        return text
