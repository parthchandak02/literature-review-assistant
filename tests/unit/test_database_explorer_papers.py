"""Data tab papers explorer: sort, multi-value filters, facet counts, export, detail."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from src.db.database import get_db
from src.web.app import _active_runs, _RunRecord, app
from src.web.papers_query import InvalidQueryError, PaperFilters, order_by

WF = "wf-dbx"
RUN_ID = "run-dbx-test"

PAPERS = [
    ("p1", "Alpha trial", '["Ann Lee", "Bob Roe"]', 2020, "pubmed", "10.1/a", "US", "Abstract A"),
    ("p2", "beta cohort", '["Cy Doe"]', 2022, "openalex", None, None, "Abstract B"),
    ("p3", "Gamma &amp;apos;review&amp;apos;", '["=cmd"]', 2018, "pubmed", "10.1/c", "UK", None),
    ("p4", "Delta study", '["Di Poe"]', None, "scopus", None, "US", "Abstract D"),
]


@pytest_asyncio.fixture()
async def seeded(tmp_path: Path):
    db_path = tmp_path / "runtime.db"
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            (WF, "Topic", "hash", "completed"),
        )
        for pid, title, authors, year, source, doi, country, abstract in PAPERS:
            await db.execute(
                "INSERT INTO papers (paper_id, title, authors, year, source_database, doi, country, abstract) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (pid, title, authors, year, source, doi, country, abstract),
            )
        for pid, stage, decision in [
            ("p1", "title_abstract", "include"),
            ("p2", "title_abstract", "exclude"),
            ("p3", "title_abstract", "include"),
            ("p1", "fulltext", "include"),
            ("p3", "fulltext", "exclude"),
        ]:
            await db.execute(
                "INSERT INTO dual_screening_results "
                "(workflow_id, paper_id, stage, agreement, final_decision, adjudication_needed) "
                "VALUES (?, ?, ?, 1, ?, 0)",
                (WF, pid, stage, decision),
            )
        await db.execute(
            "INSERT INTO screening_decisions "
            "(workflow_id, paper_id, stage, decision, reason, exclusion_reason, reviewer_type, confidence) "
            "VALUES (?, 'p3', 'fulltext', 'exclude', 'Not primary research', 'wrong_design', 'reviewer_a', 0.9)",
            (WF,),
        )
        await db.execute(
            "INSERT INTO extraction_records "
            "(workflow_id, paper_id, study_design, primary_study_status, extraction_source, data) "
            "VALUES (?, 'p1', 'rct', 'primary', 'text', ?)",
            (
                WF,
                json.dumps(
                    {
                        "extraction_confidence": 0.8,
                        "participant_count": 120,
                        "outcomes": [{"name": "mortality"}],
                    }
                ),
            ),
        )
        await db.commit()

    _active_runs[RUN_ID] = _RunRecord(run_id=RUN_ID, topic="Explorer test")
    _active_runs[RUN_ID].db_path = str(db_path)
    _active_runs[RUN_ID].workflow_id = WF
    _active_runs[RUN_ID].done = True
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    _active_runs.pop(RUN_ID, None)


def _ids(payload: dict) -> list[str]:
    return [p["paper_id"] for p in payload["papers"]]


@pytest.mark.asyncio
async def test_papers_all_default_order_is_backward_compatible(seeded: httpx.AsyncClient) -> None:
    res = await seeded.get(f"/api/db/{RUN_ID}/papers-all")
    assert res.status_code == 200
    payload = res.json()
    assert payload["total"] == 4
    assert _ids(payload) == ["p2", "p1", "p3", "p4"]
    assert payload["papers"][2]["title"] == "Gamma 'review'"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("sort", "direction", "expected"),
    [
        ("title", "asc", ["p1", "p2", "p4", "p3"]),
        ("title", "desc", ["p3", "p4", "p2", "p1"]),
        ("year", "asc", ["p3", "p1", "p2", "p4"]),
        ("year", "desc", ["p2", "p1", "p3", "p4"]),
        ("source", "asc", ["p2", "p1", "p3", "p4"]),
        ("ta_decision", "asc", ["p2", "p1", "p3", "p4"]),
        ("ft_decision", "desc", ["p1", "p3", "p2", "p4"]),
        ("confidence", "desc", ["p1", "p2", "p3", "p4"]),
        ("primary_status", "asc", ["p1", "p2", "p3", "p4"]),
    ],
)
async def test_papers_all_sort(seeded: httpx.AsyncClient, sort: str, direction: str, expected: list[str]) -> None:
    res = await seeded.get(f"/api/db/{RUN_ID}/papers-all", params={"sort": sort, "dir": direction})
    assert res.status_code == 200
    assert _ids(res.json()) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [
        {"sort": "p.title; DROP TABLE papers"},
        {"sort": "title", "dir": "asc; DROP TABLE papers"},
        {"sort": "abstract"},
        {"sort": "1"},
    ],
)
async def test_papers_all_rejects_unlisted_sort(seeded: httpx.AsyncClient, params: dict[str, str]) -> None:
    res = await seeded.get(f"/api/db/{RUN_ID}/papers-all", params=params)
    assert res.status_code == 400
    again = await seeded.get(f"/api/db/{RUN_ID}/papers-all")
    assert again.json()["total"] == 4


def test_order_by_only_emits_whitelisted_sql() -> None:
    assert "p.year DESC" in order_by("", "desc")
    with pytest.raises(InvalidQueryError):
        order_by("title) --", "asc")
    with pytest.raises(InvalidQueryError):
        order_by("title", "sideways")


def test_filter_values_are_bound_not_interpolated() -> None:
    evil = "x' OR 1=1 --"
    where, params = PaperFilters(source=[evil], match="exact", title=evil).where()
    assert evil not in where
    assert evil in params


@pytest.mark.asyncio
async def test_papers_all_multi_value_exact_and_year_range(seeded: httpx.AsyncClient) -> None:
    res = await seeded.get(
        f"/api/db/{RUN_ID}/papers-all",
        params=[("match", "exact"), ("source", "pubmed"), ("source", "openalex"), ("year_min", "2019")],
    )
    assert sorted(_ids(res.json())) == ["p1", "p2"]

    res = await seeded.get(
        f"/api/db/{RUN_ID}/papers-all",
        params=[("match", "exact"), ("ta_decision", "__none__")],
    )
    assert _ids(res.json()) == ["p4"]


@pytest.mark.asyncio
async def test_papers_all_legacy_contains_filter(seeded: httpx.AsyncClient) -> None:
    res = await seeded.get(f"/api/db/{RUN_ID}/papers-all", params={"ta_decision": "incl"})
    assert sorted(_ids(res.json())) == ["p1", "p3"]


@pytest.mark.asyncio
async def test_papers_facets_counts_respect_other_filters(seeded: httpx.AsyncClient) -> None:
    res = await seeded.get(f"/api/db/{RUN_ID}/papers-facets")
    payload = res.json()
    assert payload["sources"] == ["openalex", "pubmed", "scopus"]
    counts = payload["counts"]
    assert {c["value"]: c["count"] for c in counts["source"]} == {"pubmed": 2, "openalex": 1, "scopus": 1}
    assert {c["value"]: c["count"] for c in counts["ta_decision"]} == {"include": 2, "exclude": 1, None: 1}

    res = await seeded.get(
        f"/api/db/{RUN_ID}/papers-facets",
        params=[("match", "exact"), ("source", "pubmed")],
    )
    counts = res.json()["counts"]
    assert {c["value"]: c["count"] for c in counts["source"]} == {"pubmed": 2, "openalex": 1, "scopus": 1}
    assert {c["value"]: c["count"] for c in counts["ta_decision"]} == {"include": 2}
    assert [c["value"] for c in counts["year"]] == [2020, 2018]


@pytest.mark.asyncio
async def test_papers_all_include_facets_has_counts(seeded: httpx.AsyncClient) -> None:
    res = await seeded.get(f"/api/db/{RUN_ID}/papers-all", params={"include": "facets"})
    facets = res.json()["facets"]
    assert "years" in facets and "counts" in facets


@pytest.mark.asyncio
async def test_papers_export_csv(seeded: httpx.AsyncClient) -> None:
    res = await seeded.get(
        f"/api/db/{RUN_ID}/papers-export",
        params=[("format", "csv"), ("match", "exact"), ("source", "pubmed"), ("sort", "title"), ("dir", "asc")],
    )
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert "attachment" in res.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(res.text)))
    assert [r["paper_id"] for r in rows] == ["p1", "p3"]
    assert rows[0]["authors"] == "Ann Lee, Bob Roe"
    assert rows[1]["title"] == "Gamma 'review'"
    assert rows[1]["authors"] == "'=cmd"


@pytest.mark.asyncio
async def test_papers_export_ris(seeded: httpx.AsyncClient) -> None:
    res = await seeded.get(f"/api/db/{RUN_ID}/papers-export", params={"format": "ris", "sort": "title", "dir": "asc"})
    assert res.status_code == 200
    text = res.text
    assert text.count("TY  - JOUR") == 4
    assert text.count("ER  - ") == 4
    assert "AU  - Ann Lee\r\nAU  - Bob Roe" in text
    assert "DO  - 10.1/a" in text
    assert "PY  - 2020" in text


@pytest.mark.asyncio
async def test_papers_export_rejects_unknown_format(seeded: httpx.AsyncClient) -> None:
    res = await seeded.get(f"/api/db/{RUN_ID}/papers-export", params={"format": "xlsx"})
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_paper_detail(seeded: httpx.AsyncClient) -> None:
    res = await seeded.get(f"/api/db/{RUN_ID}/papers/p3")
    assert res.status_code == 200
    detail = res.json()
    assert detail["title"] == "Gamma 'review'"
    stages = {s["stage"]: s for s in detail["screening"]}
    assert stages["title_abstract"]["final_decision"] == "include"
    assert stages["fulltext"]["decisions"][0]["reason"] == "Not primary research"
    assert detail["extraction"] is None

    detail = (await seeded.get(f"/api/db/{RUN_ID}/papers/p1")).json()
    assert detail["authors"] == ["Ann Lee", "Bob Roe"]
    assert detail["extraction"]["extraction_confidence"] == 0.8
    assert detail["extraction"]["outcome_count"] == 1

    missing = await seeded.get(f"/api/db/{RUN_ID}/papers/nope")
    assert missing.status_code == 404


async def _seed_outcomes() -> None:
    db_path = _active_runs[RUN_ID].db_path
    assert db_path
    async with get_db(db_path) as db:
        await db.execute("DELETE FROM extraction_records")
        for pid, outcomes in [
            ("p1", [{"name": "mortality", "effect_size": 0.5}, {"name": "los", "p_value": 0.04}, {"name": "none"}]),
            ("p2", [{"name": "pain", "ci_lower": 0.1, "ci_upper": 0.9}]),
            ("p3", [{"name": "qol", "effect_size": 1.2}, {"name": "cost", "effect_size": 2.0}]),
            ("p4", [{"name": "text only"}]),
        ]:
            await db.execute(
                "INSERT INTO extraction_records "
                "(workflow_id, paper_id, study_design, primary_study_status, extraction_source, data) "
                "VALUES (?, ?, 'rct', 'primary', 'text', ?)",
                (WF, pid, json.dumps({"outcomes": outcomes})),
            )
        await db.commit()


def _outcome_names(payload: dict) -> list[str]:
    return [o["name"] for p in payload["papers"] for o in p["outcomes"]]


@pytest.mark.asyncio
async def test_tables_without_filters_is_backward_compatible(seeded: httpx.AsyncClient) -> None:
    await _seed_outcomes()
    res = await seeded.get(f"/api/db/{RUN_ID}/tables")
    assert res.status_code == 200
    payload = res.json()
    assert payload["total_rows"] == 5
    assert payload["total_papers"] == 3
    assert payload["filtered"] is False
    assert _ids(payload) == ["p1", "p2", "p3"]
    assert _outcome_names(payload) == ["mortality", "los", "pain", "qol", "cost"]
    assert payload["papers"][2]["title"] == "Gamma 'review'"


@pytest.mark.asyncio
async def test_tables_follow_paper_filters(seeded: httpx.AsyncClient) -> None:
    await _seed_outcomes()
    res = await seeded.get(
        f"/api/db/{RUN_ID}/tables",
        params=[("match", "exact"), ("source", "pubmed"), ("ta_decision", "include")],
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["filtered"] is True
    assert _ids(payload) == ["p1", "p3"]
    assert payload["total_rows"] == 4
    assert payload["total_papers"] == 2

    res = await seeded.get(f"/api/db/{RUN_ID}/tables", params={"year_min": 2021})
    assert _ids(res.json()) == ["p2"]

    res = await seeded.get(f"/api/db/{RUN_ID}/tables", params={"source": "scopus", "match": "exact"})
    assert res.json()["papers"] == []
    assert res.json()["total_rows"] == 0


@pytest.mark.asyncio
async def test_tables_paginate_by_outcome_row(seeded: httpx.AsyncClient) -> None:
    await _seed_outcomes()
    first = (await seeded.get(f"/api/db/{RUN_ID}/tables", params={"offset": 0, "limit": 2})).json()
    assert _outcome_names(first) == ["mortality", "los"]
    assert first["total_rows"] == 5
    assert (first["offset"], first["limit"]) == (0, 2)
    middle = (await seeded.get(f"/api/db/{RUN_ID}/tables", params={"offset": 2, "limit": 2})).json()
    assert _ids(middle) == ["p2", "p3"]
    assert _outcome_names(middle) == ["pain", "qol"]
    tail = (await seeded.get(f"/api/db/{RUN_ID}/tables", params={"offset": 4, "limit": 2})).json()
    assert _outcome_names(tail) == ["cost"]
    past = (await seeded.get(f"/api/db/{RUN_ID}/tables", params={"offset": 10, "limit": 2})).json()
    assert past["papers"] == []
    assert past["total_rows"] == 5


@pytest.mark.asyncio
@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 501}, {"offset": -1}, {"match": "regex"}])
async def test_tables_rejects_bad_params(seeded: httpx.AsyncClient, params: dict[str, object]) -> None:
    res = await seeded.get(f"/api/db/{RUN_ID}/tables", params=params)
    assert res.status_code in (400, 422)


@pytest.mark.asyncio
async def test_tables_filter_values_are_bound(seeded: httpx.AsyncClient) -> None:
    await _seed_outcomes()
    res = await seeded.get(
        f"/api/db/{RUN_ID}/tables",
        params={"source": "x') OR 1=1; DROP TABLE papers; --", "match": "exact"},
    )
    assert res.status_code == 200
    assert res.json()["papers"] == []
    again = await seeded.get(f"/api/db/{RUN_ID}/tables")
    assert again.json()["total_papers"] == 3


def test_outcome_restriction_binds_filter_values() -> None:
    evil = "x' OR 1=1 --"
    filters = PaperFilters(source=[evil], match="exact")
    assert filters.is_active()
    assert not PaperFilters().is_active()
    where, params = filters.where()
    assert evil not in where
    assert params == [evil]
