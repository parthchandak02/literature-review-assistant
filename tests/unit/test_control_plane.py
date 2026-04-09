"""Tests for the DB control-plane: step journal, recovery policies, writing manifests."""

from __future__ import annotations

import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.models.enums import FailureCategory, RecoveryAction, StepStatus
from src.models.workflow import (
    RecoveryPolicyRecord,
    WorkflowStepRecord,
    WritingManifestRecord,
)


@pytest.fixture
async def repo(tmp_path):
    db_path = str(tmp_path / "test_control_plane.db")
    async with get_db(db_path) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-test", "test topic", "abc123")
        yield repo


@pytest.mark.asyncio
async def test_save_and_load_workflow_step(repo):
    step = WorkflowStepRecord(
        step_id="step-001",
        workflow_id="wf-test",
        phase="phase_2_search",
        step_name="search_phase",
        status=StepStatus.RUNNING,
    )
    await repo.save_workflow_step(step)

    history = await repo.get_step_history("wf-test", "phase_2_search")
    assert len(history) == 1
    assert history[0].step_id == "step-001"
    assert history[0].status == StepStatus.RUNNING

    step.status = StepStatus.SUCCEEDED
    step.duration_ms = 1200
    await repo.save_workflow_step(step)

    history = await repo.get_step_history("wf-test", "phase_2_search")
    assert len(history) == 1
    assert history[0].status == StepStatus.SUCCEEDED
    assert history[0].duration_ms == 1200


@pytest.mark.asyncio
async def test_step_failure_with_category(repo):
    step = WorkflowStepRecord(
        step_id="step-002",
        workflow_id="wf-test",
        phase="phase_5c_pre_writing_gate",
        step_name="pre_writing_validation",
        status=StepStatus.FAILED,
        error_message="rag_chunk_coverage check failed",
        failure_category=FailureCategory.REWINDABLE,
        recovery_action=RecoveryAction.REWIND,
    )
    await repo.save_workflow_step(step)

    count = await repo.count_step_failures("wf-test")
    assert count == 1

    count_phase = await repo.count_step_failures("wf-test", "phase_5c_pre_writing_gate")
    assert count_phase == 1

    count_other = await repo.count_step_failures("wf-test", "phase_2_search")
    assert count_other == 0


@pytest.mark.asyncio
async def test_step_summary_aggregation(repo):
    for i, status in enumerate([StepStatus.SUCCEEDED, StepStatus.SUCCEEDED, StepStatus.FAILED]):
        step = WorkflowStepRecord(
            step_id=f"step-agg-{i}",
            workflow_id="wf-test",
            phase="phase_3_screening",
            step_name=f"screen_{i}",
            status=status,
        )
        await repo.save_workflow_step(step)

    summary = await repo.get_step_summary("wf-test")
    assert "phase_3_screening" in summary
    assert summary["phase_3_screening"]["succeeded"] == 2
    assert summary["phase_3_screening"]["failed"] == 1


@pytest.mark.asyncio
async def test_recovery_policy_create_and_increment(repo):
    policy = await repo.get_or_create_recovery_policy(
        "wf-test", "phase_5c_pre_writing_gate", "pre_writing_validation",
        max_retries=0, max_rewinds=1,
    )
    assert policy.max_rewinds == 1
    assert policy.current_rewinds == 0
    assert not policy.rewinds_exhausted

    new_count = await repo.increment_rewind_count(
        "wf-test", "phase_5c_pre_writing_gate", "pre_writing_validation",
    )
    assert new_count == 1

    policy2 = await repo.get_or_create_recovery_policy(
        "wf-test", "phase_5c_pre_writing_gate", "pre_writing_validation",
    )
    assert policy2.current_rewinds == 1
    assert policy2.rewinds_exhausted


@pytest.mark.asyncio
async def test_recovery_policy_retry_exhaustion(repo):
    policy = await repo.get_or_create_recovery_policy(
        "wf-test", "phase_6_writing", "section_write",
        max_retries=2, max_rewinds=0,
    )
    assert not policy.retries_exhausted

    await repo.increment_retry_count("wf-test", "phase_6_writing", "section_write")
    count = await repo.increment_retry_count("wf-test", "phase_6_writing", "section_write")
    assert count == 2

    policy2 = await repo.get_or_create_recovery_policy(
        "wf-test", "phase_6_writing", "section_write",
    )
    assert policy2.retries_exhausted
    assert policy2.status_label() == "exhausted"


@pytest.mark.asyncio
async def test_writing_manifest_save_and_load(repo):
    manifest = WritingManifestRecord(
        workflow_id="wf-test",
        section_key="results",
        attempt_number=1,
        grounding_hash="abc123",
        contract_status="passed",
        fallback_used=False,
        word_count=450,
    )
    await repo.save_writing_manifest(manifest)

    manifests = await repo.get_writing_manifests("wf-test", "results")
    assert len(manifests) == 1
    assert manifests[0].section_key == "results"
    assert manifests[0].word_count == 450
    assert manifests[0].contract_status == "passed"
    assert not manifests[0].fallback_used


@pytest.mark.asyncio
async def test_writing_manifest_fallback_tracking(repo):
    for sec in ["abstract", "methods", "results"]:
        m = WritingManifestRecord(
            workflow_id="wf-test",
            section_key=sec,
            attempt_number=1,
            contract_status="passed" if sec != "results" else "failed",
            fallback_used=sec == "results",
            word_count=300,
        )
        await repo.save_writing_manifest(m)

    all_manifests = await repo.get_writing_manifests("wf-test")
    assert len(all_manifests) == 3
    fallback_sections = [m.section_key for m in all_manifests if m.fallback_used]
    assert fallback_sections == ["results"]


@pytest.mark.asyncio
async def test_model_properties():
    step = WorkflowStepRecord(
        step_id="s1", workflow_id="wf", phase="p", step_name="n",
        status=StepStatus.SUCCEEDED,
    )
    assert step.is_terminal

    step2 = WorkflowStepRecord(
        step_id="s2", workflow_id="wf", phase="p", step_name="n",
        status=StepStatus.RUNNING,
    )
    assert not step2.is_terminal

    policy = RecoveryPolicyRecord(
        workflow_id="wf", phase="p", step_name="n",
        max_retries=3, max_rewinds=1,
        current_retries=3, current_rewinds=0,
    )
    assert policy.retries_exhausted
    assert not policy.rewinds_exhausted
    assert "exhausted" not in policy.status_label()

    policy2 = RecoveryPolicyRecord(
        workflow_id="wf", phase="p", step_name="n",
        max_retries=3, max_rewinds=1,
        current_retries=3, current_rewinds=1,
    )
    assert policy2.status_label() == "exhausted"


@pytest.mark.asyncio
async def test_writing_manifest_evidence_ids():
    m = WritingManifestRecord(
        workflow_id="wf", section_key="intro", attempt_number=1,
        evidence_source_ids='["p1", "p2", "p3"]',
        contract_issues='["missing_citations"]',
    )
    assert m.evidence_ids == ["p1", "p2", "p3"]
    assert m.issues == ["missing_citations"]


@pytest.mark.asyncio
async def test_rollback_clears_control_plane_tables(tmp_path):
    db_path = str(tmp_path / "test_rollback.db")
    async with get_db(db_path) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-rb", "rollback test", "hash")

        step = WorkflowStepRecord(
            step_id="step-rb-1",
            workflow_id="wf-rb",
            phase="phase_6_writing",
            step_name="writing_phase",
            status=StepStatus.SUCCEEDED,
        )
        await repo.save_workflow_step(step)
        await repo.get_or_create_recovery_policy(
            "wf-rb", "phase_6_writing", "section_write",
        )
        await repo.save_writing_manifest(WritingManifestRecord(
            workflow_id="wf-rb", section_key="results", attempt_number=1,
        ))

        history_before = await repo.get_step_history("wf-rb", "phase_6_writing")
        assert len(history_before) == 1

        await repo.rollback_phase_data("wf-rb", "phase_6_writing")

        history_after = await repo.get_step_history("wf-rb", "phase_6_writing")
        assert len(history_after) == 0

        manifests_after = await repo.get_writing_manifests("wf-rb")
        assert len(manifests_after) == 0
