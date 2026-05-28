"""Unit tests for resume state loading."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.db.workflow_registry import RegistryEntry
from src.models import (
    CandidatePaper,
    ExtractionRecord,
    FallbackEventRecord,
    PrimaryStudyStatus,
    SectionDraft,
    StudyDesign,
)
from src.models.enums import ScreeningDecisionType, SourceCategory
from src.orchestration import workflow as workflow_module
from src.orchestration.resume import PHASE_ORDER, ResumeNotAllowedError, load_resume_state, validate_resume_allowed
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
    assert "custom_diagram_01" in state.artifacts
    assert "custom_diagram_02" in state.artifacts
    assert "diagram_brief_pack" in state.artifacts
    assert "diagram_placement_plan" in state.artifacts


@pytest.mark.asyncio
async def test_load_resume_state_prefers_config_snapshot_over_workspace_review(tmp_path) -> None:
    run_dir = tmp_path / "2026-02-16" / "topic" / "run_01-00-00PM"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = run_dir / "runtime.db"
    (run_dir / "config_snapshot.yaml").write_text(
        "\n".join(
            [
                "research_question: Snapshot RQ",
                "review_type: systematic",
                "pico:",
                "  population: Snapshot population",
                "  intervention: Snapshot intervention",
                "  comparison: Snapshot comparison",
                "  outcome: Snapshot outcome",
                "keywords: [snapshot]",
                "domain: Snapshot domain",
                "scope: Snapshot scope",
                "inclusion_criteria: ['Include snapshot']",
                "exclusion_criteria: ['Exclude snapshot']",
                "date_range_start: 2020",
                "date_range_end: 2024",
                "target_databases: [openalex]",
                "target_sections: [abstract, introduction, methods, results, discussion, conclusion]",
                "search_query: snapshot query",
                "search_overrides: {}",
                "quality_framework: rob2",
                "meta_analysis_required: false",
                "min_studies_for_meta: 2",
                "citation_style: ieee",
                "manuscript_output: markdown",
                "protocol:",
                "  registration_number: ''",
                "funding:",
                "  source: None declared",
                "conflicts_of_interest: None declared",
                "ethical_approval: Not required",
            ]
        ),
        encoding="utf-8",
    )
    async with get_db(str(db_path)) as db:
        await db.executescript(Path("src/db/schema.sql").read_text())
        await db.commit()
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-snapshot", "Workspace RQ", "abc123")
        await repo.save_checkpoint("wf-snapshot", "phase_2_search", papers_processed=0)

    state, _ = await load_resume_state(
        db_path=str(db_path),
        workflow_id="wf-snapshot",
        review_path="config/review.yaml",
        settings_path="config/settings.yaml",
        run_root=str(tmp_path),
    )
    assert state.review is not None
    assert state.review.research_question == "Snapshot RQ"
    assert state.review.pico.intervention == "Snapshot intervention"


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
async def test_load_resume_state_from_writing_clears_outline_subphase_checkpoint(tmp_path) -> None:
    run_dir = tmp_path / "2026-02-16" / "topic" / "run_01-00-00PM"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = run_dir / "runtime.db"
    async with get_db(str(db_path)) as db:
        await db.executescript(Path("src/db/schema.sql").read_text())
        await db.commit()
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-outline-resume", "Test topic", "abc123")
        await repo.save_checkpoint("wf-outline-resume", "phase_2_search", papers_processed=1)
        await repo.save_checkpoint("wf-outline-resume", "phase_3_screening", papers_processed=1)
        await repo.save_checkpoint("wf-outline-resume", "phase_4_extraction_quality", papers_processed=1)
        await repo.save_checkpoint("wf-outline-resume", "phase_4b_embedding", papers_processed=1)
        await repo.save_checkpoint("wf-outline-resume", "phase_5_synthesis", papers_processed=1)
        await repo.save_checkpoint("wf-outline-resume", "phase_5b_knowledge_graph", papers_processed=1)
        await repo.save_checkpoint("wf-outline-resume", "phase_5c_pre_writing_gate", papers_processed=1)
        await repo.save_checkpoint("wf-outline-resume", "phase_6_writing", papers_processed=1)
        await repo.save_checkpoint("wf-outline-resume", "phase_6a_hyde", papers_processed=6)
        await repo.save_checkpoint("wf-outline-resume", "phase_6a2_outline", papers_processed=6)
        await repo.save_checkpoint("wf-outline-resume", "phase_6b_phase_a", papers_processed=4)
        await repo.save_checkpoint("wf-outline-resume", "phase_6e_concepts", papers_processed=6)
        await repo.save_checkpoint("wf-outline-resume", "phase_6f_custom_diagrams", papers_processed=2)

    _, next_phase = await load_resume_state(
        db_path=str(db_path),
        workflow_id="wf-outline-resume",
        review_path="config/review.yaml",
        settings_path="config/settings.yaml",
        run_root=str(tmp_path),
        from_phase="phase_6_writing",
    )
    assert next_phase == "phase_6_writing"

    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        checkpoints = await repo.get_checkpoints("wf-outline-resume")
    assert "phase_6_writing" not in checkpoints
    assert "phase_6a_hyde" not in checkpoints
    assert "phase_6a2_outline" not in checkpoints
    assert "phase_6b_phase_a" not in checkpoints
    assert "phase_6e_concepts" not in checkpoints
    assert "phase_6f_custom_diagrams" not in checkpoints


@pytest.mark.asyncio
async def test_load_resume_state_from_search_clears_downstream_phase_data(tmp_path) -> None:
    run_dir = tmp_path / "2026-02-16" / "topic" / "run_01-00-00PM"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = run_dir / "runtime.db"
    async with get_db(str(db_path)) as db:
        await db.executescript(Path("src/db/schema.sql").read_text())
        await db.commit()
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-from-search", "Test topic", "abc123")
        await repo.save_checkpoint("wf-from-search", "phase_2_search", papers_processed=1)
        await repo.save_checkpoint("wf-from-search", "phase_3_screening", papers_processed=1)
        await repo.save_paper(
            CandidatePaper(
                paper_id="p1",
                title="Paper 1",
                authors=["A"],
                source_database="openalex",
                source_category=SourceCategory.DATABASE,
            )
        )
        await db.execute(
            """
            INSERT INTO search_results
            (database_name, source_category, search_date, search_query, records_retrieved, workflow_id)
            VALUES ('openalex', 'database', '2026-03-23', 'q', 1, 'wf-from-search')
            """
        )
        await db.execute(
            """
            INSERT INTO screening_decisions
            (workflow_id, paper_id, stage, decision, reviewer_type, confidence)
            VALUES ('wf-from-search', 'p1', 'title_abstract', 'include', 'reviewer_a', 0.9)
            """
        )
        await db.commit()

    _, next_phase = await load_resume_state(
        db_path=str(db_path),
        workflow_id="wf-from-search",
        review_path="config/review.yaml",
        settings_path="config/settings.yaml",
        run_root=str(tmp_path),
        from_phase="phase_2_search",
    )
    assert next_phase == "phase_2_search"

    async with get_db(str(db_path)) as db:
        search_count = await (
            await db.execute("SELECT COUNT(*) FROM search_results WHERE workflow_id = ?", ("wf-from-search",))
        ).fetchone()
        screening_count = await (
            await db.execute("SELECT COUNT(*) FROM screening_decisions WHERE workflow_id = ?", ("wf-from-search",))
        ).fetchone()
        paper_count = await (await db.execute("SELECT COUNT(*) FROM papers")).fetchone()
    assert int(search_count[0]) == 0
    assert int(screening_count[0]) == 0
    assert int(paper_count[0]) == 0


@pytest.mark.asyncio
async def test_load_resume_state_from_screening_clears_screening_and_extraction_state(tmp_path) -> None:
    run_dir = tmp_path / "2026-02-16" / "topic" / "run_01-00-00PM"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = run_dir / "runtime.db"
    async with get_db(str(db_path)) as db:
        await db.executescript(Path("src/db/schema.sql").read_text())
        await db.commit()
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-from-screening", "Test topic", "abc123")
        await repo.save_checkpoint("wf-from-screening", "phase_2_search", papers_processed=2)
        await repo.save_checkpoint("wf-from-screening", "phase_3_screening", papers_processed=1)
        await repo.save_checkpoint("wf-from-screening", "phase_4_extraction_quality", papers_processed=1)
        await repo.save_paper(
            CandidatePaper(
                paper_id="p1",
                title="Paper 1",
                authors=["A"],
                source_database="openalex",
                source_category=SourceCategory.DATABASE,
            )
        )
        await db.execute(
            """
            INSERT INTO screening_decisions
            (workflow_id, paper_id, stage, decision, reviewer_type, confidence)
            VALUES ('wf-from-screening', 'p1', 'fulltext', 'include', 'reviewer_a', 0.9)
            """
        )
        await repo.save_dual_screening_result(
            "wf-from-screening",
            "p1",
            "fulltext",
            True,
            ScreeningDecisionType.INCLUDE,
            False,
        )
        await repo.save_extraction_record(
            "wf-from-screening",
            ExtractionRecord(
                paper_id="p1",
                study_design=StudyDesign.MIXED_METHODS,
                primary_study_status=PrimaryStudyStatus.PRIMARY,
                participant_count=20,
                intervention_description="Intervention",
                results_summary={"summary": "Improved coverage."},
                extraction_source="openalex_content",
            ),
        )
        await db.commit()

    _, next_phase = await load_resume_state(
        db_path=str(db_path),
        workflow_id="wf-from-screening",
        review_path="config/review.yaml",
        settings_path="config/settings.yaml",
        run_root=str(tmp_path),
        from_phase="phase_3_screening",
    )
    assert next_phase == "phase_3_screening"

    async with get_db(str(db_path)) as db:
        screening_count = await (
            await db.execute("SELECT COUNT(*) FROM screening_decisions WHERE workflow_id = ?", ("wf-from-screening",))
        ).fetchone()
        dual_count = await (
            await db.execute(
                "SELECT COUNT(*) FROM dual_screening_results WHERE workflow_id = ?", ("wf-from-screening",)
            )
        ).fetchone()
        extraction_count = await (
            await db.execute("SELECT COUNT(*) FROM extraction_records WHERE workflow_id = ?", ("wf-from-screening",))
        ).fetchone()
    assert int(screening_count[0]) == 0
    assert int(dual_count[0]) == 0
    assert int(extraction_count[0]) == 0


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
        await repo.save_checkpoint("wf-clear-sections", "phase_5c_pre_writing_gate", papers_processed=1)
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
async def test_load_resume_state_from_phase4_clears_persisted_writing_state(tmp_path) -> None:
    run_dir = tmp_path / "2026-02-16" / "topic" / "run_01-00-00PM"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = run_dir / "runtime.db"
    async with get_db(str(db_path)) as db:
        await db.executescript(Path("src/db/schema.sql").read_text())
        await db.commit()
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-phase4-reset", "Test topic", "abc123")
        for phase in (
            "phase_2_search",
            "phase_3_screening",
            "phase_4_extraction_quality",
            "phase_4b_embedding",
            "phase_5_synthesis",
            "phase_5b_knowledge_graph",
            "phase_5c_pre_writing_gate",
            "phase_6_writing",
        ):
            await repo.save_checkpoint("wf-phase4-reset", phase, papers_processed=1)
        draft = SectionDraft(
            workflow_id="wf-phase4-reset",
            section="discussion",
            version=1,
            content="stale discussion",
            claims_used=[],
            citations_used=[],
            word_count=2,
        )
        await repo.save_section_draft(draft)
        await repo.save_manuscript_section_from_draft(draft, section_order=5)
        await repo.save_fallback_event(
            FallbackEventRecord(
                workflow_id="wf-phase4-reset",
                phase="phase_6_writing",
                module="writing.section_writer",
                fallback_type="deterministic_section_fallback",
                reason="section=discussion",
            )
        )

    _, next_phase = await load_resume_state(
        db_path=str(db_path),
        workflow_id="wf-phase4-reset",
        review_path="config/review.yaml",
        settings_path="config/settings.yaml",
        run_root=str(tmp_path),
        from_phase="phase_4_extraction_quality",
    )
    assert next_phase == "phase_4_extraction_quality"

    async with get_db(str(db_path)) as db:
        draft_count = await (
            await db.execute("SELECT COUNT(*) FROM section_drafts WHERE workflow_id = ?", ("wf-phase4-reset",))
        ).fetchone()
        section_count = await (
            await db.execute("SELECT COUNT(*) FROM manuscript_sections WHERE workflow_id = ?", ("wf-phase4-reset",))
        ).fetchone()
        fallback_count = await (
            await db.execute("SELECT COUNT(*) FROM fallback_events WHERE workflow_id = ?", ("wf-phase4-reset",))
        ).fetchone()
    assert int(draft_count[0]) == 0
    assert int(section_count[0]) == 0
    assert int(fallback_count[0]) == 0


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


@pytest.mark.asyncio
async def test_load_resume_state_from_phase_before_writing_bumps_generation(tmp_path) -> None:
    run_dir = tmp_path / "2026-02-16" / "topic" / "run_01-00-00PM"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = run_dir / "runtime.db"
    async with get_db(str(db_path)) as db:
        await db.executescript(Path("src/db/schema.sql").read_text())
        await db.commit()
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-generation", "Test topic", "abc123")
        await repo.save_checkpoint("wf-generation", "phase_2_search", papers_processed=1)
        await repo.save_checkpoint("wf-generation", "phase_3_screening", papers_processed=1)
        await repo.save_checkpoint("wf-generation", "phase_4_extraction_quality", papers_processed=1)
        await repo.save_checkpoint("wf-generation", "phase_5_synthesis", papers_processed=1)
        await repo.save_section_draft(
            SectionDraft(
                workflow_id="wf-generation",
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
        workflow_id="wf-generation",
        review_path="config/review.yaml",
        settings_path="config/settings.yaml",
        run_root=str(tmp_path),
        from_phase="phase_4_extraction_quality",
    )
    assert next_phase == "phase_4_extraction_quality"

    async with get_db(str(db_path)) as db:
        generation_row = await (
            await db.execute("SELECT writing_generation FROM workflows WHERE workflow_id = ?", ("wf-generation",))
        ).fetchone()
    assert generation_row is not None
    assert int(generation_row[0]) == 2


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


def test_phase_order_routes_writing_directly_to_finalize() -> None:
    assert "phase_6_writing" in PHASE_ORDER
    assert PHASE_ORDER.index("phase_6_writing") < PHASE_ORDER.index("finalize")


def test_phase_order_includes_pre_writing_gate_before_writing() -> None:
    assert "phase_5c_pre_writing_gate" in PHASE_ORDER
    assert PHASE_ORDER.index("phase_5b_knowledge_graph") < PHASE_ORDER.index("phase_5c_pre_writing_gate")
    assert PHASE_ORDER.index("phase_5c_pre_writing_gate") < PHASE_ORDER.index("phase_6_writing")


@pytest.mark.asyncio
async def test_validate_resume_allowed_rejects_from_phase_on_completed_finalize(tmp_path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    db_path = run_dir / "runtime.db"
    async with get_db(str(db_path)) as db:
        await db.executescript(Path("src/db/schema.sql").read_text())
        await db.commit()
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-done", "Completed topic", "hash")
        for phase in PHASE_ORDER:
            await repo.save_checkpoint("wf-done", phase, papers_processed=1)

    with pytest.raises(ResumeNotAllowedError, match="finalize checkpoint is completed"):
        await validate_resume_allowed(str(db_path), "wf-done", from_phase="phase_3_screening")


@pytest.mark.asyncio
async def test_validate_resume_allowed_rejects_resume_when_all_phases_done(tmp_path) -> None:
    run_dir = tmp_path / "run2"
    run_dir.mkdir()
    db_path = run_dir / "runtime.db"
    async with get_db(str(db_path)) as db:
        await db.executescript(Path("src/db/schema.sql").read_text())
        await db.commit()
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-all", "All done topic", "hash")
        for phase in PHASE_ORDER:
            await repo.save_checkpoint("wf-all", phase, papers_processed=1)

    with pytest.raises(ResumeNotAllowedError, match="nothing remains to resume"):
        await validate_resume_allowed(str(db_path), "wf-all", from_phase=None)
