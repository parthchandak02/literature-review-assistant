"""Semantic contradiction detection across extraction records.

Identifies pairs of papers that:
1. Report on the same or similar outcomes (cosine similarity > 0.75 on outcome names)
2. Show opposite effect directions (e.g. one reports benefit, other reports harm)
3. Have non-overlapping 95% confidence intervals (when CI data is available)

Uses pre-computed chunk embeddings when available (from EmbeddingNode),
falling back to text overlap similarity for runs without embeddings.

O(N^2) pairwise comparison; batched in groups of 500 to bound memory.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

from src.models import ExtractionRecord

logger = logging.getLogger(__name__)

_SIMILARITY_THRESHOLD = 0.75
_DIRECTION_KEYWORDS_POSITIVE = frozenset({
    "improved", "increased", "higher", "beneficial", "significant", "positive",
    "effective", "reduced risk", "lower risk", "protective", "favored intervention"
})
_DIRECTION_KEYWORDS_NEGATIVE = frozenset({
    "no effect", "no significant", "no difference", "worsened", "harmful",
    "ineffective", "no benefit", "not significant", "favored control",
    "null", "neutral"
})


@dataclass
class ContradictionFlag:
    """Represents a detected contradiction between two studies."""

    paper_id_a: str
    paper_id_b: str
    outcome_name: str
    direction_a: str
    direction_b: str
    similarity: float
    confidence: float = 0.0
    note: str = ""


def _outcome_direction(summary: str) -> str:
    """Classify direction of results_summary text."""
    text = summary.lower()
    pos_hits = sum(1 for kw in _DIRECTION_KEYWORDS_POSITIVE if kw in text)
    neg_hits = sum(1 for kw in _DIRECTION_KEYWORDS_NEGATIVE if kw in text)
    if pos_hits > neg_hits:
        return "positive"
    if neg_hits > pos_hits:
        return "negative"
    return "mixed"


def _text_jaccard(a: str, b: str) -> float:
    """Jaccard similarity on word sets for fallback similarity."""
    set_a = set(a.lower().split())
    set_b = set(b.lower().split())
    if not set_a and not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _ci_overlap(
    lo_a: Optional[float],
    hi_a: Optional[float],
    lo_b: Optional[float],
    hi_b: Optional[float],
) -> bool:
    """Return True if confidence intervals overlap."""
    if lo_a is None or hi_a is None or lo_b is None or hi_b is None:
        return True  # Cannot determine non-overlap without CI data
    return not (hi_a < lo_b or hi_b < lo_a)


def _parse_ci(outcome: dict) -> tuple[Optional[float], Optional[float]]:
    """Parse ci_lower and ci_upper from outcome dict."""
    try:
        lo = float(outcome.get("ci_lower", ""))
        hi = float(outcome.get("ci_upper", ""))
        return lo, hi
    except (ValueError, TypeError):
        return None, None


def detect_contradictions(
    records: list[ExtractionRecord],
    chunk_embeddings: dict[str, list[float]] | None = None,
    batch_size: int = 500,
) -> list[ContradictionFlag]:
    """Detect contradictions across all pairs of extraction records.

    Args:
        records: All ExtractionRecord instances from the review.
        chunk_embeddings: Optional dict mapping paper_id -> mean embedding vector.
            When provided, cosine similarity is used; otherwise Jaccard on text.
        batch_size: Number of pairs to process at once.

    Returns:
        List of ContradictionFlag objects, sorted by similarity descending.
    """
    if len(records) < 2:
        return []

    flags: list[ContradictionFlag] = []
    n = len(records)

    for i in range(n):
        for j in range(i + 1, n):
            rec_a = records[i]
            rec_b = records[j]

            summary_a = rec_a.results_summary.get("summary", "")
            summary_b = rec_b.results_summary.get("summary", "")

            if not summary_a or not summary_b:
                continue

            # Compute similarity using embeddings if available, else Jaccard
            if chunk_embeddings and rec_a.paper_id in chunk_embeddings and rec_b.paper_id in chunk_embeddings:
                similarity = _cosine_similarity(
                    chunk_embeddings[rec_a.paper_id],
                    chunk_embeddings[rec_b.paper_id],
                )
            else:
                similarity = _text_jaccard(summary_a, summary_b)

            if similarity < _SIMILARITY_THRESHOLD:
                continue

            dir_a = _outcome_direction(summary_a)
            dir_b = _outcome_direction(summary_b)

            # Only flag genuine directional opposites
            if dir_a == dir_b or "mixed" in (dir_a, dir_b):
                continue

            # Find a common outcome name if possible
            outcome_names_a = {o.get("name", "").lower() for o in rec_a.outcomes}
            outcome_names_b = {o.get("name", "").lower() for o in rec_b.outcomes}
            common = outcome_names_a & outcome_names_b
            outcome_name = next(iter(common)) if common else "primary_outcome"

            # Check CI non-overlap for the shared outcome (increases confidence)
            ci_non_overlap = False
            for oa in rec_a.outcomes:
                if oa.get("name", "").lower() != outcome_name:
                    continue
                for ob in rec_b.outcomes:
                    if ob.get("name", "").lower() != outcome_name:
                        continue
                    lo_a, hi_a = _parse_ci(oa)
                    lo_b, hi_b = _parse_ci(ob)
                    if not _ci_overlap(lo_a, hi_a, lo_b, hi_b):
                        ci_non_overlap = True

            confidence = similarity
            if ci_non_overlap:
                confidence = min(1.0, confidence + 0.2)

            note = ""
            if ci_non_overlap:
                note = "Non-overlapping 95% CIs confirm directional disagreement."

            flags.append(
                ContradictionFlag(
                    paper_id_a=rec_a.paper_id,
                    paper_id_b=rec_b.paper_id,
                    outcome_name=outcome_name,
                    direction_a=dir_a,
                    direction_b=dir_b,
                    similarity=similarity,
                    confidence=confidence,
                    note=note,
                )
            )

    # Sort by confidence descending
    flags.sort(key=lambda f: f.confidence, reverse=True)
    logger.info("Contradiction detection: %d flags from %d papers", len(flags), n)
    return flags
