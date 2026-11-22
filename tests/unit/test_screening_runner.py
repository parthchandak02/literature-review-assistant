"""Tests for Phase 3 screening runner (`src/orchestration/runners/screening_runner.py`).

Covers metadata pre-filtering, keyword pre-filter fallback, BM25 ranking/cap,
Jev live cap override, adaptive threshold calibration (success, failure, skip),
batch LLM pre-ranker forwarding/exclusion + resume skip, intermediate
`phase_3b_fulltext` checkpoint guard and stale recovery, Stage 2 zero-decision
resume/fallback, forward citation chasing, Cohen's kappa logging, partial
checkpointing, and screening safeguard gate enforcement against real SQLite
runtime and registry databases.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_graph import End, GraphRunContext

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.db.workflow_registry import find_by_workflow_id
from src.db.workflow_registry import register as register_workflow
from src.models import (
    CandidatePaper,
    DomainExpertConfig,
    DualScreeningResult,
    ExclusionReason,
    ReviewConfig,
    ReviewerType,
    ScreeningDecision,
    ScreeningDecisionType,
    SearchResult,
    SettingsConfig,
    SourceCategory,
)
from src.models.config import GatesConfig, JevConfig, ScreeningConfig, SearchConfig
from src.models.workflow import WorkflowRunResult, WorkflowRunStatus
from src.orchestration.runners.screening_runner import run_screening_node
from src.orchestration.state import ReviewState
from src.screening.dual_screener import ScreeningResponse
from src.screening.reliability import CalibratedThresholds
from src.search.pdf_retrieval import FullTextCoverageSummary, PDFRetrievalResult

_WORKFLOW_ID = "wf-screening-runner-test"


@pytest.fixture(autouse=True)
def _no_rate_limit_sleep():
    """Avoid real RPM sleeps in RateLimiter during unit tests."""
    with patch("src.llm.rate_limiter.RateLimiter.acquire", new=AsyncMock()):
        yield


class _DeterministicIncludeClient:
    """Fast deterministic ScreeningLLMClient stub that includes papers across both stages."""

    async def complete_json(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
    ) -> str:
        _ = (prompt, agent_name, model, temperature)
        payload = ScreeningResponse(
            decision=ScreeningDecisionType.INCLUDE,
            confidence=0.95,
            short_reason="Inclusion criteria met",
            reasoning="Paper meets PICO and empirical study criteria.",
        )
        return payload.model_dump_json()

    async def complete_screening_response_with_usage(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
    ) -> tuple[ScreeningResponse, int, int, int, int]:
        raw = await self.complete_json(prompt, agent_name=agent_name, model=model, temperature=temperature)
        parsed = ScreeningResponse.model_validate_json(raw)
        return parsed, 10, 10, 0, 0


class _FakePDFRetriever:
    """Deterministic in-memory PDFRetriever replacement that makes no network calls."""

    def __init__(self, *, fail_paper_ids: set[str] | None = None, **_kwargs: object) -> None:
        self.fail_paper_ids = fail_paper_ids or set()

    async def retrieve_batch(
        self,
        papers: list[CandidatePaper],
        on_progress=None,
        concurrency: int = 1,
        per_paper_timeout: int = 30,
        on_result=None,
    ) -> tuple[dict[str, PDFRetrievalResult], FullTextCoverageSummary]:
        _ = (concurrency, per_paper_timeout)
        results: dict[str, PDFRetrievalResult] = {}
        failed_ids: list[str] = []
        total = len(papers)
        for idx, paper in enumerate(papers, start=1):
            if paper.paper_id in self.fail_paper_ids:
                failed_ids.append(paper.paper_id)
                results[paper.paper_id] = PDFRetrievalResult(
                    paper_id=paper.paper_id,
                    success=False,
                    reason_code="not_found",
                )
                if on_result:
                    on_result(paper.paper_id, paper.title, "abstract", False, "not_found")
            else:
                results[paper.paper_id] = PDFRetrievalResult(
                    paper_id=paper.paper_id,
                    success=True,
                    full_text=(
                        "Full text empirical trial evaluating digital reminder and medication adherence "
                        "in primary care outpatient adults with measured outcome proportions."
                    ),
                    source="unpaywall",
                )
                if on_result:
                    on_result(paper.paper_id, paper.title, "unpaywall", True, None)
            if on_progress:
                on_progress(idx, total)
        summary = FullTextCoverageSummary(
            attempted=total,
            succeeded=total - len(failed_ids),
            failed=len(failed_ids),
            success_rate=((total - len(failed_ids)) / total) if total else 1.0,
            failed_paper_ids=failed_ids,
        )
        return results, summary


def _build_review() -> ReviewConfig:
    return ReviewConfig(
        research_question="How effective are digital reminders on medication adherence in primary care?",
        review_type="systematic",
        pico={
            "population": "Adult primary care patients prescribed chronic medications",
            "intervention": "digital reminder",
            "comparison": "Usual care without digital reminders",
            "outcome": "Medication adherence proportion",
        },
        keywords=["digital reminder", "medication adherence", "primary care"],
        domain="clinical informatics",
        scope="Primary care outpatient medication adherence interventions.",
        domain_expert=DomainExpertConfig(
            domain_summary="Evaluates digital medication reminder tools in outpatient primary care.",
        ),
        inclusion_criteria=["Empirical human studies reporting medication adherence outcomes"],
        exclusion_criteria=["Editorials and opinion pieces"],
        date_range_start=2018,
        date_range_end=2026,
        target_databases=["openalex"],
    )


def _build_settings(
    *,
    screening: ScreeningConfig | None = None,
    gates: GatesConfig | None = None,
    jev: JevConfig | None = None,
    search: SearchConfig | None = None,
) -> SettingsConfig:
    return SettingsConfig(
        agents={
            "screening_reviewer_a": {"model": "google:gemini-2.5-flash-lite", "temperature": 0.1},
            "screening_reviewer_b": {"model": "google:gemini-2.5-flash-lite", "temperature": 0.3},
            "screening_adjudicator": {"model": "google:gemini-2.5-pro", "temperature": 0.2},
            "batch_screener": {"model": "google:gemini-2.5-flash-lite", "temperature": 0.1},
        },
        screening=screening
        or ScreeningConfig(max_llm_screen=10, calibrate_threshold=False, batch_screen_enabled=False),
        gates=gates or GatesConfig(profile="warning", screening_minimum=1, sparse_topic_continuation=True),
        jev=jev or JevConfig(),
        search=search or SearchConfig(citation_chasing_enabled=False),
    )


def _make_paper(
    paper_id: str,
    *,
    title: str = "Digital reminder randomized trial for medication adherence in primary care",
    abstract: str | None = (
        "This primary care trial evaluates a digital reminder intervention for medication adherence "
        "among adult patients with chronic hypertension."
    ),
    year: int | None = 2024,
    doi: str | None = None,
) -> CandidatePaper:
    return CandidatePaper(
        paper_id=paper_id,
        title=title,
        authors=["Smith, J.", "Lee, A."],
        year=year,
        source_database="openalex",
        source_category=SourceCategory.DATABASE,
        doi=doi,
        abstract=abstract,
    )


async def _init_state(
    tmp_path: Path,
    papers: list[CandidatePaper],
    *,
    workflow_id: str = _WORKFLOW_ID,
    screening: ScreeningConfig | None = None,
    gates: GatesConfig | None = None,
    jev: JevConfig | None = None,
    search: SearchConfig | None = None,
    offline: bool = False,
    verbose: bool = False,
) -> ReviewState:
    run_root = tmp_path / "runs"
    run_dir = run_root / "2026-11-14" / workflow_id / "run_01"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = run_dir / "runtime.db"
    summary_path = run_dir / "run_summary.json"
    coverage_path = run_dir / "coverage_report.md"

    review = _build_review()
    settings = _build_settings(screening=screening, gates=gates, jev=jev, search=search)

    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow(workflow_id, review.research_question, "cfg-hash-screen")
        for p in papers:
            await repo.papers.save_paper(p)
        await db.commit()

    await register_workflow(
        run_root=str(run_root),
        workflow_id=workflow_id,
        topic=review.research_question,
        config_hash="cfg-hash-screen",
        db_path=str(db_path),
        status="running",
    )

    rc = MagicMock()
    rc.verbose = verbose
    rc.debug = False
    rc.offline = offline
    rc.should_proceed_with_partial.return_value = False

    return ReviewState(
        review_path=str(run_dir / "review.yaml"),
        settings_path=str(run_dir / "settings.yaml"),
        run_root=str(run_root),
        run_context=rc,
        run_id="20261114-112651",
        workflow_id=workflow_id,
        review=review,
        settings=settings,
        db_path=str(db_path),
        log_dir=str(run_dir),
        output_dir=str(run_dir),
        dedup_count=len(papers),
        deduped_papers=list(papers),
        artifacts={
            "run_summary": str(summary_path),
            "coverage_report": str(coverage_path),
        },
    )


def _ctx(state: ReviewState) -> GraphRunContext[ReviewState]:
    return GraphRunContext(state=state, deps=None)


def _emitted_events(rc: MagicMock) -> list[dict]:
    return [call.args[0] for call in rc._emit.call_args_list if call.args and isinstance(call.args[0], dict)]


async def test_screening_runner_prefilter_bm25_fulltext_and_persistence(tmp_path: Path) -> None:
    """Exercise Gate 0 metadata, deterministic/keyword prefilters, BM25 cap, Stage 1+2, cohort, and metrics."""
    p_meta_bad = _make_paper("p-meta", abstract="", year=None)
    p_secondary = _make_paper(
        "p-secondary",
        title="A systematic review of digital reminder interventions",
        abstract="We conducted a systematic review of digital reminder studies in primary care.",
    )
    p_no_kw = _make_paper(
        "p-nokw",
        title="Unrelated surgical technique outcomes",
        abstract="Orthopedic fixation hardware comparison in hospital inpatient wards.",
    )
    p_rel_1 = _make_paper(
        "p-rel-1",
        title="Digital reminder RCT for medication adherence in primary care",
        abstract="Digital reminder and medication adherence primary care randomized trial.",
    )
    p_rel_2 = _make_paper(
        "p-rel-2",
        title="Digital reminder mobile app for medication adherence in primary care",
        abstract="Digital reminder intervention improved medication adherence in primary care.",
    )
    p_rel_3 = _make_paper(
        "p-rel-3",
        title="Clinic scheduling note with digital reminder mention",
        abstract="Brief mention of digital reminder during clinic intake workflow.",
    )

    papers = [p_meta_bad, p_secondary, p_no_kw, p_rel_1, p_rel_2, p_rel_3]
    state = await _init_state(
        tmp_path,
        papers,
        screening=ScreeningConfig(
            max_llm_screen=2,
            bm25_validation_tail_size=0,
            keyword_filter_min_matches=1,
            keyword_prefilter_fallback_exclusion_ratio=0.95,
            deterministic_exclude_qa_sample_size=5,
            calibrate_threshold=False,
            batch_screen_enabled=False,
        ),
    )

    with (
        patch("src.orchestration.runners.screening_runner._llm_available", return_value=True),
        patch("src.orchestration.runners.screening_runner.PydanticAIScreeningClient", _DeterministicIncludeClient),
        patch("src.orchestration.runners.screening_runner.PDFRetriever", _FakePDFRetriever),
    ):
        result = await run_screening_node(state, _ctx(state))

    assert result is None
    assert len(state.included_papers) == 2
    assert state.fulltext_sought == 2
    assert state.fulltext_not_retrieved == 0

    events = _emitted_events(state.run_context)
    prefilter_events = [e for e in events if e.get("type") == "screening_prefilter_done"]
    assert len(prefilter_events) == 1
    pf = prefilter_events[0]
    assert pf["deduped"] == 6
    assert pf["metadata_rejected"] == 1
    assert pf["after_metadata"] == 5
    assert pf["automation_excluded"] == 3  # p-secondary, p-nokw, plus 1 BM25 cap exclusion
    assert pf["to_llm"] == 2
    assert pf["dual_review_cap"] == 2
    assert pf["keyword_fallback_applied"] is False

    qa_events = [e for e in events if e.get("type") == "deterministic_exclusion_qa_sample"]
    assert len(qa_events) == 1
    assert qa_events[0]["pool_size"] == 1
    assert qa_events[0]["items"][0]["paper_id"] == "p-secondary"

    async with get_db(state.db_path) as db:
        repo = WorkflowRepository(db)
        checkpoints = await repo.get_checkpoints(state.workflow_id)
        assert checkpoints["phase_3b_fulltext"] == "completed"
        assert checkpoints["phase_3_screening"] == "completed"

        included_ids = await repo.get_included_paper_ids(state.workflow_id)
        assert included_ids == {p.paper_id for p in state.included_papers}

        cursor = await db.execute(
            "SELECT paper_id, screening_status, fulltext_status, synthesis_eligibility "
            "FROM study_cohort_membership WHERE workflow_id = ?",
            (state.workflow_id,),
        )
        cohort_rows = {r[0]: (r[1], r[2], r[3]) for r in await cursor.fetchall()}
        for inc_p in state.included_papers:
            assert cohort_rows[inc_p.paper_id] == ("included", "assessed", "pending")

        cursor = await db.execute(
            "SELECT decision_type, decision, rationale FROM decision_log",
        )
        logs = await cursor.fetchall()
        assert any(row[0] == "screening_summary" and "pre_filter_method=bm25_rank_and_cap" in row[2] for row in logs)
        metric_names = {json.loads(row[2])["metric"] for row in logs if row[0] == "screening_metric"}
        assert {
            "prefilter_metadata_rejected",
            "prefilter_automation_excluded",
            "prefilter_to_llm",
            "fulltext_sought",
        }.issubset(metric_names)

        steps = await repo.get_step_history(state.workflow_id, "phase_3_screening")
        assert len(steps) == 1
        assert steps[0].status.value == "succeeded"


async def test_screening_runner_keyword_fallback_when_exclusion_ratio_exceeded(tmp_path: Path) -> None:
    """When keyword exclusions exceed ratio threshold, drop keyword-only exclusions and keep rule exclusions."""
    p_secondary = _make_paper(
        "p-sec",
        title="A systematic review of clinic scheduling",
        abstract="Systematic review of outpatient scheduling systems.",
    )
    p_1 = _make_paper(
        "p-1",
        title="Outpatient adherence SMS study",
        abstract="Short message reminders improved adherence in clinic patients.",
    )
    p_2 = _make_paper(
        "p-2",
        title="Automated phone prompt trial",
        abstract="Phone calls improved chronic prescription refills in adults.",
    )
    p_3 = _make_paper(
        "p-3",
        title="Electronic pillbox monitoring study",
        abstract="Smart pillboxes supported outpatient hypertension management.",
    )

    state = await _init_state(
        tmp_path,
        [p_secondary, p_1, p_2, p_3],
        screening=ScreeningConfig(
            max_llm_screen=5,
            keyword_filter_min_matches=1,
            keyword_prefilter_fallback_exclusion_ratio=0.50,
            calibrate_threshold=False,
            batch_screen_enabled=False,
        ),
    )

    with (
        patch("src.orchestration.runners.screening_runner._llm_available", return_value=True),
        patch("src.orchestration.runners.screening_runner.PydanticAIScreeningClient", _DeterministicIncludeClient),
        patch("src.orchestration.runners.screening_runner.PDFRetriever", _FakePDFRetriever),
    ):
        result = await run_screening_node(state, _ctx(state))

    assert result is None
    assert {p.paper_id for p in state.included_papers} == {"p-1", "p-2", "p-3"}

    events = _emitted_events(state.run_context)
    pf = next(e for e in events if e.get("type") == "screening_prefilter_done")
    assert pf["keyword_filter_excluded"] == 3
    assert pf["keyword_fallback_applied"] is True
    assert pf["to_llm"] == 3


async def test_screening_runner_jev_live_overrides_cap(tmp_path: Path) -> None:
    """When jev screening_reviewer_b is live, screening_cap_when_enabled overrides max_llm_screen in cap tracking."""
    papers = [_make_paper(f"p-{i}") for i in range(3)]
    state = await _init_state(
        tmp_path,
        papers,
        screening=ScreeningConfig(max_llm_screen=1, calibrate_threshold=False, batch_screen_enabled=False),
        jev=JevConfig(enabled=True, screening_reviewer_b="live", screening_cap_when_enabled=5),
        offline=True,
    )

    with patch("src.orchestration.runners.screening_runner.PDFRetriever", _FakePDFRetriever):
        await run_screening_node(state, _ctx(state))

    pf = next(e for e in _emitted_events(state.run_context) if e.get("type") == "screening_prefilter_done")
    assert pf["dual_review_cap"] == 5


async def test_screening_runner_calibration_success_failure_and_delta_skip(tmp_path: Path) -> None:
    """Verify calibration updates thresholds on success, falls back cleanly on error, and skips on delta runs."""
    papers = [_make_paper("p-cal-1"), _make_paper("p-cal-2")]

    # 1) Calibration succeeds
    state_ok = await _init_state(
        tmp_path / "ok",
        papers,
        screening=ScreeningConfig(
            max_llm_screen=5,
            calibrate_threshold=True,
            calibration_sample_size=5,
            calibration_max_iterations=2,
            batch_screen_enabled=False,
        ),
        offline=False,
    )
    calib_result = CalibratedThresholds(
        include_threshold=0.72,
        exclude_threshold=0.67,
        achieved_kappa=0.84,
        iterations=2,
        sample_size=2,
    )
    with (
        patch("src.orchestration.runners.screening_runner._llm_available", return_value=True),
        patch("src.orchestration.runners.screening_runner.PydanticAIScreeningClient", _DeterministicIncludeClient),
        patch("src.orchestration.runners.screening_runner.PDFRetriever", _FakePDFRetriever),
        patch("src.screening.reliability.calibrate_threshold", new=AsyncMock(return_value=calib_result)) as mock_cal,
    ):
        await run_screening_node(state_ok, _ctx(state_ok))

    assert mock_cal.await_count == 1
    assert state_ok.settings.screening.stage1_include_threshold == pytest.approx(0.72)
    assert state_ok.settings.screening.stage1_exclude_threshold == pytest.approx(0.67)
    events = _emitted_events(state_ok.run_context)
    assert any(e.get("type") == "screening_calibration" and e.get("kappa") == 0.84 for e in events)

    async with get_db(state_ok.db_path) as db:
        cursor = await db.execute(
            "SELECT rationale FROM decision_log WHERE workflow_id = ? AND decision_type = 'screening_metric'",
            (state_ok.workflow_id,),
        )
        metrics = {json.loads(r[0])["metric"]: json.loads(r[0])["value"] for r in await cursor.fetchall()}
        assert metrics["calibration_include_threshold"] == pytest.approx(0.72)
        assert metrics["calibration_kappa"] == pytest.approx(0.84)

    # 2) Calibration fails -> non-fatal fallback
    state_err = await _init_state(
        tmp_path / "err",
        papers,
        screening=ScreeningConfig(
            max_llm_screen=5,
            stage1_include_threshold=0.85,
            calibrate_threshold=True,
            batch_screen_enabled=False,
        ),
        offline=False,
    )
    with (
        patch("src.orchestration.runners.screening_runner._llm_available", return_value=True),
        patch("src.orchestration.runners.screening_runner.PydanticAIScreeningClient", _DeterministicIncludeClient),
        patch("src.orchestration.runners.screening_runner.PDFRetriever", _FakePDFRetriever),
        patch(
            "src.screening.reliability.calibrate_threshold",
            new=AsyncMock(side_effect=RuntimeError("calibration failure")),
        ),
    ):
        await run_screening_node(state_err, _ctx(state_err))

    assert state_err.settings.screening.stage1_include_threshold == pytest.approx(0.85)
    assert len(state_err.included_papers) == 2
    state_err.run_context.emit_phase_done.assert_any_call(
        "screening_calibration",
        summary={"error": "calibration failure", "using_defaults": True},
    )

    # 3) Living-refresh delta run -> calibration skipped
    state_delta = await _init_state(
        tmp_path / "delta",
        papers,
        screening=ScreeningConfig(max_llm_screen=5, calibrate_threshold=True, batch_screen_enabled=False),
        offline=False,
    )
    state_delta.parent_db_path = str(tmp_path / "parent.db")
    with (
        patch("src.orchestration.runners.screening_runner._llm_available", return_value=True),
        patch("src.orchestration.runners.screening_runner.PydanticAIScreeningClient", _DeterministicIncludeClient),
        patch("src.orchestration.runners.screening_runner.PDFRetriever", _FakePDFRetriever),
        patch("src.screening.reliability.calibrate_threshold", new=AsyncMock()) as mock_cal_skip,
    ):
        await run_screening_node(state_delta, _ctx(state_delta))

    mock_cal_skip.assert_not_called()


async def test_screening_runner_batch_ranker_splits_forwards_and_exclusions(tmp_path: Path) -> None:
    """Batch pre-ranker forwards top slice, persists exclusions to DB, and records validation metrics."""
    papers = [_make_paper(f"p-{i}", title=f"Digital reminder medication adherence study {i}") for i in range(4)]
    state = await _init_state(
        tmp_path,
        papers,
        screening=ScreeningConfig(
            max_llm_screen=4,
            calibrate_threshold=False,
            batch_screen_enabled=True,
            batch_screen_threshold=0.25,
        ),
        offline=False,
    )

    class _FakeBatchRanker:
        def __init__(self, **_kwargs: object) -> None:
            self.validation_sampled_n = 1
            self.validation_npv = 0.95
            self.borderline_forwarded_n = 1

        async def rank_and_split(
            self, batch: list[CandidatePaper]
        ) -> tuple[list[CandidatePaper], list[ScreeningDecision]]:
            forwarded = batch[:2]
            excluded = [
                ScreeningDecision(
                    paper_id=p.paper_id,
                    decision=ScreeningDecisionType.EXCLUDE,
                    confidence=0.9,
                    reason="batch_screened_low|below threshold",
                    exclusion_reason=ExclusionReason.BATCH_SCREENED_LOW,
                    reviewer_type=ReviewerType.BATCH_RANKER,
                )
                for p in batch[2:]
            ]
            return forwarded, excluded

    with (
        patch("src.orchestration.runners.screening_runner._llm_available", return_value=True),
        patch("src.orchestration.runners.screening_runner.PydanticAIScreeningClient", _DeterministicIncludeClient),
        patch("src.orchestration.runners.screening_runner.PDFRetriever", _FakePDFRetriever),
        patch("src.screening.batch_ranker.BatchLLMRanker", _FakeBatchRanker),
        patch("src.screening.batch_ranker.PydanticAIBatchRankerClient", MagicMock),
    ):
        await run_screening_node(state, _ctx(state))

    assert state.batch_screen_forwarded == 2
    assert state.batch_screen_excluded == 2
    assert state.batch_screen_validation_n == 1
    assert state.batch_screen_validation_npv == pytest.approx(0.95)
    assert state.batch_screen_borderline_forwarded == 1
    assert len(state.included_papers) == 2

    batch_ev = next(e for e in _emitted_events(state.run_context) if e.get("type") == "batch_screen_done")
    assert batch_ev["scored"] == 4
    assert batch_ev["forwarded"] == 2
    assert batch_ev["excluded"] == 2
    assert batch_ev["reason_code"] == "batch_screened_low"

    async with get_db(state.db_path) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM screening_decisions WHERE workflow_id = ? AND reviewer_type = ?",
            (state.workflow_id, ReviewerType.BATCH_RANKER.value),
        )
        row = await cursor.fetchone()
        assert row is not None and row[0] == 2


async def test_screening_runner_batch_ranker_skips_already_processed_on_resume(tmp_path: Path) -> None:
    """When all papers already have title_abstract decisions, batch pre-ranker is skipped cleanly."""
    papers = [_make_paper("p-res-1"), _make_paper("p-res-2")]
    state = await _init_state(
        tmp_path,
        papers,
        screening=ScreeningConfig(
            max_llm_screen=5,
            calibrate_threshold=False,
            batch_screen_enabled=True,
        ),
        offline=False,
    )

    async with get_db(state.db_path) as db:
        repo = WorkflowRepository(db)
        for p in papers:
            await repo.save_screening_decision(
                state.workflow_id,
                "title_abstract",
                ScreeningDecision(
                    paper_id=p.paper_id,
                    decision=ScreeningDecisionType.INCLUDE,
                    confidence=0.95,
                    reason="Prior run include",
                    reviewer_type=ReviewerType.REVIEWER_A,
                ),
            )
            await repo.save_dual_screening_result(
                state.workflow_id,
                p.paper_id,
                "title_abstract",
                agreement=True,
                final_decision=ScreeningDecisionType.INCLUDE,
                adjudication_needed=False,
            )

    rank_mock = AsyncMock()
    with (
        patch("src.orchestration.runners.screening_runner._llm_available", return_value=True),
        patch("src.orchestration.runners.screening_runner.PydanticAIScreeningClient", _DeterministicIncludeClient),
        patch("src.orchestration.runners.screening_runner.PDFRetriever", _FakePDFRetriever),
        patch("src.screening.batch_ranker.BatchLLMRanker.rank_and_split", new=rank_mock),
    ):
        await run_screening_node(state, _ctx(state))

    rank_mock.assert_not_awaited()
    batch_ev = next(e for e in _emitted_events(state.run_context) if e.get("type") == "batch_screen_done")
    assert batch_ev["scored"] == 0
    assert batch_ev["skipped_resume"] == 2


async def test_screening_runner_fulltext_checkpoint_skip_and_stale_recovery(tmp_path: Path) -> None:
    """Valid phase_3b_fulltext checkpoint skips Stage 2; stale checkpoint without DB decisions re-runs Stage 2."""
    p_inc = _make_paper("p-ft-inc")
    p_exc = _make_paper("p-ft-exc")

    # 1) Valid phase_3b_fulltext checkpoint + DB fulltext decisions -> Stage 2 skipped
    state_valid = await _init_state(tmp_path / "valid", [p_inc, p_exc], offline=True)
    async with get_db(state_valid.db_path) as db:
        repo = WorkflowRepository(db)
        for pid in ("p-ft-inc", "p-ft-exc"):
            await repo.save_screening_decision(
                state_valid.workflow_id,
                "title_abstract",
                ScreeningDecision(
                    paper_id=pid,
                    decision=ScreeningDecisionType.INCLUDE,
                    confidence=0.9,
                    reason="TA include",
                    reviewer_type=ReviewerType.REVIEWER_A,
                ),
            )
            await repo.save_dual_screening_result(
                state_valid.workflow_id,
                pid,
                "title_abstract",
                agreement=True,
                final_decision=ScreeningDecisionType.INCLUDE,
                adjudication_needed=False,
            )
        await repo.save_screening_decision(
            state_valid.workflow_id,
            "fulltext",
            ScreeningDecision(
                paper_id="p-ft-inc",
                decision=ScreeningDecisionType.INCLUDE,
                confidence=0.92,
                reason="Fulltext include",
                reviewer_type=ReviewerType.REVIEWER_A,
            ),
        )
        await repo.save_dual_screening_result(
            state_valid.workflow_id,
            "p-ft-inc",
            "fulltext",
            agreement=True,
            final_decision=ScreeningDecisionType.INCLUDE,
            adjudication_needed=False,
        )
        await repo.save_screening_decision(
            state_valid.workflow_id,
            "fulltext",
            ScreeningDecision(
                paper_id="p-ft-exc",
                decision=ScreeningDecisionType.EXCLUDE,
                confidence=0.95,
                reason="No PDF",
                exclusion_reason=ExclusionReason.NO_FULL_TEXT,
                reviewer_type=ReviewerType.REVIEWER_A,
            ),
        )
        await repo.save_dual_screening_result(
            state_valid.workflow_id,
            "p-ft-exc",
            "fulltext",
            agreement=True,
            final_decision=ScreeningDecisionType.EXCLUDE,
            adjudication_needed=False,
        )
        await repo.save_checkpoint(state_valid.workflow_id, "phase_3b_fulltext", papers_processed=1)

    with patch("src.orchestration.runners.screening_runner.PDFRetriever") as mock_retriever:
        await run_screening_node(state_valid, _ctx(state_valid))

    mock_retriever.assert_not_called()
    assert [p.paper_id for p in state_valid.included_papers] == ["p-ft-inc"]
    assert state_valid.fulltext_sought == 2
    assert state_valid.fulltext_not_retrieved == 1

    # 2) Stale phase_3b_fulltext checkpoint (no fulltext decisions in DB) -> cleared and Stage 2 runs
    state_stale = await _init_state(tmp_path / "stale", [_make_paper("p-stale-1")])
    async with get_db(state_stale.db_path) as db:
        repo = WorkflowRepository(db)
        await repo.save_checkpoint(state_stale.workflow_id, "phase_3b_fulltext", papers_processed=0)

    with (
        patch("src.orchestration.runners.screening_runner._llm_available", return_value=True),
        patch("src.orchestration.runners.screening_runner.PydanticAIScreeningClient", _DeterministicIncludeClient),
        patch("src.orchestration.runners.screening_runner.PDFRetriever", _FakePDFRetriever),
    ):
        await run_screening_node(state_stale, _ctx(state_stale))

    assert [p.paper_id for p in state_stale.included_papers] == ["p-stale-1"]
    async with get_db(state_stale.db_path) as db:
        repo = WorkflowRepository(db)
        assert await repo.get_processed_paper_ids(state_stale.workflow_id, "fulltext") == {"p-stale-1"}


async def test_screening_runner_stage2_zero_decisions_resume_and_fallback(tmp_path: Path) -> None:
    """When Stage 2 returns 0 new decisions, load DB fulltext decisions if present or fall back to Stage 1."""
    paper = _make_paper("p-s2")

    async def _stage1_only_screen_batch(self, workflow_id: str, stage: str, papers, **_kwargs):
        _ = (self, workflow_id)
        if stage == "title_abstract":
            return [
                ScreeningDecision(
                    paper_id=p.paper_id,
                    decision=ScreeningDecisionType.INCLUDE,
                    confidence=0.9,
                    reason="TA include",
                    reviewer_type=ReviewerType.REVIEWER_A,
                )
                for p in papers
            ]
        return []

    # 1) DB has prior fulltext decisions -> screening_stage2_resume
    state_db = await _init_state(tmp_path / "db_resume", [paper], offline=True)
    async with get_db(state_db.db_path) as db:
        repo = WorkflowRepository(db)
        await repo.save_screening_decision(
            state_db.workflow_id,
            "fulltext",
            ScreeningDecision(
                paper_id="p-s2",
                decision=ScreeningDecisionType.INCLUDE,
                confidence=0.9,
                reason="Prior FT",
                reviewer_type=ReviewerType.REVIEWER_A,
            ),
        )
        await repo.save_dual_screening_result(
            state_db.workflow_id,
            "p-s2",
            "fulltext",
            agreement=True,
            final_decision=ScreeningDecisionType.INCLUDE,
            adjudication_needed=False,
        )

    with (
        patch("src.orchestration.runners.screening_runner.PDFRetriever", _FakePDFRetriever),
        patch(
            "src.screening.dual_screener.DualReviewerScreener.screen_batch",
            new=_stage1_only_screen_batch,
        ),
    ):
        await run_screening_node(state_db, _ctx(state_db))

    assert [p.paper_id for p in state_db.included_papers] == ["p-s2"]
    async with get_db(state_db.db_path) as db:
        cursor = await db.execute("SELECT decision_type FROM decision_log")
        types = {r[0] for r in await cursor.fetchall()}
        assert "screening_stage2_resume" in types

    # 2) DB has NO fulltext decisions -> screening_stage2_fallback
    state_fb = await _init_state(tmp_path / "fallback", [_make_paper("p-s2-fb")], offline=True)
    with (
        patch("src.orchestration.runners.screening_runner.PDFRetriever", _FakePDFRetriever),
        patch(
            "src.screening.dual_screener.DualReviewerScreener.screen_batch",
            new=_stage1_only_screen_batch,
        ),
    ):
        await run_screening_node(state_fb, _ctx(state_fb))

    assert [p.paper_id for p in state_fb.included_papers] == ["p-s2-fb"]
    async with get_db(state_fb.db_path) as db:
        cursor = await db.execute("SELECT decision_type FROM decision_log")
        types = {r[0] for r in await cursor.fetchall()}
        assert "screening_stage2_fallback" in types


async def test_screening_runner_citation_chasing_success_and_error_handling(tmp_path: Path) -> None:
    """Forward citation chasing appends newly included papers and gracefully survives chaser errors."""
    base_paper = _make_paper("p-base", doi="10.1000/base")
    chased_paper = _make_paper("p-chased", doi="10.1000/chased")

    # 1) Chasing succeeds
    state_ok = await _init_state(
        tmp_path / "chase_ok",
        [base_paper],
        search=SearchConfig(citation_chasing_enabled=True, citation_chasing_concurrency=2),
    )

    class _FakeChaserSuccess:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def chase_citations_to_search_results(self, included, known_dois, concurrency=5):
            _ = concurrency
            assert "10.1000/base" in known_dois
            assert len(included) == 1
            return [
                SearchResult(
                    workflow_id=state_ok.workflow_id,
                    database_name="citation_chasing",
                    source_category=SourceCategory.OTHER_SOURCE,
                    search_date="2026-11-14",
                    search_query="forward_citation_chasing",
                    limits_applied="max_per_paper=10",
                    records_retrieved=1,
                    papers=[chased_paper],
                )
            ]

    with (
        patch("src.orchestration.runners.screening_runner._llm_available", return_value=True),
        patch("src.orchestration.runners.screening_runner.PydanticAIScreeningClient", _DeterministicIncludeClient),
        patch("src.orchestration.runners.screening_runner.PDFRetriever", _FakePDFRetriever),
        patch("src.orchestration.runners.screening_runner.CitationChaser", _FakeChaserSuccess),
    ):
        await run_screening_node(state_ok, _ctx(state_ok))

    assert {p.paper_id for p in state_ok.included_papers} == {"p-base", "p-chased"}
    assert {p.paper_id for p in state_ok.deduped_papers} == {"p-base", "p-chased"}
    state_ok.run_context.emit_phase_done.assert_any_call(
        "citation_chasing",
        {"new_papers": 1, "chased_included": 1},
    )

    async with get_db(state_ok.db_path) as db:
        cursor = await db.execute(
            "SELECT source_phase, screening_status FROM study_cohort_membership WHERE workflow_id = ? AND paper_id = ?",
            (state_ok.workflow_id, "p-chased"),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert tuple(row) == ("phase_3_screening_citation_chasing", "included")

    # 2) Chasing fails -> non-fatal
    state_err = await _init_state(
        tmp_path / "chase_err",
        [base_paper],
        search=SearchConfig(citation_chasing_enabled=True),
    )

    class _FakeChaserFail:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def chase_citations_to_search_results(self, *_args, **_kwargs):
            raise RuntimeError("chaser timeout")

    with (
        patch("src.orchestration.runners.screening_runner._llm_available", return_value=True),
        patch("src.orchestration.runners.screening_runner.PydanticAIScreeningClient", _DeterministicIncludeClient),
        patch("src.orchestration.runners.screening_runner.PDFRetriever", _FakePDFRetriever),
        patch("src.orchestration.runners.screening_runner.CitationChaser", _FakeChaserFail),
    ):
        result = await run_screening_node(state_err, _ctx(state_err))

    assert result is None
    assert [p.paper_id for p in state_err.included_papers] == ["p-base"]
    state_err.run_context.emit_phase_done.assert_any_call(
        "citation_chasing",
        {"new_papers": 0, "error": "chaser timeout"},
    )


async def test_screening_runner_safeguard_gate_strict_blocks_and_sparse_continues(tmp_path: Path) -> None:
    """Strict safeguard gate without sparse continuation fails and returns End; sparse continuation warns."""
    paper = _make_paper("p-gate-1")

    # 1) Strict fail
    state_fail = await _init_state(
        tmp_path / "strict_fail",
        [paper],
        gates=GatesConfig(profile="strict", screening_minimum=5, sparse_topic_continuation=False),
    )
    with (
        patch("src.orchestration.runners.screening_runner._llm_available", return_value=True),
        patch("src.orchestration.runners.screening_runner.PydanticAIScreeningClient", _DeterministicIncludeClient),
        patch("src.orchestration.runners.screening_runner.PDFRetriever", _FakePDFRetriever),
    ):
        end_result = await run_screening_node(state_fail, _ctx(state_fail))

    assert isinstance(end_result, End)
    assert isinstance(end_result.data, WorkflowRunResult)
    assert end_result.data.status == WorkflowRunStatus.FAILED
    assert end_result.data.gate == "screening_safeguard"
    assert end_result.data.phase == "phase_3_screening"

    summary_data = json.loads(Path(state_fail.artifacts["run_summary"]).read_text(encoding="utf-8"))
    assert summary_data["status"] == "failed"
    assert summary_data["gate"] == "screening_safeguard"

    async with get_db(state_fail.db_path) as db:
        cursor = await db.execute("SELECT status FROM workflows WHERE workflow_id = ?", (state_fail.workflow_id,))
        row = await cursor.fetchone()
        assert row is not None and row[0] == "failed"

    reg = await find_by_workflow_id(state_fail.run_root, state_fail.workflow_id)
    assert reg is not None and reg.status == "failed"

    # 2) Sparse continuation active
    state_sparse = await _init_state(
        tmp_path / "sparse_ok",
        [paper],
        gates=GatesConfig(profile="strict", screening_minimum=5, sparse_topic_continuation=True),
    )
    with (
        patch("src.orchestration.runners.screening_runner._llm_available", return_value=True),
        patch("src.orchestration.runners.screening_runner.PydanticAIScreeningClient", _DeterministicIncludeClient),
        patch("src.orchestration.runners.screening_runner.PDFRetriever", _FakePDFRetriever),
    ):
        sparse_result = await run_screening_node(state_sparse, _ctx(state_sparse))

    assert sparse_result is None
    assert state_sparse.sparse_evidence_mode is True


async def test_screening_runner_partial_checkpoint_and_cohens_kappa(tmp_path: Path) -> None:
    """Partial interrupt saves status='partial'; dual-review pairs populate Cohen's kappa and reliability log."""
    paper = _make_paper("p-kappa-1")
    state = await _init_state(tmp_path, [paper], offline=True)
    state.run_context.should_proceed_with_partial.return_value = True

    fake_dual = DualScreeningResult(
        paper_id="p-kappa-1",
        reviewer_a=ScreeningDecision(
            paper_id="p-kappa-1",
            decision=ScreeningDecisionType.INCLUDE,
            confidence=0.9,
            reason="Include A",
            reviewer_type=ReviewerType.REVIEWER_A,
        ),
        reviewer_b=ScreeningDecision(
            paper_id="p-kappa-1",
            decision=ScreeningDecisionType.INCLUDE,
            confidence=0.88,
            reason="Include B",
            reviewer_type=ReviewerType.REVIEWER_B,
        ),
        agreement=True,
        final_decision=ScreeningDecisionType.INCLUDE,
    )

    async def _screen_with_dual(self, workflow_id: str, stage: str, papers, **_kwargs):
        _ = workflow_id
        if stage == "title_abstract":
            self._dual_results.append(fake_dual)
        return [
            ScreeningDecision(
                paper_id=p.paper_id,
                decision=ScreeningDecisionType.INCLUDE,
                confidence=0.9,
                reason="Include",
                reviewer_type=ReviewerType.REVIEWER_A,
            )
            for p in papers
        ]

    with (
        patch("src.orchestration.runners.screening_runner.PDFRetriever", _FakePDFRetriever),
        patch("src.screening.dual_screener.DualReviewerScreener.screen_batch", new=_screen_with_dual),
    ):
        result = await run_screening_node(state, _ctx(state))

    assert result is None
    assert state.kappa_stage == "title_abstract"
    assert state.kappa_n == 1
    assert state.cohens_kappa is not None

    async with get_db(state.db_path) as db:
        repo = WorkflowRepository(db)
        checkpoints = await repo.get_checkpoints(state.workflow_id)
        assert checkpoints["phase_3_screening"] == "partial"

        cursor = await db.execute("SELECT decision_type FROM decision_log")
        types = {r[0] for r in await cursor.fetchall()}
        assert "inter_rater_reliability" in types


async def test_screening_runner_uncapped_max_llm_screen_none_emits_prefilter_done(tmp_path: Path) -> None:
    """When max_llm_screen is None (e.g. max_quality profile), Phase 3 must emit prefilter telemetry without crashing."""
    papers = [_make_paper("p-uncapped-1"), _make_paper("p-uncapped-2")]
    state = await _init_state(
        tmp_path,
        papers,
        screening=ScreeningConfig(
            max_llm_screen=None,
            keyword_prefilter_fallback_exclusion_ratio=0.75,
            calibrate_threshold=False,
            batch_screen_enabled=False,
        ),
    )

    with (
        patch("src.orchestration.runners.screening_runner._llm_available", return_value=True),
        patch("src.orchestration.runners.screening_runner.PydanticAIScreeningClient", _DeterministicIncludeClient),
        patch("src.orchestration.runners.screening_runner.PDFRetriever", _FakePDFRetriever),
    ):
        result = await run_screening_node(state, _ctx(state))

    assert result is None
    assert {p.paper_id for p in state.included_papers} == {"p-uncapped-1", "p-uncapped-2"}
    pf = next(e for e in _emitted_events(state.run_context) if e.get("type") == "screening_prefilter_done")
    assert pf["dual_review_cap"] is None
    assert pf["keyword_fallback_threshold"] == pytest.approx(0.75)
    assert pf["to_llm"] == 2
