from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

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


def _session_capturing(calls: list[tuple[str, dict[str, str] | None]], payload: dict[str, object]) -> MagicMock:
    """ClientSession stand-in that records get() URL and params."""

    @asynccontextmanager
    async def _get(url: str, params: dict[str, str] | None = None, **_kwargs: object):
        calls.append((url, params))
        response = MagicMock()
        response.status = 200
        response.json = AsyncMock(return_value=payload)
        yield response

    session = MagicMock()
    session.get = _get

    @asynccontextmanager
    async def _enter(*_args: object, **_kwargs: object):
        yield session

    factory = MagicMock(side_effect=_enter)
    return factory


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "seed_doi",
    [
        "10.1000/seed",
        "https://doi.org/10.1000/seed",
        "http://dx.doi.org/10.1000/seed",
        "DOI:10.1000/seed",
    ],
)
async def test_chase_openalex_does_not_double_prefix_doi_urls(seed_doi: str) -> None:
    """OpenAlex stores DOIs as resolver URLs. The cites filter must stay a single URL."""
    chaser = CitationChaser(workflow_id="wf-cite", max_per_paper=5)
    calls: list[tuple[str, dict[str, str] | None]] = []
    session = _session_capturing(calls, {"results": []})

    with patch("src.search.citation_chasing.aiohttp.ClientSession", session):
        await chaser._chase_openalex(_paper("seed", seed_doi), set())

    assert calls
    assert calls[0][1] is not None
    assert calls[0][1]["filter"] == "cites:https://doi.org/10.1000/seed"


@pytest.mark.asyncio
async def test_chase_semantic_scholar_uses_bare_doi() -> None:
    """A resolver URL is not a Semantic Scholar DOI identifier."""
    chaser = CitationChaser(workflow_id="wf-cite", max_per_paper=5)
    calls: list[tuple[str, dict[str, str] | None]] = []
    session = _session_capturing(calls, {"data": []})

    with patch("src.search.citation_chasing.aiohttp.ClientSession", session):
        await chaser._chase_semantic_scholar(_paper("seed", "https://doi.org/10.1000/seed"), set())

    assert calls
    assert "doi.org" not in calls[0][0]
    assert "DOI:10.1000/seed" in calls[0][0]


@pytest.mark.asyncio
async def test_chase_citations_drops_known_doi_when_forms_differ() -> None:
    chaser = CitationChaser(workflow_id="wf-cite", max_per_paper=5)
    already_known = _paper("dup", "10.1000/dup")

    with (
        patch.object(chaser, "_chase_semantic_scholar", new=AsyncMock(return_value=[already_known])),
        patch.object(chaser, "_chase_openalex", new=AsyncMock(return_value=[])),
    ):
        results = await chaser.chase_citations(
            [_paper("seed", "https://doi.org/10.1000/seed")],
            known_doi_set={"https://doi.org/10.1000/dup"},
            concurrency=1,
        )

    assert results == []
