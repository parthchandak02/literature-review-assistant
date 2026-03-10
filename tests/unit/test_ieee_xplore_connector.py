"""Unit tests for the IEEE Xplore search connector (offline -- mocks aiohttp)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.search.ieee_xplore import IEEEXploreConnector

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_article(
    title: str = "Study on Intervention Effectiveness",
    doi: str = "10.1109/test.2023.001",
    year: int | str = 2023,
    html_url: str = "https://ieeexplore.ieee.org/document/12345",
    abstract: str = "An abstract about intervention outcomes.",
    authors: list[str] | None = None,
) -> dict[str, Any]:
    author_list = [{"full_name": name} for name in (authors or ["Smith, J.", "Jones, A."])]
    return {
        "title": title,
        "doi": doi,
        "publication_year": year,
        "html_url": html_url,
        "abstract": abstract,
        "authors": {"authors": author_list},
    }


def _make_payload(articles: list[dict[str, Any]], total: int = 0) -> dict[str, Any]:
    return {
        "total_records": total or len(articles),
        "articles": articles,
    }


@asynccontextmanager
async def _mock_session(payload: dict[str, Any], status: int = 200):
    """Yield a mock aiohttp.ClientSession returning a single response."""

    @asynccontextmanager
    async def _get(*args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status = status
        mock_resp.json = AsyncMock(return_value=payload)
        yield mock_resp

    session = MagicMock()
    session.get = _get
    yield session


# ---------------------------------------------------------------------------
# Test 1: Missing IEEE_API_KEY returns empty SearchResult (no exception)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_api_key_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IEEE_API_KEY", raising=False)
    connector = IEEEXploreConnector("wf-test")
    result = await connector.search("intervention effectiveness", max_results=10)

    assert result.records_retrieved == 0
    assert result.papers == []
    assert result.limits_applied == "missing_api_key"
    assert result.database_name == "ieee_xplore"


# ---------------------------------------------------------------------------
# Test 2: Successful search returns CandidatePaper list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_successful_search_returns_papers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IEEE_API_KEY", "fake-ieee-key")
    connector = IEEEXploreConnector("wf-test")

    articles = [
        _make_article(title="Paper A", doi="10.1109/a.2023.001", year=2023),
        _make_article(title="Paper B", doi="10.1109/b.2022.002", year=2022),
    ]
    payload = _make_payload(articles)

    with (
        patch("src.search.ieee_xplore.aiohttp.ClientSession") as mock_cls,
        patch("src.search.ieee_xplore.tcp_connector_with_certifi", return_value=MagicMock()),
    ):
        async with _mock_session(payload) as mock_session:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await connector.search("intervention study outcome", max_results=10)

    assert result.records_retrieved == 2
    assert len(result.papers) == 2
    titles = {p.title for p in result.papers}
    assert "Paper A" in titles
    assert "Paper B" in titles


# ---------------------------------------------------------------------------
# Test 3: Author parsing -- full_name extracted correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_author_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IEEE_API_KEY", "fake-ieee-key")
    connector = IEEEXploreConnector("wf-test")

    article = _make_article(
        authors=["Doe, Jane", "Smith, John", "Kumar, R."],
    )
    payload = _make_payload([article])

    with (
        patch("src.search.ieee_xplore.aiohttp.ClientSession") as mock_cls,
        patch("src.search.ieee_xplore.tcp_connector_with_certifi", return_value=MagicMock()),
    ):
        async with _mock_session(payload) as mock_session:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await connector.search("systematic review outcomes", max_results=5)

    assert len(result.papers) == 1
    paper = result.papers[0]
    assert "Doe, Jane" in paper.authors
    assert "Smith, John" in paper.authors
    assert "Kumar, R." in paper.authors


# ---------------------------------------------------------------------------
# Test 4: Year as string (common in API responses) is parsed to int
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_year_as_string_is_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IEEE_API_KEY", "fake-ieee-key")
    connector = IEEEXploreConnector("wf-test")

    article = _make_article(year="2021")
    payload = _make_payload([article])

    with (
        patch("src.search.ieee_xplore.aiohttp.ClientSession") as mock_cls,
        patch("src.search.ieee_xplore.tcp_connector_with_certifi", return_value=MagicMock()),
    ):
        async with _mock_session(payload) as mock_session:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await connector.search("study design", max_results=5)

    assert result.papers[0].year == 2021


# ---------------------------------------------------------------------------
# Test 5: Non-200 HTTP response raises RuntimeError (visible in Activity log as SEARCH FAIL)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_200_response_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IEEE_API_KEY", "fake-ieee-key")
    connector = IEEEXploreConnector("wf-test")

    @asynccontextmanager
    async def _mock_session_with_text(payload: dict, status: int = 403):
        @asynccontextmanager
        async def _get(*args, **kwargs):
            mock_resp = MagicMock()
            mock_resp.status = status
            mock_resp.json = AsyncMock(return_value=payload)
            mock_resp.text = AsyncMock(return_value='{"error": "Forbidden"}')
            yield mock_resp

        session = MagicMock()
        session.get = _get
        yield session

    with (
        patch("src.search.ieee_xplore.aiohttp.ClientSession") as mock_cls,
        patch("src.search.ieee_xplore.tcp_connector_with_certifi", return_value=MagicMock()),
    ):
        async with _mock_session_with_text({}, status=403) as mock_session:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(RuntimeError, match="HTTP 403"):
                await connector.search("population intervention outcome", max_results=5)


# ---------------------------------------------------------------------------
# Test 6: Date range params are forwarded to the API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_date_range_sent_as_params(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IEEE_API_KEY", "fake-ieee-key")
    connector = IEEEXploreConnector("wf-test")

    captured_params: list[dict] = []

    @asynccontextmanager
    async def _capturing_get(url, params, timeout):
        captured_params.append(dict(params))
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=_make_payload([]))
        yield mock_resp

    mock_session = MagicMock()
    mock_session.get = _capturing_get

    with (
        patch("src.search.ieee_xplore.aiohttp.ClientSession") as mock_cls,
        patch("src.search.ieee_xplore.tcp_connector_with_certifi", return_value=MagicMock()),
    ):
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        await connector.search("intervention population", max_results=20, date_start=2015, date_end=2024)

    assert captured_params, "Expected at least one API call"
    params = captured_params[0]
    assert params.get("start_year") == "2015"
    assert params.get("end_year") == "2024"
    assert params.get("apikey") == "fake-ieee-key"
    assert params.get("max_records") == "20"


# ---------------------------------------------------------------------------
# Test 7: SearchResult metadata is populated correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_result_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IEEE_API_KEY", "fake-ieee-key")
    connector = IEEEXploreConnector("wf-999")

    payload = _make_payload([_make_article()])

    with (
        patch("src.search.ieee_xplore.aiohttp.ClientSession") as mock_cls,
        patch("src.search.ieee_xplore.tcp_connector_with_certifi", return_value=MagicMock()),
    ):
        async with _mock_session(payload) as mock_session:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await connector.search("evidence synthesis", max_results=25)

    assert result.workflow_id == "wf-999"
    assert result.database_name == "ieee_xplore"
    assert result.search_query == "evidence synthesis"
    assert "max_results=25" in result.limits_applied
    from src.models import SourceCategory

    assert result.source_category == SourceCategory.DATABASE


# ---------------------------------------------------------------------------
# Test 8: Article missing doi and pdf_url falls back gracefully
# ---------------------------------------------------------------------------


def test_to_candidate_missing_doi_and_url() -> None:
    article: dict[str, Any] = {
        "title": "No DOI Article",
        "publication_year": 2020,
        "authors": {"authors": [{"full_name": "Author A"}]},
        "abstract": "Abstract text",
    }
    paper = IEEEXploreConnector._to_candidate(article)
    assert paper.title == "No DOI Article"
    assert paper.doi is None
    assert paper.url is None
    assert paper.year == 2020


# ---------------------------------------------------------------------------
# Test 9: Empty authors block falls back to ["Unknown"]
# ---------------------------------------------------------------------------


def test_to_candidate_empty_authors() -> None:
    article: dict[str, Any] = {
        "title": "No Authors",
        "publication_year": 2019,
        "authors": {},
    }
    paper = IEEEXploreConnector._to_candidate(article)
    assert paper.authors == ["Unknown"]
