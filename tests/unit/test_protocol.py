from __future__ import annotations

import pytest

from src.config.loader import load_configs
from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.models import CandidatePaper, SearchResult, SourceCategory
from src.orchestration.gates import GateRunner
from src.protocol.generator import ProtocolGenerator
from src.search.arxiv import ArxivConnector
from src.search.deduplication import deduplicate_papers
from src.search.ieee_xplore import IEEEXploreConnector
from src.search.openalex import OpenAlexConnector
from src.search.pubmed import PubMedConnector
from src.search.strategy import SearchStrategyCoordinator


def test_protocol_document_generates_22_sections() -> None:
    review, _ = load_configs("config/review.yaml", "config/settings.yaml")
    generator = ProtocolGenerator(output_dir="runs")
    protocol = generator.generate("wf-protocol", review)
    markdown = generator.render_markdown(protocol, review)
    assert markdown.count("## ") >= 22
    assert "Review question" in markdown


def test_dedup_merges_exact_doi() -> None:
    p1 = CandidatePaper(title="A", authors=["X"], source_database="openalex", doi="10.1/test")
    p2 = CandidatePaper(title="A variant", authors=["Y"], source_database="pubmed", doi="10.1/test")
    unique, duplicates = deduplicate_papers([p1, p2])
    assert len(unique) == 1
    assert duplicates == 1


class _StubConnector:
    def __init__(self, workflow_id: str, name: str, count: int):
        self.workflow_id = workflow_id
        self.name = name
        self.source_category = SourceCategory.DATABASE
        self.count = count

    async def search(self, query: str, max_results: int = 100, date_start: int | None = None, date_end: int | None = None) -> SearchResult:
        papers = [
            CandidatePaper(
                title=f"{self.name}-{idx}",
                authors=["Author"],
                source_database=self.name,
                doi=f"10.1000/{self.name}-{idx}",
                abstract="abstract",
            )
            for idx in range(self.count)
        ]
        return SearchResult(
            workflow_id=self.workflow_id,
            database_name=self.name,
            source_category=SourceCategory.DATABASE,
            search_date="2026-02-15",
            search_query=query,
            limits_applied=f"max_results={max_results}",
            records_retrieved=len(papers),
            papers=papers,
        )


@pytest.mark.asyncio
async def test_strategy_runs_and_gate_executes(tmp_path) -> None:
    review, settings = load_configs("config/review.yaml", "config/settings.yaml")
    workflow_id = "wf-phase2"
    async with get_db(str(tmp_path / "phase2.db")) as db:
        repository = WorkflowRepository(db)
        await repository.create_workflow(workflow_id, review.research_question, "hash")
        gates = GateRunner(repository, settings)
        connectors = [_StubConnector(workflow_id, "openalex", 30), _StubConnector(workflow_id, "pubmed", 25)]
        coordinator = SearchStrategyCoordinator(
            workflow_id=workflow_id,
            config=review,
            connectors=connectors,
            repository=repository,
            gate_runner=gates,
            output_dir=str(tmp_path),
        )
        results, dedup_count = await coordinator.run(max_results=50)
        assert len(results) == 2
        assert dedup_count >= 0
        counts = await repository.get_search_counts(workflow_id)
        assert counts["openalex"] == 30
        assert counts["pubmed"] == 25
        cursor = await db.execute(
            "SELECT COUNT(*) FROM gate_results WHERE workflow_id = ? AND gate_name = 'search_volume'",
            (workflow_id,),
        )
        gate_count = await cursor.fetchone()
        assert int(gate_count[0]) == 1


@pytest.mark.asyncio
async def test_connectors_return_typed_search_results(monkeypatch) -> None:
    from datetime import date
    from unittest.mock import AsyncMock, MagicMock

    workflow_id = "wf-connectors"

    # OpenAlex: mock aiohttp to avoid real API call
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"results": []})
    mock_response.text = AsyncMock(return_value="{}")
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_response)

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_session)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    monkeypatch.setenv("OPENALEX_API_KEY", "dummy")
    monkeypatch.setattr("src.search.openalex.aiohttp.ClientSession", lambda **kw: mock_client)
    openalex = OpenAlexConnector(workflow_id)
    openalex_result = await openalex.search("query", max_results=5)
    assert isinstance(openalex_result, SearchResult)

    pubmed = PubMedConnector(workflow_id)
    monkeypatch.setattr(pubmed, "_sync_search", lambda *args, **kwargs: [])
    pubmed_result = await pubmed.search("query", max_results=5)
    assert isinstance(pubmed_result, SearchResult)

    arxiv_connector = ArxivConnector(workflow_id)
    monkeypatch.setattr(arxiv_connector, "_sync_search", lambda *args, **kwargs: [])
    arxiv_result = await arxiv_connector.search("query", max_results=5)
    assert isinstance(arxiv_result, SearchResult)

    ieee = IEEEXploreConnector(workflow_id)
    ieee_stub = SearchResult(
        workflow_id=workflow_id,
        database_name="ieee_xplore",
        source_category=SourceCategory.DATABASE,
        search_date=date.today().isoformat(),
        search_query="query",
        limits_applied="max_results=5",
        records_retrieved=0,
        papers=[],
    )
    monkeypatch.setattr(ieee, "search", AsyncMock(return_value=ieee_stub))
    ieee_result = await ieee.search("query", max_results=5)
    assert isinstance(ieee_result, SearchResult)


@pytest.mark.asyncio
async def test_strategy_best_effort_continues_on_connector_error(tmp_path) -> None:
    review, settings = load_configs("config/review.yaml", "config/settings.yaml")
    workflow_id = "wf-errors"

    class _FailingConnector:
        name = "openalex"
        source_category = SourceCategory.DATABASE

        async def search(self, *args, **kwargs):  # noqa: ANN002, ANN003
            raise RuntimeError("simulated failure")

    async with get_db(str(tmp_path / "phase2_errors.db")) as db:
        repository = WorkflowRepository(db)
        await repository.create_workflow(workflow_id, review.research_question, "hash")
        gates = GateRunner(repository, settings)
        connectors = [_FailingConnector(), _StubConnector(workflow_id, "pubmed", 12)]
        coordinator = SearchStrategyCoordinator(
            workflow_id=workflow_id,
            config=review,
            connectors=connectors,
            repository=repository,
            gate_runner=gates,
            output_dir=str(tmp_path),
        )
        results, _ = await coordinator.run(max_results=20)
        assert len(results) == 1
        assert results[0].database_name == "pubmed"
