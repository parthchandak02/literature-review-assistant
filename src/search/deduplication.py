"""Two-stage deduplication: DOI exact then fuzzy title."""

from __future__ import annotations

from typing import Iterable

from thefuzz import fuzz

from src.models import CandidatePaper


def deduplicate_papers(papers: Iterable[CandidatePaper], fuzzy_threshold: int = 90) -> tuple[list[CandidatePaper], int]:
    unique: list[CandidatePaper] = []
    seen_doi: set[str] = set()
    duplicates = 0

    for paper in papers:
        doi = (paper.doi or "").strip().lower()
        if doi:
            if doi in seen_doi:
                duplicates += 1
                continue
            seen_doi.add(doi)
        unique.append(paper)

    final_list: list[CandidatePaper] = []
    for paper in unique:
        is_dup = False
        for existing in final_list:
            score = fuzz.ratio((paper.title or "").lower(), (existing.title or "").lower())
            if score >= fuzzy_threshold:
                duplicates += 1
                is_dup = True
                break
        if not is_dup:
            final_list.append(paper)

    return final_list, duplicates
