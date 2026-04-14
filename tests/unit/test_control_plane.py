"""Tests for the DB control-plane: step journal, recovery policies, writing manifests."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

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


@pytest.mark.asyncio
async def test_reconcile_stale_running_steps_marks_superseded_attempts(repo):
    stale = WorkflowStepRecord(
        step_id="step-old",
        workflow_id="wf-test",
        phase="phase_6_writing",
        step_name="writing_phase",
        status=StepStatus.RUNNING,
    )
    current = WorkflowStepRecord(
        step_id="step-new",
        workflow_id="wf-test",
        phase="phase_6_writing",
        step_name="writing_phase",
        status=StepStatus.RUNNING,
    )
    await repo.save_workflow_step(stale)
    await repo.save_workflow_step(current)

    updated = await repo.reconcile_stale_running_steps(
        "wf-test",
        "phase_6_writing",
        "writing_phase",
        replacement_step_id="step-new",
    )
    history = await repo.get_step_history("wf-test", "phase_6_writing")
    by_id = {item.step_id: item for item in history}

    assert updated == 1
    assert by_id["step-old"].status == StepStatus.SKIPPED
    assert by_id["step-new"].status == StepStatus.RUNNING


# ---------------------------------------------------------------------------
# Enum validation guards -- prevent FailureCategory.GATE_FAILURE class of bug
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_journal_step_complete_rejects_invalid_failure_category(repo):
    """Passing a non-existent FailureCategory must raise ValueError immediately."""
    from src.orchestration.workflow import _journal_step_complete

    step = WorkflowStepRecord(
        step_id="step-bad-fc",
        workflow_id="wf-test",
        phase="phase_4_extraction_quality",
        step_name="extraction_quality",
        status=StepStatus.RUNNING,
    )
    await repo.save_workflow_step(step)

    with pytest.raises(ValueError, match="Invalid FailureCategory"):
        await _journal_step_complete(
            repo, step,
            status=StepStatus.FAILED,
            error_message="gate failed",
            failure_category="gate_failure",  # type: ignore[arg-type]
            recovery_action=RecoveryAction.ABORT,
        )


@pytest.mark.asyncio
async def test_journal_step_complete_rejects_invalid_recovery_action(repo):
    """Passing a non-existent RecoveryAction must raise ValueError immediately."""
    from src.orchestration.workflow import _journal_step_complete

    step = WorkflowStepRecord(
        step_id="step-bad-ra",
        workflow_id="wf-test",
        phase="phase_4_extraction_quality",
        step_name="extraction_quality",
        status=StepStatus.RUNNING,
    )
    await repo.save_workflow_step(step)

    with pytest.raises(ValueError, match="Invalid RecoveryAction"):
        await _journal_step_complete(
            repo, step,
            status=StepStatus.FAILED,
            error_message="gate failed",
            failure_category=FailureCategory.TERMINAL,
            recovery_action="stop",  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_journal_step_complete_rejects_invalid_step_status(repo):
    """Passing a non-existent StepStatus must raise ValueError immediately."""
    from src.orchestration.workflow import _journal_step_complete

    step = WorkflowStepRecord(
        step_id="step-bad-ss",
        workflow_id="wf-test",
        phase="phase_4_extraction_quality",
        step_name="extraction_quality",
        status=StepStatus.RUNNING,
    )
    await repo.save_workflow_step(step)

    with pytest.raises(ValueError, match="Invalid StepStatus"):
        await _journal_step_complete(
            repo, step,
            status="done",  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_journal_step_complete_accepts_all_valid_failure_categories(repo):
    """Every FailureCategory member must be accepted without error."""
    from src.orchestration.workflow import _journal_step_complete

    for i, fc in enumerate(FailureCategory):
        step = WorkflowStepRecord(
            step_id=f"step-fc-{i}",
            workflow_id="wf-test",
            phase="phase_4_extraction_quality",
            step_name="extraction_quality",
            status=StepStatus.RUNNING,
        )
        await repo.save_workflow_step(step)
        await _journal_step_complete(
            repo, step,
            status=StepStatus.FAILED,
            error_message=f"testing {fc.value}",
            failure_category=fc,
            recovery_action=RecoveryAction.ABORT,
        )
        assert step.failure_category == fc


@pytest.mark.asyncio
async def test_journal_step_complete_accepts_all_valid_recovery_actions(repo):
    """Every RecoveryAction member must be accepted without error."""
    from src.orchestration.workflow import _journal_step_complete

    for i, ra in enumerate(RecoveryAction):
        step = WorkflowStepRecord(
            step_id=f"step-ra-{i}",
            workflow_id="wf-test",
            phase="phase_5c_pre_writing_gate",
            step_name="pre_writing_validation",
            status=StepStatus.RUNNING,
        )
        await repo.save_workflow_step(step)
        await _journal_step_complete(
            repo, step,
            status=StepStatus.FAILED,
            error_message=f"testing {ra.value}",
            failure_category=FailureCategory.TERMINAL,
            recovery_action=ra,
        )
        assert step.recovery_action == ra


@pytest.mark.asyncio
async def test_journal_step_complete_allows_none_for_optional_enums(repo):
    """None must be valid for failure_category and recovery_action (success path)."""
    from src.orchestration.workflow import _journal_step_complete

    step = WorkflowStepRecord(
        step_id="step-none-ok",
        workflow_id="wf-test",
        phase="phase_2_search",
        step_name="search_phase",
        status=StepStatus.RUNNING,
    )
    await repo.save_workflow_step(step)
    await _journal_step_complete(repo, step)
    assert step.status == StepStatus.SUCCEEDED
    assert step.failure_category is None
    assert step.recovery_action is None


def test_workflow_step_record_rejects_invalid_enum_on_assignment():
    """Pydantic validate_assignment must reject invalid enum values."""
    step = WorkflowStepRecord(
        step_id="s1", workflow_id="wf", phase="p", step_name="n",
    )
    with pytest.raises(Exception):
        step.failure_category = "gate_failure"  # type: ignore[assignment]
    with pytest.raises(Exception):
        step.recovery_action = "stop"  # type: ignore[assignment]
    with pytest.raises(Exception):
        step.status = "done"  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Static source scan -- catch non-existent enum members at test time
# ---------------------------------------------------------------------------

_ENUM_MEMBERS = {
    "FailureCategory": {m.name for m in FailureCategory},
    "RecoveryAction": {m.name for m in RecoveryAction},
    "StepStatus": {m.name for m in StepStatus},
}


def _collect_enum_attr_accesses(source: str) -> list[tuple[int, str, str]]:
    """Parse source and return (lineno, EnumClass, MEMBER) for attribute accesses."""
    tree = ast.parse(source)
    hits: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in _ENUM_MEMBERS:
                hits.append((node.lineno, node.value.id, node.attr))
    return hits


def test_workflow_module_uses_only_valid_enum_members():
    """Scan src/orchestration/workflow.py for enum attribute accesses and
    verify every one refers to a real member.  This would have caught
    FailureCategory.GATE_FAILURE and RecoveryAction.STOP before runtime.
    """
    workflow_src = Path(inspect.getfile(
        __import__("src.orchestration.workflow", fromlist=["_journal_step_complete"])
    )).read_text(encoding="utf-8")

    accesses = _collect_enum_attr_accesses(workflow_src)
    assert accesses, "Expected at least one enum access in workflow.py"

    invalid: list[str] = []
    for lineno, cls_name, member_name in accesses:
        if member_name not in _ENUM_MEMBERS[cls_name]:
            invalid.append(
                f"  line {lineno}: {cls_name}.{member_name} "
                f"(valid: {sorted(_ENUM_MEMBERS[cls_name])})"
            )

    assert not invalid, (
        "workflow.py references non-existent enum members:\n"
        + "\n".join(invalid)
    )
