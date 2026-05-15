"""Deterministic source-quality priors for screening guidance."""

from __future__ import annotations

from src.models.papers import CandidatePaper

_SOURCE_PRIORS: dict[str, tuple[str, bool, bool]] = {
    # tier, peer_reviewed_likely, open_index
    "pubmed": ("high", True, True),
    "scopus": ("high", True, False),
    "web_of_science": ("high", True, False),
    "ieee_xplore": ("high", True, False),
    "openalex": ("medium", True, True),
    "semantic_scholar": ("medium", True, True),
    "crossref": ("medium", True, True),
    "dblp": ("medium", True, True),
    "core": ("medium", True, True),
    "europepmc": ("high", True, True),
    "embase": ("high", True, False),
    "arxiv": ("medium", False, True),
    "clinicaltrials_gov": ("medium", False, True),
    "perplexity_search": ("low", False, True),
}


def source_quality_prior(source_database: str) -> tuple[str, bool, bool]:
    key = str(source_database or "").strip().lower()
    if key == "wos":
        key = "web_of_science"
    if key == "clinicaltrials":
        key = "clinicaltrials_gov"
    return _SOURCE_PRIORS.get(key, ("unknown", False, True))


def apply_source_quality_prior(paper: CandidatePaper) -> CandidatePaper:
    if paper.source_quality_tier is not None and paper.source_peer_reviewed is not None and paper.source_open_index is not None:
        return paper
    tier, peer_reviewed, open_index = source_quality_prior(paper.source_database)
    return paper.model_copy(
        update={
            "source_quality_tier": paper.source_quality_tier or tier,
            "source_peer_reviewed": peer_reviewed if paper.source_peer_reviewed is None else paper.source_peer_reviewed,
            "source_open_index": open_index if paper.source_open_index is None else paper.source_open_index,
        }
    )


def screening_quality_hint(paper: CandidatePaper) -> str:
    tier, peer_reviewed, open_index = source_quality_prior(paper.source_database)
    source = paper.source_database
    peer_text = "peer-reviewed index likely" if peer_reviewed else "non-peer-reviewed or mixed source"
    openness = "open index" if open_index else "licensed index"
    return f"Source prior: {source} ({tier} quality tier; {peer_text}; {openness})."


def quality_priority_score(
    source_database: str,
    *,
    tier_weights: dict[str, float] | None = None,
    open_index_bonus: float = 0.1,
    peer_review_bonus: float = 0.2,
) -> float:
    tier, peer_reviewed, open_index = source_quality_prior(source_database)
    weights = tier_weights or {"high": 1.0, "medium": 0.7, "low": 0.4, "unknown": 0.5}
    score = float(weights.get(tier, weights.get("unknown", 0.5)))
    if peer_reviewed:
        score += float(peer_review_bonus)
    if open_index:
        score += float(open_index_bonus)
    return score
