"""Narrative synthesis fallback when pooling is not feasible.

Effect direction is assessed by the LLM (structured output) when an LLM client
is provided. A keyword-based heuristic is used as a fallback.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel

from src.models import ExtractionRecord

logger = logging.getLogger(__name__)


class NarrativeSynthesis(BaseModel):
    outcome_name: str
    n_studies: int
    effect_direction_summary: str
    key_themes: list[str]
    synthesis_table: list[dict[str, str]]
    narrative_text: str


# ---------------------------------------------------------------------------
# LLM-based direction classification
# ---------------------------------------------------------------------------

class _DirectionLLMResponse(BaseModel):
    direction: Literal["positive", "negative", "mixed", "null"] = "null"
    justification: str = ""


def _build_direction_prompt(results_summary: str, outcome_name: str) -> str:
    return "\n".join([
        "You are a systematic review methodologist assessing effect direction.",
        f"Outcome being assessed: {outcome_name}",
        "",
        "Study findings:",
        results_summary[:2000],
        "",
        "Classify the overall direction of effect for this study as EXACTLY one of:",
        "  positive  - intervention shows improvement / benefit",
        "  negative  - intervention shows harm / worse outcomes",
        "  mixed     - some outcomes improved, others worsened, or results are conditional",
        "  null      - no statistically or clinically meaningful effect, or data insufficient",
        "",
        "Do NOT classify as 'positive' if the text uses negation (e.g., 'did not improve').",
        "Return ONLY valid JSON matching the schema.",
    ])


async def _classify_direction_llm(
    results_summary: str,
    outcome_name: str,
    llm_client: object,
    settings: object,
) -> Literal["positive", "negative", "mixed", "null"]:
    """Call LLM to classify effect direction for a single study summary."""
    from src.llm.pydantic_client import PydanticAIClient
    from src.models.config import SettingsConfig

    if not isinstance(llm_client, PydanticAIClient) or not isinstance(settings, SettingsConfig):
        return _keyword_direction(results_summary)

    agent_cfg = settings.agents.get("extraction")
    model = agent_cfg.model if agent_cfg else "google-gla:gemini-2.0-flash-lite"
    temperature = 0.0

    prompt = _build_direction_prompt(results_summary, outcome_name)
    schema = _DirectionLLMResponse.model_json_schema()
    try:
        raw = await llm_client.complete(
            prompt, model=model, temperature=temperature, json_schema=schema
        )
        parsed = _DirectionLLMResponse.model_validate_json(raw)
        return parsed.direction
    except Exception as exc:
        logger.warning("LLM direction classification failed (%s); using keyword fallback.", exc)
        return _keyword_direction(results_summary)


# ---------------------------------------------------------------------------
# Keyword fallback (kept for offline / LLM-unavailable runs)
# ---------------------------------------------------------------------------

def _keyword_direction(
    summary: str,
) -> Literal["positive", "negative", "mixed", "null"]:
    s = summary.lower()
    positive = any(t in s for t in ["improv", "better", "increase", "higher"])
    negative = any(t in s for t in ["worse", "decrease", "lower", "decline"])
    if positive and not negative:
        return "positive"
    if negative and not positive:
        return "negative"
    if positive and negative:
        return "mixed"
    return "null"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def build_narrative_synthesis(
    outcome_name: str,
    records: Sequence[ExtractionRecord],
    llm_client: object | None = None,
    settings: object | None = None,
) -> NarrativeSynthesis:
    """Build a narrative synthesis from extraction records.

    When *llm_client* and *settings* are provided, each study's effect direction
    is assessed by the LLM to handle negation, conditionality, and mixed findings.
    Falls back to keyword heuristic when the LLM is unavailable.
    """
    rows: list[dict[str, str]] = []
    direction_counts: dict[str, int] = {"positive": 0, "negative": 0, "mixed": 0, "null": 0}
    themes: list[str] = []
    use_llm = llm_client is not None and settings is not None

    for record in records:
        summary = (record.results_summary.get("summary") or "").strip()

        if use_llm:
            direction = await _classify_direction_llm(
                summary, outcome_name, llm_client, settings
            )
        else:
            direction = _keyword_direction(summary)

        direction_counts[direction] = direction_counts.get(direction, 0) + 1
        rows.append(
            {
                "paper_id": record.paper_id,
                "study_design": record.study_design.value,
                "direction": direction,
                "summary_excerpt": summary[:160],
            }
        )
        for outcome in record.outcomes:
            name = outcome.get("name", "").strip().lower().replace(" ", "_")
            if name and name not in {"not_reported", "primary_outcome", "secondary_outcome"}:
                themes.append(name)

    positive = direction_counts.get("positive", 0)
    negative = direction_counts.get("negative", 0)
    mixed = direction_counts.get("mixed", 0)
    null = direction_counts.get("null", 0)

    if positive > max(negative, mixed, null):
        direction_summary = "predominantly_positive"
    elif negative > max(positive, mixed, null):
        direction_summary = "predominantly_negative"
    elif mixed > 0:
        direction_summary = "mixed"
    else:
        direction_summary = "insufficient_data"

    unique_themes = sorted(set(themes))
    total = len(records)
    assessment_method = "LLM-based" if use_llm else "keyword-heuristic"
    narrative = (
        f"Across {total} studies, the evidence direction is {direction_summary} "
        f"({assessment_method} assessment). "
        f"Direction counts: positive={positive}, negative={negative}, "
        f"mixed={mixed}, null/unclear={null}."
    )
    if unique_themes:
        narrative += f" Key outcome themes: {', '.join(unique_themes[:10])}."

    return NarrativeSynthesis(
        outcome_name=outcome_name,
        n_studies=total,
        effect_direction_summary=direction_summary,
        key_themes=unique_themes,
        synthesis_table=rows,
        narrative_text=narrative,
    )
