"""Unit tests for the ClinicalTrials.gov search connector (offline -- mocks aiohttp)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.search.clinicaltrials import ClinicalTrialsConnector

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_study(
    nct_id: str = "NCT04567890",
    brief_title: str = "Intervention Effectiveness Trial",
    official_title: str | None = None,
    brief_summary: str = "A study evaluating intervention outcomes in adults.",
    start_date: str = "2021-03-01",
    sponsor: str = "University Hospital",
) -> dict[str, Any]:
    """Build a minimal ClinicalTrials.gov v2 study JSON object."""
    return {
        "protocolSection": {
            "identificationModule": {
                "nctId": nct_id,
                "briefTitle": brief_title,
                **({"officialTitle": official_title} if official_title else {}),
            },
            "descriptionModule": {
                "briefSummary": brief_summary,
            },
            "statusModule": {
                "startDateStruct": {"date": start_date},
            },
            "sponsorCollaboratorsModule": {
                "leadSponsor": {"name": sponsor},
            },
            "contactsLocationsModule": {},
        }
    }


def _make_response(studies: list[dict[str, Any]], total: int = 0) -> dict[str, Any]:
    return {
        "totalCount": total or len(studies),
        "studies": studies,
    }


@asynccontextmanager
async def _mock_session(payload: dict[str, Any], status: int = 200):
    """Yield a mock aiohttp.ClientSession returning a single JSON response."""

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
# Test 1: No API key required -- connector initialises without env vars
# ---------------------------------------------------------------------------


def test_no_api_key_required() -> None:
    """ClinicalTrials.gov connector needs no API key; must not raise."""
    connector = ClinicalTrialsConnector("wf-test")
    assert connector.name == "clinicaltrials_gov"


# ---------------------------------------------------------------------------
# Test 2: Successful search returns a list with one SearchResult
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_successful_search_returns_results() -> None:
    connector = ClinicalTrialsConnector("wf-test")

    studies = [
        _make_study(nct_id="NCT00000001", brief_title="Study A"),
        _make_study(nct_id="NCT00000002", brief_title="Study B"),
    ]
    payload = _make_response(studies)

    with (
        patch("src.search.clinicaltrials.aiohttp.ClientSession") as mock_cls,
        patch("src.search.clinicaltrials.tcp_connector_with_certifi", return_value=MagicMock()),
    ):
        async with _mock_session(payload) as mock_session:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await connector.search("intervention population adults", max_results=25)

    assert isinstance(results, list)
    assert len(results) == 1
    result = results[0]
    assert result.records_retrieved == 2
    assert len(result.papers) == 2
    titles = {p.title for p in result.papers}
    assert "Study A" in titles
    assert "Study B" in titles


# ---------------------------------------------------------------------------
# Test 3: Empty result set returns empty list (not a list with an empty result)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_studies_returns_empty_list() -> None:
    connector = ClinicalTrialsConnector("wf-test")

    payload = _make_response([])

    with (
        patch("src.search.clinicaltrials.aiohttp.ClientSession") as mock_cls,
        patch("src.search.clinicaltrials.tcp_connector_with_certifi", return_value=MagicMock()),
    ):
        async with _mock_session(payload) as mock_session:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await connector.search("nonexistent condition xyz", max_results=10)

    assert results == []


# ---------------------------------------------------------------------------
# Test 4: Non-200 HTTP response returns empty list (no exception)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_200_returns_empty_list() -> None:
    connector = ClinicalTrialsConnector("wf-test")

    with (
        patch("src.search.clinicaltrials.aiohttp.ClientSession") as mock_cls,
        patch("src.search.clinicaltrials.tcp_connector_with_certifi", return_value=MagicMock()),
    ):
        async with _mock_session({}, status=500) as mock_session:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await connector.search("intervention effectiveness", max_results=10)

    assert results == []


# ---------------------------------------------------------------------------
# Test 5: Network error returns empty list (no exception propagated)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_network_error_returns_empty_list() -> None:
    connector = ClinicalTrialsConnector("wf-test")

    with (
        patch("src.search.clinicaltrials.aiohttp.ClientSession") as mock_cls,
        patch("src.search.clinicaltrials.tcp_connector_with_certifi", return_value=MagicMock()),
    ):
        mock_cls.return_value.__aenter__ = AsyncMock(side_effect=Exception("Connection refused"))
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        results = await connector.search("intervention effectiveness", max_results=10)

    assert results == []


# ---------------------------------------------------------------------------
# Test 6: Year is parsed from start_date correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_year_parsed_from_start_date() -> None:
    connector = ClinicalTrialsConnector("wf-test")

    study = _make_study(start_date="2019-08-15")
    payload = _make_response([study])

    with (
        patch("src.search.clinicaltrials.aiohttp.ClientSession") as mock_cls,
        patch("src.search.clinicaltrials.tcp_connector_with_certifi", return_value=MagicMock()),
    ):
        async with _mock_session(payload) as mock_session:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await connector.search("study outcomes", max_results=5)

    assert results[0].papers[0].year == 2019


# ---------------------------------------------------------------------------
# Test 7: source_category is OTHER_SOURCE (grey literature, not DATABASE)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_source_category_is_other_source() -> None:
    from src.models import SourceCategory

    connector = ClinicalTrialsConnector("wf-test")

    study = _make_study()
    payload = _make_response([study])

    with (
        patch("src.search.clinicaltrials.aiohttp.ClientSession") as mock_cls,
        patch("src.search.clinicaltrials.tcp_connector_with_certifi", return_value=MagicMock()),
    ):
        async with _mock_session(payload) as mock_session:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await connector.search("trial", max_results=5)

    result = results[0]
    assert result.source_category == SourceCategory.OTHER_SOURCE
    assert result.papers[0].source_category == SourceCategory.OTHER_SOURCE
    # Each paper's URL should point to clinicaltrials.gov/study/<nct_id>
    assert "clinicaltrials.gov/study/" in result.papers[0].url


# ---------------------------------------------------------------------------
# Test 8: date_start filter is forwarded as filter.advanced param
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_date_start_forwarded_as_filter_advanced() -> None:
    connector = ClinicalTrialsConnector("wf-test")

    captured_params: list[dict] = []

    @asynccontextmanager
    async def _capturing_get(url, params):
        captured_params.append(dict(params))
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=_make_response([]))
        yield mock_resp

    mock_session = MagicMock()
    mock_session.get = _capturing_get

    with (
        patch("src.search.clinicaltrials.aiohttp.ClientSession") as mock_cls,
        patch("src.search.clinicaltrials.tcp_connector_with_certifi", return_value=MagicMock()),
    ):
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        await connector.search("intervention outcomes", max_results=10, date_start=2018)

    assert captured_params, "Expected at least one API call"
    params = captured_params[0]
    assert "filter.advanced" in params
    assert "2018-01-01" in params["filter.advanced"]


# ---------------------------------------------------------------------------
# Test 9: _to_candidate returns None for missing nctId or title
# ---------------------------------------------------------------------------


def test_to_candidate_missing_nct_id_returns_none() -> None:
    study: dict[str, Any] = {
        "protocolSection": {
            "identificationModule": {"briefTitle": "Has Title But No NCT"},
            "descriptionModule": {},
            "statusModule": {},
            "sponsorCollaboratorsModule": {},
            "contactsLocationsModule": {},
        }
    }
    result = ClinicalTrialsConnector._to_candidate(study)
    assert result is None


def test_to_candidate_missing_title_falls_back_to_untitled() -> None:
    """When briefTitle and officialTitle are absent, title falls back to "Untitled".
    The connector only returns None for a missing nctId, not for a missing title
    (a fallback is used instead to keep the trial record rather than silently drop it)."""
    study: dict[str, Any] = {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT12345678"},
            "descriptionModule": {},
            "statusModule": {},
            "sponsorCollaboratorsModule": {},
            "contactsLocationsModule": {},
        }
    }
    result = ClinicalTrialsConnector._to_candidate(study)
    assert result is not None
    assert result.title == "Untitled"


# ---------------------------------------------------------------------------
# Test 10: Sponsor name used as author; falls back to "Unknown" when absent
# ---------------------------------------------------------------------------


def test_to_candidate_sponsor_as_author() -> None:
    study = _make_study(sponsor="Mayo Clinic")
    paper = ClinicalTrialsConnector._to_candidate(study)
    assert paper is not None
    assert paper.authors == ["Mayo Clinic"]


def test_to_candidate_missing_sponsor_falls_back_to_unknown() -> None:
    study: dict[str, Any] = {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT99999999", "briefTitle": "No Sponsor Study"},
            "descriptionModule": {"briefSummary": "Summary."},
            "statusModule": {"startDateStruct": {"date": "2020-01-01"}},
            "sponsorCollaboratorsModule": {},
            "contactsLocationsModule": {},
        }
    }
    paper = ClinicalTrialsConnector._to_candidate(study)
    assert paper is not None
    assert paper.authors == ["Unknown"]


# ---------------------------------------------------------------------------
# Test 11: SearchResult metadata populated correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_result_metadata() -> None:
    connector = ClinicalTrialsConnector("wf-777")

    study = _make_study()
    payload = _make_response([study])

    with (
        patch("src.search.clinicaltrials.aiohttp.ClientSession") as mock_cls,
        patch("src.search.clinicaltrials.tcp_connector_with_certifi", return_value=MagicMock()),
    ):
        async with _mock_session(payload) as mock_session:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await connector.search("intervention trial", max_results=15)

    result = results[0]
    assert result.workflow_id == "wf-777"
    assert result.database_name == "clinicaltrials_gov"
    assert result.search_query == "intervention trial"
    assert "pageSize" in result.limits_applied
