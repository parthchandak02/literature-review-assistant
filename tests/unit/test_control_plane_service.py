"""Unit tests for ControlPlaneService read facade."""

from __future__ import annotations

import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.models.enums import StepStatus
from src.models.workflow import RecoveryPolicyRecord, WorkflowStepRecord, WritingManifestRecord
from src.web.control_plane_service import ControlPlaneService


@pytest.fixture
async def control_plane(tmp_path):
    db_path = str(tmp_path / "control_plane_service.db")
    async with get_db(db_path) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-cp", "control plane topic", "hash")
        yield ControlPlaneService(repo), repo


@pytest.mark.asyncio
async def test_get_step_summary_delegates(control_plane):
    service, repo = control_plane
    await repo.save_workflow_step(
        WorkflowStepRecord(
            step_id="step-1",
            workflow_id="wf-cp",
            phase="phase_2_search",
            step_name="search_phase",
            status=StepStatus.SUCCEEDED,
        )
    )

    summary = await service.get_step_summary("wf-cp")
    assert summary["phase_2_search"]["succeeded"] == 1


@pytest.mark.asyncio
async def test_get_recovery_policies_delegates(control_plane):
    service, repo = control_plane
    await repo.get_or_create_recovery_policy(
        "wf-cp",
        "phase_6_writing",
        "section_write",
        max_retries=2,
        max_rewinds=1,
    )

    policies = await service.get_recovery_policies("wf-cp")
    assert len(policies) == 1
    assert policies[0].step_name == "section_write"
    assert policies[0].max_retries == 2


@pytest.mark.asyncio
async def test_get_writing_manifests_delegates(control_plane):
    service, repo = control_plane
    await repo.save_writing_manifest(
        WritingManifestRecord(
            workflow_id="wf-cp",
            section_key="abstract",
            attempt_number=1,
            contract_status="passed",
        )
    )

    manifests = await service.get_writing_manifests("wf-cp")
    assert len(manifests) == 1
    assert manifests[0].section_key == "abstract"


@pytest.mark.asyncio
async def test_get_snapshot_bundles_control_plane_reads(control_plane):
    service, repo = control_plane
    await repo.save_workflow_step(
        WorkflowStepRecord(
            step_id="step-fail",
            workflow_id="wf-cp",
            phase="phase_3_screening",
            step_name="screen",
            status=StepStatus.FAILED,
        )
    )
    await repo.get_or_create_recovery_policy("wf-cp", "phase_3_screening", "screen")
    await repo.save_writing_manifest(
        WritingManifestRecord(
            workflow_id="wf-cp",
            section_key="methods",
            attempt_number=1,
        )
    )

    snapshot = await service.get_snapshot("wf-cp")
    payload = snapshot.as_diagnostics_payload()

    assert snapshot.workflow_id == "wf-cp"
    assert snapshot.step_failures == 1
    assert snapshot.running_steps == 0
    assert len(snapshot.recovery_policies) == 1
    assert len(snapshot.writing_manifests) == 1
    assert payload["step_summary"]["phase_3_screening"]["failed"] == 1
    assert len(payload["recovery_policies"]) == 1
    assert payload["recovery_policies"][0]["step_name"] == "screen"


@pytest.mark.asyncio
async def test_list_recovery_policies_filters_by_phase(control_plane):
    _service, repo = control_plane
    await repo.get_or_create_recovery_policy("wf-cp", "phase_2_search", "search_phase")
    await repo.get_or_create_recovery_policy("wf-cp", "phase_6_writing", "section_write")

    all_policies = await repo.list_recovery_policies("wf-cp")
    writing_policies = await repo.list_recovery_policies("wf-cp", "phase_6_writing")

    assert len(all_policies) == 2
    assert len(writing_policies) == 1
    assert isinstance(writing_policies[0], RecoveryPolicyRecord)
