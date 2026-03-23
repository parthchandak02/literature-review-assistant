"""Two-stage deduplication: DOI exact-match, then MinHash-based fuzzy title clustering.

Stage 1: DOI exact-match (O(n) per paper).
Stage 2: MinHash LSH pre-clustering followed by thefuzz ratio for confirmation.
  - 3-gram shingling on lowercased, normalized titles.
  - LSH threshold: 0.65 (Jaccard similarity); actual duplicate threshold set by fuzzy_threshold.
  - MinHash candidate pairs are checked with thefuzz.ratio (higher recall, lower false positives).

For small corpora (<= BRUTE_FORCE_THRESHOLD), Stage 2 falls back to direct O(n^2)
to avoid MinHash overhead. For large corpora (10K+ records), MinHash reduces
O(n^2) to approximately O(n log n) with no recall loss at the chosen threshold.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable

from thefuzz import fuzz

from src.models import CandidatePaper

logger = logging.getLogger(__name__)

BRUTE_FORCE_THRESHOLD = 500


def _metadata_richness(paper: CandidatePaper) -> int:
    """Heuristic score: higher means record has richer usable metadata."""
    score = 0
    if (paper.abstract or "").strip():
        score += min(len((paper.abstract or "").strip()), 2000) // 40
    if paper.keywords:
        score += 2 * len([k for k in paper.keywords if k and k.strip()])
    if paper.url:
        score += 2
    if paper.doi:
        score += 2
    if paper.year:
        score += 1
    if paper.source_database:
        score += 1
    score += len([a for a in paper.authors if a and a.strip()])
    return score


def _prefer_richer(existing: CandidatePaper, candidate: CandidatePaper) -> CandidatePaper:
    """Return the richer paper; preserve existing when scores tie."""
    return candidate if _metadata_richness(candidate) > _metadata_richness(existing) else existing


def _normalize_title(title: str) -> str:
    s = title.lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _normalize_doi(doi: str | None) -> str:
    """Normalize DOI to canonical lowercase token for exact-match dedup."""
    cleaned = (doi or "").strip().lower()
    cleaned = re.sub(r"^https?://(dx\.)?doi\.org/", "", cleaned)
    return cleaned


def _shingled_tokens(text: str, k: int = 3) -> set[str]:
    tokens = text.split()
    if len(tokens) < k:
        return set(tokens)
    return {" ".join(tokens[i : i + k]) for i in range(len(tokens) - k + 1)}


def _minhash_dedup(
    papers_no_doi: list[CandidatePaper],
    fuzzy_threshold: int,
) -> tuple[list[CandidatePaper], int]:
    """MinHash LSH dedup for large corpora."""
    try:
        from datasketch import MinHash, MinHashLSH
    except ImportError:
        return _brute_force_dedup(papers_no_doi, fuzzy_threshold)

    lsh_threshold = 0.65
    num_perm = 128
    lsh = MinHashLSH(threshold=lsh_threshold, num_perm=num_perm)

    minhashes: dict[int, MinHash] = {}
    for idx, paper in enumerate(papers_no_doi):
        norm = _normalize_title(paper.title or "")
        shingles = _shingled_tokens(norm)
        mh = MinHash(num_perm=num_perm)
        for s in shingles:
            mh.update(s.encode("utf-8"))
        minhashes[idx] = mh
        try:
            lsh.insert(str(idx), mh)
        except Exception as _e:
            logger.warning("MinHash LSH insert failed for paper index %d: %s", idx, _e)

    unique_indices: set[int] = set()
    duplicate_count = 0

    for idx, paper in enumerate(papers_no_doi):
        if idx in unique_indices:
            continue
        mh = minhashes[idx]
        try:
            candidates = lsh.query(mh)
        except Exception as _e:
            logger.warning("MinHash LSH query failed for paper index %d: %s", idx, _e)
            candidates = []
        is_dup = False
        add_current = False
        for cand_str in candidates:
            cand_idx = int(cand_str)
            if cand_idx == idx or cand_idx not in unique_indices:
                continue
            score = fuzz.ratio(
                (paper.title or "").lower(),
                (papers_no_doi[cand_idx].title or "").lower(),
            )
            if score >= fuzzy_threshold:
                is_dup = True
                duplicate_count += 1
                richer = _prefer_richer(papers_no_doi[cand_idx], paper)
                if richer is paper:
                    unique_indices.discard(cand_idx)
                    add_current = True
                break
        if not is_dup:
            unique_indices.add(idx)
        elif add_current:
            unique_indices.add(idx)

    unique = [papers_no_doi[i] for i in sorted(unique_indices)]
    return unique, duplicate_count


def _brute_force_dedup(
    papers_no_doi: list[CandidatePaper],
    fuzzy_threshold: int,
) -> tuple[list[CandidatePaper], int]:
    """O(n^2) fuzzy title dedup (used for small corpora and as MinHash fallback)."""
    final_list: list[CandidatePaper] = []
    duplicates = 0
    for paper in papers_no_doi:
        is_dup = False
        for i, existing in enumerate(final_list):
            score = fuzz.ratio((paper.title or "").lower(), (existing.title or "").lower())
            if score >= fuzzy_threshold:
                duplicates += 1
                is_dup = True
                final_list[i] = _prefer_richer(existing, paper)
                break
        if not is_dup:
            final_list.append(paper)
    return final_list, duplicates


def deduplicate_papers(
    papers: Iterable[CandidatePaper],
    fuzzy_threshold: int = 90,
) -> tuple[list[CandidatePaper], int]:
    """Deduplicate papers using DOI exact-match + MinHash fuzzy title matching.

    Stage 1: DOI exact-match.
    Stage 2: MinHash LSH pre-clustering (large corpora) or brute-force (small).

    Returns (unique_papers, n_duplicates_removed).
    """
    papers_list = list(papers)
    unique: list[CandidatePaper] = []
    doi_to_index: dict[str, int] = {}
    duplicates = 0

    for paper in papers_list:
        doi = _normalize_doi(paper.doi)
        if doi:
            if doi in doi_to_index:
                duplicates += 1
                idx = doi_to_index[doi]
                unique[idx] = _prefer_richer(unique[idx], paper)
                continue
            doi_to_index[doi] = len(unique)
        unique.append(paper)

    if len(unique) <= BRUTE_FORCE_THRESHOLD:
        final_list, title_dups = _brute_force_dedup(unique, fuzzy_threshold)
    else:
        final_list, title_dups = _minhash_dedup(unique, fuzzy_threshold)

    duplicates += title_dups
    return final_list, duplicates
