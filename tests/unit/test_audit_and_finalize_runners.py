"""Tests for Phase 7 manuscript audit and finalize runners.

Covers gate routing (missing manuscript, strict, needs_revision, advisory),
DB and registry state transitions, DB-backed audit context assembly,
PROSPERO artifact generation/supplementation, and finalize error/cost/lineage
reporting against real SQLite runtime and registry databases.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_graph import End, GraphRunContext

from src.citation.ledger import CitationLedger
from src.db.database import get_db
from src.db.repositories import CitationRepository, WorkflowRepository
from src.db.workflow_registry import find_by_workflow_id
from src.db.workflow_registry import register as register_workflow
from src.manuscript.contracts import ContractViolation, ManuscriptContractResult
from src.models import (
    CandidatePaper,
    CitationEntryRecord,
    CohortMembershipRecord,
    CostRecord,
    DomainExpertConfig,
    ExtractionRecord,
    FallbackEventRecord,
    ManuscriptAuditFinding,
    ManuscriptAuditResult,
    ReviewConfig,
    RiskOfBiasJudgment,
    RoB2Assessment,
    SettingsConfig,
    SourceCategory,
    StudyDesign,
)
from src.models.config import GatesConfig
from src.models.workflow import WorkflowRunResult, WorkflowRunStatus
from src.orchestration.nodes.finalize import FinalizeNode
from src.orchestration.nodes.manuscript_audit import ManuscriptAuditNode
from src.orchestration.runners.audit_runner import run_manuscript_audit_node
from src.orchestration.runners.finalize_runner import run_finalize_node, write_prospero_artifacts
from src.orchestration.state import ReviewState

_WORKFLOW_ID = "wf-audit-finalize-test"


def _build_review(*, registered: bool = False, registration_number: str = "") -> ReviewConfig:
    return ReviewConfig(
        research_question="How effective are digital reminders on medication adherence in primary care?",
        review_type="systematic",
        pico={
            "population": "Adult primary care patients prescribed chronic medications",
            "intervention": "Automated digital medication reminders",
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
        protocol={
            "registered": registered,
            "registration_number": registration_number,
            "registration_date": "2026-02-01" if registered else "",
        },
    )


def _build_settings(*, audit_gate_mode: str = "needs_revision") -> SettingsConfig:
    return SettingsConfig(
        agents={
            "screening_reviewer_a": {"model": "google:gemini-2.5-flash-lite", "temperature": 0.1},
            "writing": {"model": "google:gemini-2.5-pro", "temperature": 0.2},
        },
        gates=GatesConfig(
            profile="warning",
            audit_gate_mode=audit_gate_mode,
            manuscript_audit_mode="strict",
            manuscript_contract_mode="strict",
        ),
    )


def _passing_contract() -> ManuscriptContractResult:
    return ManuscriptContractResult(passed=True, mode="strict", violations=[])


def _failing_contract() -> ManuscriptContractResult:
    return ManuscriptContractResult(
        passed=False,
        mode="strict",
        violations=[
            ContractViolation(
                code="PLACEHOLDER_LEAK",
                severity="error",
                message="Unresolved placeholder leaked in manuscript.",
            )
        ],
    )


def _passing_audit(workflow_id: str = _WORKFLOW_ID) -> tuple[ManuscriptAuditResult, list[ManuscriptAuditFinding]]:
    return (
        ManuscriptAuditResult(
            audit_run_id="audit-pass-1",
            workflow_id=workflow_id,
            mode="strict",
            verdict="accept",
            passed=True,
            selected_profiles=["general_systematic_review"],
            summary="No blocking defects found.",
            total_findings=0,
            major_count=0,
            minor_count=0,
            note_count=0,
            blocking_count=0,
            total_cost_usd=0.01,
        ),
        [],
    )


def _failing_audit(workflow_id: str = _WORKFLOW_ID) -> tuple[ManuscriptAuditResult, list[ManuscriptAuditFinding]]:
    finding = ManuscriptAuditFinding(
        finding_id="f-block-1",
        profile="general_systematic_review",
        severity="major",
        category="coherence",
        section="Results",
        evidence="Included study total disagrees with PRISMA text.",
        recommendation="Reconcile included count across Results and abstract.",
        owner_module="writing",
        blocking=True,
    )
    return (
        ManuscriptAuditResult(
            audit_run_id="audit-fail-1",
            workflow_id=workflow_id,
            mode="strict",
            verdict="major_revisions",
            passed=False,
            selected_profiles=["general_systematic_review"],
            summary="Blocking coherence defect detected.",
            total_findings=1,
            major_count=1,
            minor_count=0,
            note_count=0,
            blocking_count=1,
            total_cost_usd=0.02,
        ),
        [finding],
    )


async def _init_state(
    tmp_path: Path,
    *,
    workflow_id: str = _WORKFLOW_ID,
    audit_gate_mode: str = "needs_revision",
    with_manuscript: bool = True,
    manuscript_text: str = "# Review\n\n## Abstract\n\nSummary text.\n\n## Methods\n\nMethods text.\n",
    registered: bool = False,
    registration_number: str = "",
) -> ReviewState:
    run_root = tmp_path / "runs"
    run_dir = run_root / "2026-11-14" / workflow_id / "run_01"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = run_dir / "runtime.db"
    summary_path = run_dir / "run_summary.json"
    manuscript_path = run_dir / "doc_manuscript.md"
    if with_manuscript:
        manuscript_path.write_text(manuscript_text, encoding="utf-8")

    review = _build_review(registered=registered, registration_number=registration_number)
    settings = _build_settings(audit_gate_mode=audit_gate_mode)

    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow(workflow_id, review.research_question, "cfg-hash-1")

    await register_workflow(
        run_root=str(run_root),
        workflow_id=workflow_id,
        topic=review.research_question,
        config_hash="cfg-hash-1",
        db_path=str(db_path),
        status="running",
    )

    rc = MagicMock()
    rc.verbose = False
    rc.debug = False
    rc.offline = False

    artifacts: dict[str, str] = {"run_summary": str(summary_path)}
    if with_manuscript:
        artifacts["manuscript_md"] = str(manuscript_path)

    return ReviewState(
        review_path=str(run_dir / "review.yaml"),
        settings_path=str(run_dir / "settings.yaml"),
        run_root=str(run_root),
        run_context=rc,
        run_id="20261114-031000",
        workflow_id=workflow_id,
        review=review,
        settings=settings,
        db_path=str(db_path),
        log_dir=str(run_dir),
        output_dir=str(run_dir),
        artifacts=artifacts,
        search_counts={"openalex": 12},
        search_queries={"openalex": "digital adherence"},
    )


def _ctx(state: ReviewState) -> GraphRunContext[ReviewState]:
    return GraphRunContext(state=state, deps=None)


@pytest.mark.asyncio
async def test_audit_runner_missing_manuscript_marks_failed_and_ends(tmp_path: Path) -> None:
    state = await _init_state(tmp_path, with_manuscript=False)

    result = await run_manuscript_audit_node(state, _ctx(state))

    assert isinstance(result, End)
    assert isinstance(result.data, WorkflowRunResult)
    assert result.data.status == WorkflowRunStatus.FAILED
    assert result.data.error == "manuscript_missing"
    assert result.data.phase == "phase_7_audit"

    summary = json.loads(Path(state.artifacts["run_summary"]).read_text(encoding="utf-8"))
    assert summary["status"] == "failed"
    assert summary["error"] == "manuscript_missing"

    async with get_db(state.db_path) as db:
        repo = WorkflowRepository(db)
        checkpoints = await repo.get_checkpoints(state.workflow_id)
        wf_row = await (
            await db.execute("SELECT status FROM workflows WHERE workflow_id = ?", (state.workflow_id,))
        ).fetchone()
    assert checkpoints["phase_7_audit"] == "partial"
    assert wf_row is not None and wf_row[0] == "failed"

    reg = await find_by_workflow_id(state.run_root, state.workflow_id)
    assert reg is not None and reg.status == "failed"
    state.run_context.emit_phase_done.assert_called_once_with(
        "phase_7_audit", {"status": "skipped", "reason": "manuscript_missing"}
    )


@pytest.mark.asyncio
async def test_audit_runner_strict_mode_blocks_and_ends_with_gate_blocked(tmp_path: Path) -> None:
    state = await _init_state(tmp_path, audit_gate_mode="strict")
    tex_path = Path(state.output_dir) / "doc_manuscript.tex"
    tex_path.write_text("\\section{Abstract}", encoding="utf-8")

    with (
        patch(
            "src.orchestration.runners.audit_runner.refresh_manuscript_export_artifacts",
            new=AsyncMock(return_value=str(tex_path)),
        ),
        patch(
            "src.orchestration.runners.audit_runner.run_manuscript_contracts",
            new=AsyncMock(return_value=_failing_contract()),
        ),
        patch(
            "src.orchestration.runners.audit_runner.run_manuscript_audit",
            new=AsyncMock(return_value=_failing_audit()),
        ),
    ):
        result = await run_manuscript_audit_node(state, _ctx(state))

    assert isinstance(result, End)
    assert result.data.status == WorkflowRunStatus.GATE_BLOCKED
    assert "contract gate failed" in (result.data.error or "")
    assert "audit gate failed" in (result.data.error or "")
    assert state.manuscript_gate_blocked is False

    summary = json.loads(Path(state.artifacts["run_summary"]).read_text(encoding="utf-8"))
    assert summary["status"] == "failed"
    assert summary["manuscript_audit"]["gate_blocked"] is True
    assert summary["manuscript_audit"]["gate_action"] == "strict_block"
    assert len(summary["manuscript_audit"]["gate_failure_reasons"]) == 2

    async with get_db(state.db_path) as db:
        repo = WorkflowRepository(db)
        checkpoints = await repo.get_checkpoints(state.workflow_id)
        wf_row = await (
            await db.execute("SELECT status FROM workflows WHERE workflow_id = ?", (state.workflow_id,))
        ).fetchone()
        audit_row = await (
            await db.execute(
                "SELECT gate_blocked, gate_mode, gate_action, contract_passed, total_findings "
                "FROM manuscript_audit_runs WHERE workflow_id = ?",
                (state.workflow_id,),
            )
        ).fetchone()
        finding_count = await (
            await db.execute(
                "SELECT COUNT(*) FROM manuscript_audit_findings WHERE workflow_id = ?",
                (state.workflow_id,),
            )
        ).fetchone()

    assert checkpoints["phase_7_audit"] == "blocked"
    assert wf_row is not None and wf_row[0] == "failed"
    assert audit_row is not None
    assert tuple(audit_row) == (1, "strict", "strict_block", 0, 1)
    assert finding_count is not None and finding_count[0] == 1

    reg = await find_by_workflow_id(state.run_root, state.workflow_id)
    assert reg is not None and reg.status == "failed"


@pytest.mark.asyncio
async def test_audit_runner_needs_revision_mode_marks_state_and_proceeds(tmp_path: Path) -> None:
    state = await _init_state(tmp_path, audit_gate_mode="needs_revision")

    with (
        patch(
            "src.orchestration.runners.audit_runner.refresh_manuscript_export_artifacts",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "src.orchestration.runners.audit_runner.run_manuscript_contracts",
            new=AsyncMock(return_value=_passing_contract()),
        ),
        patch(
            "src.orchestration.runners.audit_runner.run_manuscript_audit",
            new=AsyncMock(return_value=_failing_audit()),
        ),
    ):
        next_node = await ManuscriptAuditNode().run(_ctx(state))

    assert isinstance(next_node, FinalizeNode)
    assert state.manuscript_gate_blocked is True
    assert len(state.manuscript_gate_failure_reasons) == 1
    assert "audit gate failed" in state.manuscript_gate_failure_reasons[0]

    async with get_db(state.db_path) as db:
        checkpoints = await WorkflowRepository(db).get_checkpoints(state.workflow_id)
        wf_row = await (
            await db.execute("SELECT status FROM workflows WHERE workflow_id = ?", (state.workflow_id,))
        ).fetchone()
        audit_row = await (
            await db.execute(
                "SELECT gate_blocked, gate_mode, gate_action FROM manuscript_audit_runs WHERE workflow_id = ?",
                (state.workflow_id,),
            )
        ).fetchone()

    assert checkpoints["phase_7_audit"] == "completed"
    assert wf_row is not None and wf_row[0] == "running"
    assert audit_row is not None and tuple(audit_row) == (1, "needs_revision", "needs_revision")


@pytest.mark.asyncio
async def test_audit_runner_advisory_mode_does_not_block_state_when_audit_fails(tmp_path: Path) -> None:
    state = await _init_state(tmp_path, audit_gate_mode="advisory")

    with (
        patch(
            "src.orchestration.runners.audit_runner.refresh_manuscript_export_artifacts",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "src.orchestration.runners.audit_runner.run_manuscript_contracts",
            new=AsyncMock(return_value=_passing_contract()),
        ),
        patch(
            "src.orchestration.runners.audit_runner.run_manuscript_audit",
            new=AsyncMock(return_value=_failing_audit()),
        ),
    ):
        result = await run_manuscript_audit_node(state, _ctx(state))

    assert result is None
    assert state.manuscript_gate_blocked is False
    assert state.manuscript_gate_failure_reasons == []

    async with get_db(state.db_path) as db:
        checkpoints = await WorkflowRepository(db).get_checkpoints(state.workflow_id)
        audit_row = await (
            await db.execute(
                "SELECT gate_blocked, gate_mode, gate_action FROM manuscript_audit_runs WHERE workflow_id = ?",
                (state.workflow_id,),
            )
        ).fetchone()

    assert checkpoints["phase_7_audit"] == "completed"
    assert audit_row is not None and tuple(audit_row) == (1, "advisory", "advisory_only")


@pytest.mark.asyncio
async def test_audit_runner_tex_export_failure_is_non_fatal(tmp_path: Path) -> None:
    state = await _init_state(tmp_path, audit_gate_mode="strict")
    contracts_mock = AsyncMock(return_value=_passing_contract())

    with (
        patch(
            "src.orchestration.runners.audit_runner.refresh_manuscript_export_artifacts",
            new=AsyncMock(side_effect=RuntimeError("latex missing")),
        ),
        patch("src.orchestration.runners.audit_runner.run_manuscript_contracts", new=contracts_mock),
        patch(
            "src.orchestration.runners.audit_runner.run_manuscript_audit",
            new=AsyncMock(return_value=_passing_audit()),
        ),
    ):
        result = await run_manuscript_audit_node(state, _ctx(state))

    assert result is None
    assert contracts_mock.await_args is not None
    assert contracts_mock.await_args.kwargs["manuscript_tex_path"] is None


@pytest.mark.asyncio
async def test_audit_runner_exception_saves_partial_checkpoint_and_reraises(tmp_path: Path) -> None:
    state = await _init_state(tmp_path, audit_gate_mode="needs_revision")

    with (
        patch(
            "src.orchestration.runners.audit_runner.refresh_manuscript_export_artifacts",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "src.orchestration.runners.audit_runner.run_manuscript_contracts",
            new=AsyncMock(return_value=_passing_contract()),
        ),
        patch(
            "src.orchestration.runners.audit_runner.run_manuscript_audit",
            new=AsyncMock(side_effect=RuntimeError("audit provider crashed")),
        ),
    ):
        with pytest.raises(RuntimeError, match="audit provider crashed"):
            await run_manuscript_audit_node(state, _ctx(state))

    async with get_db(state.db_path) as db:
        checkpoints = await WorkflowRepository(db).get_checkpoints(state.workflow_id)
    assert checkpoints["phase_7_audit"] == "partial"


@pytest.mark.asyncio
async def test_audit_runner_passes_db_backed_counts_in_audit_context(tmp_path: Path) -> None:
    state = await _init_state(tmp_path, audit_gate_mode="needs_revision")
    paper = CandidatePaper(
        paper_id="p-ctx-1",
        title="Digital adherence trial",
        authors=["Author One"],
        year=2024,
        source_database="openalex",
        source_category=SourceCategory.DATABASE,
    )
    record = ExtractionRecord(
        paper_id="p-ctx-1",
        study_design=StudyDesign.RCT,
        intervention_description="SMS medication reminder",
        outcomes=[],
        results_summary={"summary": "Improved adherence."},
    )
    rob2 = RoB2Assessment(
        paper_id="p-ctx-1",
        domain_1_randomization=RiskOfBiasJudgment.LOW,
        domain_1_rationale="Adequate sequence.",
        domain_2_deviations=RiskOfBiasJudgment.LOW,
        domain_2_rationale="Low deviations.",
        domain_3_missing_data=RiskOfBiasJudgment.LOW,
        domain_3_rationale="Complete follow-up.",
        domain_4_measurement=RiskOfBiasJudgment.LOW,
        domain_4_rationale="Blinded outcome.",
        domain_5_selection=RiskOfBiasJudgment.LOW,
        domain_5_rationale="Pre-specified outcome.",
        overall_judgment=RiskOfBiasJudgment.LOW,
        overall_rationale="Low risk overall.",
    )

    async with get_db(state.db_path) as db:
        repo = WorkflowRepository(db)
        await repo.save_paper(paper)
        await repo.save_dedup_count(state.workflow_id, 5)
        await repo.bulk_upsert_cohort_memberships(
            [
                CohortMembershipRecord(
                    workflow_id=state.workflow_id,
                    paper_id="p-ctx-1",
                    screening_status="included",
                    fulltext_status="assessed",
                    synthesis_eligibility="included_primary",
                    source_phase="phase_4_extraction_quality",
                )
            ]
        )
        await repo.save_extraction_record(state.workflow_id, record)
        await repo.save_rob2_assessment(state.workflow_id, rob2)
        await repo.save_fallback_event(
            FallbackEventRecord(
                workflow_id=state.workflow_id,
                phase="phase_4_extraction_quality",
                module="quality.rob2",
                fallback_type="heuristic_fallback",
                reason="timeout",
                paper_id="p-ctx-1",
            )
        )

    audit_mock = AsyncMock(return_value=_passing_audit())
    with (
        patch(
            "src.orchestration.runners.audit_runner.refresh_manuscript_export_artifacts",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "src.orchestration.runners.audit_runner.run_manuscript_contracts",
            new=AsyncMock(return_value=_passing_contract()),
        ),
        patch("src.orchestration.runners.audit_runner.run_manuscript_audit", new=audit_mock),
    ):
        result = await run_manuscript_audit_node(state, _ctx(state))

    assert result is None
    assert audit_mock.await_args is not None
    context_payload = json.loads(audit_mock.await_args.kwargs["audit_context_json"])
    assert context_payload["db_backed_counts"] == {
        "deduplicated_records": 5,
        "included_primary_studies": 1,
        "extraction_records": 1,
        "grade_assessments": 0,
        "fallback_events_current_generation": 1,
    }
    assert context_payload["quality_assessment_counts"] == {
        "rob2": 1,
        "robins_i": 0,
        "casp": 0,
        "mmat": 0,
    }


@pytest.mark.asyncio
async def test_write_prospero_artifacts_validates_required_state(tmp_path: Path) -> None:
    state = await _init_state(tmp_path)
    state.review = None
    with pytest.raises(ValueError, match="requires state.review and state.output_dir"):
        await write_prospero_artifacts(state)

    state2 = await _init_state(tmp_path, workflow_id="wf-no-out")
    state2.output_dir = ""
    with pytest.raises(ValueError, match="requires state.review and state.output_dir"):
        await write_prospero_artifacts(state2)


@pytest.mark.asyncio
async def test_write_prospero_artifacts_intersects_manifest_with_included_cohort(tmp_path: Path) -> None:
    state = await _init_state(tmp_path)
    paper1 = CandidatePaper(
        paper_id="p-inc-1",
        title="Included Study",
        authors=["Smith A"],
        year=2024,
        source_database="openalex",
        source_category=SourceCategory.DATABASE,
    )
    paper2 = CandidatePaper(
        paper_id="p-excl-2",
        title="Excluded Study",
        authors=["Doe B"],
        year=2024,
        source_database="openalex",
        source_category=SourceCategory.DATABASE,
    )
    async with get_db(state.db_path) as db:
        repo = WorkflowRepository(db)
        await repo.save_paper(paper1)
        await repo.save_paper(paper2)
        await repo.bulk_upsert_cohort_memberships(
            [
                CohortMembershipRecord(
                    workflow_id=state.workflow_id,
                    paper_id="p-inc-1",
                    screening_status="included",
                    fulltext_status="assessed",
                    synthesis_eligibility="included_primary",
                    source_phase="phase_4_extraction_quality",
                ),
                CohortMembershipRecord(
                    workflow_id=state.workflow_id,
                    paper_id="p-excl-2",
                    screening_status="excluded",
                    fulltext_status="assessed",
                    synthesis_eligibility="excluded_screening",
                    source_phase="phase_3_screening",
                ),
            ]
        )

    manifest_path = Path(state.output_dir) / "papers_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "p-inc-1": {"file_path": "/tmp/p-inc-1.pdf"},
                "p-excl-2": {"file_path": "/tmp/p-excl-2.pdf"},
            }
        ),
        encoding="utf-8",
    )
    state.artifacts["papers_manifest"] = str(manifest_path)

    docx_path = await write_prospero_artifacts(state, state.run_context)

    assert docx_path == Path(state.output_dir) / "doc_prospero_registration.docx"
    assert docx_path.exists() and docx_path.stat().st_size > 0
    assert Path(state.artifacts["protocol"]).exists()
    md_path = Path(state.artifacts["prospero_form_md"])
    assert md_path.exists()
    md_text = md_path.read_text(encoding="utf-8")
    assert "Records after deduplication and screening: 1 studies included. Full texts retrieved: 1." in md_text


@pytest.mark.asyncio
async def test_write_prospero_artifacts_appends_supplement_idempotently_when_registered(tmp_path: Path) -> None:
    state = await _init_state(tmp_path, registered=True, registration_number="CRD42026000123")
    prospero_md = Path(state.output_dir) / "doc_prospero_registration.md"
    prospero_md.write_text("# PROSPERO Registration\n\nExisting protocol text.\n", encoding="utf-8")

    await write_prospero_artifacts(state, state.run_context)
    first_content = prospero_md.read_text(encoding="utf-8")
    assert first_content.count("## POST-RUN SEARCH COUNTS (SUPPLEMENT)") == 1
    assert "- openalex: 12 records" in first_content

    await write_prospero_artifacts(state, state.run_context)
    second_content = prospero_md.read_text(encoding="utf-8")
    assert second_content.count("## POST-RUN SEARCH COUNTS (SUPPLEMENT)") == 1
    assert Path(state.artifacts["prospero_form"]).exists()


@pytest.mark.asyncio
async def test_finalize_runner_clean_completion_aggregates_cohort_cost_and_lineage(tmp_path: Path) -> None:
    state = await _init_state(
        tmp_path,
        manuscript_text=(
            "# Review\n\n## Abstract\n\nClean abstract.\n\n"
            "## Results\n\nTrial results improved adherence [Smith2024].\n"
        ),
    )
    for pid in ("p-fin-1", "p-fin-2"):
        paper = CandidatePaper(
            paper_id=pid,
            title=f"Study {pid}",
            authors=["Smith J"],
            year=2024,
            source_database="openalex",
            source_category=SourceCategory.DATABASE,
        )
        async with get_db(state.db_path) as db:
            repo = WorkflowRepository(db)
            await repo.save_paper(paper)
            await repo.bulk_upsert_cohort_memberships(
                [
                    CohortMembershipRecord(
                        workflow_id=state.workflow_id,
                        paper_id=pid,
                        screening_status="included",
                        fulltext_status="assessed",
                        synthesis_eligibility="included_primary",
                        source_phase="phase_4_extraction_quality",
                    )
                ]
            )

    async with get_db(state.db_path) as db:
        repo = WorkflowRepository(db)
        await repo.save_cost_record(
            CostRecord(
                workflow_id=state.workflow_id,
                model="deepseek-v4p1-flash",
                tokens_in=100,
                tokens_out=50,
                cost_usd=0.12,
                latency_ms=250,
                phase="phase_3_screening",
            )
        )
        await repo.save_cost_record(
            CostRecord(
                workflow_id=state.workflow_id,
                model="glm-5p3",
                tokens_in=200,
                tokens_out=100,
                cost_usd=0.08,
                latency_ms=400,
                phase="phase_6_writing",
            )
        )
        await CitationLedger(CitationRepository(db)).register_citation(
            CitationEntryRecord(
                citekey="Smith2024",
                doi="10.1000/smith2024",
                title="Digital Adherence Trial",
                authors=["Smith J"],
                year=2024,
                journal="J Med Inform",
                resolved=True,
            )
        )

    with (
        patch(
            "src.orchestration.runners.finalize_runner.refresh_manuscript_export_artifacts",
            new=AsyncMock(return_value=str(Path(state.output_dir) / "doc_manuscript.tex")),
        ),
        patch(
            "src.export.submission_packager.package_submission",
            new=AsyncMock(return_value=Path(state.output_dir) / "submission"),
        ),
    ):
        end_result = await FinalizeNode().run(_ctx(state))

    assert isinstance(end_result, End)
    assert end_result.data.status == WorkflowRunStatus.COMPLETED

    summary = json.loads(Path(state.artifacts["run_summary"]).read_text(encoding="utf-8"))
    assert summary["status"] == "done"
    assert summary["included_papers"] == 2
    assert summary["total_cost"] == pytest.approx(0.20)
    assert summary["citation_lineage_valid"] is True
    assert summary["citation_lineage"] == {
        "valid": True,
        "unresolved_claim_count": 0,
        "unresolved_citation_count": 0,
    }

    async with get_db(state.db_path) as db:
        repo = WorkflowRepository(db)
        checkpoints = await repo.get_checkpoints(state.workflow_id)
        wf_row = await (
            await db.execute("SELECT status FROM workflows WHERE workflow_id = ?", (state.workflow_id,))
        ).fetchone()
        step_rows = await repo.get_step_history(state.workflow_id, phase="finalize")

    assert checkpoints["finalize"] == "completed"
    assert wf_row is not None and wf_row[0] == "completed"
    assert step_rows and step_rows[0].status.value == "succeeded"

    reg = await find_by_workflow_id(state.run_root, state.workflow_id)
    assert reg is not None and reg.status == "completed"


@pytest.mark.asyncio
async def test_audit_to_finalize_needs_revision_propagates_terminal_status(tmp_path: Path) -> None:
    state = await _init_state(tmp_path, audit_gate_mode="needs_revision")

    with (
        patch(
            "src.orchestration.runners.audit_runner.refresh_manuscript_export_artifacts",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "src.orchestration.runners.audit_runner.run_manuscript_contracts",
            new=AsyncMock(return_value=_failing_contract()),
        ),
        patch(
            "src.orchestration.runners.audit_runner.run_manuscript_audit",
            new=AsyncMock(return_value=_failing_audit()),
        ),
        patch(
            "src.orchestration.runners.finalize_runner.refresh_manuscript_export_artifacts",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "src.export.submission_packager.package_submission",
            new=AsyncMock(return_value=Path(state.output_dir) / "submission"),
        ),
    ):
        next_node = await ManuscriptAuditNode().run(_ctx(state))
        assert isinstance(next_node, FinalizeNode)
        end_result = await next_node.run(_ctx(state))

    assert isinstance(end_result, End)
    assert end_result.data.status == WorkflowRunStatus.NEEDS_REVISION

    summary = json.loads(Path(state.artifacts["run_summary"]).read_text(encoding="utf-8"))
    assert summary["status"] == "needs_revision"
    assert len(summary["gate_failure_reasons"]) == 2

    async with get_db(state.db_path) as db:
        repo = WorkflowRepository(db)
        checkpoints = await repo.get_checkpoints(state.workflow_id)
        wf_row = await (
            await db.execute("SELECT status FROM workflows WHERE workflow_id = ?", (state.workflow_id,))
        ).fetchone()

    assert checkpoints["phase_7_audit"] == "completed"
    assert checkpoints["finalize"] == "completed"
    assert wf_row is not None and wf_row[0] == "needs_revision"

    reg = await find_by_workflow_id(state.run_root, state.workflow_id)
    assert reg is not None and reg.status == "needs_revision"


@pytest.mark.asyncio
async def test_finalize_runner_export_and_packaging_errors_mark_failed_while_prospero_error_is_non_fatal(
    tmp_path: Path,
) -> None:
    state = await _init_state(tmp_path)

    with (
        patch(
            "src.orchestration.runners.finalize_runner.refresh_manuscript_export_artifacts",
            new=AsyncMock(side_effect=RuntimeError("unresolved citations")),
        ),
        patch(
            "src.orchestration.runners.finalize_runner.write_prospero_artifacts",
            new=AsyncMock(side_effect=RuntimeError("docx non-fatal")),
        ),
        patch(
            "src.export.submission_packager.package_submission",
            new=AsyncMock(side_effect=RuntimeError("package failed")),
        ),
    ):
        summary = await run_finalize_node(state, _ctx(state))

    assert summary["status"] == "failed"
    assert "LaTeX artifact generation failed: unresolved citations" in str(summary["error"])
    assert "submission pre-packaging failed: package failed" in str(summary["error"])
    assert "docx non-fatal" not in str(summary["error"])

    async with get_db(state.db_path) as db:
        repo = WorkflowRepository(db)
        checkpoints = await repo.get_checkpoints(state.workflow_id)
        wf_row = await (
            await db.execute("SELECT status FROM workflows WHERE workflow_id = ?", (state.workflow_id,))
        ).fetchone()
        step_rows = await repo.get_step_history(state.workflow_id, phase="finalize")

    assert checkpoints["finalize"] == "blocked"
    assert wf_row is not None and wf_row[0] == "failed"
    assert step_rows and step_rows[0].status.value == "failed"
    assert "unresolved citations" in (step_rows[0].error_message or "")

    reg = await find_by_workflow_id(state.run_root, state.workflow_id)
    assert reg is not None and reg.status == "failed"


@pytest.mark.asyncio
async def test_write_prospero_artifacts_falls_back_to_papers_dir_when_manifest_missing(tmp_path: Path) -> None:
    state = await _init_state(tmp_path)
    papers_dir = Path(state.output_dir) / "papers"
    papers_dir.mkdir(parents=True, exist_ok=True)
    (papers_dir / "study1.pdf").write_bytes(b"%PDF-1.4 content")
    (papers_dir / "study2.txt").write_text("full text content", encoding="utf-8")
    (papers_dir / "empty.pdf").write_bytes(b"")
    (papers_dir / "notes.md").write_text("ignored extension", encoding="utf-8")

    await write_prospero_artifacts(state, state.run_context)

    md_text = Path(state.artifacts["prospero_form_md"]).read_text(encoding="utf-8")
    assert "Full texts retrieved: 2." in md_text


@pytest.mark.asyncio
async def test_finalize_runner_missing_manuscript_marks_failed(tmp_path: Path) -> None:
    state = await _init_state(tmp_path, with_manuscript=False)

    with patch(
        "src.export.submission_packager.package_submission",
        new=AsyncMock(return_value=Path(state.output_dir) / "submission"),
    ):
        summary = await run_finalize_node(state, _ctx(state))

    assert summary["status"] == "failed"
    assert "manuscript_md missing or not found at finalize" in str(summary["error"])

    async with get_db(state.db_path) as db:
        checkpoints = await WorkflowRepository(db).get_checkpoints(state.workflow_id)
        wf_row = await (
            await db.execute("SELECT status FROM workflows WHERE workflow_id = ?", (state.workflow_id,))
        ).fetchone()
    assert checkpoints["finalize"] == "blocked"
    assert wf_row is not None and wf_row[0] == "failed"
