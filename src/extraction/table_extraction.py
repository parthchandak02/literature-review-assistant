"""Multimodal PDF table extraction using Gemini vision API.

Sends PDF bytes to Gemini 2.5 Flash vision endpoint and extracts structured
effect sizes, confidence intervals, p-values, and sample sizes from tables.
Falls back gracefully if no PDF is available or the API call fails.

Every call is wrapped in the standard cost-tracking pattern (caller responsibility).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_TABLE_EXTRACTION_PROMPT = """\
You are a systematic review data extractor specializing in clinical trial result tables.

Examine ALL tables in this document and extract structured outcome data.
For each table row that reports a quantitative result, output one JSON object with:
  - name: outcome measure name (exact from paper, e.g. "HbA1c reduction", "30-day mortality")
  - description: brief description of the outcome
  - effect_size: the reported effect (e.g. "SMD=0.45", "OR=2.1 (95% CI 1.3-3.4)", "MD=-0.8")
  - se: standard error if reported (numeric string, e.g. "0.12")
  - n: sample size for this outcome (e.g. "120")
  - p_value: p-value if reported (e.g. "0.032", "<0.001")
  - ci_lower: lower bound of 95% CI (numeric string)
  - ci_upper: upper bound of 95% CI (numeric string)
  - group: intervention group label if applicable

Return a JSON array of outcome objects. If no quantitative tables are found, return [].
Return ONLY valid JSON -- no markdown, no explanation.
"""


def _extract_tables_sync(
    pdf_bytes: bytes,
    model_name: str,
    api_key: str,
) -> list[dict[str, str]]:
    """Synchronous Gemini vision call -- run in executor."""
    try:
        import google.generativeai as genai  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("google-generativeai not installed; skipping table extraction")
        return []

    if not api_key:
        logger.warning("No GEMINI_API_KEY; skipping table extraction")
        return []

    genai.configure(api_key=api_key)

    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(
            [
                {"mime_type": "application/pdf", "data": pdf_bytes},
                _TABLE_EXTRACTION_PROMPT,
            ]
        )
        raw = response.text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        if isinstance(data, list):
            return [
                {k: str(v) for k, v in item.items() if isinstance(v, (str, int, float))}
                for item in data
                if isinstance(item, dict)
            ]
    except json.JSONDecodeError as exc:
        logger.warning("Table extraction: JSON parse error: %s", exc)
    except Exception as exc:
        logger.warning("Table extraction: vision API error: %s", exc)

    return []


async def extract_tables_from_pdf(
    pdf_bytes: Optional[bytes],
    model_name: str = "gemini-2.5-flash",
    api_key: Optional[str] = None,
) -> list[dict[str, str]]:
    """Extract quantitative outcome tables from PDF bytes via Gemini vision.

    Args:
        pdf_bytes: Raw PDF bytes. If None, returns empty list.
        model_name: Gemini model to use for vision extraction.
        api_key: Gemini API key. Falls back to GEMINI_API_KEY env var.

    Returns:
        List of outcome dicts with keys: name, description, effect_size,
        se, n, p_value, ci_lower, ci_upper, group.
    """
    if not pdf_bytes:
        return []

    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        return []

    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _extract_tables_sync, pdf_bytes, model_name, key
    )


def merge_outcomes(
    text_outcomes: list[dict[str, str]],
    vision_outcomes: list[dict[str, str]],
) -> tuple[list[dict[str, str]], str]:
    """Merge text-extracted and vision-extracted outcomes, deduplicating by name.

    Returns (merged_outcomes, extraction_source) where extraction_source is one
    of 'text', 'pdf_vision', or 'hybrid'.
    """
    if not vision_outcomes:
        return text_outcomes, "text"
    if not text_outcomes:
        return vision_outcomes, "pdf_vision"

    # Merge: vision outcomes take precedence for numeric fields when both exist
    name_to_outcome: dict[str, dict[str, str]] = {}
    for o in text_outcomes:
        name = o.get("name", "").lower().strip()
        if name:
            name_to_outcome[name] = dict(o)

    for o in vision_outcomes:
        name = o.get("name", "").lower().strip()
        if not name:
            continue
        if name in name_to_outcome:
            existing = name_to_outcome[name]
            # Vision takes precedence for effect_size, se, ci_lower, ci_upper, p_value
            for key in ("effect_size", "se", "ci_lower", "ci_upper", "p_value", "n"):
                if o.get(key) and o[key] not in ("", "not reported"):
                    existing[key] = o[key]
        else:
            name_to_outcome[name] = dict(o)

    return list(name_to_outcome.values()), "hybrid"
