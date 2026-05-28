"""Multimodal PDF table extraction (Gemini vision).

Full-text retrieval lives in ``src.fulltext``; this module re-exports compatibility
symbols for legacy imports.
"""

from __future__ import annotations

import json
import logging
import time

from pydantic import BaseModel

import src.fulltext.retrieval as _fulltext_retrieval
from src.db.repositories import WorkflowRepository
from src.fulltext import (
    FullTextResult,
    fetch_full_text,
    resolve_landing_page,
)
from src.llm.factory import get_chat_client
from src.llm.provider import LLMProvider
from src.models import CostRecord
from src.models.extraction import OutcomeRecord

# Backward-compatible namespace for tests that patch tier helpers on this module.
for _symbol in dir(_fulltext_retrieval):
    if _symbol.startswith("_") and not _symbol.startswith("__"):
        globals()[_symbol] = getattr(_fulltext_retrieval, _symbol)

# Backward-compatible re-exports for legacy imports and tests.
__all__ = [
    "FullTextResult",
    "fetch_full_text",
    "resolve_landing_page",
    "extract_tables_from_pdf",
    "merge_outcomes",
]

logger = logging.getLogger(__name__)


def _get_model_from_settings() -> str:
    try:
        from src.config.loader import load_configs

        _, s = load_configs(settings_path="config/settings.yaml")
        return s.agents["table_extraction"].model
    except Exception:
        from src.llm.model_fallback import get_fallback_model

        return get_fallback_model("lite")


_TABLE_EXTRACTION_PROMPT = """\
You are a systematic review data extractor specializing in extracting quantitative results from study tables.

Examine ALL tables in this document and extract structured outcome data.
For each table row that reports a quantitative result, output one JSON object with:
  - name: outcome measure name (exact from paper, e.g. "anxiety score reduction", "quality of life improvement")
  - description: brief description of the outcome
  - effect_size: the reported effect (e.g. "SMD=0.45", "OR=2.1 (95% CI 1.3-3.4)", "MD=-0.8")
  - se: standard error if reported (numeric string, e.g. "0.12")
  - n: sample size for this outcome (e.g. "120")
  - p_value: p-value if reported (e.g. "0.032", "<0.001")
  - ci_lower: lower bound of 95% CI (numeric string)
  - ci_upper: upper bound of 95% CI (numeric string)
  - group: intervention group label if applicable

Return a JSON object with an "outcomes" array of outcome objects.
If no quantitative tables are found, return {"outcomes": []}.
Return ONLY valid JSON -- no markdown, no explanation.
"""


class _TableOutcomePayload(BaseModel):
    name: str = ""
    description: str = ""
    effect_size: str = ""
    se: str = ""
    n: str = ""
    p_value: str = ""
    ci_lower: str = ""
    ci_upper: str = ""
    group: str = ""


class _TableOutcomePayloadEnvelope(BaseModel):
    outcomes: list[_TableOutcomePayload]


def _parse_table_json(raw: str) -> list[dict[str, str]]:
    """Parse JSON array from LLM output, stripping markdown fences if present."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("Table extraction: malformed JSON payload from model: %s", exc)
        raise
    if isinstance(data, list):
        return [
            {k: str(v) for k, v in item.items() if isinstance(v, (str, int, float))}
            for item in data
            if isinstance(item, dict)
        ]
    return []


async def extract_tables_from_pdf(
    pdf_bytes: bytes | None,
    model_name: str | None = None,
    repository: WorkflowRepository | None = None,
    workflow_id: str = "",
) -> list[OutcomeRecord]:
    """Extract quantitative outcome tables from PDF bytes via PydanticAI multimodal.

    Uses PydanticAI BinaryContent to pass raw PDF bytes to Gemini vision
    natively (no deprecated google-generativeai SDK, no run_in_executor).

    Args:
        pdf_bytes: Raw PDF bytes. If None, returns empty list.
        model_name: Model to use for vision extraction. May be a full provider:model
            string or bare model ref. Defaults to settings.yaml table_extraction model.

    Returns:
        List of OutcomeRecord objects with keys: name, description, effect_size,
        se, n, p_value, ci_lower, ci_upper.
    """
    if not pdf_bytes:
        return []

    if model_name is None:
        model_name = _get_model_from_settings()

    from pydantic_ai.messages import BinaryContent

    if ":" in model_name:
        full_model = model_name
    else:
        configured_model = _get_model_from_settings()
        if ":" in configured_model:
            provider_prefix = configured_model.split(":", 1)[0]
            full_model = f"{provider_prefix}:{model_name}"
        else:
            full_model = model_name

    try:
        t0 = time.monotonic()
        pdf_part = BinaryContent(data=pdf_bytes, media_type="application/pdf")
        client = get_chat_client()
        (
            parsed,
            tokens_in,
            tokens_out,
            cache_write_tokens,
            cache_read_tokens,
            _retries,
        ) = await client.complete_validated_parts(
            [pdf_part, _TABLE_EXTRACTION_PROMPT],
            model=full_model,
            temperature=0.1,
            response_model=_TableOutcomePayloadEnvelope,
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        if repository is not None and workflow_id:
            await repository.save_cost_record(
                CostRecord(
                    workflow_id=workflow_id,
                    model=full_model,
                    phase="phase_4_pdf_vision_table_extraction",
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=LLMProvider.estimate_cost_usd(
                        model=full_model,
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        cache_write=cache_write_tokens,
                        cache_read=cache_read_tokens,
                    ),
                    latency_ms=elapsed_ms,
                    cache_read_tokens=cache_read_tokens,
                    cache_write_tokens=cache_write_tokens,
                )
            )
        return [
            OutcomeRecord(**{k: v for k, v in item.model_dump().items() if k in OutcomeRecord.model_fields})
            for item in parsed.outcomes
        ]
    except json.JSONDecodeError as exc:
        logger.warning("Table extraction: JSON parse error: %s", exc)
    except Exception as exc:
        logger.warning("Table extraction: vision API error: %s", exc)

    return []


def merge_outcomes(
    text_outcomes: list[OutcomeRecord],
    vision_outcomes: list[OutcomeRecord],
) -> tuple[list[OutcomeRecord], str]:
    """Merge text-extracted and vision-extracted outcomes, deduplicating by name.

    Returns (merged_outcomes, extraction_source) where extraction_source is one
    of 'text', 'pdf_vision', or 'hybrid'.
    """
    if not vision_outcomes:
        return text_outcomes, "text"
    if not text_outcomes:
        return vision_outcomes, "pdf_vision"

    # Merge: vision outcomes take precedence for numeric fields when both exist
    name_to_outcome: dict[str, OutcomeRecord] = {}
    for o in text_outcomes:
        name = o.name.lower().strip()
        if name:
            name_to_outcome[name] = o.model_copy()

    for o in vision_outcomes:
        name = o.name.lower().strip()
        if not name:
            continue
        if name in name_to_outcome:
            existing = name_to_outcome[name]
            # Vision takes precedence for numeric fields when non-empty
            numeric_fields = ("effect_size", "se", "ci_lower", "ci_upper", "p_value", "n")
            updates = {
                f: getattr(o, f) for f in numeric_fields if getattr(o, f) and getattr(o, f) not in ("", "not reported")
            }
            if updates:
                name_to_outcome[name] = existing.model_copy(update=updates)
        else:
            name_to_outcome[name] = o.model_copy()

    return list(name_to_outcome.values()), "hybrid"
