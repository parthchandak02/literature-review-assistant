"""Data tab: stored records that never reached screening are labelled duplicate or superseded."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.web.app import _active_runs, _RunRecord, app

WF = "wf-origin"
RUN_ID = "run-origin-test"
FIRST_SEARCH = "2026-09-01 08:34:45"
RETRY = "2026-09-01 08:35:33"

# paper_id, source, created_at, ta final decision (None = never screened)
PAPERS: list[tuple[str, str, str, str | None]] = [
    ("p1", "pubmed", FIRST_SEARCH, "include"),
    ("p2", "pubmed", FIRST_SEARCH, "exclude"),
    ("d1", "pubmed", FIRST_SEARCH, None),
    ("d2", "ieee_xplore", RETRY, None),
    ("s1", "ieee_xplore", FIRST_SEARCH, None),
    ("i1", "ieee_xplore", RETRY, "include"),
]


async def _seed(db_path: Path, *, dedup_count: int, with_retry: bool = True) -> None:
    async with get_db(str(db_path)) as db:
        await WorkflowRepository(db).create_workflow(WF, "topic", "hash")
        await db.execute("UPDATE workflows SET dedup_count = ? WHERE workflow_id = ?", (dedup_count, WF))
        for name, records in (("pubmed", 3), ("ieee_xplore", 2)):
            await db.execute(
                "INSERT INTO search_results (database_name, source_category, search_date, search_query, "
                "records_retrieved, workflow_id) VALUES (?, 'database', '2026-09-01', 'q', ?, ?)",
                (name, records, WF),
            )
        if with_retry:
            await db.execute(
                "INSERT INTO decision_log (workflow_id, decision_type, decision, rationale, actor, phase, created_at) "
                "VALUES (?, 'search_low_recall_retry', 'executed', 'ieee_xplore: relaxed query fallback applied', "
                "'search_strategy', 'phase_2_search', ?)",
                (WF, RETRY),
            )
        for paper_id, source, created_at, final in PAPERS:
            await db.execute(
                "INSERT INTO papers (paper_id, title, authors, year, source_database, created_at) "
                "VALUES (?, ?, '[]', 2020, ?, ?)",
                (paper_id, f"Title {paper_id}", source, created_at),
            )
            if final is None:
                continue
            await db.execute(
                "INSERT INTO dual_screening_results "
                "(workflow_id, paper_id, stage, agreement, final_decision, adjudication_needed) "
                "VALUES (?, ?, 'title_abstract', 1, ?, 0)",
                (WF, paper_id, final),
            )
            await db.execute(
                "INSERT INTO screening_decisions "
                "(workflow_id, paper_id, stage, decision, reason, reviewer_type, confidence) "
                "VALUES (?, ?, 'title_abstract', ?, 'r', 'reviewer_a', 0.9)",
                (WF, paper_id, final),
            )
        await db.commit()


@pytest_asyncio.fixture()
async def make_client(tmp_path: Path):
    clients: list[httpx.AsyncClient] = []

    async def _make(**seed_kwargs) -> httpx.AsyncClient:
        db_path = tmp_path / f"runtime-{len(clients)}.db"
        await _seed(db_path, **seed_kwargs)
        _active_runs[RUN_ID] = _RunRecord(run_id=RUN_ID, topic="Origin test")
        _active_runs[RUN_ID].db_path = str(db_path)
        _active_runs[RUN_ID].workflow_id = WF
        _active_runs[RUN_ID].done = True
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        clients.append(client)
        return client

    yield _make
    for client in clients:
        await client.aclose()
    _active_runs.pop(RUN_ID, None)


def _ta_counts(body: dict) -> dict:
    return {c["value"]: c["count"] for c in body["counts"]["ta_decision"]}


@pytest.mark.asyncio
async def test_facets_split_duplicates_and_superseded(make_client) -> None:
    client = await make_client(dedup_count=2)
    body = (await client.get(f"/api/db/{RUN_ID}/papers-facets")).json()
    assert _ta_counts(body) == {"include": 2, "exclude": 1, "duplicate": 2, "superseded": 1}
    assert {"duplicate", "superseded"} <= set(body["ta_decisions"])


@pytest.mark.asyncio
async def test_papers_all_filters_by_origin(make_client) -> None:
    client = await make_client(dedup_count=2)
    res = await client.get(f"/api/db/{RUN_ID}/papers-all", params=[("match", "exact"), ("ta_decision", "duplicate")])
    assert {p["paper_id"] for p in res.json()["papers"]} == {"d1", "d2"}
    res = await client.get(f"/api/db/{RUN_ID}/papers-all", params=[("match", "exact"), ("ta_decision", "superseded")])
    papers = res.json()["papers"]
    assert [p["paper_id"] for p in papers] == ["s1"]
    assert papers[0]["ta_decision"] == "superseded"
    res = await client.get(f"/api/db/{RUN_ID}/papers-all", params=[("match", "exact"), ("ta_decision", "__none__")])
    assert res.json()["total"] == 0


@pytest.mark.asyncio
async def test_paper_detail_reports_origin(make_client) -> None:
    client = await make_client(dedup_count=2)
    assert (await client.get(f"/api/db/{RUN_ID}/papers/s1")).json()["unscreened_origin"] == "superseded"
    assert (await client.get(f"/api/db/{RUN_ID}/papers/d1")).json()["unscreened_origin"] == "duplicate"
    assert (await client.get(f"/api/db/{RUN_ID}/papers/p1")).json()["unscreened_origin"] is None


@pytest.mark.asyncio
async def test_no_labels_when_counts_do_not_reconcile(make_client) -> None:
    client = await make_client(dedup_count=5, with_retry=False)
    body = (await client.get(f"/api/db/{RUN_ID}/papers-facets")).json()
    assert _ta_counts(body) == {"include": 2, "exclude": 1, None: 3}
