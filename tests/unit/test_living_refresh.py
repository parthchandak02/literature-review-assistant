"""Unit tests for living review delta pipeline DB merge (Enhancement #6)."""

from __future__ import annotations

import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository, merge_papers_from_parent


async def _setup_parent_db(db_path: str, paper_ids: list) -> None:
    """Populate a parent DB with papers and dual_screening_results decisions."""
    async with get_db(db_path) as db:
        await WorkflowRepository(db).create_workflow("wf-parent", "Parent topic", "hash-parent")
        for pid in paper_ids:
            await db.execute(
                """INSERT INTO papers
                   (paper_id, title, abstract, authors, year, doi, url, source_database,
                    display_label, openalex_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    pid,
                    f"Title {pid}",
                    "Abstract.",
                    '["Author A"]',
                    2023,
                    f"10.1234/{pid}",
                    None,
                    "openalex",
                    f"Label {pid}",
                    None,
                ),
            )
        await db.commit()
        for pid in paper_ids:
            await db.execute(
                """INSERT INTO dual_screening_results
                   (workflow_id, paper_id, stage, agreement, final_decision, adjudication_needed)
                   VALUES ('wf-parent', ?, 'stage1', 1, 'include', 0)""",
                (pid,),
            )
        await db.commit()


@pytest.mark.asyncio
async def test_merge_copies_papers_and_decisions(tmp_path) -> None:
    parent_db = str(tmp_path / "parent.db")
    dst_path = str(tmp_path / "dst.db")
    await _setup_parent_db(parent_db, ["p1", "p2", "p3"])
    async with get_db(dst_path) as dst_db:
        await WorkflowRepository(dst_db).create_workflow("wf-dst", "topic", "hash")
        await merge_papers_from_parent(parent_db, dst_db)
        cur = await dst_db.execute("SELECT COUNT(*) FROM papers")
        assert (await cur.fetchone())[0] == 3
        cur = await dst_db.execute("SELECT COUNT(*) FROM dual_screening_results")
        assert (await cur.fetchone())[0] == 3


@pytest.mark.asyncio
async def test_merge_is_idempotent(tmp_path) -> None:
    parent_db = str(tmp_path / "parent.db")
    dst_path = str(tmp_path / "dst.db")
    await _setup_parent_db(parent_db, ["p1", "p2"])
    async with get_db(dst_path) as dst_db:
        await WorkflowRepository(dst_db).create_workflow("wf-dst", "topic", "hash")
        await merge_papers_from_parent(parent_db, dst_db)
        await merge_papers_from_parent(parent_db, dst_db)
        cur = await dst_db.execute("SELECT COUNT(*) FROM papers")
        assert (await cur.fetchone())[0] == 2


@pytest.mark.asyncio
async def test_merge_marks_source_as_merged_from_parent(tmp_path) -> None:
    parent_db = str(tmp_path / "parent.db")
    dst_path = str(tmp_path / "dst.db")
    await _setup_parent_db(parent_db, ["p1"])
    async with get_db(dst_path) as dst_db:
        await WorkflowRepository(dst_db).create_workflow("wf-dst", "topic", "hash")
        await merge_papers_from_parent(parent_db, dst_db)
        cur = await dst_db.execute("SELECT source_database FROM papers WHERE paper_id='p1'")
        row = await cur.fetchone()
        assert row is not None and row[0] == "merged_from_parent"


@pytest.mark.asyncio
async def test_merge_skips_papers_already_in_dst(tmp_path) -> None:
    parent_db = str(tmp_path / "parent.db")
    dst_path = str(tmp_path / "dst.db")
    await _setup_parent_db(parent_db, ["p1", "p2"])
    async with get_db(dst_path) as dst_db:
        await WorkflowRepository(dst_db).create_workflow("wf-dst", "topic", "hash")
        await dst_db.execute(
            "INSERT INTO papers (paper_id, title, authors, source_database, year) "
            "VALUES ('p1', 'Pre-existing', '[\"A\"]', 'openalex', 2020)"
        )
        await dst_db.commit()
        await merge_papers_from_parent(parent_db, dst_db)
        cur = await dst_db.execute("SELECT COUNT(*) FROM papers")
        assert (await cur.fetchone())[0] == 2
        cur = await dst_db.execute("SELECT source_database FROM papers WHERE paper_id='p1'")
        row = await cur.fetchone()
        assert row[0] == "openalex"


@pytest.mark.asyncio
async def test_merge_returns_count(tmp_path) -> None:
    parent_db = str(tmp_path / "parent.db")
    dst_path = str(tmp_path / "dst.db")
    await _setup_parent_db(parent_db, ["p1", "p2", "p3"])
    async with get_db(dst_path) as dst_db:
        await WorkflowRepository(dst_db).create_workflow("wf-dst", "topic", "hash")
        n = await merge_papers_from_parent(parent_db, dst_db)
        assert n == 3


@pytest.mark.asyncio
async def test_merge_graceful_on_bad_parent_path(tmp_path) -> None:
    dst_path = str(tmp_path / "dst.db")
    async with get_db(dst_path) as dst_db:
        await WorkflowRepository(dst_db).create_workflow("wf-dst", "topic", "hash")
        n = await merge_papers_from_parent("/nonexistent/path/parent.db", dst_db)
        assert n == 0


def test_build_living_refresh_config_keeps_prior_last_search_date() -> None:
    from src.web.routers.advanced import build_living_refresh_config

    prior = {
        "research_question": "Does intervention work?",
        "date_range_start": 2015,
        "date_range_end": 2026,
        "last_search_date": "2023-06-01",
        "living_review": False,
    }
    res = build_living_refresh_config(prior, parent_updated_at="2025-01-10 09:00:00")
    assert res["living_review"] is True
    assert res["last_search_date"] == "2023-06-01"
    assert res["date_range_start"] == 2023
    assert res["date_range_end"] == 2026


def test_build_living_refresh_config_never_lowers_prior_date_range_start() -> None:
    from src.web.routers.advanced import build_living_refresh_config

    prior = {
        "research_question": "Does intervention work?",
        "date_range_start": 2024,
        "date_range_end": 2026,
        "last_search_date": "2023-06-01",
    }
    res = build_living_refresh_config(prior)
    assert res["living_review"] is True
    assert res["last_search_date"] == "2023-06-01"
    assert res["date_range_start"] == 2024


def test_build_living_refresh_config_uses_parent_updated_at_when_last_search_date_absent() -> None:
    from src.web.routers.advanced import build_living_refresh_config

    prior = {
        "research_question": "Does intervention work?",
        "date_range_start": 2015,
        "date_range_end": 2026,
    }
    res = build_living_refresh_config(prior, parent_updated_at="2024-03-15 14:22:10")
    assert res["living_review"] is True
    assert res["last_search_date"] == "2024-03-15"
    assert res["date_range_start"] == 2024


def _make_review_config(**overrides):
    from src.models import ReviewConfig, ReviewType

    payload = {
        "research_question": "Does intervention work?",
        "review_type": ReviewType.SYSTEMATIC,
        "pico": {
            "population": "adults",
            "intervention": "intervention",
            "comparison": "control",
            "outcome": "outcome",
        },
        "keywords": ["intervention", "outcome"],
        "domain": "health",
        "scope": "scope",
        "inclusion_criteria": ["primary"],
        "exclusion_criteria": ["reviews"],
        "date_range_start": 2015,
        "date_range_end": 2026,
        "target_databases": ["openalex"],
    }
    payload.update(overrides)
    return ReviewConfig(**payload)


def test_effective_date_start_respects_living_review_and_last_search_date() -> None:
    from src.search.strategy import effective_date_start

    cfg_living = _make_review_config(living_review=True, last_search_date="2023-06-01", date_range_start=2015)
    assert effective_date_start(cfg_living) == 2023

    cfg_higher_start = _make_review_config(living_review=True, last_search_date="2023-06-01", date_range_start=2024)
    assert effective_date_start(cfg_higher_start) == 2024

    cfg_non_living = _make_review_config(living_review=False, last_search_date="2023-06-01", date_range_start=2015)
    assert effective_date_start(cfg_non_living) == 2015


@pytest.mark.asyncio
async def test_search_strategy_coordinator_passes_effective_date_start(tmp_path) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from src.models import SearchResult, SourceCategory
    from src.search.strategy import SearchStrategyCoordinator

    seen_date_starts: list[int | None] = []

    class _StubConnector:
        name = "openalex"
        source_category = SourceCategory.DATABASE

        async def search(
            self, query: str, max_results: int = 100, date_start: int | None = None, date_end: int | None = None
        ):
            seen_date_starts.append(date_start)
            return SearchResult(
                workflow_id="wf-test",
                database_name="openalex",
                source_category=SourceCategory.DATABASE,
                search_date="2026-01-01",
                search_query=query,
                records_retrieved=0,
                papers=[],
            )

    repo = MagicMock()
    repo.save_search_result = AsyncMock()
    repo.append_decision_log = AsyncMock()
    gate_runner = MagicMock()
    gate_runner.run_search_volume_gate = AsyncMock()

    cfg = _make_review_config(living_review=True, last_search_date="2023-06-01", date_range_start=2015)
    coordinator = SearchStrategyCoordinator(
        workflow_id="wf-test",
        config=cfg,
        connectors=[_StubConnector()],
        repository=repo,
        gate_runner=gate_runner,
        output_dir=str(tmp_path),
        low_recall_threshold=0,
    )
    await coordinator.run()
    assert seen_date_starts == [2023]


def test_filter_living_review_candidates_drops_pre_floor_and_keeps_later_and_missing_year() -> None:
    from src.models import CandidatePaper
    from src.orchestration.runners.search_runner import filter_living_review_candidates

    papers = [
        CandidatePaper(
            paper_id="old", title="Old Paper", authors=["A"], year=2022, source_database="openalex", doi="10.1/old"
        ),
        CandidatePaper(
            paper_id="same", title="Same Year", authors=["A"], year=2023, source_database="openalex", doi="10.1/same"
        ),
        CandidatePaper(
            paper_id="later",
            title="Later Paper",
            authors=["A"],
            year=2024,
            source_database="openalex",
            doi="10.1/later",
        ),
        CandidatePaper(
            paper_id="missing",
            title="Missing Year",
            authors=["A"],
            year=None,
            source_database="openalex",
            doi="10.1/missing",
        ),
    ]
    kept = filter_living_review_candidates(papers, known_dois=set(), floor_year=2023)
    assert [p.paper_id for p in kept] == ["same", "later", "missing"]


@pytest.mark.asyncio
async def test_run_search_node_living_review_drops_pre_floor_and_normalized_dois(tmp_path, monkeypatch) -> None:
    from unittest.mock import patch

    import yaml

    from src.models import CandidatePaper, SearchResult, SettingsConfig, SourceCategory
    from src.models.config import GatesConfig, SearchConfig
    from src.orchestration.runners.search_runner import run_search_node
    from src.orchestration.state import ReviewState

    # 1. Parent DB has paper screened as https://doi.org/10.1000/abc
    parent_db = str(tmp_path / "parent.db")
    async with get_db(parent_db) as pdb:
        await WorkflowRepository(pdb).create_workflow("wf-parent", "Does intervention work?", "hash-p")
        await pdb.execute(
            """INSERT INTO papers
               (paper_id, title, abstract, authors, year, doi, url, source_database, display_label, openalex_id)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                "parent-p1",
                "Screened Study",
                "Abs",
                '["A"]',
                2023,
                "https://doi.org/10.1000/abc",
                None,
                "openalex",
                "A2023",
                None,
            ),
        )
        await pdb.execute(
            """INSERT INTO dual_screening_results
               (workflow_id, paper_id, stage, agreement, final_decision, adjudication_needed)
               VALUES ('wf-parent', 'parent-p1', 'title_abstract', 1, 'include', 0)"""
        )
        await pdb.commit()

    # 2. Config for living refresh
    review_cfg = _make_review_config(living_review=True, last_search_date="2023-06-01", date_range_start=2015)
    review_path = tmp_path / "review.yaml"
    review_path.write_text(yaml.safe_dump(review_cfg.model_dump(mode="json")), encoding="utf-8")

    settings = SettingsConfig(
        agents={"search": {"model": "google:gemini-2.5-flash", "temperature": 0.1}},
        gates=GatesConfig(profile="warning"),
        search=SearchConfig(low_recall_warning_threshold=0),
    )
    child_db = str(tmp_path / "child" / "runtime.db")
    (tmp_path / "child").mkdir(parents=True, exist_ok=True)
    run_summary = tmp_path / "child" / "run_summary.json"

    state = ReviewState(
        workflow_id="wf-child",
        review_path=str(review_path),
        settings_path="config/settings.yaml",
        run_root=str(tmp_path),
        db_path=child_db,
        output_dir=str(tmp_path / "child"),
        parent_db_path=parent_db,
        review=review_cfg,
        settings=settings,
        artifacts={"run_summary": str(run_summary)},
    )

    seen_date_starts: list[int | None] = []

    class _MockConnector:
        name = "openalex"
        source_category = SourceCategory.DATABASE

        async def search(
            self, query: str, max_results: int = 100, date_start: int | None = None, date_end: int | None = None
        ):
            seen_date_starts.append(date_start)
            return SearchResult(
                workflow_id="wf-child",
                database_name="openalex",
                source_category=SourceCategory.DATABASE,
                search_date="2026-11-15",
                search_query=query,
                records_retrieved=6,
                papers=[
                    CandidatePaper(
                        paper_id="old-2022",
                        title="Too Old",
                        authors=["A"],
                        year=2022,
                        source_database="openalex",
                        doi="10.1000/old",
                    ),
                    CandidatePaper(
                        paper_id="hit-bare",
                        title="Already Screened Bare",
                        authors=["B"],
                        year=2024,
                        source_database="pubmed",
                        doi="10.1000/abc",
                    ),
                    CandidatePaper(
                        paper_id="hit-prefix",
                        title="Already Screened Prefix",
                        authors=["B"],
                        year=2024,
                        source_database="crossref",
                        doi="doi:10.1000/abc",
                    ),
                    CandidatePaper(
                        paper_id="hit-dx",
                        title="Already Screened DX",
                        authors=["B"],
                        year=2024,
                        source_database="scopus",
                        doi="https://dx.doi.org/10.1000/abc",
                    ),
                    CandidatePaper(
                        paper_id="new-2024",
                        title="Brand New Study",
                        authors=["C"],
                        year=2024,
                        source_database="openalex",
                        doi="10.1000/new",
                    ),
                    CandidatePaper(
                        paper_id="no-year",
                        title="Undated Study",
                        authors=["D"],
                        year=None,
                        source_database="openalex",
                        doi="10.1000/nodate",
                    ),
                ],
            )

    with patch(
        "src.orchestration.runners.search_runner._build_connectors",
        return_value=([_MockConnector()], {}),
    ):
        node_result = await run_search_node(state, None)  # type: ignore[arg-type]

    assert node_result is None
    assert seen_date_starts == [2023]
    kept_dois = {p.doi for p in state.deduped_papers}
    assert kept_dois == {"10.1000/new", "10.1000/nodate"}


@pytest.mark.asyncio
async def test_load_screened_doi_keys_checks_both_tables_and_canonicalizes(tmp_path) -> None:
    from src.orchestration.runners.search_runner import _load_screened_doi_keys

    db_path = str(tmp_path / "screened.db")
    async with get_db(db_path) as db:
        await WorkflowRepository(db).create_workflow("wf-1", "topic", "hash")
        await db.executemany(
            "INSERT INTO papers (paper_id, title, authors, source_database, year, doi) VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("p-sd", "Single Screened", '["A"]', "openalex", 2023, "https://doi.org/10.1000/SD"),
                ("p-dsr", "Dual Screened", '["B"]', "crossref", 2024, "doi:10.1000/DSR"),
                ("p-unscreened", "Unscreened", '["C"]', "pubmed", 2024, "10.1000/unscreened"),
            ],
        )
        await db.execute(
            "INSERT INTO screening_decisions "
            "(workflow_id, paper_id, stage, decision, reviewer_type, confidence) "
            "VALUES ('wf-1', 'p-sd', 'title_abstract', 'include', 'primary', 0.9)"
        )
        await db.execute(
            "INSERT INTO dual_screening_results "
            "(workflow_id, paper_id, stage, agreement, final_decision, adjudication_needed) "
            "VALUES ('wf-1', 'p-dsr', 'title_abstract', 1, 'exclude', 0)"
        )
        await db.commit()

        keys = await _load_screened_doi_keys(db)
        assert keys == {"10.1000/sd", "10.1000/dsr"}
