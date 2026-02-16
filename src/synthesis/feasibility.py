"""Feasibility checks for quantitative synthesis."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from src.models import ExtractionRecord


class SynthesisFeasibility(BaseModel):
    feasible: bool
    rationale: str
    groupings: list[str]


def assess_meta_analysis_feasibility(
    records: Sequence[ExtractionRecord],
    min_studies: int = 2,
) -> SynthesisFeasibility:
    if len(records) < min_studies:
        return SynthesisFeasibility(
            feasible=False,
            rationale=f"Insufficient studies for pooling: n={len(records)}, minimum={min_studies}.",
            groupings=[],
        )
    grouping_keys: list[str] = []
    for record in records:
        for outcome in record.outcomes:
            name = outcome.get("name", "").strip().lower().replace(" ", "_")
            if name:
                grouping_keys.append(name)
    unique_groupings = sorted(set(grouping_keys))
    if not unique_groupings:
        return SynthesisFeasibility(
            feasible=False,
            rationale="No structured outcomes available for grouping.",
            groupings=[],
        )
    return SynthesisFeasibility(
        feasible=True,
        rationale=f"Detected {len(unique_groupings)} outcome groups from {len(records)} studies.",
        groupings=unique_groupings,
    )
