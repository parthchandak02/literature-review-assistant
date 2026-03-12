"""Non-LLM keyword pre-filter and BM25 relevance ranking for title/abstract screening.

Three strategies are available:

0. metadata_prefilter(): Hard metadata quality gate. Papers with no title,
   no content (abstract + doi + url all empty), or no year are rejected
   immediately before any keyword or LLM call. Ensures the inclusion DB only
   contains papers with enough metadata to screen and extract from.

1. keyword_prefilter(): Hard-gate filter. Papers matching fewer than
   `screening.keyword_filter_min_matches` terms are auto-excluded before any
   LLM call. Reduces cost but risks recall loss for non-standard vocabulary.

2. bm25_rank_and_cap(): Full-corpus BM25 ranking. Ranks ALL papers by
   relevance to the research question + PICO and returns the top N for LLM
   dual-review. Optionally forwards a near-cutoff validation tail to reduce
   false exclusions. Remaining tail papers receive LOW_RELEVANCE_SCORE
   exclusion so every paper has a persisted decision (PRISMA compliance).
   Used when max_llm_screen is set.
"""

from __future__ import annotations

import logging

from src.models.config import ReviewConfig, ScreeningConfig
from src.models.enums import ExclusionReason, ReviewerType, ScreeningDecisionType
from src.models.papers import CandidatePaper
from src.models.screening import ScreeningDecision

_log = logging.getLogger(__name__)


def _paper_text(paper: CandidatePaper) -> str:
    return f"{paper.title or ''} {paper.abstract or ''}".strip().lower()


def _first_match(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        token = pattern.strip().lower()
        if token and token in text:
            return token
    return None


def _is_allowlisted(text: str, screening: ScreeningConfig) -> bool:
    allowlist = [p.strip().lower() for p in screening.deterministic_allowlist_patterns if p.strip()]
    return any(token in text for token in allowlist)


def _deterministic_prefilter_decision(
    paper: CandidatePaper,
    screening: ScreeningConfig,
) -> ScreeningDecision | None:
    """Return deterministic pre-LLM exclusion decision, or None if paper may continue."""
    text = _paper_text(paper)
    abstract = (paper.abstract or "").strip()

    if screening.auto_exclude_empty_abstract and not abstract:
        return ScreeningDecision(
            paper_id=paper.paper_id,
            decision=ScreeningDecisionType.EXCLUDE,
            confidence=1.0,
            reason="Deterministic pre-filter: empty abstract.",
            exclusion_reason=ExclusionReason.INSUFFICIENT_DATA,
            reviewer_type=ReviewerType.KEYWORD_FILTER,
        )

    if _is_allowlisted(text, screening):
        return None

    protocol_match = _first_match(text, screening.protocol_only_patterns)
    if protocol_match is not None:
        return ScreeningDecision(
            paper_id=paper.paper_id,
            decision=ScreeningDecisionType.EXCLUDE,
            confidence=1.0,
            reason=f"Deterministic pre-filter: protocol-only marker '{protocol_match}'.",
            exclusion_reason=ExclusionReason.PROTOCOL_ONLY,
            reviewer_type=ReviewerType.KEYWORD_FILTER,
        )

    secondary_match = _first_match(text, screening.secondary_review_patterns)
    if secondary_match is not None:
        return ScreeningDecision(
            paper_id=paper.paper_id,
            decision=ScreeningDecisionType.EXCLUDE,
            confidence=1.0,
            reason=f"Deterministic pre-filter: secondary-review marker '{secondary_match}'.",
            exclusion_reason=ExclusionReason.WRONG_STUDY_DESIGN,
            reviewer_type=ReviewerType.KEYWORD_FILTER,
        )

    return None


def _title_keyword_matches(paper: CandidatePaper, config: ReviewConfig) -> int:
    title = (paper.title or "").lower()
    terms = [t.lower() for t in (config.keywords or []) + [config.pico.intervention, config.pico.population]]
    uniq_terms = [t for t in dict.fromkeys(term.strip() for term in terms if term and term.strip())]
    return sum(1 for term in uniq_terms if term in title)


def metadata_prefilter(
    papers: list[CandidatePaper],
) -> tuple[list[CandidatePaper], list[ScreeningDecision]]:
    """Reject papers that lack the minimum metadata needed to screen or extract.

    A paper is rejected if ANY of the following are true:
    - No title (empty or whitespace-only)
    - No abstract AND no DOI AND no URL (nothing to retrieve for screening)
    - No publication year (cannot satisfy date range inclusion criterion)

    Rejected papers receive a ScreeningDecision with INSUFFICIENT_DATA so they
    appear correctly in PRISMA flow as "Records removed before screening."
    Returns (acceptable_papers, rejected_decisions).
    """
    acceptable: list[CandidatePaper] = []
    rejected: list[ScreeningDecision] = []

    for paper in papers:
        missing_title = not (paper.title or "").strip()
        has_content = (
            bool((paper.abstract or "").strip()) or bool((paper.doi or "").strip()) or bool((paper.url or "").strip())
        )
        missing_content = not has_content
        missing_year = paper.year is None

        reasons: list[str] = []
        if missing_title:
            reasons.append("no title")
        if missing_content:
            reasons.append("no abstract, DOI, or URL")
        if missing_year:
            reasons.append("no publication year")

        if reasons:
            reason_str = "Metadata pre-filter: " + "; ".join(reasons) + "."
            _log.debug(
                "Metadata pre-filter: rejecting paper %s (%s).",
                paper.paper_id[:12],
                reason_str,
            )
            rejected.append(
                ScreeningDecision(
                    paper_id=paper.paper_id,
                    decision=ScreeningDecisionType.EXCLUDE,
                    confidence=1.0,
                    reason=reason_str,
                    exclusion_reason=ExclusionReason.INSUFFICIENT_DATA,
                    reviewer_type=ReviewerType.KEYWORD_FILTER,
                )
            )
        else:
            acceptable.append(paper)

    if rejected:
        _log.info(
            "Metadata pre-filter: %d/%d papers rejected for missing metadata "
            "(no title/abstract/year); %d forwarded to keyword/LLM screening.",
            len(rejected),
            len(papers),
            len(acceptable),
        )

    return acceptable, rejected


def bm25_rank_and_cap(
    papers: list[CandidatePaper],
    config: ReviewConfig,
    screening: ScreeningConfig,
) -> tuple[list[CandidatePaper], list[ScreeningDecision]]:
    """Rank ALL papers by BM25 relevance; return (top_n_for_llm, tail_decisions).

    When len(papers) <= cap, all papers are returned with no tail exclusions.
    Each tail paper gets a ScreeningDecision with LOW_RELEVANCE_SCORE and the
    numeric BM25 score + rank recorded in the reason string.

    Papers with no title AND no abstract are counted and logged as a data quality
    signal but are still ranked (they score 0 and fall to the tail naturally).
    """
    import bm25s

    cap = screening.max_llm_screen
    total = len(papers)

    if total == 0:
        return [], []

    # Build corpus: title + abstract for each paper.
    corpus: list[str] = []
    zero_abstract_count = 0
    for p in papers:
        title = (p.title or "").strip()
        abstract = (p.abstract or "").strip()
        if not title and not abstract:
            zero_abstract_count += 1
        corpus.append(f"{title} {abstract}".strip() or "no_content")

    if zero_abstract_count > 0:
        _log.warning(
            "BM25 ranking: %d/%d papers have no title or abstract (data quality issue from search connectors).",
            zero_abstract_count,
            total,
        )

    # Build query from research question + PICO fields + review keywords.
    pico = config.pico
    query_parts = [
        config.research_question,
        pico.population,
        pico.intervention,
        pico.comparison,
        pico.outcome,
    ] + (config.keywords or [])
    query_text = " ".join(p for p in query_parts if p)

    # Tokenize corpus and query.
    corpus_tokens = bm25s.tokenize(corpus, show_progress=False)
    query_tokens = bm25s.tokenize([query_text], show_progress=False)

    retriever = bm25s.BM25(corpus=corpus)
    retriever.index(corpus_tokens, show_progress=False)

    # Retrieve scores for all papers (k = total so every paper is ranked).
    results, scores = retriever.retrieve(query_tokens, corpus=corpus, k=total, sorted=True, show_progress=False)

    # results[0] and scores[0] are arrays of length `total` sorted descending.
    ranked_docs: list[str] = list(results[0])
    ranked_scores: list[float] = [float(s) for s in scores[0]]

    # Map ranked corpus strings back to CandidatePaper objects via paper index.
    corpus_to_idx: dict[str, int] = {}
    for idx, text in enumerate(corpus):
        corpus_to_idx.setdefault(text, idx)

    ranked_papers: list[CandidatePaper] = []
    ranked_paper_scores: list[float] = []
    seen_paper_ids: set[str] = set()

    for doc_text, score in zip(ranked_docs, ranked_scores):
        idx = corpus_to_idx.get(doc_text)
        if idx is None:
            continue
        paper = papers[idx]
        if paper.paper_id in seen_paper_ids:
            # Duplicate corpus text (two papers with identical title+abstract).
            # Find next unseen paper that matches this score bucket.
            for alt_idx, alt_text in enumerate(corpus):
                alt_paper = papers[alt_idx]
                if alt_text == doc_text and alt_paper.paper_id not in seen_paper_ids:
                    paper = alt_paper
                    break
        seen_paper_ids.add(paper.paper_id)
        ranked_papers.append(paper)
        ranked_paper_scores.append(score)

    # Any papers not yet in ranked list (edge case: identical texts exhausted) go last.
    for p in papers:
        if p.paper_id not in seen_paper_ids:
            ranked_papers.append(p)
            ranked_paper_scores.append(0.0)
            seen_paper_ids.add(p.paper_id)

    if cap is None or total <= cap:
        _log.info(
            "BM25 ranking: %d papers, cap=%s -> all forwarded to LLM screening.",
            total,
            cap,
        )
        return ranked_papers, []

    cutoff_score = ranked_paper_scores[cap - 1] if cap > 0 else 0.0
    top_papers = ranked_papers[:cap]
    tail_papers = ranked_papers[cap:]
    tail_scores = ranked_paper_scores[cap:]
    validation_tail_size = max(0, min(getattr(screening, "bm25_validation_tail_size", 0), len(tail_papers)))
    validation_tail = tail_papers[:validation_tail_size]
    validation_scores = tail_scores[:validation_tail_size]
    hard_excluded_tail = tail_papers[validation_tail_size:]
    hard_excluded_scores = tail_scores[validation_tail_size:]
    if validation_tail:
        top_papers = top_papers + validation_tail

    _log.info(
        "BM25 ranking: %d papers scored, top %d forwarded to LLM (+%d validation tail), %d auto-excluded (cutoff BM25 score=%.4f).",
        total,
        cap,
        len(validation_tail),
        len(hard_excluded_tail),
        cutoff_score,
    )
    if validation_tail:
        _log.info(
            "BM25 validation tail forwarded: %d papers, score range %.4f..%.4f.",
            len(validation_tail),
            min(validation_scores),
            max(validation_scores),
        )

    tail_decisions: list[ScreeningDecision] = []
    for rank_offset, (paper, score) in enumerate(zip(hard_excluded_tail, hard_excluded_scores)):
        rank = cap + validation_tail_size + rank_offset + 1
        tail_decisions.append(
            ScreeningDecision(
                paper_id=paper.paper_id,
                decision=ScreeningDecisionType.EXCLUDE,
                confidence=1.0,
                reason=(f"BM25 score below cap cutoff: score={score:.4f}, rank={rank}/{total} (cap={cap})."),
                exclusion_reason=ExclusionReason.LOW_RELEVANCE_SCORE,
                reviewer_type=ReviewerType.KEYWORD_FILTER,
            )
        )

    return top_papers, tail_decisions


def keyword_prefilter(
    papers: list[CandidatePaper],
    config: ReviewConfig,
    screening: ScreeningConfig,
) -> tuple[list[ScreeningDecision], list[CandidatePaper]]:
    """Score each paper against intervention keywords from the review config.

    Returns (auto_excluded_decisions, papers_needing_llm_review). Papers with
    fewer than screening.keyword_filter_min_matches keyword hits are
    auto-excluded (no LLM call). When min_matches == 0 the pre-filter is
    disabled and all papers are forwarded to LLM screening.
    """
    auto_excluded: list[ScreeningDecision] = []
    deterministic_pass: list[CandidatePaper] = []
    empty_abstract_rescue_remaining = max(getattr(screening, "empty_abstract_rescue_sample_size", 0), 0)
    empty_abstract_rescue_min = max(getattr(screening, "empty_abstract_rescue_keyword_min_matches", 2), 1)

    for paper in papers:
        deterministic = _deterministic_prefilter_decision(paper, screening)
        if deterministic is not None:
            if (
                deterministic.exclusion_reason == ExclusionReason.INSUFFICIENT_DATA
                and "empty abstract" in (deterministic.reason or "").lower()
                and empty_abstract_rescue_remaining > 0
                and _title_keyword_matches(paper, config) >= empty_abstract_rescue_min
            ):
                deterministic_pass.append(paper)
                empty_abstract_rescue_remaining -= 1
                continue
            auto_excluded.append(deterministic)
        else:
            deterministic_pass.append(paper)

    min_matches = screening.keyword_filter_min_matches
    if min_matches <= 0:
        return auto_excluded, deterministic_pass

    terms = [t.lower() for t in (config.keywords or []) + [config.pico.intervention]]
    if not terms:
        return auto_excluded, deterministic_pass

    for_llm: list[CandidatePaper] = []
    for paper in deterministic_pass:
        text = _paper_text(paper)
        matches = sum(1 for term in terms if term and term in text)
        if matches < min_matches:
            auto_excluded.append(
                ScreeningDecision(
                    paper_id=paper.paper_id,
                    decision=ScreeningDecisionType.EXCLUDE,
                    confidence=1.0,
                    reason=(
                        f"Keyword pre-filter: matched {matches}/{len(terms)} intervention terms in title/abstract."
                    ),
                    exclusion_reason=ExclusionReason.KEYWORD_FILTER,
                    reviewer_type=ReviewerType.KEYWORD_FILTER,
                )
            )
        else:
            for_llm.append(paper)

    return auto_excluded, for_llm
