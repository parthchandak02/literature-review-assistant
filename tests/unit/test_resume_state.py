"""Unit tests for resume state loading."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.db.workflow_registry import RegistryEntry
from src.models import CandidatePaper, SectionDraft
from src.models.enums import ScreeningDecisionType, SourceCategory
from src.orchestration import workflow as workflow_module
from src.orchestration.resume import load_resume_state
from src.orchestration.state import ReviewState
from src.orchestration.workflow import _rc_print


@pytest.mark.asyncio
async def test_load_resume_state_phase3(tmp_path) -> None:
    run_dir = tmp_path / "2026-02-16" / "how-do-ai-tutors-impact-learning" / "run_01-00-00PM"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = run_dir / "runtime.db"
    async with get_db(str(db_path)) as db:
        await db.executescript(Path("src/db/schema.sql").read_text())
        await db.commit()
        repo = WorkflowRepository(db)
        await repo.save_paper(
            CandidatePaper(
                paper_id="p1",
                title="Paper 1",
                authors=["A"],
                source_database="openalex",
                source_category=SourceCategory.DATABASE,
            )
        )
        await repo.save_paper(
            CandidatePaper(
                paper_id="p2",
                title="Paper 2",
                authors=["B"],
                source_database="openalex",
                source_category=SourceCategory.DATABASE,
            )
        )
        await repo.create_workflow("wf-resume", "How do AI tutors impact learning?", "abc123")
        await repo.save_checkpoint("wf-resume", "phase_2_search", papers_processed=2)
        await repo.save_dual_screening_result(
            "wf-resume", "p1", "title_abstract", True, ScreeningDecisionType.INCLUDE, False
        )
        await repo.save_dual_screening_result("wf-resume", "p1", "fulltext", True, ScreeningDecisionType.INCLUDE, False)

    state, next_phase = await load_resume_state(
        db_path=str(db_path),
        workflow_id="wf-resume",
        review_path="config/review.yaml",
        settings_path="config/settings.yaml",
        run_root=str(tmp_path),
    )
    assert isinstance(state, ReviewState)
    assert state.workflow_id == "wf-resume"
    assert next_phase == "phase_3_screening"
    assert len(state.deduped_papers) >= 1
    assert len(state.included_papers) == 1
    assert state.included_papers[0].paper_id == "p1"


@pytest.mark.asyncio
async def test_load_resume_state_from_phase(tmp_path) -> None:
    """Resume from a specific phase clears checkpoints for that phase and later."""
    run_dir = tmp_path / "2026-02-16" / "topic" / "run_01-00-00PM"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = run_dir / "runtime.db"
    async with get_db(str(db_path)) as db:
        await db.executescript(Path("src/db/schema.sql").read_text())
        await db.commit()
        repo = WorkflowRepository(db)
        await repo.save_paper(
            CandidatePaper(
                paper_id="p1",
                title="Paper 1",
                authors=["A"],
                source_database="openalex",
                source_category=SourceCategory.DATABASE,
            )
        )
        await repo.create_workflow("wf-from-phase", "Test topic", "abc123")
        await repo.save_checkpoint("wf-from-phase", "phase_2_search", papers_processed=1)
        await repo.save_checkpoint("wf-from-phase", "phase_3_screening", papers_processed=1)

    state, next_phase = await load_resume_state(
        db_path=str(db_path),
        workflow_id="wf-from-phase",
        review_path="config/review.yaml",
        settings_path="config/settings.yaml",
        run_root=str(tmp_path),
        from_phase="phase_3_screening",
    )
    assert next_phase == "phase_3_screening"
    assert isinstance(state, ReviewState)

    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        checkpoints = await repo.get_checkpoints("wf-from-phase")
    assert "phase_2_search" in checkpoints
    assert "phase_3_screening" not in checkpoints


@pytest.mark.asyncio
async def test_load_resume_state_clears_section_drafts_when_rerunning_writing(tmp_path) -> None:
    run_dir = tmp_path / "2026-02-16" / "topic" / "run_01-00-00PM"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = run_dir / "runtime.db"
    async with get_db(str(db_path)) as db:
        await db.executescript(Path("src/db/schema.sql").read_text())
        await db.commit()
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-clear-sections", "Test topic", "abc123")
        await repo.save_checkpoint("wf-clear-sections", "phase_2_search", papers_processed=1)
        await repo.save_checkpoint("wf-clear-sections", "phase_3_screening", papers_processed=1)
        await repo.save_checkpoint("wf-clear-sections", "phase_4_extraction_quality", papers_processed=1)
        await repo.save_checkpoint("wf-clear-sections", "phase_4b_embedding", papers_processed=1)
        await repo.save_checkpoint("wf-clear-sections", "phase_5_synthesis", papers_processed=1)
        await repo.save_checkpoint("wf-clear-sections", "phase_5b_knowledge_graph", papers_processed=1)
        await repo.save_checkpoint("wf-clear-sections", "phase_6_writing", papers_processed=1)
        await repo.save_checkpoint("wf-clear-sections", "phase_6a_hyde", papers_processed=1)
        await repo.save_checkpoint("wf-clear-sections", "phase_6b_phase_a", papers_processed=1)
        await repo.save_section_draft(
            SectionDraft(
                workflow_id="wf-clear-sections",
                section="results",
                version=1,
                content="old content",
                claims_used=[],
                citations_used=[],
                word_count=2,
            )
        )

    _, next_phase = await load_resume_state(
        db_path=str(db_path),
        workflow_id="wf-clear-sections",
        review_path="config/review.yaml",
        settings_path="config/settings.yaml",
        run_root=str(tmp_path),
        from_phase="phase_6_writing",
    )
    assert next_phase == "phase_6_writing"

    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        checkpoints = await repo.get_checkpoints("wf-clear-sections")
        cursor = await db.execute(
            "SELECT COUNT(*) FROM section_drafts WHERE workflow_id = ?",
            ("wf-clear-sections",),
        )
        row = await cursor.fetchone()
    assert int(row[0]) == 0
    assert "phase_6a_hyde" not in checkpoints
    assert "phase_6b_phase_a" not in checkpoints


@pytest.mark.asyncio
async def test_load_resume_state_treats_partial_checkpoint_as_incomplete(tmp_path) -> None:
    run_dir = tmp_path / "2026-02-16" / "topic" / "run_01-00-00PM"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = run_dir / "runtime.db"
    async with get_db(str(db_path)) as db:
        await db.executescript(Path("src/db/schema.sql").read_text())
        await db.commit()
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-partial", "Test topic", "abc123")
        await repo.save_checkpoint("wf-partial", "phase_2_search", papers_processed=10, status="completed")
        await repo.save_checkpoint("wf-partial", "phase_3_screening", papers_processed=5, status="partial")

    state, next_phase = await load_resume_state(
        db_path=str(db_path),
        workflow_id="wf-partial",
        review_path="config/review.yaml",
        settings_path="config/settings.yaml",
        run_root=str(tmp_path),
    )
    assert isinstance(state, ReviewState)
    assert next_phase == "phase_3_screening"


def test_rc_print_web_context_without_console_does_not_raise() -> None:
    class DummyWebContext:
        def __init__(self) -> None:
            self.messages: list[str] = []

        def log_status(self, message: str) -> None:
            self.messages.append(message)

    rc = DummyWebContext()
    _rc_print(rc, "safe message")
    assert rc.messages == ["safe message"]


@pytest.mark.asyncio
async def test_run_workflow_web_context_without_console_uses_non_console_resume_path(monkeypatch) -> None:
    class DummyWebContext:
        web_mode = True

    class DummyDbContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    class DummyRepo:
        def __init__(self, _db) -> None:
            pass

        async def get_checkpoints(self, _workflow_id: str):
            return {"phase_2_search": {"status": "completed"}}

    async def _fake_find_by_topic(_run_root: str, _topic: str, _config_hash: str):
        return [
            RegistryEntry(
                workflow_id="wf-1234",
                topic="topic",
                config_hash="hash",
                db_path="runs/2026-01-01/topic/run_01/runtime.db",
                status="running",
                created_at="2026-01-01",
                updated_at="2026-01-01",
            )
        ]

    async def _fake_resume(**_kwargs):
        return {"status": "ok", "workflow_id": "wf-1234"}

    monkeypatch.setattr(
        workflow_module, "load_configs", lambda *_args, **_kwargs: (SimpleNamespace(research_question="topic"), None)
    )
    monkeypatch.setattr(workflow_module, "_hash_config", lambda *_args, **_kwargs: "hash")
    monkeypatch.setattr(workflow_module, "find_by_topic", _fake_find_by_topic)
    monkeypatch.setattr(workflow_module, "get_db", lambda _path: DummyDbContext())
    monkeypatch.setattr(workflow_module, "WorkflowRepository", DummyRepo)
    monkeypatch.setattr(workflow_module, "run_workflow_resume", _fake_resume)
    monkeypatch.setattr("builtins.input", lambda *_args, **_kwargs: "y")

    out = await workflow_module.run_workflow(
        review_path="config/review.yaml",
        settings_path="config/settings.yaml",
        run_root="runs",
        run_context=DummyWebContext(),
        fresh=False,
    )
    assert out["status"] == "ok"
