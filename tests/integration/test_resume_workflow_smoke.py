"""Resume smoke: real orchestration_facade.resume_workflow_run with mocked LLM only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.db.workflow_registry import register as register_workflow
from src.llm.pydantic_client import PydanticAIClient
from src.models.enums import SourceCategory
from src.models.papers import CandidatePaper
from src.web.orchestration_facade import resume_workflow_run

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


def _write_config_files(tmp_path: Path) -> tuple[Path, Path]:
    review_path = tmp_path / "review.yaml"
    settings_path = tmp_path / "settings.yaml"
    review_path.write_text(yaml.safe_dump(_MINIMAL_REVIEW, sort_keys=False), encoding="utf-8")
    settings_path.write_text(yaml.safe_dump(_MINIMAL_SETTINGS, sort_keys=False), encoding="utf-8")
    return review_path, settings_path


async def _seed_interrupted_runtime(
    run_root: Path,
    *,
    workflow_id: str = "wf-resume-smoke",
    with_paper: bool = False,
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
        await repo.save_checkpoint(workflow_id, "phase_2_search", papers_processed=1 if with_paper else 0)
        await repo.update_workflow_status(workflow_id, "interrupted")

    await register_workflow(
        str(run_root),
        workflow_id=workflow_id,
        topic=_MINIMAL_REVIEW["research_question"],
        config_hash="resume-smoke-hash",
        db_path=str(db_path),
        status="interrupted",
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
async def test_resume_workflow_run_zero_papers_advances_checkpoints(
    tmp_path: Path,
    mock_llm_clients: _StubPydanticAIClient,
) -> None:
    """Real resume path from phase_3 with zero papers; LLM patched, not resume itself."""
    _ = mock_llm_clients
    run_root = tmp_path / "runs"
    review_path, settings_path = _write_config_files(tmp_path)
    db_path = await _seed_interrupted_runtime(run_root, with_paper=False)
    workflow_id = "wf-resume-smoke"

    result = await resume_workflow_run(
        workflow_id=workflow_id,
        review_path=str(review_path),
        settings_path=str(settings_path),
        run_root=str(run_root),
        run_context=None,
        from_phase=None,
    )

    assert isinstance(result, dict)
    assert result.get("workflow_id") == workflow_id or "workflow_id" in result

    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        checkpoints = await repo.get_checkpoints(workflow_id)

    assert checkpoints.get("phase_3_screening") == "completed"
    assert checkpoints.get("phase_2_search") == "completed"
    run_summary = db_path.parent / "run_summary.json"
    assert run_summary.is_file()
    summary = json.loads(run_summary.read_text(encoding="utf-8"))
    assert summary.get("workflow_id") == workflow_id


@pytest.mark.asyncio
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
        await resume_workflow_run(
            workflow_id=workflow_id,
            review_path=str(review_path),
            settings_path=str(settings_path),
            run_root=str(run_root),
            run_context=None,
            from_phase=None,
        )
