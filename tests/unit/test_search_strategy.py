from __future__ import annotations

import asyncio

import pytest

from src.models import DomainExpertConfig, ReviewConfig, ReviewType
from src.models.enums import SourceCategory
from src.models.papers import SearchResult
from src.screening.prompts import _quality_criteria_block
from src.search.embase import EmbaseConnector
from src.search.pubmed import PubMedConnector
from src.search.scopus import ScopusConnector
from src.search.strategy import SearchStrategyCoordinator, build_database_query, requires_primary_studies
from src.search.web_of_science import WebOfScienceConnector


def _review() -> ReviewConfig:
    return ReviewConfig(
        research_question="Does intervention improve outcomes?",
        review_type=ReviewType.SYSTEMATIC,
        pico={
            "population": "adults",
            "intervention": "digital health intervention",
            "comparison": "usual care",
            "outcome": "clinical outcomes",
        },
        keywords=[
            "digital health",
            "telemedicine",
            "remote monitoring",
            "clinical outcomes",
            "adherence",
        ],
        domain="health",
        scope="systematic review scope",
        inclusion_criteria=["primary empirical studies"],
        exclusion_criteria=["secondary reviews"],
        date_range_start=2018,
        date_range_end=2025,
        target_databases=["pubmed", "scopus", "web_of_science", "embase"],
    )


def test_build_database_query_pubmed_primary_only_exclusion() -> None:
    query = build_database_query(_review(), "pubmed")
    assert '"systematic review"[Publication Type]' in query
    assert '"meta-analysis"[Publication Type]' in query
    assert '"review"[Publication Type]' in query


def test_build_database_query_scopus_primary_only_exclusion() -> None:
    query = build_database_query(_review(), "scopus")
    assert "TITLE-ABS-KEY" in query
    assert "AND NOT DOCTYPE(re)" in query


def test_build_database_query_wos_primary_only_exclusion() -> None:
    query = build_database_query(_review(), "web_of_science")
    assert "TS=" in query
    assert "AND NOT DT=Review" in query


def test_build_database_query_embase_primary_only_exclusion() -> None:
    query = build_database_query(_review(), "embase")
    assert "TITLE-ABS-KEY" in query
    assert "AND NOT DOCTYPE(re)" in query


def test_build_database_query_uses_domain_expert_terms() -> None:
    review = _review().model_copy(
        update={
            "domain_expert": DomainExpertConfig(
                canonical_terms=["telemedicine", "remote patient monitoring"],
                related_terms=["RPM"],
                outcome_focus=["hospital readmission"],
            )
        }
    )
    query = build_database_query(review, "semantic_scholar")
    assert "remote patient monitoring" in query
    assert "RPM" in query


def test_primary_filter_mode_detection() -> None:
    assert PubMedConnector._primary_filter_mode('"x AND "systematic review"[Publication Type]') == "query_exclusion"
    assert PubMedConnector._primary_filter_mode("x") == "screening_only"
    assert ScopusConnector._primary_filter_mode("TITLE-ABS-KEY(x) AND NOT DOCTYPE(re)") == "query_exclusion"
    assert ScopusConnector._primary_filter_mode("TITLE-ABS-KEY(x)") == "screening_only"
    assert WebOfScienceConnector._primary_filter_mode('TS="x" AND NOT DT=Review') == "query_exclusion"
    assert WebOfScienceConnector._primary_filter_mode('TS="x"') == "screening_only"
    assert EmbaseConnector._primary_filter_mode("TITLE-ABS-KEY(x) AND NOT DOCTYPE(re)") == "query_exclusion"
    assert EmbaseConnector._primary_filter_mode("TITLE-ABS-KEY(x)") == "screening_only"


def test_screening_quality_block_preserves_secondary_review_guard() -> None:
    block = _quality_criteria_block()
    assert "secondary review" in block
    assert "Apply these criteria even if database-level query filters were used." in block


def test_requires_primary_studies_for_systematic_reviews() -> None:
    assert requires_primary_studies(_review()) is True


class _DelayedConnector:
    """Minimal connector for coordinator tests (protocol-compatible)."""

    def __init__(self, name: str, delay_s: float, records: int = 1) -> None:
        self.name = name
        self.source_category = SourceCategory.DATABASE
        self._delay = delay_s
        self._records = records

    async def search(
        self,
        query: str,
        max_results: int = 100,
        date_start: int | None = None,
        date_end: int | None = None,
    ) -> SearchResult:
        await asyncio.sleep(self._delay)
        return SearchResult(
            workflow_id="wf-test",
            database_name=self.name,
            source_category=self.source_category,
            search_date="2026-01-01",
            search_query=query,
            records_retrieved=self._records,
            papers=[],
        )


class _StubSearchRepo:
    async def save_search_result(self, _r: SearchResult) -> None:
        return None

    async def append_decision_log(self, _entry: object) -> None:
        return None


class _StubGateRunner:
    async def run_search_volume_gate(self, **_kwargs: object) -> None:
        return None


@pytest.mark.asyncio
async def test_search_coordinator_streams_on_connector_done_in_completion_order() -> None:
    """Fast connector must emit before slow; previously gather deferred all callbacks."""
    order: list[str] = []

    def on_done(
        name: str,
        status: str,
        records: int,
        query: str,
        date_start: int | None,
        date_end: int | None,
        error: str | None,
    ) -> None:
        assert status == "success"
        assert error is None
        order.append(name)

    coordinator = SearchStrategyCoordinator(
        workflow_id="wf-test",
        config=_review(),
        connectors=[
            _DelayedConnector("slow", 0.12),
            _DelayedConnector("fast", 0.02),
        ],
        repository=_StubSearchRepo(),  # type: ignore[arg-type]
        gate_runner=_StubGateRunner(),  # type: ignore[arg-type]
        on_connector_done=on_done,
        low_recall_threshold=0,
    )
    await coordinator.run(max_results=50)
    assert order == ["fast", "slow"]


def test_build_database_query_scoping_does_not_force_primary_only_clause() -> None:
    scoping = _review().model_copy(
        update={
            "review_type": ReviewType.SCOPING,
            "exclusion_criteria": ["not relevant to question"],
        }
    )
    query = build_database_query(scoping, "pubmed")
    assert '"systematic review"[Publication Type]' not in query
