"""Tests for Phase 4 extraction and quality runner (`src/orchestration/runners/extraction_runner.py`).

Covers low-quality MMAT filtering rules, canonical cohort resolution fallback,
multi-tool quality routing (RoB 2, ROBINS-I, CASP, MMAT, not_applicable),
placeholder GRADE cleanup and outcome certainty aggregation, full-text and PDF
vision table outcome merging with manifest persistence, primary-study/scope/MMAT
filtering in both fresh extraction and quality-only resume paths, classifier and
extractor error recovery, abstract-only caution advisories, and strict
extraction completeness gate failure handling against real SQLite databases.
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
from src.fulltext import FullTextResult
from src.models import (
    CandidatePaper,
    CaspAssessment,
    DomainExpertConfig,
    ExtractionRecord,
    GRADECertainty,
    GRADEOutcomeAssessment,
    MmatAssessment,
    OutcomeRecord,
    PrimaryStudyStatus,
    ReviewConfig,
    RiskOfBiasJudgment,
    RoB2Assessment,
    RobinsIAssessment,
    RobinsIJudgment,
    ScreeningDecisionType,
    SettingsConfig,
    SourceCategory,
    StudyDesign,
)
from src.models.config import ExtractionConfig, GatesConfig, WritingConfig
from src.models.workflow import WorkflowRunResult, WorkflowRunStatus
from src.orchestration.runners.extraction_runner import (
    _should_exclude_low_quality_record,
    run_extraction_quality_node,
)
from src.orchestration.state import ReviewState

_WORKFLOW_ID = "wf-extraction-runner-test"


@pytest.fixture(autouse=True)
def _no_rate_limit_sleep():
    """Avoid real RPM sleeps in RateLimiter during unit tests."""
    with patch("src.llm.rate_limiter.RateLimiter.acquire", new=AsyncMock()):
        yield


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
            canonical_terms=["digital reminder", "medication adherence"],
        ),
        inclusion_criteria=["Empirical human studies reporting medication adherence outcomes"],
        exclusion_criteria=["Editorials and opinion pieces"],
        date_range_start=2018,
        date_range_end=2026,
        target_databases=["openalex"],
    )


def _build_settings(
    *,
    gates: GatesConfig | None = None,
    extraction: ExtractionConfig | None = None,
    writing: WritingConfig | None = None,
) -> SettingsConfig:
    return SettingsConfig(
        agents={
            "extractor": {"model": "google:gemini-2.5-flash", "temperature": 0.1},
            "study_type_detection": {"model": "google:gemini-2.5-flash-lite", "temperature": 0.1},
            "quality_assessment": {"model": "google:gemini-2.5-pro", "temperature": 0.1},
            "table_extraction": {"model": "google:gemini-2.5-flash", "temperature": 0.1},
        },
        gates=gates
        or GatesConfig(
            profile="warning",
            extraction_completeness_threshold=0.50,
            extraction_max_empty_rate=0.80,
            mmat_minimum_score=2,
        ),
        extraction=extraction
        or ExtractionConfig(
            extraction_concurrency=2,
            use_pdf_vision=True,
            pdf_vision_model="google:gemini-2.5-flash",
            full_text_min_chars=200,
        ),
        writing=writing or WritingConfig(abstract_only_caution_threshold=0.80),
    )


def _make_paper(
    paper_id: str,
    *,
    title: str = "Digital reminder randomized trial for medication adherence in primary care",
    abstract: str | None = (
        "This randomized primary care trial (n=240) evaluates a digital reminder intervention "
        "for medication adherence among adult patients with hypertension."
    ),
    year: int | None = 2024,
    doi: str | None = "10.1000/j.med.2024.001",
    url: str | None = "https://example.org/paper",
) -> CandidatePaper:
    return CandidatePaper(
        paper_id=paper_id,
        title=title,
        authors=["Smith, J.", "Lee, A."],
        year=year,
        source_database="openalex",
        source_category=SourceCategory.DATABASE,
        doi=doi,
        url=url,
        abstract=abstract,
    )


def _make_extraction_record(
    paper_id: str,
    *,
    study_design: StudyDesign = StudyDesign.RCT,
    primary_study_status: PrimaryStudyStatus = PrimaryStudyStatus.PRIMARY,
    intervention_description: str = "Automated SMS and app digital reminder sent daily to primary care patients.",
    summary: str = "Digital reminder group increased medication adherence to 84% vs 68% in usual care (p=0.002).",
    participant_count: int | None = 240,
    outcomes: list[OutcomeRecord] | None = None,
    extraction_source: str = "text",
) -> ExtractionRecord:
    return ExtractionRecord(
        paper_id=paper_id,
        study_design=study_design,
        primary_study_status=primary_study_status,
        participant_count=participant_count,
        participant_demographics="Adults aged 45-75 in outpatient clinics",
        intervention_description=intervention_description,
        comparator_description="Standard outpatient care",
        outcomes=outcomes
        if outcomes is not None
        else [
            OutcomeRecord(
                name="Medication adherence rate",
                description="Proportion of prescribed doses taken at 6 months",
                effect_size="OR=2.10",
                se="0.18",
                n="240",
            )
        ],
        results_summary={"summary": summary},
        extraction_source=extraction_source,  # type: ignore[arg-type]
    )


def _make_rob2(
    paper_id: str,
    *,
    overall: RiskOfBiasJudgment = RiskOfBiasJudgment.LOW,
    source: str = "llm",
    fallback_used: bool = False,
) -> RoB2Assessment:
    return RoB2Assessment(
        paper_id=paper_id,
        domain_1_randomization=overall,
        domain_1_rationale="Randomization assessed.",
        domain_2_deviations=overall,
        domain_2_rationale="Deviations assessed.",
        domain_3_missing_data=overall,
        domain_3_rationale="Missing data assessed.",
        domain_4_measurement=overall,
        domain_4_rationale="Measurement assessed.",
        domain_5_selection=overall,
        domain_5_rationale="Selection assessed.",
        overall_judgment=overall,
        overall_rationale="Overall RoB 2 rationale.",
        assessment_source=source,  # type: ignore[arg-type]
        fallback_used=fallback_used,
    )


def _make_robins_i(
    paper_id: str,
    *,
    overall: RobinsIJudgment = RobinsIJudgment.MODERATE,
    source: str = "llm",
    fallback_used: bool = False,
) -> RobinsIAssessment:
    return RobinsIAssessment(
        paper_id=paper_id,
        domain_1_confounding=overall,
        domain_1_rationale="Confounding assessed.",
        domain_2_selection=overall,
        domain_2_rationale="Selection assessed.",
        domain_3_classification=overall,
        domain_3_rationale="Classification assessed.",
        domain_4_deviations=overall,
        domain_4_rationale="Deviations assessed.",
        domain_5_missing_data=overall,
        domain_5_rationale="Missing data assessed.",
        domain_6_measurement=overall,
        domain_6_rationale="Measurement assessed.",
        domain_7_reported_result=overall,
        domain_7_rationale="Reported result assessed.",
        overall_judgment=overall,
        overall_rationale="Overall ROBINS-I rationale.",
        assessment_source=source,  # type: ignore[arg-type]
        fallback_used=fallback_used,
    )


def _make_casp(
    paper_id: str,
    *,
    source: str = "llm",
    fallback_used: bool = False,
) -> CaspAssessment:
    return CaspAssessment(
        paper_id=paper_id,
        design_appropriate=True,
        recruitment_strategy=True,
        data_collection_rigorous=True,
        reflexivity_considered=True,
        ethics_considered=True,
        analysis_rigorous=True,
        findings_clear=True,
        value_of_research=True,
        overall_summary="Qualitative findings met CASP rigor criteria.",
        assessment_source=source,  # type: ignore[arg-type]
        fallback_used=fallback_used,
    )


def _make_mmat(
    paper_id: str,
    *,
    score: int = 4,
    source: str = "llm",
    fallback_used: bool = False,
) -> MmatAssessment:
    return MmatAssessment(
        paper_id=paper_id,
        study_type="mixed_methods",
        screening_1_clear_question=True,
        screening_2_appropriate_data=True,
        criterion_1=score >= 1,
        criterion_2=score >= 2,
        criterion_3=score >= 3,
        criterion_4=score >= 4,
        criterion_5=score >= 5,
        overall_score=score,
        overall_summary=f"MMAT appraisal score {score}/5.",
        assessment_source=source,  # type: ignore[arg-type]
        fallback_used=fallback_used,
    )


async def _init_state(
    tmp_path: Path,
    papers: list[CandidatePaper],
    *,
    included_papers: list[CandidatePaper] | None = None,
    workflow_id: str = _WORKFLOW_ID,
    gates: GatesConfig | None = None,
    extraction: ExtractionConfig | None = None,
    writing: WritingConfig | None = None,
    offline: bool = False,
    verbose: bool = False,
) -> ReviewState:
    run_root = tmp_path / "runs"
    run_dir = run_root / "2026-11-15" / workflow_id / "run_01"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = run_dir / "runtime.db"
    summary_path = run_dir / "run_summary.json"
    papers_dir = run_dir / "papers"
    papers_manifest = run_dir / "papers_manifest.json"
    rob_fig = run_dir / "fig_rob_traffic_light.png"
    rob2_fig = run_dir / "fig_rob2_traffic_light.png"

    review = _build_review()
    settings = _build_settings(gates=gates, extraction=extraction, writing=writing)

    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow(workflow_id, review.research_question, "cfg-hash-extract")
        for p in papers:
            await repo.papers.save_paper(p)
        await db.commit()

    await register_workflow(
        run_root=str(run_root),
        workflow_id=workflow_id,
        topic=review.research_question,
        config_hash="cfg-hash-extract",
        db_path=str(db_path),
        status="running",
    )

    rc = MagicMock()
    rc.verbose = verbose
    rc.debug = True
    rc.offline = offline

    return ReviewState(
        review_path=str(run_dir / "review.yaml"),
        settings_path=str(run_dir / "settings.yaml"),
        run_root=str(run_root),
        run_context=rc,
        run_id="20261115-010550",
        workflow_id=workflow_id,
        review=review,
        settings=settings,
        db_path=str(db_path),
        log_dir=str(run_dir),
        output_dir=str(run_dir),
        dedup_count=len(papers),
        deduped_papers=list(papers),
        included_papers=list(included_papers) if included_papers is not None else list(papers),
        artifacts={
            "run_summary": str(summary_path),
            "papers_dir": str(papers_dir),
            "papers_manifest": str(papers_manifest),
            "rob_traffic_light": str(rob_fig),
            "rob2_traffic_light": str(rob2_fig),
        },
    )


def _ctx(state: ReviewState) -> GraphRunContext[ReviewState]:
    return GraphRunContext(state=state, deps=None)


def test_should_exclude_low_quality_record_branches() -> None:
    """Verify MMAT threshold and sanitized summary rules for low-quality exclusion."""
    nr_record = _make_extraction_record("p-nr", summary="No outcomes were reported in the available excerpt.")
    empty_record = _make_extraction_record("p-empty", summary="")
    substantive_record = _make_extraction_record(
        "p-sub",
        summary="Adherence improved by 16 percentage points in the digital reminder arm (p=0.01).",
    )
    malformed_summary_record = _make_extraction_record("p-mal", summary="")
    malformed_summary_record.results_summary = None  # type: ignore[assignment]

    # Disabled when mmat_minimum_score <= 0
    assert _should_exclude_low_quality_record(nr_record, mmat_score=0, mmat_minimum_score=0) is False
    # Kept when mmat_score meets or exceeds mmat_minimum_score
    assert _should_exclude_low_quality_record(nr_record, mmat_score=2, mmat_minimum_score=2) is False
    assert _should_exclude_low_quality_record(nr_record, mmat_score=4, mmat_minimum_score=2) is False
    # Excluded when below threshold and summary sanitizes to NR
    assert _should_exclude_low_quality_record(nr_record, mmat_score=1, mmat_minimum_score=2) is True
    assert _should_exclude_low_quality_record(empty_record, mmat_score=1, mmat_minimum_score=2) is True
    assert _should_exclude_low_quality_record(malformed_summary_record, mmat_score=1, mmat_minimum_score=2) is True
    # Kept when below threshold but summary contains reportable empirical findings
    assert _should_exclude_low_quality_record(substantive_record, mmat_score=1, mmat_minimum_score=2) is False


@pytest.mark.asyncio
async def test_extraction_runner_happy_path_routes_tools_aggregates_grade_and_saves_checkpoint(
    tmp_path: Path,
) -> None:
    """Exercise title/abstract cohort fallback, 5 study design routes, GRADE cleanup/aggregation, and checkpoint."""
    papers = [
        _make_paper("p-rct", title="RCT of digital reminder"),
        _make_paper("p-cohort", title="Cohort study of digital reminder"),
        _make_paper("p-qual", title="Qualitative study of digital reminder"),
        _make_paper("p-mixed", title="Mixed methods study of digital reminder"),
        _make_paper("p-dev", title="Development architecture of digital reminder"),
    ]
    # Start with empty state.included_papers so runner resolves from DB title_abstract includes
    state = await _init_state(tmp_path, papers, included_papers=[], offline=True, verbose=True)

    async with get_db(state.db_path) as db:
        repo = WorkflowRepository(db)
        for p in papers:
            await repo.save_dual_screening_result(
                state.workflow_id,
                p.paper_id,
                "title_abstract",
                agreement=True,
                final_decision=ScreeningDecisionType.INCLUDE,
                adjudication_needed=False,
            )
        # Insert a stale placeholder GRADE row directly in grade_assessments to verify cleanup
        placeholder_grade = GRADEOutcomeAssessment(
            outcome_name="primary_outcome",
            number_of_studies=1,
            study_designs="rct",
            starting_certainty=GRADECertainty.HIGH,
            risk_of_bias_downgrade=0,
            inconsistency_downgrade=0,
            indirectness_downgrade=0,
            imprecision_downgrade=0,
            publication_bias_downgrade=0,
            large_effect_upgrade=0,
            dose_response_upgrade=0,
            residual_confounding_upgrade=0,
            final_certainty=GRADECertainty.HIGH,
            justification="Stale placeholder row.",
        )
        await db.execute(
            "INSERT INTO grade_assessments (workflow_id, outcome_name, assessment_data, final_certainty) "
            "VALUES (?, ?, ?, ?)",
            (
                state.workflow_id,
                "primary_outcome",
                placeholder_grade.model_dump_json(),
                placeholder_grade.final_certainty.value,
            ),
        )
        await db.commit()

    designs_by_id = {
        "p-rct": StudyDesign.RCT,
        "p-cohort": StudyDesign.COHORT,
        "p-qual": StudyDesign.QUALITATIVE,
        "p-mixed": StudyDesign.MIXED_METHODS,
        "p-dev": StudyDesign.DEVELOPMENT_STUDY,
    }
    records_by_id = {
        "p-rct": _make_extraction_record(
            "p-rct",
            study_design=StudyDesign.RCT,
            outcomes=[OutcomeRecord(name="Medication adherence rate", effect_size="OR=2.1", se="0.2", n="200")],
        ),
        "p-cohort": _make_extraction_record(
            "p-cohort",
            study_design=StudyDesign.COHORT,
            outcomes=[OutcomeRecord(name="Medication adherence rate", effect_size="OR=1.6", se="0.3", n="150")],
        ),
        "p-qual": _make_extraction_record(
            "p-qual",
            study_design=StudyDesign.QUALITATIVE,
            outcomes=[OutcomeRecord(name="Patient satisfaction", description="High perceived utility")],
        ),
        "p-mixed": _make_extraction_record(
            "p-mixed",
            study_design=StudyDesign.MIXED_METHODS,
            outcomes=[OutcomeRecord(name="primary_outcome", description="Generic placeholder outcome")],
        ),
        "p-dev": _make_extraction_record(
            "p-dev",
            study_design=StudyDesign.DEVELOPMENT_STUDY,
            outcomes=[],
        ),
    }

    async def _classify(workflow_id: str, paper: CandidatePaper, *, abstract_only: bool = False) -> StudyDesign:
        _ = (workflow_id, abstract_only)
        return designs_by_id[paper.paper_id]

    async def _extract(
        *,
        workflow_id: str,
        paper: CandidatePaper,
        study_design: StudyDesign,
        full_text: str,
    ) -> ExtractionRecord:
        _ = (workflow_id, study_design, full_text)
        return records_by_id[paper.paper_id]

    with (
        patch("src.orchestration.runners.extraction_runner.StudyClassifier.classify", side_effect=_classify),
        patch("src.orchestration.runners.extraction_runner.ExtractionService.extract", side_effect=_extract),
        patch(
            "src.orchestration.runners.extraction_runner.Rob2Assessor.assess",
            new=AsyncMock(
                return_value=_make_rob2(
                    "p-rct",
                    overall=RiskOfBiasJudgment.SOME_CONCERNS,
                    source="heuristic",
                    fallback_used=True,
                )
            ),
        ),
        patch(
            "src.orchestration.runners.extraction_runner.RobinsIAssessor.assess",
            new=AsyncMock(
                return_value=_make_robins_i(
                    "p-cohort",
                    overall=RobinsIJudgment.MODERATE,
                    source="llm",
                    fallback_used=False,
                )
            ),
        ),
        patch(
            "src.orchestration.runners.extraction_runner.CaspAssessor.assess",
            new=AsyncMock(return_value=_make_casp("p-qual", source="heuristic", fallback_used=True)),
        ),
        patch(
            "src.orchestration.runners.extraction_runner.MmatAssessor.assess",
            new=AsyncMock(return_value=_make_mmat("p-mixed", score=4, source="llm", fallback_used=False)),
        ),
        patch("src.orchestration.runners.extraction_runner.render_rob_traffic_light") as mock_render_rob,
    ):
        result = await run_extraction_quality_node(state, _ctx(state))

    assert result is None
    assert {p.paper_id for p in state.included_papers} == set(designs_by_id)
    assert {r.paper_id for r in state.extraction_records} == set(designs_by_id)
    assert state.heuristic_assessment_count == 2
    assert state.excluded_non_primary_count == 0

    mock_render_rob.assert_called_once()
    assert mock_render_rob.call_args.kwargs["not_applicable_count"] == 1

    async with get_db(state.db_path) as db:
        repo = WorkflowRepository(db)
        saved_records = await repo.load_extraction_records(state.workflow_id)
        assert {r.paper_id for r in saved_records} == set(designs_by_id)

        rob2_rows, robins_i_rows = await repo.load_rob_assessments(state.workflow_id)
        casp_rows = await repo.load_casp_assessments(state.workflow_id)
        mmat_rows = await repo.load_mmat_assessments(state.workflow_id)
        assert [r.paper_id for r in rob2_rows] == ["p-rct"]
        assert [r.paper_id for r in robins_i_rows] == ["p-cohort"]
        assert [r.paper_id for r in casp_rows] == ["p-qual"]
        assert [r.paper_id for r in mmat_rows] == ["p-mixed"]

        grade_rows = await repo.load_grade_assessments(state.workflow_id)
        grade_by_outcome = {g.outcome_name: g for g in grade_rows}
        assert set(grade_by_outcome) == {"Medication adherence rate", "Patient satisfaction"}
        assert grade_by_outcome["Medication adherence rate"].number_of_studies == 2
        assert grade_by_outcome["Medication adherence rate"].risk_of_bias_downgrade == 1
        assert grade_by_outcome["Patient satisfaction"].number_of_studies == 1

        # Verify stale placeholder row was deleted from grade_assessments table
        cur = await db.execute(
            "SELECT COUNT(*) FROM grade_assessments WHERE workflow_id = ? AND outcome_name = 'primary_outcome'",
            (state.workflow_id,),
        )
        assert (await cur.fetchone())[0] == 0

        # Verify fallback events recorded for heuristic RoB2 and CASP assessments
        cur = await db.execute(
            "SELECT module, paper_id FROM fallback_events WHERE workflow_id = ? ORDER BY module",
            (state.workflow_id,),
        )
        fallback_rows = [(str(r[0]), str(r[1])) for r in await cur.fetchall()]
        assert fallback_rows == [("quality.casp", "p-qual"), ("quality.rob2", "p-rct")]

        # Verify decision_log entries for casp, mmat, and rob_not_applicable
        cur = await db.execute(
            "SELECT decision_type, paper_id, decision FROM decision_log WHERE phase = 'phase_4_extraction_quality'",
        )
        decisions = {(str(r[0]), str(r[1]), str(r[2])) for r in await cur.fetchall()}
        assert ("casp_assessment", "p-qual", "completed") in decisions
        assert ("mmat_assessment", "p-mixed", "completed") in decisions
        assert ("rob_not_applicable", "p-dev", "not_applicable") in decisions

        # Verify checkpoint and step journal succeeded
        cur = await db.execute(
            "SELECT papers_processed FROM checkpoints WHERE workflow_id = ? AND phase = 'phase_4_extraction_quality'",
            (state.workflow_id,),
        )
        cp_row = await cur.fetchone()
        assert cp_row is not None and int(cp_row[0]) == 5

        cur = await db.execute(
            "SELECT status FROM workflow_steps WHERE workflow_id = ? AND step_name = 'extraction_quality_phase'",
            (state.workflow_id,),
        )
        step_row = await cur.fetchone()
        assert step_row is not None and str(step_row[0]) == "succeeded"


@pytest.mark.asyncio
async def test_extraction_runner_fulltext_pdf_manifest_and_vision_table_merge(tmp_path: Path) -> None:
    """Exercise full-text fetch, PDF parse + fallback, PDF file/manifest writing, and vision table outcome merging."""
    p_pdf = _make_paper("p-pdf", title="PDF vision trial")
    p_text = _make_paper("p-text", title="Full-text XML trial")
    p_corrupt = _make_paper("p-corrupt", title="Corrupt PDF trial", abstract="Fallback abstract text for corrupt PDF.")
    papers = [p_pdf, p_text, p_corrupt]
    state = await _init_state(tmp_path, papers, offline=False, verbose=True)

    pdf_bytes = b"%PDF-1.4\n" + b"0" * 1200
    ft_by_doi = {
        p_pdf.paper_id: FullTextResult(text="", pdf_bytes=pdf_bytes, source="unpaywall_pdf"),
        p_text.paper_id: FullTextResult(
            text="Full article prose from Europe PMC with 240 adult patients. " * 10,
            pdf_bytes=None,
            source="europepmc",
        ),
        p_corrupt.paper_id: FullTextResult(text="", pdf_bytes=pdf_bytes, source="pmc_pdf"),
    }
    # Give each paper a distinct DOI so fetch_full_text can dispatch deterministically
    p_pdf.doi = "10.1000/pdf"
    p_text.doi = "10.1000/text"
    p_corrupt.doi = "10.1000/corrupt"
    doi_to_ft = {
        "10.1000/pdf": ft_by_doi["p-pdf"],
        "10.1000/text": ft_by_doi["p-text"],
        "10.1000/corrupt": ft_by_doi["p-corrupt"],
    }

    async def _fake_fetch_full_text(*, doi: str | None = None, **_kwargs: object) -> FullTextResult:
        return doi_to_doi_result(doi)

    def doi_to_doi_result(doi: str | None) -> FullTextResult:
        return doi_to_ft[str(doi)]

    parsed_calls: list[bytes] = []

    async def _fake_parse_pdf(raw_bytes: bytes) -> str:
        parsed_calls.append(raw_bytes)
        if len(parsed_calls) == 2:
            raise ValueError("corrupt PDF xref table")
        return "Parsed PDF body text describing randomized digital reminder trial (n=240)."

    observed_full_texts: dict[str, str] = {}

    async def _extract(
        *,
        workflow_id: str,
        paper: CandidatePaper,
        study_design: StudyDesign,
        full_text: str,
    ) -> ExtractionRecord:
        _ = (workflow_id, study_design)
        observed_full_texts[paper.paper_id] = full_text
        return _make_extraction_record(
            paper.paper_id,
            study_design=StudyDesign.RCT,
            outcomes=[OutcomeRecord(name="Medication adherence rate", effect_size="", se="", n="240")],
        )

    vision_outcomes = [
        OutcomeRecord(
            name="Medication adherence rate",
            description="6-month adherence from Table 2",
            effect_size="OR=2.45",
            se="0.15",
            n="240",
            p_value="0.001",
        )
    ]

    with (
        patch("src.orchestration.runners.extraction_runner._llm_available", return_value=True),
        patch("src.orchestration.runners.extraction_runner.get_chat_client", return_value=MagicMock()),
        patch("src.extraction.table_extraction.fetch_full_text", side_effect=_fake_fetch_full_text),
        patch("src.orchestration.runners.extraction_runner.parse_pdf_bytes_async", side_effect=_fake_parse_pdf),
        patch(
            "src.extraction.table_extraction.extract_tables_from_pdf",
            new=AsyncMock(return_value=vision_outcomes),
        ),
        patch(
            "src.orchestration.runners.extraction_runner.StudyClassifier.classify",
            new=AsyncMock(return_value=StudyDesign.RCT),
        ),
        patch("src.orchestration.runners.extraction_runner.ExtractionService.extract", side_effect=_extract),
        patch(
            "src.orchestration.runners.extraction_runner.Rob2Assessor.assess",
            new=AsyncMock(return_value=_make_rob2("p-pdf")),
        ),
        patch("src.orchestration.runners.extraction_runner.render_rob_traffic_light"),
    ):
        # Process sequentially so parse_pdf call order is deterministic
        state.settings.extraction.extraction_concurrency = 1
        result = await run_extraction_quality_node(state, _ctx(state))

    assert result is None
    assert "Parsed PDF body text" in observed_full_texts["p-pdf"]
    assert "Full article prose from Europe PMC" in observed_full_texts["p-text"]
    assert observed_full_texts["p-corrupt"] == "Fallback abstract text for corrupt PDF."

    # Verify PDF saved to papers_dir and papers_manifest.json populated
    saved_pdf = Path(state.artifacts["papers_dir"]) / "p-pdf.pdf"
    assert saved_pdf.exists()
    assert saved_pdf.read_bytes() == pdf_bytes

    manifest = json.loads(Path(state.artifacts["papers_manifest"]).read_text(encoding="utf-8"))
    assert set(manifest) == {"p-pdf", "p-text", "p-corrupt"}
    assert manifest["p-pdf"]["file_type"] == "pdf"
    assert manifest["p-pdf"]["source"] == "unpaywall_pdf"
    assert manifest["p-text"]["file_path"] is None
    assert manifest["p-text"]["source"] == "europepmc"

    # Verify vision outcome merge updated extraction_source and outcomes in DB
    async with get_db(state.db_path) as db:
        repo = WorkflowRepository(db)
        loaded = {r.paper_id: r for r in await repo.load_extraction_records(state.workflow_id)}
        assert loaded["p-pdf"].extraction_source == "hybrid"
        assert loaded["p-pdf"].outcomes[0].effect_size == "OR=2.45"
        assert loaded["p-text"].extraction_source == "europepmc"


@pytest.mark.asyncio
async def test_extraction_runner_filters_non_primary_scope_mismatch_and_low_quality_mmat(
    tmp_path: Path,
) -> None:
    """Verify non-primary status, explicit scope mismatch, and low-quality MMAT records are filtered before synthesis."""
    p_non_primary = _make_paper("p-non-primary", title="Scoping review of digital reminders")
    p_scope_bad = _make_paper("p-scope-bad", title="Surgical ward workflow")
    p_low_mmat = _make_paper("p-low-mmat", title="Pre-post pilot with no reportable data")
    p_keep = _make_paper("p-keep", title="Primary care digital reminder RCT")
    papers = [p_non_primary, p_scope_bad, p_low_mmat, p_keep]
    state = await _init_state(tmp_path, papers, offline=True)

    designs = {
        "p-non-primary": StudyDesign.NARRATIVE_REVIEW,
        "p-scope-bad": StudyDesign.RCT,
        "p-low-mmat": StudyDesign.PRE_POST,
        "p-keep": StudyDesign.RCT,
    }
    records = {
        "p-non-primary": _make_extraction_record(
            "p-non-primary",
            study_design=StudyDesign.NARRATIVE_REVIEW,
            primary_study_status=PrimaryStudyStatus.SECONDARY_REVIEW,
        ),
        "p-scope-bad": _make_extraction_record(
            "p-scope-bad",
            study_design=StudyDesign.RCT,
            primary_study_status=PrimaryStudyStatus.PRIMARY,
            intervention_description=(
                "This study does not describe a digital reminder intervention and is outside the scope "
                "of digital reminder medication adherence programs."
            ),
        ),
        "p-low-mmat": _make_extraction_record(
            "p-low-mmat",
            study_design=StudyDesign.PRE_POST,
            primary_study_status=PrimaryStudyStatus.PRIMARY,
            summary="No outcomes were reported in the available excerpt.",
        ),
        "p-keep": _make_extraction_record(
            "p-keep",
            study_design=StudyDesign.RCT,
            primary_study_status=PrimaryStudyStatus.PRIMARY,
        ),
    }

    async def _classify(workflow_id: str, paper: CandidatePaper, *, abstract_only: bool = False) -> StudyDesign:
        _ = (workflow_id, abstract_only)
        return designs[paper.paper_id]

    async def _extract(
        *,
        workflow_id: str,
        paper: CandidatePaper,
        study_design: StudyDesign,
        full_text: str,
    ) -> ExtractionRecord:
        _ = (workflow_id, study_design, full_text)
        return records[paper.paper_id]

    with (
        patch("src.orchestration.runners.extraction_runner.StudyClassifier.classify", side_effect=_classify),
        patch("src.orchestration.runners.extraction_runner.ExtractionService.extract", side_effect=_extract),
        patch(
            "src.orchestration.runners.extraction_runner.MmatAssessor.assess",
            new=AsyncMock(return_value=_make_mmat("p-low-mmat", score=1)),
        ),
        patch(
            "src.orchestration.runners.extraction_runner.Rob2Assessor.assess",
            new=AsyncMock(return_value=_make_rob2("p-keep")),
        ),
        patch("src.orchestration.runners.extraction_runner.render_rob_traffic_light"),
    ):
        result = await run_extraction_quality_node(state, _ctx(state))

    assert result is None
    assert state.excluded_non_primary_count == 1
    assert [p.paper_id for p in state.included_papers] == ["p-keep"]
    assert [r.paper_id for r in state.extraction_records] == ["p-keep"]

    async with get_db(state.db_path) as db:
        cur = await db.execute(
            "SELECT paper_id, synthesis_eligibility, exclusion_reason_code "
            "FROM study_cohort_membership WHERE workflow_id = ?",
            (state.workflow_id,),
        )
        cohort = {str(r[0]): (str(r[1]), r[2]) for r in await cur.fetchall()}
        assert cohort["p-non-primary"] == ("excluded_non_primary", "secondary_review")
        assert cohort["p-scope-bad"] == ("excluded_scope_mismatch", "wrong_intervention")
        assert cohort["p-low-mmat"] == ("excluded_low_quality", "low_quality_mmat")
        assert cohort["p-keep"] == ("included_primary", None)

        cur = await db.execute(
            "SELECT decision_type, paper_id, decision FROM decision_log WHERE phase = 'phase_4_extraction_quality'",
        )
        decisions = {(str(r[0]), str(r[1]), str(r[2])) for r in await cur.fetchall()}
        assert ("primary_data_filter", "p-non-primary", "exclude_non_primary") in decisions
        assert ("scope_filter", "p-scope-bad", "exclude_scope_mismatch") in decisions
        assert ("quality_exclusion", "p-low-mmat", "exclude_low_quality") in decisions


@pytest.mark.asyncio
async def test_extraction_runner_quality_only_resume_filters_and_retries(tmp_path: Path) -> None:
    """Exercise quality_only path when extraction_records already exist in SQLite on resume."""
    p_already = _make_paper("p-already")
    p_q_nonprimary = _make_paper("p-q-nonprimary")
    p_q_scope = _make_paper("p-q-scope")
    p_q_lowmmat = _make_paper("p-q-lowmmat")
    p_q_err = _make_paper("p-q-err")
    papers = [p_already, p_q_nonprimary, p_q_scope, p_q_lowmmat, p_q_err]
    state = await _init_state(tmp_path, papers, offline=True)

    async with get_db(state.db_path) as db:
        repo = WorkflowRepository(db)
        await repo.save_extraction_record(
            state.workflow_id,
            _make_extraction_record("p-already", study_design=StudyDesign.RCT),
        )
        await repo.save_rob2_assessment(state.workflow_id, _make_rob2("p-already"))

        await repo.save_extraction_record(
            state.workflow_id,
            _make_extraction_record(
                "p-q-nonprimary",
                study_design=StudyDesign.PROTOCOL,
                primary_study_status=PrimaryStudyStatus.PROTOCOL_ONLY,
            ),
        )
        # Simulate legacy row where column was 'unknown' while JSON payload holds protocol_only
        await db.execute(
            "UPDATE extraction_records SET primary_study_status = 'unknown' WHERE paper_id = 'p-q-nonprimary'"
        )
        await db.commit()
        await repo.save_extraction_record(
            state.workflow_id,
            _make_extraction_record(
                "p-q-scope",
                study_design=StudyDesign.RCT,
                intervention_description=(
                    "This study is not aligned with digital reminder interventions and is outside the scope "
                    "of digital reminder adherence."
                ),
            ),
        )
        await repo.save_extraction_record(
            state.workflow_id,
            _make_extraction_record(
                "p-q-lowmmat",
                study_design=StudyDesign.MIXED_METHODS,
                summary="No outcomes were reported in the available excerpt.",
            ),
        )
        await repo.save_extraction_record(
            state.workflow_id,
            _make_extraction_record("p-q-err", study_design=StudyDesign.RCT),
        )

    with (
        patch(
            "src.orchestration.runners.extraction_runner.ExtractionService.extract",
            new=AsyncMock(side_effect=AssertionError("extract should not be called when already_extracted")),
        ),
        patch(
            "src.extraction.table_extraction.fetch_full_text",
            new=AsyncMock(return_value=FullTextResult(text="", pdf_bytes=None, source="abstract")),
        ),
        patch(
            "src.orchestration.runners.extraction_runner.MmatAssessor.assess",
            new=AsyncMock(return_value=_make_mmat("p-q-lowmmat", score=1)),
        ),
        patch(
            "src.orchestration.runners.extraction_runner.Rob2Assessor.assess",
            new=AsyncMock(side_effect=RuntimeError("RoB2 service timeout")),
        ),
        patch("src.orchestration.runners.extraction_runner.render_rob_traffic_light"),
    ):
        result = await run_extraction_quality_node(state, _ctx(state))

    assert result is None
    assert state.excluded_non_primary_count == 1

    async with get_db(state.db_path) as db:
        cur = await db.execute(
            "SELECT paper_id, synthesis_eligibility, exclusion_reason_code "
            "FROM study_cohort_membership WHERE workflow_id = ?",
            (state.workflow_id,),
        )
        cohort = {str(r[0]): (str(r[1]), r[2]) for r in await cur.fetchall()}
        assert cohort["p-q-nonprimary"] == ("excluded_non_primary", "protocol_only")
        assert cohort["p-q-scope"] == ("excluded_scope_mismatch", "wrong_intervention")
        assert cohort["p-q-lowmmat"] == ("excluded_low_quality", "low_quality_mmat")

        cur = await db.execute(
            "SELECT decision_type, paper_id, decision FROM decision_log WHERE phase = 'phase_4_extraction_quality'",
        )
        decisions = {(str(r[0]), str(r[1]), str(r[2])) for r in await cur.fetchall()}
        assert ("primary_data_filter", "p-q-nonprimary", "exclude_non_primary") in decisions
        assert ("scope_filter", "p-q-scope", "exclude_scope_mismatch") in decisions
        assert ("quality_exclusion", "p-q-lowmmat", "exclude_low_quality") in decisions
        assert ("quality_retry_error", "p-q-err", "error") in decisions


@pytest.mark.asyncio
async def test_extraction_runner_classifier_fallback_extraction_error_and_abstract_only_advisory(
    tmp_path: Path,
) -> None:
    """Verify StudyClassifier fallback to NON_RANDOMIZED, extraction error recovery, and abstract-only advisory log."""
    p_cls_err = _make_paper("p-cls-err", title="Classifier error paper")
    p_ext_err = _make_paper("p-ext-err", title="Extraction error paper")
    state = await _init_state(
        tmp_path,
        [p_cls_err, p_ext_err],
        writing=WritingConfig(abstract_only_caution_threshold=0.50),
        offline=True,
    )

    observed_designs: dict[str, StudyDesign] = {}

    async def _extract(
        *,
        workflow_id: str,
        paper: CandidatePaper,
        study_design: StudyDesign,
        full_text: str,
    ) -> ExtractionRecord:
        _ = (workflow_id, full_text)
        observed_designs[paper.paper_id] = study_design
        if paper.paper_id == "p-ext-err":
            raise ValueError("unparseable extraction response")
        return _make_extraction_record(
            paper.paper_id,
            study_design=study_design,
            extraction_source="text",
        )

    with (
        patch(
            "src.orchestration.runners.extraction_runner.StudyClassifier.classify",
            new=AsyncMock(side_effect=RuntimeError("classifier unavailable")),
        ),
        patch("src.orchestration.runners.extraction_runner.ExtractionService.extract", side_effect=_extract),
        patch(
            "src.orchestration.runners.extraction_runner.RobinsIAssessor.assess",
            new=AsyncMock(return_value=_make_robins_i("p-cls-err")),
        ),
        patch("src.orchestration.runners.extraction_runner.render_rob_traffic_light"),
    ):
        result = await run_extraction_quality_node(state, _ctx(state))

    assert result is None
    assert observed_designs["p-cls-err"] == StudyDesign.NON_RANDOMIZED
    assert [r.paper_id for r in state.extraction_records] == ["p-cls-err"]

    async with get_db(state.db_path) as db:
        cur = await db.execute(
            "SELECT paper_id, synthesis_eligibility, exclusion_reason_code "
            "FROM study_cohort_membership WHERE workflow_id = ?",
            (state.workflow_id,),
        )
        cohort = {str(r[0]): (str(r[1]), r[2]) for r in await cur.fetchall()}
        assert cohort["p-cls-err"] == ("included_primary", None)
        assert cohort["p-ext-err"] == ("excluded_failed_extraction", "failed_extraction")

        cur = await db.execute(
            "SELECT decision_type, paper_id, decision FROM decision_log WHERE phase = 'phase_4_extraction_quality'",
        )
        decisions = {(str(r[0]), str(r[1]), str(r[2])) for r in await cur.fetchall()}
        assert ("study_design_classification", "p-cls-err", "non_randomized") in decisions
        assert ("extraction_error", "p-ext-err", "error") in decisions
        assert ("gate_advisory", "__pipeline__", "fulltext_retrieval_low") in decisions


@pytest.mark.asyncio
async def test_extraction_runner_strict_completeness_gate_failure_aborts_workflow(tmp_path: Path) -> None:
    """Verify strict extraction_completeness gate failure writes run_summary, marks DB/registry failed, and returns End."""
    p_weak = _make_paper("p-weak", title="Weak abstract-only study")
    state = await _init_state(
        tmp_path,
        [p_weak],
        gates=GatesConfig(
            profile="strict",
            extraction_completeness_threshold=0.90,
            extraction_max_empty_rate=0.10,
            mmat_minimum_score=0,
        ),
        offline=True,
    )

    weak_record = _make_extraction_record(
        "p-weak",
        study_design=StudyDesign.RCT,
        summary="Not reported",
        participant_count=None,
        extraction_source="text",
    )
    weak_record.participant_demographics = None

    with (
        patch(
            "src.orchestration.runners.extraction_runner.StudyClassifier.classify",
            new=AsyncMock(return_value=StudyDesign.RCT),
        ),
        patch(
            "src.orchestration.runners.extraction_runner.ExtractionService.extract",
            new=AsyncMock(return_value=weak_record),
        ),
        patch(
            "src.orchestration.runners.extraction_runner.Rob2Assessor.assess",
            new=AsyncMock(return_value=_make_rob2("p-weak")),
        ),
        patch("src.orchestration.runners.extraction_runner.render_rob_traffic_light") as mock_render_rob,
    ):
        result = await run_extraction_quality_node(state, _ctx(state))

    assert isinstance(result, End)
    assert isinstance(result.data, WorkflowRunResult)
    assert result.data.status == WorkflowRunStatus.FAILED
    assert result.data.phase == "phase_4_extraction_quality"
    assert result.data.gate == "extraction_completeness"
    assert "Extraction completeness gate failed" in (result.data.error or "")
    mock_render_rob.assert_not_called()

    summary_payload = json.loads(Path(state.artifacts["run_summary"]).read_text(encoding="utf-8"))
    assert summary_payload["status"] == "failed"
    assert summary_payload["gate"] == "extraction_completeness"
    assert summary_payload["phase"] == "phase_4_extraction_quality"

    reg_entry = await find_by_workflow_id(state.run_root, state.workflow_id)
    assert reg_entry is not None
    assert reg_entry.status == "failed"

    async with get_db(state.db_path) as db:
        cur = await db.execute(
            "SELECT status FROM workflows WHERE workflow_id = ?",
            (state.workflow_id,),
        )
        wf_row = await cur.fetchone()
        assert wf_row is not None and str(wf_row[0]) == "failed"

        cur = await db.execute(
            "SELECT status, failure_category, recovery_action "
            "FROM workflow_steps WHERE workflow_id = ? AND step_name = 'extraction_quality_phase'",
            (state.workflow_id,),
        )
        step_row = await cur.fetchone()
        assert step_row is not None
        assert (str(step_row[0]), str(step_row[1]), str(step_row[2])) == ("failed", "terminal", "abort")


@pytest.mark.asyncio
async def test_extraction_runner_quality_only_fulltext_pdf_and_not_applicable_grade(tmp_path: Path) -> None:
    """Exercise quality_only full-text text/PDF/error branches, not_applicable routing, and GRADE aggregation."""
    p_ft_text = _make_paper("p-ft-text", doi="10.1000/q-text")
    p_ft_pdf = _make_paper("p-ft-pdf", doi="10.1000/q-pdf")
    p_ft_badpdf = _make_paper("p-ft-badpdf", doi="10.1000/q-badpdf", abstract="Fallback abstract for bad PDF.")
    p_ft_exc = _make_paper("p-ft-exc", doi="10.1000/q-exc", abstract="Fallback abstract after fetch error.")
    papers = [p_ft_text, p_ft_pdf, p_ft_badpdf, p_ft_exc]
    state = await _init_state(tmp_path, papers, offline=True)

    async with get_db(state.db_path) as db:
        repo = WorkflowRepository(db)
        await repo.save_extraction_record(
            state.workflow_id,
            _make_extraction_record(
                "p-ft-text",
                study_design=StudyDesign.RCT,
                outcomes=[OutcomeRecord(name="Systolic BP reduction", effect_size="-8.2 mmHg", se="1.4", n="180")],
            ),
        )
        await repo.save_extraction_record(
            state.workflow_id,
            _make_extraction_record(
                "p-ft-pdf",
                study_design=StudyDesign.COHORT,
                outcomes=[OutcomeRecord(name="Systolic BP reduction", effect_size="-6.0 mmHg", se="1.8", n="210")],
            ),
        )
        await repo.save_extraction_record(
            state.workflow_id,
            _make_extraction_record(
                "p-ft-badpdf",
                study_design=StudyDesign.QUALITATIVE,
                outcomes=[OutcomeRecord(name="Clinician workflow acceptance", description="Positive acceptance")],
            ),
        )
        await repo.save_extraction_record(
            state.workflow_id,
            _make_extraction_record(
                "p-ft-exc",
                study_design=StudyDesign.DEVELOPMENT_STUDY,
                outcomes=[],
            ),
        )

    pdf_bytes = b"%PDF-1.4\n" + b"1" * 1200

    async def _fake_fetch(*, doi: str | None = None, **_kwargs: object) -> FullTextResult:
        if doi == "10.1000/q-text":
            return FullTextResult(text="Full text from PMC for quality retry. " * 10, pdf_bytes=None, source="pmc")
        if doi in {"10.1000/q-pdf", "10.1000/q-badpdf"}:
            return FullTextResult(text="", pdf_bytes=pdf_bytes, source="unpaywall_pdf")
        raise RuntimeError("upstream fulltext connector timeout")

    parse_calls = 0

    async def _fake_parse_pdf(_raw: bytes) -> str:
        nonlocal parse_calls
        parse_calls += 1
        if parse_calls == 2:
            raise ValueError("damaged PDF stream")
        return "Parsed PDF text for quality-only ROBINS-I assessment."

    observed_quality_texts: dict[str, str] = {}

    async def _rob2_assess(record: ExtractionRecord, full_text: str = "") -> RoB2Assessment:
        observed_quality_texts[record.paper_id] = full_text
        return _make_rob2(record.paper_id)

    async def _robins_assess(record: ExtractionRecord, full_text: str = "") -> RobinsIAssessment:
        observed_quality_texts[record.paper_id] = full_text
        return _make_robins_i(record.paper_id)

    async def _casp_assess(record: ExtractionRecord, full_text: str = "") -> CaspAssessment:
        observed_quality_texts[record.paper_id] = full_text
        return _make_casp(record.paper_id)

    state.settings.extraction.extraction_concurrency = 1
    with (
        patch("src.extraction.table_extraction.fetch_full_text", side_effect=_fake_fetch),
        patch("src.orchestration.runners.extraction_runner.parse_pdf_bytes_async", side_effect=_fake_parse_pdf),
        patch("src.orchestration.runners.extraction_runner.Rob2Assessor.assess", side_effect=_rob2_assess),
        patch("src.orchestration.runners.extraction_runner.RobinsIAssessor.assess", side_effect=_robins_assess),
        patch("src.orchestration.runners.extraction_runner.CaspAssessor.assess", side_effect=_casp_assess),
        patch("src.orchestration.runners.extraction_runner.render_rob_traffic_light") as mock_render_rob,
    ):
        result = await run_extraction_quality_node(state, _ctx(state))

    assert result is None
    assert "Full text from PMC for quality retry." in observed_quality_texts["p-ft-text"]
    assert observed_quality_texts["p-ft-pdf"] == "Parsed PDF text for quality-only ROBINS-I assessment."
    assert observed_quality_texts["p-ft-badpdf"] == "Fallback abstract for bad PDF."
    assert mock_render_rob.call_args.kwargs["not_applicable_count"] == 1

    async with get_db(state.db_path) as db:
        repo = WorkflowRepository(db)
        grades = {g.outcome_name: g for g in await repo.load_grade_assessments(state.workflow_id)}
        assert set(grades) == {"Systolic BP reduction", "Clinician workflow acceptance"}
        assert grades["Systolic BP reduction"].number_of_studies == 2


@pytest.mark.asyncio
async def test_extraction_runner_handles_fulltext_vision_and_grade_exceptions_gracefully(
    tmp_path: Path,
) -> None:
    """Verify full-text fetch failure, PDF vision failure, and GRADE aggregation error do not abort extraction."""
    p1 = _make_paper("p-resilient", abstract="Resilient abstract text with 150 participants.")
    state = await _init_state(tmp_path, [p1], offline=False, verbose=True)

    pdf_bytes = b"%PDF-1.4\n" + b"2" * 1200

    with (
        patch("src.orchestration.runners.extraction_runner._llm_available", return_value=True),
        patch("src.orchestration.runners.extraction_runner.get_chat_client", return_value=MagicMock()),
        patch(
            "src.extraction.table_extraction.fetch_full_text",
            new=AsyncMock(return_value=FullTextResult(text="Full text body. " * 20, pdf_bytes=pdf_bytes, source="pmc")),
        ),
        patch(
            "src.extraction.table_extraction.extract_tables_from_pdf",
            new=AsyncMock(side_effect=RuntimeError("vision endpoint 503")),
        ),
        patch(
            "src.orchestration.runners.extraction_runner.StudyClassifier.classify",
            new=AsyncMock(return_value=StudyDesign.RCT),
        ),
        patch(
            "src.orchestration.runners.extraction_runner.ExtractionService.extract",
            new=AsyncMock(return_value=_make_extraction_record("p-resilient", study_design=StudyDesign.RCT)),
        ),
        patch(
            "src.orchestration.runners.extraction_runner.Rob2Assessor.assess",
            new=AsyncMock(return_value=_make_rob2("p-resilient")),
        ),
        patch(
            "src.orchestration.runners.extraction_runner.GradeAssessor.assess_from_rob",
            side_effect=RuntimeError("GRADE calculation error"),
        ),
        patch("src.orchestration.runners.extraction_runner.render_rob_traffic_light"),
    ):
        result = await run_extraction_quality_node(state, _ctx(state))

    assert result is None
    assert [r.paper_id for r in state.extraction_records] == ["p-resilient"]
    assert state.extraction_records[0].extraction_source == "pmc"

