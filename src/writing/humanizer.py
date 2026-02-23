"""Second-pass LLM refinement to improve academic tone and naturalness."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from src.llm.pydantic_client import PydanticAIClient

if TYPE_CHECKING:
    from src.llm.provider import LLMProvider

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


def humanize(text: str, max_chars: int = 12_000) -> str:
    """Synchronous pass-through stub for offline/test usage."""
    _ = max_chars
    return text


async def humanize_async(
    text: str,
    model: str = "google-gla:gemini-2.5-pro",
    temperature: float = 0.3,
    max_chars: int = 12_000,
    provider: LLMProvider | None = None,
) -> str:
    """Refine AI-generated text for academic naturalness using Gemini Pro.

    Truncates input to max_chars (at a word boundary) before sending.
    Falls back to returning the original text if the LLM call fails.
    When provider is supplied, the LLM call's token counts and cost are
    logged to the cost_records table.
    """
    # Cut at the last whitespace before max_chars to avoid splitting mid-word.
    if len(text) > max_chars:
        cut = text.rfind(" ", 0, max_chars)
        cut = cut if cut > 0 else max_chars
    else:
        cut = len(text)
    truncated = text[:cut]
    prompt = _HUMANIZE_PROMPT_TEMPLATE.format(text=truncated)
    client = PydanticAIClient()
    try:
        t0 = time.monotonic()
        refined, tok_in, tok_out, cw, cr = await client.complete_with_usage(
            prompt, model=model, temperature=temperature
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        if provider is not None:
            from src.llm.provider import LLMProvider as _LLMProvider
            cost = _LLMProvider.estimate_cost_usd(model, tok_in, tok_out, cw, cr)
            await provider.log_cost(
                model=model,
                tokens_in=tok_in,
                tokens_out=tok_out,
                cost_usd=cost,
                latency_ms=latency_ms,
                phase="phase_6_humanizer",
                cache_read_tokens=cr,
                cache_write_tokens=cw,
            )
        # Re-attach any text that was beyond the cut point.
        if cut < len(text):
            refined = refined + " " + text[cut:].lstrip()
        return refined
    except Exception as exc:
        logger.warning(
            "Humanizer LLM call failed (%s); returning original text.", type(exc).__name__
        )
        return text
