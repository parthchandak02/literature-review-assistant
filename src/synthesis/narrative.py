"""Narrative synthesis fallback when pooling is not feasible."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from src.models import ExtractionRecord


class NarrativeSynthesis(BaseModel):
    outcome_name: str
    n_studies: int
    effect_direction_summary: str
    key_themes: list[str]
    synthesis_table: list[dict[str, str]]
    narrative_text: str


def build_narrative_synthesis(
    outcome_name: str,
    records: Sequence[ExtractionRecord],
) -> NarrativeSynthesis:
    rows: list[dict[str, str]] = []
    positive = 0
    negative = 0
    themes: list[str] = []
    for record in records:
        summary = (record.results_summary.get("summary") or "").strip()
        summary_lower = summary.lower()
        if any(token in summary_lower for token in ["improv", "better", "increase", "higher"]):
            positive += 1
            direction = "positive"
        elif any(token in summary_lower for token in ["worse", "decrease", "lower", "decline"]):
            negative += 1
            direction = "negative"
        else:
            direction = "mixed_or_unclear"
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
            if name:
                themes.append(name)
    if positive > negative:
        direction_summary = "predominantly_positive"
    elif negative > positive:
        direction_summary = "predominantly_negative"
    else:
        direction_summary = "mixed"
    unique_themes = sorted(set(themes))
    narrative = (
        f"Across {len(records)} studies, the evidence direction is {direction_summary}. "
        f"The most common outcome themes are: {', '.join(unique_themes) if unique_themes else 'none'}."
    )
    return NarrativeSynthesis(
        outcome_name=outcome_name,
        n_studies=len(records),
        effect_direction_summary=direction_summary,
        key_themes=unique_themes,
        synthesis_table=rows,
        narrative_text=narrative,
    )
