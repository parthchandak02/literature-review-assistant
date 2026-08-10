"""HTTP integration tests for workflow draft and PROSPERO gate endpoints."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite
import httpx
import pytest
import pytest_asyncio
import yaml

from src.db.workflow_registry import REGISTRY_SCHEMA, find_by_workflow_id
from src.web.app import _active_runs, app
from src.web.state import _RunRecord
from tests.integration.conftest import MINIMAL_REVIEW, init_runtime_workflow_db

# ---------------------------------------------------------------------------
# Shared fixture: async HTTP client bound to the FastAPI ASGI app
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _init_registry(
    registry_path: Path,
    *,
    workflow_id: str,
    db_path: Path,
    topic: str,
    status: str,
    config_hash: str = "",
) -> None:
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(registry_path)) as reg_db:
        await reg_db.executescript(REGISTRY_SCHEMA)
        await reg_db.execute(
            """
            INSERT INTO workflows_registry
                (workflow_id, topic, config_hash, db_path, status, created_at, updated_at, heartbeat_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'), NULL)
            """,
            (workflow_id, topic, config_hash, str(db_path), status),
        )
        await reg_db.commit()


async def _setup_prospero_run(
    tmp_path: Path,
    *,
    workflow_id: str = "wf-prospero-test",
    run_id: str = "run-prospero-test",
    registry_status: str = "awaiting_prospero",
    register_active: bool = True,
) -> tuple[str, str, Path, Path]:
    """Create a minimal parked PROSPERO run with registry + optional active record."""
    run_root = tmp_path / "runs"
    run_dir = run_root / "2026-08-10" / f"{workflow_id}-topic" / "run_01"
    run_dir.mkdir(parents=True)
    db_path = run_dir / "runtime.db"

    review = {
        **MINIMAL_REVIEW,
        "protocol": {
            "registered": False,
            "registration_number": "",
            "registration_date": "",
            "registry": "PROSPERO",
        },
    }
    review_yaml = yaml.safe_dump(review, sort_keys=False)
    (run_dir / "review.yaml").write_text(review_yaml, encoding="utf-8")
    (run_dir / "config_snapshot.yaml").write_text(review_yaml, encoding="utf-8")

    await init_runtime_workflow_db(db_path, workflow_id, topic="PROSPERO gate topic", status="running")
    await _init_registry(
        run_root / "workflows_registry.db",
        workflow_id=workflow_id,
        db_path=db_path,
        topic="PROSPERO gate topic",
        status=registry_status,
    )

    if register_active:
        record = _RunRecord(run_id=run_id, topic="PROSPERO gate topic")
        record.db_path = str(db_path)
        record.workflow_id = workflow_id
        record.run_root = str(run_root)
        record.done = False
        _active_runs[run_id] = record

    return run_id, workflow_id, run_root, run_dir


# ---------------------------------------------------------------------------
# Workflow draft round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_draft_reserve_and_config_round_trip(client: httpx.AsyncClient, tmp_path: Path) -> None:
    run_root = str(tmp_path / "runs")
    topic = "Chair volleyball in care homes"

    reserve_response = await client.post(
        "/api/workflow/reserve",
        json={"topic": topic, "run_root": run_root},
    )
    assert reserve_response.status_code == 200
    reserved = reserve_response.json()
    workflow_id = reserved["workflow_id"]
    assert workflow_id.startswith("wf-")
    assert Path(reserved["db_path"]).exists()
    assert Path(reserved["run_dir"]).exists()

    entry = await find_by_workflow_id(run_root, workflow_id)
    assert entry is not None
    assert entry.status == "config_generating"

    review_yaml = yaml.safe_dump(
        {**MINIMAL_REVIEW, "research_question": topic},
        sort_keys=False,
    )
    save_response = await client.put(
        f"/api/workflow/{workflow_id}/config-draft",
        json={"review_yaml": review_yaml, "run_root": run_root},
    )
    assert save_response.status_code == 200
    assert save_response.json() == {"workflow_id": workflow_id, "status": "config_ready"}

    entry = await find_by_workflow_id(run_root, workflow_id)
    assert entry is not None
    assert entry.status == "config_ready"

    run_dir = Path(entry.db_path).parent
    assert (run_dir / "review.yaml").exists()
    assert (run_dir / "config_snapshot.yaml").exists()
    saved_review = yaml.safe_load((run_dir / "review.yaml").read_text(encoding="utf-8"))
    assert saved_review["research_question"] == topic


# ---------------------------------------------------------------------------
# submit-prospero
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_prospero_rejects_invalid_crd(client: httpx.AsyncClient, tmp_path: Path) -> None:
    run_id, _workflow_id, _run_root, _run_dir = await _setup_prospero_run(tmp_path)
    try:
        response = await client.post(
            f"/api/run/{run_id}/submit-prospero",
            json={
                "registration_number": "CRD123",
                "registration_date": "2026-01-15",
            },
        )
        assert response.status_code == 400
        assert "detail" in response.json()
    finally:
        _active_runs.pop(run_id, None)


@pytest.mark.asyncio
async def test_submit_prospero_parked_active_run_updates_registry(client: httpx.AsyncClient, tmp_path: Path) -> None:
    run_id, workflow_id, run_root, run_dir = await _setup_prospero_run(tmp_path)
    registry_path = run_root / "workflows_registry.db"

    with patch(
        "src.web.routers.prospero_gate._lifecycle_coordinator.start_resume",
        new_callable=AsyncMock,
    ) as mock_start_resume:
        try:
            response = await client.post(
                f"/api/run/{run_id}/submit-prospero",
                json={
                    "registration_number": "CRD42025678901",
                    "registration_date": "2026-01-15",
                },
            )
        finally:
            _active_runs.pop(run_id, None)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "submitted"
    assert body["workflow_id"] == workflow_id
    assert body["registration_number"] == "CRD42025678901"
    mock_start_resume.assert_not_awaited()

    async with aiosqlite.connect(str(registry_path)) as reg_db:
        async with reg_db.execute(
            "SELECT status FROM workflows_registry WHERE workflow_id = ?",
            (workflow_id,),
        ) as cur:
            row = await cur.fetchone()
    assert row is not None
    assert row[0] == "running"

    review = yaml.safe_load((run_dir / "review.yaml").read_text(encoding="utf-8"))
    assert review["protocol"]["registered"] is True
    assert review["protocol"]["registration_number"] == "CRD42025678901"
    assert review["protocol"]["registration_date"] == "2026-01-15"

    snapshot = yaml.safe_load((run_dir / "config_snapshot.yaml").read_text(encoding="utf-8"))
    assert snapshot["protocol"]["registered"] is True
    assert snapshot["protocol"]["registration_number"] == "CRD42025678901"
