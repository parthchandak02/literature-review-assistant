"""Second-pass LLM refinement to improve academic tone and naturalness."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from src.llm.factory import get_chat_client
from src.writing.humanizer_checks import (
    HumanizerFlag,
    format_flags_for_repair,
    has_high_severity,
    scan_humanizer_flags,
)
from src.writing.humanizer_guardrails import extract_citation_blocks, extract_numeric_tokens
from src.writing.prompts.humanizer_prompt import build_humanize_repair_prompt, build_humanize_system_prompt

if TYPE_CHECKING:
    from src.llm.provider import LLMProvider

logger = logging.getLogger(__name__)


def _get_model_from_settings() -> str:
    try:
        from src.config.loader import load_configs

        _, s = load_configs(settings_path="config/settings.yaml")
        return s.agents["humanizer"].model
    except Exception:
        from src.llm.model_fallback import get_fallback_model

        return get_fallback_model("flash")


_HUMANIZE_USER_TEMPLATE = """\
Section text:

{text}

Return ONLY the revised section text. Do not include any commentary or explanation.
"""


def _passes_integrity_checks(before: str, after: str) -> bool:
    """Validate that humanization did not alter protected artifacts."""
    if extract_citation_blocks(before) != extract_citation_blocks(after):
        return False
    if extract_numeric_tokens(before) != extract_numeric_tokens(after):
        return False
    if not before.strip():
        return True
    ratio = len(after) / max(len(before), 1)
    return 0.60 <= ratio <= 1.50


async def humanize_async(
    text: str,
    section: str | None = None,
    model: str | None = None,
    temperature: float = 0.3,
    max_chars: int = 12_000,
    provider: LLMProvider | None = None,
    timeout_seconds: float | None = None,
    enable_verification_repair: bool = True,
    repair_max_per_pass: int = 1,
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
    if model is None:
        model = _get_model_from_settings()
    if timeout_seconds is None:
        try:
            from src.config.loader import load_configs

            _, s = load_configs(settings_path="config/settings.yaml")
            timeout_seconds = float(s.llm.request_timeout_seconds)
        except Exception:
            timeout_seconds = 180.0
    truncated = text[:cut]
    prompt = f"{build_humanize_system_prompt(section)}\n\n{_HUMANIZE_USER_TEMPLATE.format(text=truncated)}"
    client = get_chat_client(timeout_seconds=timeout_seconds)
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
        if not _passes_integrity_checks(text, refined):
            logger.warning("Humanizer integrity check failed; returning original text.")
            return text
        flags = scan_humanizer_flags(refined)
        if has_high_severity(flags):
            high_count = len([f for f in flags if f.tier == "high"])
            logger.info(
                "Humanizer found %d high-severity flags for section '%s'.",
                high_count,
                section or "unknown",
            )
            if enable_verification_repair and repair_max_per_pass > 0:
                repaired = await humanize_repair_async(
                    original_text=text,
                    current_text=refined,
                    section=section or "unknown_section",
                    model=model,
                    temperature=temperature,
                    provider=provider,
                    timeout_seconds=timeout_seconds,
                    max_repairs=repair_max_per_pass,
                    flags=flags,
                )
                if _passes_integrity_checks(text, repaired):
                    refined = repaired
                else:
                    return text
                if has_high_severity(scan_humanizer_flags(refined)):
                    logger.warning("Humanizer repair left unresolved high-severity flags; returning original text.")
                    return text
            else:
                logger.warning(
                    "Humanizer returned unresolved high-severity flags with repair disabled; returning original text."
                )
                return text
        return refined
    except Exception as exc:
        logger.warning("Humanizer LLM call failed (%s); returning original text.", type(exc).__name__)
        return text


async def humanize_repair_async(
    *,
    original_text: str,
    current_text: str,
    section: str,
    model: str,
    temperature: float,
    provider: LLMProvider | None,
    timeout_seconds: float,
    max_repairs: int,
    flags: list[HumanizerFlag],
) -> str:
    """Run a bounded targeted repair for unresolved high-severity humanizer flags."""
    client = get_chat_client(timeout_seconds=timeout_seconds)
    revised = current_text
    for _ in range(max_repairs):
        if not has_high_severity(flags):
            return revised
        if not format_flags_for_repair(flags):
            return revised
        repair_prompt = build_humanize_repair_prompt(section, revised, flags)
        t0 = time.monotonic()
        candidate, tok_in, tok_out, cw, cr = await client.complete_with_usage(
            repair_prompt,
            model=model,
            temperature=temperature,
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
        if not _passes_integrity_checks(original_text, candidate):
            return original_text
        revised = candidate
        flags = scan_humanizer_flags(revised)
    return revised
