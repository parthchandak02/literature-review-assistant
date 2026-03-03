"""Unit tests for the Scopus search connector (offline -- mocks aiohttp)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.search.scopus import ScopusConnector

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(
    title: str = "Test Paper",
    doi: str = "10.1234/test",
    cover_date: str = "2023-06-15",
    cover_display_date: str = "",
    creator: str = "Smith J.",
    authors: list[dict] | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "dc:title": title,
        "prism:doi": doi,
        "prism:coverDate": cover_date,
        "prism:coverDisplayDate": cover_display_date,
        "dc:creator": creator,
        "prism:publicationName": "Journal of Testing",
        "dc:description": "An abstract.",
        "prism:url": "https://api.elsevier.com/content/article/doi/10.1234/test",
    }
    if authors is not None:
        entry["author"] = authors
    return entry


def _make_payload(entries: list[dict], total: int = 0) -> dict:
    return {
        "search-results": {
            "opensearch:totalResults": str(total or len(entries)),
            "entry": entries,
        }
    }


@asynccontextmanager
async def _mock_session(responses: list[dict], statuses: list[int] | None = None):
    """Context manager yielding a mock aiohttp.ClientSession that returns
    pre-built JSON payloads in order. Statuses defaults to all 200."""
    if statuses is None:
        statuses = [200] * len(responses)

    call_index = 0

    @asynccontextmanager
    async def _get(*args, **kwargs):
        nonlocal call_index
        idx = min(call_index, len(responses) - 1)
        status = statuses[idx]
        payload = responses[idx]
        call_index += 1

        mock_resp = MagicMock()
        mock_resp.status = status
        mock_resp.json = AsyncMock(return_value=payload)
        mock_resp.text = AsyncMock(return_value=str(payload))
        yield mock_resp

    session = MagicMock()
    session.get = _get
    yield session


# ---------------------------------------------------------------------------
# Test 1: Missing SCOPUS_API_KEY raises ValueError at init
# ---------------------------------------------------------------------------

def test_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCOPUS_API_KEY", raising=False)
    with pytest.raises(ValueError, match="SCOPUS_API_KEY"):
        ScopusConnector("wf-test")


# ---------------------------------------------------------------------------
# Test 2: Date range embeds PUBYEAR in the query string
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_date_range_injected_into_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCOPUS_API_KEY", "fake-key")
    connector = ScopusConnector("wf-test")

    captured_params: list[dict] = []

    @asynccontextmanager
    async def _fake_get(url, params, timeout):
        captured_params.append(dict(params))
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=_make_payload([], total=0))
        yield mock_resp

    mock_session = MagicMock()
    mock_session.get = _fake_get

    with (
        patch("src.search.scopus.aiohttp.ClientSession") as mock_cls,
        patch("src.search.scopus.tcp_connector_with_certifi", return_value=MagicMock()),
        patch("src.search.scopus.asyncio.sleep", new_callable=AsyncMock),
    ):
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await connector.search(
            query="TITLE-ABS-KEY(robotic dispensing)",
            max_results=10,
            date_start=2015,
            date_end=2024,
        )

    assert len(captured_params) >= 1
    q = captured_params[0]["query"]
    assert "PUBYEAR > 2014" in q
    assert "PUBYEAR < 2025" in q


# ---------------------------------------------------------------------------
# Test 3: PUBYEAR not injected when query already contains PUBYEAR
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pubyear_not_duplicated_if_already_in_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCOPUS_API_KEY", "fake-key")
    connector = ScopusConnector("wf-test")

    captured_params: list[dict] = []

    @asynccontextmanager
    async def _fake_get(url, params, timeout):
        captured_params.append(dict(params))
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=_make_payload([], total=0))
        yield mock_resp

    mock_session = MagicMock()
    mock_session.get = _fake_get

    with (
        patch("src.search.scopus.aiohttp.ClientSession") as mock_cls,
        patch("src.search.scopus.tcp_connector_with_certifi", return_value=MagicMock()),
        patch("src.search.scopus.asyncio.sleep", new_callable=AsyncMock),
    ):
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        await connector.search(
            query="TITLE-ABS-KEY(robotic) AND PUBYEAR > 2014",
            date_start=2015,
            date_end=2024,
        )

    q = captured_params[0]["query"]
    # Must appear exactly once
    assert q.count("PUBYEAR") == 1


# ---------------------------------------------------------------------------
# Test 4: Pagination stops when max_results is reached before totalResults
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pagination_stops_at_max_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCOPUS_API_KEY", "fake-key")
    connector = ScopusConnector("wf-test")

    page_calls = 0

    @asynccontextmanager
    async def _fake_get(url, params, timeout):
        nonlocal page_calls
        page_calls += 1
        # Each page returns 5 entries; total reported = 100
        entries = [_make_entry(title=f"Paper {page_calls}-{i}") for i in range(5)]
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=_make_payload(entries, total=100))
        yield mock_resp

    mock_session = MagicMock()
    mock_session.get = _fake_get

    with (
        patch("src.search.scopus.aiohttp.ClientSession") as mock_cls,
        patch("src.search.scopus.tcp_connector_with_certifi", return_value=MagicMock()),
        patch("src.search.scopus.asyncio.sleep", new_callable=AsyncMock),
    ):
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await connector.search(query="test", max_results=12)

    # 5 per page -> page 1 = 5 papers, page 2 = 10, page 3 = 15 > 12 -> stops after 3 pages
    assert result.records_retrieved <= 12 + 5  # allow one overshoot page
    assert result.records_retrieved >= 10      # must have fetched at least 2 pages


# ---------------------------------------------------------------------------
# Test 5: HTTP 429 triggers asyncio.sleep and retries
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_429_triggers_sleep_and_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCOPUS_API_KEY", "fake-key")
    connector = ScopusConnector("wf-test")

    call_count = 0
    sleep_calls: list[float] = []

    @asynccontextmanager
    async def _fake_get(url, params, timeout):
        nonlocal call_count
        call_count += 1
        mock_resp = MagicMock()
        if call_count == 1:
            # First request: rate limited
            mock_resp.status = 429
            mock_resp.text = AsyncMock(return_value="Too Many Requests")
        else:
            # Second request: success with empty results to terminate loop
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=_make_payload([], total=0))
        yield mock_resp

    async def _fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    mock_session = MagicMock()
    mock_session.get = _fake_get

    with (
        patch("src.search.scopus.aiohttp.ClientSession") as mock_cls,
        patch("src.search.scopus.tcp_connector_with_certifi", return_value=MagicMock()),
        patch("src.search.scopus.asyncio.sleep", side_effect=_fake_sleep),
    ):
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await connector.search(query="test", max_results=10)

    # The 429 handler must have slept for >= 2 seconds before retrying
    rate_limit_sleeps = [s for s in sleep_calls if s >= 2.0]
    assert rate_limit_sleeps, "Expected a >= 2.0s sleep after 429 response"
    assert call_count >= 2, "Expected a retry after the 429"


# ---------------------------------------------------------------------------
# Test 6: Malformed entry (missing dc:title) is skipped, not raised
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_malformed_entry_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCOPUS_API_KEY", "fake-key")
    connector = ScopusConnector("wf-test")

    good_entry = _make_entry(title="Good Paper", doi="10.1111/good")
    # Entry with None title -- should default to "Untitled", not crash
    bad_entry: dict[str, Any] = {"dc:title": None, "prism:doi": "10.9999/bad"}

    payload = _make_payload([bad_entry, good_entry], total=2)

    @asynccontextmanager
    async def _fake_get(url, params, timeout):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=payload)
        yield mock_resp

    # Second call returns empty to stop pagination
    call_count = 0

    @asynccontextmanager
    async def _fake_get_seq(url, params, timeout):
        nonlocal call_count
        call_count += 1
        mock_resp = MagicMock()
        mock_resp.status = 200
        if call_count == 1:
            mock_resp.json = AsyncMock(return_value=payload)
        else:
            mock_resp.json = AsyncMock(return_value=_make_payload([], total=2))
        yield mock_resp

    mock_session = MagicMock()
    mock_session.get = _fake_get_seq

    with (
        patch("src.search.scopus.aiohttp.ClientSession") as mock_cls,
        patch("src.search.scopus.tcp_connector_with_certifi", return_value=MagicMock()),
        patch("src.search.scopus.asyncio.sleep", new_callable=AsyncMock),
    ):
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await connector.search(query="test", max_results=10)

    # Both entries processed: bad_entry produces "Untitled", good produces "Good Paper"
    assert result.records_retrieved >= 1
    titles = [p.title for p in result.papers]
    assert "Good Paper" in titles


# ---------------------------------------------------------------------------
# Test 7: _parse_year handles coverDate and falls back to coverDisplayDate
# ---------------------------------------------------------------------------

def test_parse_year_from_cover_date() -> None:
    entry = {"prism:coverDate": "2024-03-15"}
    assert ScopusConnector._parse_year(entry) == 2024


def test_parse_year_fallback_to_display_date() -> None:
    entry = {"prism:coverDate": "", "prism:coverDisplayDate": "March 2022"}
    assert ScopusConnector._parse_year(entry) == 2022


def test_parse_year_returns_none_when_no_dates() -> None:
    entry: dict[str, Any] = {}
    assert ScopusConnector._parse_year(entry) is None


# ---------------------------------------------------------------------------
# Test 8: _parse_authors handles list, dict, and dc:creator fallback
# ---------------------------------------------------------------------------

def test_parse_authors_from_list() -> None:
    entry = {"author": [{"authname": "Smith J."}, {"authname": "Doe A."}]}
    authors = ScopusConnector._parse_authors(entry)
    assert authors == ["Smith J.", "Doe A."]


def test_parse_authors_single_dict() -> None:
    entry = {"author": {"authname": "Jones K."}}
    authors = ScopusConnector._parse_authors(entry)
    assert "Jones K." in authors


def test_parse_authors_fallback_to_creator() -> None:
    entry = {"author": [], "dc:creator": "Brown L."}
    authors = ScopusConnector._parse_authors(entry)
    assert "Brown L." in authors


def test_parse_authors_empty_returns_unknown() -> None:
    entry: dict[str, Any] = {}
    authors = ScopusConnector._parse_authors(entry)
    assert authors == ["Unknown"]


# ---------------------------------------------------------------------------
# Test 9: Empty result set {"error": ...} terminates loop cleanly
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_result_set_terminates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCOPUS_API_KEY", "fake-key")
    connector = ScopusConnector("wf-test")

    error_payload = {
        "search-results": {
            "opensearch:totalResults": "0",
            "entry": [{"error": "Result set was empty"}],
        }
    }

    @asynccontextmanager
    async def _fake_get(url, params, timeout):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=error_payload)
        yield mock_resp

    mock_session = MagicMock()
    mock_session.get = _fake_get

    with (
        patch("src.search.scopus.aiohttp.ClientSession") as mock_cls,
        patch("src.search.scopus.tcp_connector_with_certifi", return_value=MagicMock()),
        patch("src.search.scopus.asyncio.sleep", new_callable=AsyncMock),
    ):
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await connector.search(query="test", max_results=100)

    assert result.records_retrieved == 0
    assert result.papers == []
