"""Research gap detection from the evidence knowledge graph.

Identifies underrepresented populations, missing outcomes, and methodology
gaps by analyzing the distribution of extraction record attributes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import uuid4

from src.models import ExtractionRecord

logger = logging.getLogger(__name__)

_MIN_STUDY_COUNT_FOR_GAP = 3


@dataclass
class ResearchGap:
    """A detected gap in the evidence base."""

    gap_id: str
    description: str
    related_paper_ids: list[str]
    gap_type: str  # 'underrepresented_population' | 'missing_outcome' | 'methodology_gap'


def detect_research_gaps(records: list[ExtractionRecord]) -> list[ResearchGap]:
    """Identify research gaps from extraction record distributions.

    Detects:
    1. Underrepresented populations (demographics mentioned in < 20% of studies)
    2. Missing outcomes (outcomes mentioned in only 1 study)
    3. Methodology gaps (study designs absent when others are present)

    Args:
        records: All extraction records from the review.

    Returns:
        List of ResearchGap objects. Empty if fewer than 3 records.
    """
    if len(records) < _MIN_STUDY_COUNT_FOR_GAP:
        return []

    gaps: list[ResearchGap] = []
    n = len(records)

    # Gap 1: underrepresented populations
    population_mentions: dict[str, list[str]] = {}
    for rec in records:
        demos = (rec.participant_demographics or "").lower()
        for keyword in ("elderly", "pediatric", "children", "women", "men", "rural", "urban",
                        "low-income", "minority", "black", "hispanic", "asian", "white"):
            if keyword in demos:
                population_mentions.setdefault(keyword, []).append(rec.paper_id)

    for pop, paper_ids in population_mentions.items():
        if 1 <= len(paper_ids) < max(2, n // 5):
            gaps.append(
                ResearchGap(
                    gap_id=str(uuid4()),
                    description=(
                        f"Population '{pop}' is underrepresented: only {len(paper_ids)} "
                        f"of {n} studies explicitly addressed this group."
                    ),
                    related_paper_ids=paper_ids,
                    gap_type="underrepresented_population",
                )
            )

    # Gap 2: outcome mentioned in only one study
    outcome_papers: dict[str, list[str]] = {}
    for rec in records:
        for outcome in rec.outcomes:
            name = outcome.get("name", "").lower().strip()
            if name and name not in ("primary_outcome", "secondary_outcome", ""):
                outcome_papers.setdefault(name, []).append(rec.paper_id)

    for outcome_name, paper_ids in outcome_papers.items():
        if len(paper_ids) == 1 and n >= 5:
            gaps.append(
                ResearchGap(
                    gap_id=str(uuid4()),
                    description=(
                        f"Outcome '{outcome_name}' was measured in only 1 of {n} studies. "
                        f"Replication would strengthen the evidence base."
                    ),
                    related_paper_ids=paper_ids,
                    gap_type="missing_outcome",
                )
            )

    # Gap 3: methodology gap (only one study design type when multiple are appropriate)
    design_counts: dict[str, list[str]] = {}
    for rec in records:
        design = rec.study_design.value if rec.study_design else "unknown"
        design_counts.setdefault(design, []).append(rec.paper_id)

    dominant_design = max(design_counts, key=lambda d: len(design_counts[d]))
    dominant_count = len(design_counts[dominant_design])
    if dominant_count > n * 0.7 and n >= 5:
        gaps.append(
            ResearchGap(
                gap_id=str(uuid4()),
                description=(
                    f"The evidence base is dominated by '{dominant_design}' studies "
                    f"({dominant_count}/{n}). Higher-quality study designs may be needed."
                ),
                related_paper_ids=design_counts[dominant_design],
                gap_type="methodology_gap",
            )
        )

    logger.info("Gap detection: %d gaps identified from %d records", len(gaps), n)
    return gaps
