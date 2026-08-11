"""Resume smoke: real run_workflow_resume with the heavy graph tail stubbed.

The full RUN_GRAPH tail (extraction -> embedding -> synthesis -> ... -> finalize)
exceeds any reasonable test budget even with the LLM stubbed, because embedding,
RAG, and synthesis do real CPU work. These tests therefore exercise the *resume
facade* end to end -- registry lookup, ``load_resume_state``, ``ResumeStartNode``
routing, and the graph runner -- while short-circuiting the first post-resume
node to ``End``. That proves the resume path advances past its gate (and, for the
awaiting_review case, re-parks correctly) without ever hanging.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml
from pydantic_graph import End, GraphRunContext

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.db.workflow_registry import register as register_workflow
from src.llm.pydantic_client import PydanticAIClient
from src.models.enums import SourceCategory
from src.models.papers import CandidatePaper
from src.models.workflow import WorkflowRunResult, WorkflowRunStatus
from src.orchestration.state import ReviewState
from src.orchestration.workflow import ExtractionQualityNode, run_workflow_resume

_MINIMAL_REVIEW = {
    "research_question": "What is the effect of the intervention on the primary outcome in the target population?",
    "review_type": "systematic",
    "pico": {
        "population": "adult participants in controlled settings",
        "intervention": "structured intervention program",
        "comparison": "standard care or control condition",
        "outcome": "primary outcome measure",
    },
    "keywords": ["intervention", "outcome", "systematic review"],
    "domain": "health and wellbeing",
    "scope": "clinical and community settings",
    "inclusion_criteria": ["peer-reviewed"],
    "exclusion_criteria": ["opinion pieces"],
    "date_range_start": 2015,
    "date_range_end": 2026,
    "target_databases": ["openalex"],
}

_MINIMAL_SETTINGS = {
    "agents": {
        "screening_reviewer_a": {"model": "google:gemini-2.5-flash-lite", "temperature": 0.1},
        "screening_reviewer_b": {"model": "google:gemini-2.5-flash-lite", "temperature": 0.3},
        "screening_adjudicator": {"model": "google:gemini-2.5-pro", "temperature": 0.2},
        "quality_assessment": {"model": "google:gemini-2.5-pro", "temperature": 0.1},
        "search": {"model": "google:gemini-2.5-flash", "temperature": 0.1},
        "extraction": {"model": "google:gemini-2.5-pro", "temperature": 0.1},
        "writing": {"model": "google:gemini-2.5-pro", "temperature": 0.2},
    },
    "gates": {"profile": "warning"},
    "rag": {
        "embed_model": "sentence-transformers:lightonai/DenseOn",
        "use_hyde": False,
        "rerank": False,
    },
}


class _StubPydanticAIClient:
    """Scripted LLM stub; never calls provider APIs."""

    async def complete_with_usage(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float,
        json_schema: dict | None = None,
    ) -> tuple[str, int, int, int, int]:
        _ = (self, prompt, model, temperature, json_schema)
        return ("{}", 1, 1, 0, 0)

    async def complete_validated(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float,
        response_model: type[Any],
        json_schema: dict | None = None,
        max_validation_retries: int = 2,
    ) -> tuple[Any, int, int, int, int, int]:
        _ = (self, prompt, model, temperature, json_schema, max_validation_retries)
        try:
            payload = response_model.model_validate({})
        except Exception:
            payload = response_model()
        return payload, 1, 1, 0, 0, 0


def _write_config_files(tmp_path: Path, *, hitl_enabled: bool = False) -> tuple[Path, Path]:
    review_path = tmp_path / "review.yaml"
    settings_path = tmp_path / "settings.yaml"
    settings = dict(_MINIMAL_SETTINGS)
    if hitl_enabled:
        settings = {**settings, "human_in_the_loop": {"enabled": True}}
    review_path.write_text(yaml.safe_dump(_MINIMAL_REVIEW, sort_keys=False), encoding="utf-8")
    settings_path.write_text(yaml.safe_dump(settings, sort_keys=False), encoding="utf-8")
    return review_path, settings_path


# Checkpoints for a run parked immediately after screening: everything up to and
# including phase_3_screening is complete, so the next incomplete phase is
# phase_4_extraction_quality.
_POST_SCREENING_CHECKPOINTS: tuple[str, ...] = (
    "phase_1_prospero_gate",
    "phase_2_search",
    "phase_3_screening",
)


async def _seed_interrupted_runtime(
    run_root: Path,
    *,
    workflow_id: str = "wf-resume-smoke",
    with_paper: bool = False,
    checkpoints: tuple[str, ...] = ("phase_2_search",),
    status: str = "interrupted",
) -> Path:
    run_dir = run_root / "2026-07-16" / "wf-resume-smoke-topic" / "run_01-00-00PM"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = run_dir / "runtime.db"
    (run_dir / "config_snapshot.yaml").write_text(
        yaml.safe_dump(_MINIMAL_REVIEW, sort_keys=False),
        encoding="utf-8",
    )

    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow(workflow_id, _MINIMAL_REVIEW["research_question"], "resume-smoke-hash")
        if with_paper:
            await repo.save_paper(
                CandidatePaper(
                    paper_id="paper-smoke-1",
                    title="Smoke test paper",
                    authors=["Author, A."],
                    source_database="openalex",
                    source_category=SourceCategory.DATABASE,
                    abstract="Minimal abstract for resume smoke coverage.",
                )
            )
        for phase in checkpoints:
            await repo.save_checkpoint(workflow_id, phase, papers_processed=1 if with_paper else 0)
        await repo.update_workflow_status(workflow_id, status)

    await register_workflow(
        str(run_root),
        workflow_id=workflow_id,
        topic=_MINIMAL_REVIEW["research_question"],
        config_hash="resume-smoke-hash",
        db_path=str(db_path),
        status=status,
    )
    return db_path


@pytest.fixture
def mock_llm_clients(monkeypatch: pytest.MonkeyPatch) -> _StubPydanticAIClient:
    stub = _StubPydanticAIClient()

    async def _fake_complete_with_usage(
        self: PydanticAIClient,
        prompt: str,
        *,
        model: str,
        temperature: float,
        json_schema: dict | None = None,
    ) -> tuple[str, int, int, int, int]:
        return await stub.complete_with_usage(
            prompt,
            model=model,
            temperature=temperature,
            json_schema=json_schema,
        )

    async def _fake_complete_validated(
        self: PydanticAIClient,
        prompt: str,
        *,
        model: str,
        temperature: float,
        response_model: type[Any],
        json_schema: dict | None = None,
        max_validation_retries: int = 2,
    ) -> tuple[Any, int, int, int, int, int]:
        return await stub.complete_validated(
            prompt,
            model=model,
            temperature=temperature,
            response_model=response_model,
            json_schema=json_schema,
            max_validation_retries=max_validation_retries,
        )

    monkeypatch.setattr(PydanticAIClient, "complete_with_usage", _fake_complete_with_usage)
    monkeypatch.setattr(PydanticAIClient, "complete_validated", _fake_complete_validated)
    monkeypatch.setattr("src.llm.factory.get_chat_client", lambda **_kwargs: stub)
    return stub


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_resume_from_post_screening_advances_past_gate(
    tmp_path: Path,
    mock_llm_clients: _StubPydanticAIClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real resume facade routes past screening into extraction and does not re-park.

    Seeds a run parked right after screening (phase_3_screening complete,
    registry ``running``) and stubs ``ExtractionQualityNode`` -- the first
    post-resume phase -- to terminate immediately. Proves ``run_workflow_resume``
    loads state, ``ResumeStartNode`` routes forward to phase_4, and the run
    completes quickly instead of hanging in the full graph tail.
    """
    _ = mock_llm_clients
    run_root = tmp_path / "runs"
    review_path, settings_path = _write_config_files(tmp_path)
    await _seed_interrupted_runtime(
        run_root,
        with_paper=True,
        checkpoints=_POST_SCREENING_CHECKPOINTS,
        status="running",
    )
    workflow_id = "wf-resume-smoke"

    reached: dict[str, str] = {}

    async def _stub_extraction_run(
        self: ExtractionQualityNode,
        ctx: GraphRunContext[ReviewState],
    ) -> End[WorkflowRunResult]:
        reached["phase"] = "phase_4_extraction_quality"
        state = ctx.state
        return End(
            WorkflowRunResult(
                status=WorkflowRunStatus.COMPLETED,
                workflow_id=state.workflow_id,
                db_path=state.db_path,
                details={"stub_extraction_reached": True},
            )
        )

    monkeypatch.setattr(ExtractionQualityNode, "run", _stub_extraction_run)

    result = await run_workflow_resume(
        workflow_id=workflow_id,
        review_path=str(review_path),
        settings_path=str(settings_path),
        run_root=str(run_root),
        run_context=None,
        from_phase=None,
    )

    # Routed forward into extraction (past screening / human-review gate).
    assert reached.get("phase") == "phase_4_extraction_quality"
    assert isinstance(result, WorkflowRunResult)
    assert result.status is WorkflowRunStatus.COMPLETED
    assert result.status is not WorkflowRunStatus.AWAITING_REVIEW
    assert result.workflow_id == workflow_id
    assert result.details.get("stub_extraction_reached") is True


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_resume_awaiting_review_reparks_without_approval(
    tmp_path: Path,
    mock_llm_clients: _StubPydanticAIClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resume of an unapproved awaiting_review run re-parks at the gate, bounded.

    Registry status stays ``awaiting_review`` (no approval), HITL is enabled and
    the run_context is web mode, so ``ResumeStartNode`` routes to
    ``HumanReviewCheckpointNode`` which parks again immediately (no CLI polling
    loop). Guards against a resume that would blow past an un-approved gate or
    hang waiting on it. ``ExtractionQualityNode`` is stubbed so any accidental
    advance would fail loudly rather than run the real pipeline.
    """
    _ = mock_llm_clients
    run_root = tmp_path / "runs"
    review_path, settings_path = _write_config_files(tmp_path, hitl_enabled=True)
    db_path = await _seed_interrupted_runtime(
        run_root,
        with_paper=True,
        checkpoints=_POST_SCREENING_CHECKPOINTS,
        status="awaiting_review",
    )
    workflow_id = "wf-resume-smoke"

    async def _fail_extraction_run(
        self: ExtractionQualityNode,
        ctx: GraphRunContext[ReviewState],
    ) -> End[WorkflowRunResult]:
        raise AssertionError("resume advanced past an un-approved awaiting_review gate")

    monkeypatch.setattr(ExtractionQualityNode, "run", _fail_extraction_run)

    run_context = MagicMock()
    run_context.web_mode = True

    result = await run_workflow_resume(
        workflow_id=workflow_id,
        review_path=str(review_path),
        settings_path=str(settings_path),
        run_root=str(run_root),
        run_context=run_context,
        from_phase=None,
    )

    assert isinstance(result, WorkflowRunResult)
    assert result.status is WorkflowRunStatus.AWAITING_REVIEW
    assert result.workflow_id == workflow_id

    # Gate persisted awaiting_review in the registry (did not silently advance).
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        checkpoints = await repo.get_checkpoints(workflow_id)
    assert checkpoints.get("phase_4_extraction_quality") is None


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_resume_workflow_run_rejects_completed_workflow(
    tmp_path: Path,
    mock_llm_clients: _StubPydanticAIClient,
) -> None:
    """Completed workflows must fail fast through the real resume facade."""
    _ = mock_llm_clients
    from src.orchestration.phase_catalog import PHASE_ORDER
    from src.orchestration.resume import ResumeNotAllowedError

    run_root = tmp_path / "runs"
    review_path, settings_path = _write_config_files(tmp_path)
    run_dir = run_root / "2026-07-16" / "wf-resume-done-topic" / "run_01-00-00PM"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = run_dir / "runtime.db"
    workflow_id = "wf-resume-done"
    (run_dir / "config_snapshot.yaml").write_text(
        yaml.safe_dump(_MINIMAL_REVIEW, sort_keys=False),
        encoding="utf-8",
    )

    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow(workflow_id, _MINIMAL_REVIEW["research_question"], "resume-done-hash")
        for phase in PHASE_ORDER:
            await repo.save_checkpoint(workflow_id, phase, papers_processed=1)
        await repo.update_workflow_status(workflow_id, "completed")

    await register_workflow(
        str(run_root),
        workflow_id=workflow_id,
        topic=_MINIMAL_REVIEW["research_question"],
        config_hash="resume-done-hash",
        db_path=str(db_path),
        status="completed",
    )

    with pytest.raises(ResumeNotAllowedError, match="nothing remains to resume"):
        await run_workflow_resume(
            workflow_id=workflow_id,
            review_path=str(review_path),
            settings_path=str(settings_path),
            run_root=str(run_root),
            run_context=None,
            from_phase=None,
        )
