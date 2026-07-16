"""Integration test fixtures and shared setup.

Key responsibility: reset global state that would otherwise leak between tests
and cause cross-test contamination.

Specifically, `src.utils.structured_log` uses module-level `_structlog_configured`
and `_file_handles` so that `configure_run_logging` only configures structlog once
per process while opening per-run log files. This is correct behavior in production
(one process, one run), but in tests multiple runs in the same process need
independent log files.

The `reset_structured_log` autouse fixture clears that state before every test,
guaranteeing that each test gets its own `app.jsonl` written to its own
`tmp_path` rather than silently inheriting a stale configuration from a
previous test.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiosqlite
import pytest
import pytest_asyncio
import structlog
import yaml

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.db.workflow_registry import candidate_run_roots, resolve_workflow_db_path
from src.llm.pydantic_client import PydanticAIClient

MINIMAL_REVIEW: dict[str, Any] = {
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

MINIMAL_SETTINGS: dict[str, Any] = {
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


@dataclass(frozen=True)
class WorkflowDbFixture:
    workflow_id: str
    db_path: Path
    run_root: Path
    topic: str = "Graph transition test topic"
    config_hash: str = "graph-test-hash"


async def init_runtime_workflow_db(
    db_path: Path,
    workflow_id: str,
    *,
    topic: str = "Graph transition test topic",
    config_hash: str = "graph-test-hash",
    status: str = "running",
) -> None:
    """Bootstrap runtime.db schema and workflow row (test_lifecycle_restart pattern)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow(workflow_id, topic, config_hash)
        await repo.update_workflow_status(workflow_id, status)
        await db.commit()


@pytest.fixture
def minimal_config_paths(tmp_path: Path) -> tuple[Path, Path]:
    review_path = tmp_path / "review.yaml"
    settings_path = tmp_path / "settings.yaml"
    review_path.write_text(yaml.safe_dump(MINIMAL_REVIEW, sort_keys=False), encoding="utf-8")
    settings_path.write_text(yaml.safe_dump(MINIMAL_SETTINGS, sort_keys=False), encoding="utf-8")
    return review_path, settings_path


@pytest_asyncio.fixture
async def tmp_workflow_db(tmp_path: Path) -> WorkflowDbFixture:
    """Real SQLite runtime.db with schema bootstrap for orchestration graph tests."""
    workflow_id = "wf-graph-test"
    db_path = tmp_path / "runtime.db"
    await init_runtime_workflow_db(db_path, workflow_id)
    return WorkflowDbFixture(workflow_id=workflow_id, db_path=db_path, run_root=tmp_path)


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


@pytest.fixture
def mock_llm_boundary(monkeypatch: pytest.MonkeyPatch) -> _StubPydanticAIClient:
    """Patch get_chat_client / PydanticAIClient at orchestration boundaries."""
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


@pytest.fixture
def mock_search_connectors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Return empty connector list so search routing tests never hit external APIs."""

    def _fake_build_connectors(workflow_id: str, target_databases: list[str]) -> tuple[list, dict[str, str]]:
        _ = (workflow_id, target_databases)
        return [], {}

    monkeypatch.setattr(
        "src.orchestration.helpers.search_connectors.build_connectors",
        _fake_build_connectors,
    )
    monkeypatch.setattr(
        "src.orchestration.runners.search_runner._build_connectors",
        _fake_build_connectors,
    )
    monkeypatch.setattr(
        "src.orchestration.workflow._build_connectors",
        _fake_build_connectors,
    )


@pytest.fixture(autouse=True)
def clear_pydantic_ai_http_cache() -> None:
    """Clear PydanticAI's cached httpx client before and after each test.

    PydanticAI caches a shared httpx.AsyncClient via _cached_async_http_client
    (a functools.cache wrapper). The transport inside that client holds a direct
    reference to the event loop it was created on. When pytest-asyncio creates a
    new event loop for the next test, the cached transport's loop is already
    closed, triggering RuntimeError: Event loop is closed.

    Clearing the cache before each test forces PydanticAI to create a fresh
    client (and transport) bound to the current event loop.
    """
    from pydantic_ai.models import _cached_async_http_client

    _cached_async_http_client.cache_clear()
    yield
    _cached_async_http_client.cache_clear()


@pytest.fixture(autouse=True)
def reset_structured_log() -> None:
    """Reset structured_log global state before each test.

    Without this, any test that starts a workflow (e.g. via the API endpoint
    test that calls POST /api/run) will configure the logger to write to that
    run's directory. Subsequent tests that also start workflows then silently
    skip re-configuration and never create their own app.jsonl, causing
    flaky failures that only appear when tests run in a specific order.
    """
    import src.utils.structured_log as sl

    for fh in sl._file_handles.values():
        try:
            fh.close()
        except OSError:
            pass
    sl._file_handles.clear()
    sl._structlog_configured = False
    sl._log_queue = None
    sl._writer_task = None
    structlog.reset_defaults()
    yield
    sl._log_queue = None
    sl._writer_task = None


@pytest.fixture
async def real_workflow_target() -> tuple[str, Path]:
    """Return (workflow_id, runtime_db_path) for real-data replay tests.

    Priority:
    1) WORKFLOW_REPLAY_DB_PATH + WORKFLOW_REPLAY_ID
    2) WORKFLOW_REPLAY_ID resolved from registry
    3) latest workflow id in registry
    """
    env_db = os.getenv("WORKFLOW_REPLAY_DB_PATH", "").strip()
    env_wf = os.getenv("WORKFLOW_REPLAY_ID", "").strip()
    if env_db and env_wf:
        db_path = Path(env_db).expanduser().resolve()
        if not db_path.exists():
            pytest.skip(f"WORKFLOW_REPLAY_DB_PATH not found: {db_path}")
        return env_wf, db_path

    roots = candidate_run_roots("runs", anchor_file=__file__)
    workflow_id = env_wf
    if not workflow_id:
        registry = Path(roots[0]) / "workflows_registry.db"
        if not registry.exists():
            pytest.skip("No workflows_registry.db found for real workflow replay tests.")
        async with aiosqlite.connect(str(registry)) as db:
            row = await (
                await db.execute("SELECT workflow_id FROM workflows_registry ORDER BY updated_at DESC LIMIT 1")
            ).fetchone()
        if not row or not row[0]:
            pytest.skip("No workflow id found in workflows_registry.")
        workflow_id = str(row[0])

    resolved = await resolve_workflow_db_path(workflow_id, roots)
    if not resolved:
        pytest.skip(f"Could not resolve runtime.db for workflow_id={workflow_id}")
    return workflow_id, Path(resolved).resolve()
