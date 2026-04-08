from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.models import CandidatePaper
from src.search.citation_chasing import CitationChaser


def _paper(paper_id: str, doi: str | None) -> CandidatePaper:
    return CandidatePaper(
        paper_id=paper_id,
        title=f"Paper {paper_id}",
        authors=["Author A"],
        year=2024,
        source_database="openalex",
        doi=doi,
    )


@pytest.mark.asyncio
async def test_chase_citations_deduplicates_cross_source_results() -> None:
    chaser = CitationChaser(workflow_id="wf-cite", max_per_paper=5)
    source_paper = _paper("seed", "10.1000/seed")
    duplicate = _paper("dup", "10.1000/dup")
    unique = _paper("uniq", "10.1000/uniq")

    with (
        patch.object(chaser, "_chase_semantic_scholar", new=AsyncMock(return_value=[duplicate])),
        patch.object(chaser, "_chase_openalex", new=AsyncMock(return_value=[duplicate, unique])),
    ):
        results = await chaser.chase_citations([source_paper], known_doi_set=set(), concurrency=1)

    assert [p.doi for p in results] == ["10.1000/dup", "10.1000/uniq"]


@pytest.mark.asyncio
async def test_chase_citations_to_search_results_wraps_output() -> None:
    chaser = CitationChaser(workflow_id="wf-cite", max_per_paper=5)
    chased = [_paper("chased-1", "10.1000/chased-1")]

    with patch.object(chaser, "chase_citations", new=AsyncMock(return_value=chased)):
        results = await chaser.chase_citations_to_search_results([_paper("seed", "10.1000/seed")], known_doi_set=set())

    assert len(results) == 1
    assert results[0].database_name == "citation_chasing"
    assert results[0].records_retrieved == 1
    assert results[0].papers[0].paper_id == "chased-1"
