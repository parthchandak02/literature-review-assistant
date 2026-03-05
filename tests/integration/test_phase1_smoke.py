"""Phase 1 -- Foundation integration tests.

Validates the project's bedrock layer: config loading, SQLite schema creation,
WorkflowRepository CRUD, and Pydantic model validation. These must pass before
any pipeline phase is trusted to work correctly.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import yaml

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.models import ReviewConfig, SettingsConfig
from src.models.enums import ReviewType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MINIMAL_REVIEW = {
    "research_question": "How does pharmacy automation reduce dispensing errors?",
    "review_type": "systematic",
    "pico": {
        "population": "hospital pharmacies",
        "intervention": "automated dispensing",
        "comparison": "manual dispensing",
        "outcome": "dispensing error rate",
    },
    "keywords": ["pharmacy automation", "dispensing error"],
    "domain": "pharmacy",
    "scope": "health sciences",
    "inclusion_criteria": ["peer-reviewed"],
    "exclusion_criteria": ["opinion pieces"],
    "date_range_start": 2015,
    "date_range_end": 2026,
    "target_databases": ["openalex"],
}

_MINIMAL_SETTINGS = {
    "agents": {
        "screening_reviewer_a": {"model": "google-gla:gemini-2.5-flash-lite", "temperature": 0.1},
        "screening_reviewer_b": {"model": "google-gla:gemini-2.5-flash-lite", "temperature": 0.3},
        "screening_adjudicator": {"model": "google-gla:gemini-2.5-pro", "temperature": 0.2},
        "writing": {"model": "google-gla:gemini-2.5-pro", "temperature": 0.2},
    },
    "gates": {"profile": "warning"},
}

# All tables that the schema migration must create in a fresh runtime.db
_EXPECTED_TABLES = {
    "workflows",
    "papers",
    "screening_decisions",
    "dual_screening_results",
    "extraction_records",
    "rob_assessments",
    "grade_assessments",
    "gate_results",
    "decision_log",
    "cost_records",
    "citations",
    "claims",
    "evidence_links",
    "checkpoints",
    "event_log",
}


# ---------------------------------------------------------------------------
# Test 1: ReviewConfig validates from YAML-equivalent dict
# ---------------------------------------------------------------------------


def test_review_config_validates_from_dict() -> None:
    config = ReviewConfig.model_validate(_MINIMAL_REVIEW)
    assert config.research_question.startswith("How does")
    assert config.review_type == ReviewType.SYSTEMATIC
    assert "pharmacy automation" in config.keywords
    assert config.pico.population == "hospital pharmacies"
    assert config.date_range_start == 2015
    assert config.date_range_end == 2026


def test_review_config_round_trips_through_yaml(tmp_path: Path) -> None:
    """Write to YAML, read back, validate -- simulates actual user workflow."""
    config_path = tmp_path / "review.yaml"
    config_path.write_text(yaml.safe_dump(_MINIMAL_REVIEW), encoding="utf-8")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config = ReviewConfig.model_validate(raw)
    assert config.domain == "pharmacy"


def test_review_config_rejects_empty_research_question() -> None:
    bad = {**_MINIMAL_REVIEW, "research_question": ""}
    try:
        ReviewConfig.model_validate(bad)
        raised = False
    except Exception:
        raised = True
    assert raised, "Empty research_question should fail validation"


# ---------------------------------------------------------------------------
# Test 2: SettingsConfig validates and exposes agent tiers
# ---------------------------------------------------------------------------


def test_settings_config_validates_from_dict() -> None:
    settings = SettingsConfig.model_validate(_MINIMAL_SETTINGS)
    assert "screening_reviewer_a" in settings.agents
    assert settings.agents["screening_reviewer_a"].model.startswith("google-gla:")
    assert settings.gates.profile == "warning"


def test_settings_config_defaults_to_strict_gate_profile() -> None:
    settings = SettingsConfig.model_validate({"agents": _MINIMAL_SETTINGS["agents"]})
    assert settings.gates.profile == "strict"


# ---------------------------------------------------------------------------
# Test 3: Database schema creates all expected tables
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_db_schema_creates_all_tables(tmp_path: Path) -> None:
    """get_db() must run the schema migration and produce all required tables."""
    db_path = str(tmp_path / "runtime.db")
    async with get_db(db_path) as db:
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        rows = await cursor.fetchall()
        tables = {str(row[0]) for row in rows}

    missing = _EXPECTED_TABLES - tables
    assert not missing, f"Schema migration did not create tables: {missing}"


def test_db_schema_creates_tables_via_stdlib_connect(tmp_path: Path) -> None:
    """Verify schema via stdlib sqlite3 so failures are isolated to schema.sql."""
    import asyncio

    db_path = str(tmp_path / "schema_check.db")
    asyncio.run(_create_db(db_path))
    conn = sqlite3.connect(db_path)
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    missing = _EXPECTED_TABLES - tables
    assert not missing, f"Missing tables via stdlib: {missing}"


async def _create_db(path: str) -> None:
    async with get_db(path) as _:
        pass


# ---------------------------------------------------------------------------
# Test 4: WorkflowRepository CRUD operations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_repository_create_and_find(tmp_path: Path) -> None:
    async with get_db(str(tmp_path / "repo.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-phase1", "pharmacy-automation", "hash-abc")

        cursor = await db.execute("SELECT topic, config_hash FROM workflows WHERE workflow_id = ?", ("wf-phase1",))
        row = await cursor.fetchone()
        assert row is not None
        assert str(row[0]) == "pharmacy-automation"
        assert str(row[1]) == "hash-abc"


@pytest.mark.asyncio
async def test_workflow_repository_checkpoint_roundtrip(tmp_path: Path) -> None:
    async with get_db(str(tmp_path / "checkpoint.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-ckpt", "topic", "hash")

        await repo.save_checkpoint("wf-ckpt", "phase_2_search", {"papers_found": 42})

        cursor = await db.execute("SELECT phase, state_json FROM checkpoints WHERE workflow_id = ?", ("wf-ckpt",))
        row = await cursor.fetchone()
        assert row is not None
        assert str(row[0]) == "phase_2_search"
        import json

        state = json.loads(str(row[1]))
        assert state["papers_found"] == 42


@pytest.mark.asyncio
async def test_workflow_repository_decision_log_write(tmp_path: Path) -> None:
    async with get_db(str(tmp_path / "declog.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-log", "topic", "hash")
        await repo.log_decision(
            workflow_id="wf-log",
            decision_type="search_strategy",
            decision="include_pubmed",
            rationale="PubMed covers clinical studies",
        )
        cursor = await db.execute("SELECT decision, rationale FROM decision_log WHERE workflow_id = ?", ("wf-log",))
        row = await cursor.fetchone()
        assert row is not None
        assert "pubmed" in str(row[0]).lower() or "pubmed" in str(row[1]).lower()


# ---------------------------------------------------------------------------
# Test 5: Config loader reads from YAML files on disk
# ---------------------------------------------------------------------------


def test_config_loader_reads_review_yaml(tmp_path: Path) -> None:
    """The config loader function should parse a review.yaml file."""
    review_path = tmp_path / "review.yaml"
    review_path.write_text(yaml.safe_dump(_MINIMAL_REVIEW), encoding="utf-8")
    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text(yaml.safe_dump(_MINIMAL_SETTINGS), encoding="utf-8")

    from src.config.loader import load_configs

    review, settings = load_configs(str(review_path), str(settings_path))
    assert review.domain == "pharmacy"
    assert settings.gates.profile == "warning"
