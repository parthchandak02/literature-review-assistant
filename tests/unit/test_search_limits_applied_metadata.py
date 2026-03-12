from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.search.crossref import CrossrefConnector
from src.search.openalex import OpenAlexConnector


@pytest.mark.asyncio
async def test_openalex_limits_applied_marks_screening_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENALEX_API_KEY", "fake-openalex-key")
    connector = OpenAlexConnector("wf-openalex")

    payload = {"results": [], "meta": {"next_cursor": None}}

    @asynccontextmanager
    async def _fake_get(url, params, timeout):
        _ = (url, params, timeout)
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=payload)
        yield mock_resp

    mock_session = MagicMock()
    mock_session.get = _fake_get

    with (
        patch("src.search.openalex.aiohttp.ClientSession") as mock_cls,
        patch("src.search.openalex.tcp_connector_with_certifi", return_value=MagicMock()),
    ):
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await connector.search(query="test query", max_results=10)

    assert result.limits_applied is not None
    assert "primary_study_filter=screening_only" in result.limits_applied


@pytest.mark.asyncio
async def test_crossref_limits_applied_marks_screening_only() -> None:
    connector = CrossrefConnector("wf-crossref")

    payload = {"message": {"items": []}}

    @asynccontextmanager
    async def _fake_get(url, params, timeout):
        _ = (url, params, timeout)
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=payload)
        yield mock_resp

    mock_session = MagicMock()
    mock_session.get = _fake_get

    with (
        patch("src.search.crossref.aiohttp.ClientSession") as mock_cls,
        patch("src.search.crossref.tcp_connector_with_certifi", return_value=MagicMock()),
    ):
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await connector.search(query="test query", max_results=10)

    assert result.limits_applied is not None
    assert "primary_study_filter=screening_only" in result.limits_applied
