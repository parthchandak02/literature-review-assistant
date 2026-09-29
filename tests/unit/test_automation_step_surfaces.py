"""automation_step on screening-summary and the Data tab, using the PRISMA automation classification."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.web.app import _active_runs, _RunRecord, app

WF = "wf-auto"
RUN_ID = "run-auto-test"

# paper_id, ta final_decision, screening_decisions rows (decision, reason, exclusion_reason, reviewer_type)
SEED: list[tuple[str, str, list[tuple[str, str, str | None, str]]]] = [
    ("r1", "include", [("include", "Relevant", None, "reviewer_a")]),
    ("r2", "exclude", [("exclude", "Wrong population", "wrong_population", "reviewer_a")]),
    ("a1", "exclude", [("exclude", "Metadata pre-filter: no year.", "insufficient_data", "keyword_filter")]),
    ("a2", "exclude", [("exclude", "BM25 score below cap cutoff", "low_relevance_score", "keyword_filter")]),
    ("a3", "exclude", [("exclude", "BM25 score below cap cutoff", "low_relevance_score", "keyword_filter")]),
    ("a4", "exclude", [("exclude", "Batch LLM pre-ranker score 0.1", "batch_screened_low", "batch_ranker")]),
    (
        "f1",
        "exclude",
        [
            ("exclude", "BM25 score below cap cutoff", "low_relevance_score", "keyword_filter"),
            ("exclude", "Reviewer agrees", "wrong_population", "reviewer_a"),
        ],
    ),
]
EXPECTED_STEPS = {
    "r1": None,
    "r2": None,
    "a1": "metadata_filter",
    "a2": "keyword_ranking",
    "a3": "keyword_ranking",
    "a4": "batch_preranker",
    "f1": None,
}


@pytest_asyncio.fixture()
async def client(tmp_path: Path):
    db_path = tmp_path / "runtime.db"
    async with get_db(str(db_path)) as db:
        await WorkflowRepository(db).create_workflow(WF, "topic", "hash")
        for paper_id, final, decisions in SEED:
            await db.execute(
                "INSERT INTO papers (paper_id, title, authors, year, source_database) "
                "VALUES (?, ?, '[]', 2020, 'openalex')",
                (paper_id, f"Title {paper_id}"),
            )
            await db.execute(
                "INSERT INTO dual_screening_results "
                "(workflow_id, paper_id, stage, agreement, final_decision, adjudication_needed) "
                "VALUES (?, ?, 'title_abstract', 1, ?, 0)",
                (WF, paper_id, final),
            )
            for decision, reason, code, reviewer in decisions:
                await db.execute(
                    "INSERT INTO screening_decisions "
                    "(workflow_id, paper_id, stage, decision, reason, exclusion_reason, reviewer_type, confidence) "
                    "VALUES (?, ?, 'title_abstract', ?, ?, ?, ?, 0.9)",
                    (WF, paper_id, decision, reason, code, reviewer),
                )
        await db.commit()

    _active_runs[RUN_ID] = _RunRecord(run_id=RUN_ID, topic="Automation test")
    _active_runs[RUN_ID].db_path = str(db_path)
    _active_runs[RUN_ID].workflow_id = WF
    _active_runs[RUN_ID].done = True
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        yield http
    _active_runs.pop(RUN_ID, None)


@pytest.mark.asyncio
async def test_screening_summary_adds_automation_step(client: httpx.AsyncClient) -> None:
    res = await client.get(f"/api/run/{RUN_ID}/screening-summary")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == len(SEED)
    steps = {p["paper_id"]: p["automation_step"] for p in body["papers"]}
    assert steps == EXPECTED_STEPS
    automated = next(p for p in body["papers"] if p["paper_id"] == "a2")
    assert automated["decision"] == "exclude"
    assert automated["decided_by"] == "keyword_filter"


@pytest.mark.asyncio
async def test_papers_facets_split_reviewer_exclude_from_automation(client: httpx.AsyncClient) -> None:
    res = await client.get(f"/api/db/{RUN_ID}/papers-facets")
    assert res.status_code == 200
    body = res.json()
    ta = {c["value"]: c["count"] for c in body["counts"]["ta_decision"]}
    assert ta == {"include": 1, "exclude": 2, "removed_by_automation": 4}
    assert body["ta_decisions"] == ["exclude", "include", "removed_by_automation"]


@pytest.mark.asyncio
async def test_papers_all_filters_by_automation_value(client: httpx.AsyncClient) -> None:
    res = await client.get(
        f"/api/db/{RUN_ID}/papers-all",
        params=[("match", "exact"), ("ta_decision", "removed_by_automation"), ("limit", "50")],
    )
    assert res.status_code == 200
    papers = {p["paper_id"]: p for p in res.json()["papers"]}
    assert set(papers) == {"a1", "a2", "a3", "a4"}
    assert all(p["ta_decision"] == "removed_by_automation" for p in papers.values())
    assert papers["a4"]["automation_step"] == "batch_preranker"

    res = await client.get(f"/api/db/{RUN_ID}/papers-all", params=[("match", "exact"), ("ta_decision", "exclude")])
    rows = res.json()["papers"]
    assert {p["paper_id"] for p in rows} == {"r2", "f1"}
    assert all(p["automation_step"] is None for p in rows)


@pytest.mark.asyncio
async def test_papers_facets_with_automation_filter_counts_other_facets(client: httpx.AsyncClient) -> None:
    res = await client.get(
        f"/api/db/{RUN_ID}/papers-facets",
        params=[("match", "exact"), ("ta_decision", "removed_by_automation")],
    )
    counts = res.json()["counts"]
    assert {c["value"]: c["count"] for c in counts["source"]} == {"openalex": 4}


@pytest.mark.asyncio
async def test_paper_detail_includes_automation_step(client: httpx.AsyncClient) -> None:
    res = await client.get(f"/api/db/{RUN_ID}/papers/a1")
    assert res.status_code == 200
    assert res.json()["automation_step"] == "metadata_filter"
    res = await client.get(f"/api/db/{RUN_ID}/papers/r2")
    assert res.json()["automation_step"] is None
