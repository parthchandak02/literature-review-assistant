"""Integration tests for quality gate strict-mode vs warning-mode behavior.

These tests prove that:
- In strict mode (default), failing gates produce GateStatus.FAILED
- In warning mode, the same failure produces GateStatus.WARNING (never raises)
- Passing gates always produce GateStatus.PASSED in both modes

This is critical: if these tests pass incorrectly, the entire quality assurance
layer of the pipeline is silently broken and manuscripts could be generated with
unverified citation lineage or incomplete extraction.
"""

from __future__ import annotations

import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.models import GateStatus, SettingsConfig
from src.models.config import GatesConfig
from src.orchestration.gates import GateRunner

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _strict_settings() -> SettingsConfig:
    return SettingsConfig(
        agents={
            "screening_reviewer_a": {"model": "google-gla:gemini-2.5-flash-lite", "temperature": 0.1},
        },
        gates=GatesConfig(profile="strict"),
    )


def _warning_settings() -> SettingsConfig:
    return SettingsConfig(
        agents={
            "screening_reviewer_a": {"model": "google-gla:gemini-2.5-flash-lite", "temperature": 0.1},
        },
        gates=GatesConfig(profile="warning"),
    )


# ---------------------------------------------------------------------------
# Citation lineage gate: strict mode fails when unresolved > 0
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_citation_gate_fails_in_strict_mode_when_unresolved(tmp_path) -> None:
    async with get_db(str(tmp_path / "strict.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-strict-cite", "topic", "hash")

        runner = GateRunner(repo, _strict_settings())
        result = await runner.run_citation_lineage_gate(
            workflow_id="wf-strict-cite",
            phase="phase_4_extraction_quality",
            unresolved_items=3,  # clearly failing
        )

    assert result.status == GateStatus.FAILED, (
        f"Citation gate with 3 unresolved items must be FAILED in strict mode, got {result.status}"
    )


@pytest.mark.asyncio
async def test_citation_gate_warns_in_warning_mode_when_unresolved(tmp_path) -> None:
    async with get_db(str(tmp_path / "warn.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-warn-cite", "topic", "hash")

        runner = GateRunner(repo, _warning_settings())
        result = await runner.run_citation_lineage_gate(
            workflow_id="wf-warn-cite",
            phase="phase_4_extraction_quality",
            unresolved_items=3,
        )

    assert result.status == GateStatus.WARNING, (
        f"Citation gate with 3 unresolved items must be WARNING in warning mode, got {result.status}"
    )


@pytest.mark.asyncio
async def test_citation_gate_passes_when_no_unresolved(tmp_path) -> None:
    async with get_db(str(tmp_path / "pass.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-pass-cite", "topic", "hash")

        runner = GateRunner(repo, _strict_settings())
        result = await runner.run_citation_lineage_gate(
            workflow_id="wf-pass-cite",
            phase="phase_4_extraction_quality",
            unresolved_items=0,
        )

    assert result.status == GateStatus.PASSED


# ---------------------------------------------------------------------------
# Extraction completeness gate: strict mode fails below threshold
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extraction_gate_fails_in_strict_mode_below_threshold(tmp_path) -> None:
    async with get_db(str(tmp_path / "ext_strict.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-strict-ext", "topic", "hash")

        runner = GateRunner(repo, _strict_settings())
        # Default threshold is 0.80; 0.50 should fail
        result = await runner.run_extraction_completeness_gate(
            workflow_id="wf-strict-ext",
            phase="phase_4_extraction_quality",
            completeness_ratio=0.50,
        )

    assert result.status == GateStatus.FAILED, (
        f"Extraction gate at 0.50 ratio must be FAILED in strict mode, got {result.status}"
    )


@pytest.mark.asyncio
async def test_extraction_gate_warns_in_warning_mode_below_threshold(tmp_path) -> None:
    async with get_db(str(tmp_path / "ext_warn.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-warn-ext", "topic", "hash")

        runner = GateRunner(repo, _warning_settings())
        result = await runner.run_extraction_completeness_gate(
            workflow_id="wf-warn-ext",
            phase="phase_4_extraction_quality",
            completeness_ratio=0.50,
        )

    assert result.status == GateStatus.WARNING


@pytest.mark.asyncio
async def test_extraction_gate_passes_above_threshold(tmp_path) -> None:
    async with get_db(str(tmp_path / "ext_pass.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-pass-ext", "topic", "hash")

        runner = GateRunner(repo, _strict_settings())
        result = await runner.run_extraction_completeness_gate(
            workflow_id="wf-pass-ext",
            phase="phase_4_extraction_quality",
            completeness_ratio=0.95,
        )

    assert result.status == GateStatus.PASSED


# ---------------------------------------------------------------------------
# Search volume gate: strict mode fails below minimum
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_volume_gate_fails_in_strict_mode(tmp_path) -> None:
    async with get_db(str(tmp_path / "sv_strict.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-strict-sv", "topic", "hash")

        runner = GateRunner(repo, _strict_settings())
        # Default minimum is 10; 0 results should fail
        result = await runner.run_search_volume_gate(
            workflow_id="wf-strict-sv",
            phase="phase_2_search",
            total_records=0,
        )

    assert result.status == GateStatus.FAILED


@pytest.mark.asyncio
async def test_search_volume_gate_warns_in_warning_mode(tmp_path) -> None:
    async with get_db(str(tmp_path / "sv_warn.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-warn-sv", "topic", "hash")

        runner = GateRunner(repo, _warning_settings())
        result = await runner.run_search_volume_gate(
            workflow_id="wf-warn-sv",
            phase="phase_2_search",
            total_records=0,
        )

    assert result.status == GateStatus.WARNING


# ---------------------------------------------------------------------------
# Gate results are persisted to the database (audit trail)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gate_result_is_persisted(tmp_path) -> None:
    """Every gate run must write to gate_results so the audit trail is complete."""
    async with get_db(str(tmp_path / "persist.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-persist", "topic", "hash")

        runner = GateRunner(repo, _strict_settings())
        await runner.run_citation_lineage_gate(
            workflow_id="wf-persist",
            phase="phase_4",
            unresolved_items=1,
        )
        await runner.run_extraction_completeness_gate(
            workflow_id="wf-persist",
            phase="phase_4",
            completeness_ratio=0.7,
        )

        cursor = await db.execute(
            "SELECT gate_name, status FROM gate_results WHERE workflow_id = ?",
            ("wf-persist",),
        )
        rows = await cursor.fetchall()
        gate_names = {str(r[0]) for r in rows}
        statuses = {str(r[1]) for r in rows}

    assert "citation_lineage" in gate_names
    assert "extraction_completeness" in gate_names
    assert GateStatus.FAILED.value in statuses, "Failed gates must be persisted with FAILED status"
