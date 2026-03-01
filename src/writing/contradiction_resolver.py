"""Contradiction resolver: generates an evidence-based disagreement paragraph.

When the contradiction detector identifies high-confidence contradictions,
this module uses the pro-tier LLM to write a concise, balanced paragraph
acknowledging the directional disagreement and potential explanatory factors.

The generated paragraph is injected into the Discussion section.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from src.synthesis.contradiction_detector import ContradictionFlag

logger = logging.getLogger(__name__)

_RESOLVER_PROMPT_TEMPLATE = (
    "You are writing the Discussion section of a systematic review.\n"
    "The following pairs of studies report opposite findings on the same outcome.\n\n"
    "Contradictions identified:\n"
    "{contradiction_list}\n\n"
    "Write a concise paragraph (100-200 words) for the Discussion section that:\n"
    "1. Acknowledges the directional disagreement between studies\n"
    "2. Notes plausible explanatory factors (population heterogeneity, measurement differences)\n"
    "3. Avoids making a definitive claim about which direction is correct\n"
    "4. Uses hedged academic language (findings were inconsistent, evidence remains inconclusive)\n"
    "5. Does NOT fabricate statistics or effect sizes\n\n"
    "Return ONLY the paragraph text, no headings or labels.\n"
)


def _format_contradiction_list(flags: list[ContradictionFlag]) -> str:
    lines: list[str] = []
    for i, f in enumerate(flags[:5], 1):
        lines.append(
            f"{i}. Paper {f.paper_id_a[:12]} vs {f.paper_id_b[:12]}: "
            f"outcome='{f.outcome_name}', "
            f"directions={f.direction_a} vs {f.direction_b}, "
            f"similarity={f.similarity:.2f}"
        )
    return "\n".join(lines)


def _generate_paragraph_sync(flags: list[ContradictionFlag], model_name: str, api_key: str) -> str:
    try:
        import google.generativeai as genai  # type: ignore[import-untyped]
    except ImportError:
        return _fallback_paragraph(flags)

    if not api_key:
        return _fallback_paragraph(flags)

    genai.configure(api_key=api_key)
    prompt = _RESOLVER_PROMPT_TEMPLATE.format(
        contradiction_list=_format_contradiction_list(flags)
    )

    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        text = response.text.strip()
        if len(text) < 50:
            return _fallback_paragraph(flags)
        return text
    except Exception as exc:
        logger.warning("Contradiction resolver LLM call failed: %s", exc)
        return _fallback_paragraph(flags)


def _fallback_paragraph(flags: list[ContradictionFlag]) -> str:
    outcomes = list({f.outcome_name for f in flags[:3]})
    outcome_str = ", ".join(outcomes) if outcomes else "the primary outcomes"
    return (
        f"Some inconsistency was observed across included studies, particularly "
        f"regarding {outcome_str}. These discrepancies may reflect differences in "
        f"study populations, intervention protocols, outcome measurement approaches, "
        f"or follow-up duration. Given the heterogeneity in study designs and "
        f"settings, these conflicting findings should be interpreted with caution "
        f"and further research is needed to reconcile the observed inconsistencies."
    )


async def generate_contradiction_paragraph(
    flags: list[ContradictionFlag],
    model_name: str = "gemini-2.5-pro",
    api_key: Optional[str] = None,
) -> str:
    """Generate a Discussion paragraph addressing contradictions.

    Returns an empty string if flags is empty.
    """
    if not flags:
        return ""

    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    raw_model = model_name.replace("google-gla:", "").replace("google-vertex:", "")

    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _generate_paragraph_sync, flags, raw_model, key
    )
