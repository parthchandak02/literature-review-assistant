import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.models import AgentConfig, SettingsConfig
from src.orchestration.gates import GateRunner


def _settings(profile: str) -> SettingsConfig:
    return SettingsConfig(
        agents={"search": AgentConfig(model="google:gemini-2.5-flash", temperature=0.1)},
        gates={"profile": profile},
    )


@pytest.mark.asyncio
async def test_all_gates_run_in_strict_mode(tmp_path) -> None:
    db_path = tmp_path / "strict.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf", "topic", "hash")
        runner = GateRunner(repo, _settings("strict"))
        results = [
            await runner.run_search_volume_gate("wf", "phase_1", total_records=10),
            await runner.run_screening_safeguard_gate("wf", "phase_1", passed_screening=1),
            await runner.run_extraction_completeness_gate("wf", "phase_1", completeness_ratio=0.5),
            await runner.run_citation_lineage_gate("wf", "phase_1", unresolved_items=1),
            await runner.run_cost_budget_gate("wf", "phase_1", total_cost=99.0),
            await runner.run_resume_integrity_gate("wf", "phase_1"),
        ]
        assert len(results) == 6
        assert any(result.status.value == "failed" for result in results)


@pytest.mark.asyncio
async def test_all_gates_run_in_warning_mode(tmp_path) -> None:
    db_path = tmp_path / "warning.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf", "topic", "hash")
        runner = GateRunner(repo, _settings("warning"))
        result = await runner.run_search_volume_gate("wf", "phase_1", total_records=10)
        assert result.status.value == "warning"


@pytest.mark.asyncio
async def test_search_volume_sparse_continuation_returns_warning(tmp_path) -> None:
    db_path = tmp_path / "search_sparse_warning.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf", "topic", "hash")
        settings = SettingsConfig(
            agents={"search": AgentConfig(model="google:gemini-2.5-flash", temperature=0.1)},
            search={"low_recall_warning_threshold": 10},
            gates={
                "profile": "strict",
                "search_volume_minimum": 50,
            },
        )
        runner = GateRunner(repo, settings)
        result = await runner.run_search_volume_gate("wf", "phase_2_search", total_records=33)
        assert result.status.value == "warning"
        assert "continuation=enabled" in (result.details or "")


@pytest.mark.asyncio
async def test_search_volume_below_sparse_min_fails(tmp_path) -> None:
    db_path = tmp_path / "search_sparse_fail.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf", "topic", "hash")
        settings = SettingsConfig(
            agents={"search": AgentConfig(model="google:gemini-2.5-flash", temperature=0.1)},
            search={"low_recall_warning_threshold": 10},
            gates={
                "profile": "strict",
                "search_volume_minimum": 50,
            },
        )
        runner = GateRunner(repo, settings)
        result = await runner.run_search_volume_gate("wf", "phase_2_search", total_records=5)
        assert result.status.value == "failed"


@pytest.mark.asyncio
async def test_screening_safeguard_sparse_continuation_returns_warning(tmp_path) -> None:
    db_path = tmp_path / "sparse_warning.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf", "topic", "hash")
        settings = SettingsConfig(
            agents={"search": AgentConfig(model="google:gemini-2.5-flash", temperature=0.1)},
            gates={
                "profile": "strict",
                "screening_minimum": 5,
                "sparse_topic_min": 2,
                "sparse_topic_continuation": True,
            },
        )
        runner = GateRunner(repo, settings)
        result = await runner.run_screening_safeguard_gate("wf", "phase_3_screening", passed_screening=3)
        assert result.status.value == "warning"
        assert "continuation=enabled" in (result.details or "")


@pytest.mark.asyncio
async def test_screening_safeguard_below_sparse_min_still_warns_with_continuation(tmp_path) -> None:
    db_path = tmp_path / "sparse_below_min_warn.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf", "topic", "hash")
        settings = SettingsConfig(
            agents={"search": AgentConfig(model="google:gemini-2.5-flash", temperature=0.1)},
            gates={
                "profile": "strict",
                "screening_minimum": 5,
                "sparse_topic_min": 2,
                "sparse_topic_continuation": True,
            },
        )
        runner = GateRunner(repo, settings)
        result = await runner.run_screening_safeguard_gate("wf", "phase_3_screening", passed_screening=1)
        assert result.status.value == "warning"
        assert "below_sparse_topic_min_continuation" in (result.details or "")


@pytest.mark.asyncio
async def test_screening_safeguard_zero_evidence_warns_with_continuation(tmp_path) -> None:
    db_path = tmp_path / "sparse_zero_warn.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf", "topic", "hash")
        settings = SettingsConfig(
            agents={"search": AgentConfig(model="google:gemini-2.5-flash", temperature=0.1)},
            gates={
                "profile": "strict",
                "screening_minimum": 5,
                "sparse_topic_min": 2,
                "sparse_topic_continuation": True,
            },
        )
        runner = GateRunner(repo, settings)
        result = await runner.run_screening_safeguard_gate("wf", "phase_3_screening", passed_screening=0)
        assert result.status.value == "warning"
        assert "zero_evidence_continuation" in (result.details or "")


@pytest.mark.asyncio
async def test_extraction_gate_fails_when_weak_evidence_rate_too_high(tmp_path) -> None:
    db_path = tmp_path / "weak_evidence_fail.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf", "topic", "hash")
        runner = GateRunner(repo, _settings("strict"))
        result = await runner.run_extraction_completeness_gate(
            "wf",
            "phase_4_extraction_quality",
            completeness_ratio=0.95,
            weak_evidence_rate=0.60,
            metric_details="included_records=10, summary_ratio=1.00, participant_ratio=0.50, fulltext_ratio=0.90",
        )
        assert result.status.value == "failed"
        assert "weak_evidence_rate=0.60" in (result.details or "")
