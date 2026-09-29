"""PRISMA 'removed by automation tools' counts every automated pre-reviewer exclusion."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from src.db.database import get_db
from src.db.repos.screening import classify_automation_step
from src.db.repositories import WorkflowRepository
from src.models import PrismaAutomationStep, PRISMACounts, PrismaCountsSidecar
from src.prisma.diagram import (
    _map_counts_to_library_format,
    automation_box_label,
    build_prisma_counts,
    render_prisma_diagram,
)
from src.prisma.regenerate import find_stale_manuscript_counts, regenerate_prisma, stale_manuscript_warning
from src.prisma.sidecar import PRISMA_COUNTS_SIDECAR_NAME, PRISMA_COUNTS_SIDECAR_VERSION, prisma_counts_differ

_REPLAY_DB = Path(__file__).resolve().parents[1] / "fixtures" / "replay" / "runtime.db"

_WF0001_BREAKDOWN = {
    PrismaAutomationStep.METADATA_FILTER: 17,
    PrismaAutomationStep.RULE_PREFILTER: 493,
    PrismaAutomationStep.KEYWORD_RANKING: 818,
    PrismaAutomationStep.BATCH_PRERANKER: 11,
}


class _FakeRepo:
    def __init__(self, *, ta_rows: int, breakdown: dict[PrismaAutomationStep, int]) -> None:
        self._ta_rows = ta_rows
        self._breakdown = breakdown

    async def get_search_counts_by_category(self, workflow_id: str) -> tuple[dict[str, int], dict[str, int]]:
        return {"pubmed": 1000, "scopus": 715}, {}

    async def get_prisma_screening_counts(self, workflow_id: str) -> tuple[int, int, int, int, int, dict[str, int]]:
        return self._ta_rows, 1491, 57, 50, 7, {"wrong_intervention": 1}

    async def get_prisma_automation_breakdown(self, workflow_id: str) -> dict[PrismaAutomationStep, int]:
        return dict(self._breakdown)


def _assert_strict_arithmetic(counts: PRISMACounts) -> None:
    identified = counts.total_identified_databases + counts.total_identified_other
    assert identified - counts.duplicates_removed == counts.records_after_deduplication
    assert counts.records_after_deduplication - counts.automation_excluded == counts.records_screened
    assert sum(counts.automation_breakdown.values()) == counts.automation_excluded
    assert counts.records_screened - counts.records_excluded_screening == counts.reports_sought
    assert counts.reports_sought - counts.reports_not_retrieved == counts.reports_assessed
    assert counts.reports_assessed - sum(counts.reports_excluded_with_reasons.values()) == counts.total_included
    assert counts.arithmetic_valid


@pytest.mark.asyncio
async def test_all_automated_steps_count_as_automation() -> None:
    repo = _FakeRepo(ta_rows=1548, breakdown=_WF0001_BREAKDOWN)

    counts = await build_prisma_counts(repo, "wf-x", dedup_count=167, included_quantitative=6)  # type: ignore[arg-type]

    assert counts.records_after_deduplication == 1548
    assert counts.automation_excluded == 1339
    assert counts.records_screened == 209
    assert counts.records_excluded_screening == 152
    _assert_strict_arithmetic(counts)


@pytest.mark.asyncio
async def test_gap_without_automation_rows_is_unclassified_automation() -> None:
    repo = _FakeRepo(ta_rows=1500, breakdown={})

    counts = await build_prisma_counts(repo, "wf-x", dedup_count=167, included_quantitative=6)  # type: ignore[arg-type]

    assert counts.automation_breakdown == {PrismaAutomationStep.UNCLASSIFIED: 48}
    assert counts.records_screened == 1500
    _assert_strict_arithmetic(counts)


@pytest.mark.asyncio
async def test_arithmetic_invalid_when_screened_cannot_cover_sought() -> None:
    repo = _FakeRepo(ta_rows=1548, breakdown={PrismaAutomationStep.KEYWORD_RANKING: 1500})

    counts = await build_prisma_counts(repo, "wf-x", dedup_count=167, included_quantitative=6)  # type: ignore[arg-type]

    assert counts.records_screened == 48
    assert not counts.arithmetic_valid


@pytest.mark.parametrize(
    ("reviewer_type", "exclusion_reason", "reason", "step"),
    [
        ("keyword_filter", "insufficient_data", "Metadata pre-filter: no publication year.", "metadata_filter"),
        ("keyword_filter", "insufficient_data", "Deterministic pre-filter: empty abstract.", "rule_prefilter"),
        ("keyword_filter", "protocol_only", "Protocol-only heuristic: ...", "rule_prefilter"),
        ("keyword_filter", "low_relevance_score", "BM25 score below cap cutoff", "keyword_ranking"),
        ("keyword_filter", "keyword_filter", "zero keyword matches", "keyword_ranking"),
        ("batch_ranker", "batch_screened_low", "Batch LLM pre-ranker score 0.00", "batch_preranker"),
    ],
)
def test_classify_automation_step(reviewer_type: str, exclusion_reason: str, reason: str, step: str) -> None:
    assert classify_automation_step(reviewer_type, exclusion_reason, reason).value == step


async def _insert_decisions(db: Any, rows: list[tuple[str, str, str, str, str]]) -> None:
    await db.executemany(
        """
        INSERT INTO screening_decisions
            (workflow_id, paper_id, stage, decision, reason, exclusion_reason, reviewer_type, confidence)
        VALUES ('wf-a', ?, 'title_abstract', ?, ?, ?, ?, 0.9)
        """,
        rows,
    )


@pytest.mark.asyncio
async def test_repo_counts_each_unreviewed_record_once_under_latest_step(tmp_path: Path) -> None:
    async with get_db(str(tmp_path / "runtime.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-a", "topic", "hash")
        await db.executemany(
            "INSERT INTO papers (paper_id, title, authors, source_database) VALUES (?, ?, '[]', 'openalex')",
            [(f"p{i}", f"t{i}") for i in range(1, 6)],
        )
        await _insert_decisions(
            db,
            [
                ("p1", "exclude", "Metadata pre-filter: no year.", "insufficient_data", "keyword_filter"),
                ("p2", "exclude", "BM25 score below cap cutoff", "low_relevance_score", "keyword_filter"),
                ("p2", "exclude", "Batch LLM pre-ranker score 0.1", "batch_screened_low", "batch_ranker"),
                ("p3", "exclude", "BM25 score below cap cutoff", "low_relevance_score", "keyword_filter"),
                ("p3", "include", "overflow forwarded, reviewer included", None, "reviewer_a"),
                ("p4", "exclude", "Deterministic pre-filter: empty abstract.", "insufficient_data", "keyword_filter"),
                ("p5", "exclude", "reviewer exclusion", "wrong_population", "reviewer_a"),
            ],
        )
        await db.commit()

        steps = await repo.get_prisma_automation_steps("wf-a")
        breakdown = await repo.get_prisma_automation_breakdown("wf-a")

    assert steps == {
        "p1": PrismaAutomationStep.METADATA_FILTER,
        "p2": PrismaAutomationStep.BATCH_PRERANKER,
        "p4": PrismaAutomationStep.RULE_PREFILTER,
    }
    assert breakdown == {
        PrismaAutomationStep.METADATA_FILTER: 1,
        PrismaAutomationStep.BATCH_PRERANKER: 1,
        PrismaAutomationStep.RULE_PREFILTER: 1,
    }


def _counts_with_breakdown() -> PRISMACounts:
    return PRISMACounts(
        databases_records={"pubmed": 1715},
        other_sources_records={},
        total_identified_databases=1715,
        total_identified_other=0,
        duplicates_removed=167,
        automation_excluded=1339,
        automation_breakdown=_WF0001_BREAKDOWN,
        records_screened=209,
        records_excluded_screening=152,
        reports_sought=57,
        reports_not_retrieved=50,
        reports_assessed=7,
        reports_excluded_with_reasons={"wrong_intervention": 1},
        studies_included_qualitative=0,
        studies_included_quantitative=6,
        arithmetic_valid=True,
        records_after_deduplication=1548,
        total_included=6,
    )


def test_automation_box_label_lists_each_step() -> None:
    label = automation_box_label(_counts_with_breakdown())
    assert label.startswith("Records removed by automation tools (n=1,339)")
    assert "metadata filter n=17" in label
    assert "rule-based pre-filter n=493" in label
    assert "keyword ranking n=818" in label
    assert "batch pre-ranker n=11" in label


def test_library_mapping_passes_automation_total_and_breakdown() -> None:
    db_registers, _, _ = _map_counts_to_library_format(_counts_with_breakdown())
    removed = db_registers["removed_before_screening"]
    assert removed["automation"] == 1339
    assert list(removed["automation_breakdown"].items()) == [
        ("metadata filter", 17),
        ("rule-based pre-filter", 493),
        ("keyword ranking", 818),
        ("batch pre-ranker", 11),
    ]
    assert db_registers["records"] == {"screened": 209, "excluded": 152}


def test_render_writes_counts_sidecar_beside_figure(tmp_path: Path) -> None:
    counts = _counts_with_breakdown()
    figure = render_prisma_diagram(counts, tmp_path / "fig_prisma_flow.png")

    sidecar_path = tmp_path / PRISMA_COUNTS_SIDECAR_NAME
    assert figure.exists()
    sidecar = PrismaCountsSidecar.model_validate_json(sidecar_path.read_text())
    assert sidecar.version == PRISMA_COUNTS_SIDECAR_VERSION
    assert sidecar.figure == "fig_prisma_flow.png"
    assert not prisma_counts_differ(sidecar.counts, counts)
    assert json.loads(sidecar_path.read_text())["counts"]["automation_breakdown"]["batch_preranker"] == 11


@pytest.mark.asyncio
async def test_regenerate_wf0001_fixture_counts_and_sidecar(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    shutil.copyfile(_REPLAY_DB, run_dir / "runtime.db")

    dry = await regenerate_prisma(str(run_dir), dry_run=True)
    assert dry.old is None
    assert dry.written == []
    assert not (run_dir / PRISMA_COUNTS_SIDECAR_NAME).exists()
    assert not (run_dir / "fig_prisma_flow.png").exists()

    counts = dry.new
    assert counts.total_identified_databases + counts.total_identified_other == 1715
    assert counts.duplicates_removed == 167
    assert counts.automation_breakdown == _WF0001_BREAKDOWN
    assert counts.automation_excluded == 1339
    assert counts.records_screened == 209
    assert counts.records_excluded_screening == 152
    assert (counts.reports_sought, counts.reports_not_retrieved, counts.reports_assessed) == (57, 50, 7)
    assert counts.total_included == 6
    _assert_strict_arithmetic(counts)

    result = await regenerate_prisma(str(run_dir))
    assert (run_dir / "fig_prisma_flow.png").exists()
    sidecar = PrismaCountsSidecar.model_validate_json((run_dir / PRISMA_COUNTS_SIDECAR_NAME).read_text())
    assert not prisma_counts_differ(sidecar.counts, result.new)

    again = await regenerate_prisma(str(run_dir / "runtime.db"), dry_run=True)
    assert again.old is not None
    assert not prisma_counts_differ(again.old, again.new)


def test_stale_manuscript_counts_flag_only_differing_numbers() -> None:
    counts = _counts_with_breakdown()
    text = (
        "The review screened 1,537 records, sought 57 full-text reports, did not retrieve 50, "
        "assessed 7 reports for eligibility. Of these, 1480 records were excluded at title and abstract "
        "screening. Two reviewers then screened those 209 records."
    )
    assert find_stale_manuscript_counts(text, counts) == [
        "screened 1,537 records",
        "1480 records were excluded at title and abstract",
    ]
    assert find_stale_manuscript_counts("We screened 209 records; 57 reports sought.", counts) == []


@pytest.mark.asyncio
async def test_regenerate_warns_when_manuscript_has_old_counts(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    shutil.copyfile(_REPLAY_DB, run_dir / "runtime.db")
    (run_dir / "doc_manuscript.md").write_text("The review screened 1537 records.", encoding="utf-8")

    result = await regenerate_prisma(str(run_dir), dry_run=True)

    assert stale_manuscript_warning(result) == (
        "Manuscript text still states old PRISMA counts (e.g. 'screened 1537 records'); "
        "re-run the writing phase to update it."
    )
    (run_dir / "doc_manuscript.md").write_text("The review screened 209 records.", encoding="utf-8")
    assert stale_manuscript_warning(await regenerate_prisma(str(run_dir), dry_run=True)) is None
