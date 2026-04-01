from __future__ import annotations

import httpx
import pytest

from src.db.database import get_db
from src.web.app import _active_runs, _RunRecord, app


@pytest.fixture
async def api_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_workflow_validation_summary_and_checks(api_client: httpx.AsyncClient, tmp_path) -> None:
    db_path = tmp_path / "validation_api.db"
    workflow_id = "wf-validation-api"
    async with get_db(str(db_path)) as db:
        await db.execute(
            """
            INSERT INTO validation_runs (validation_run_id, workflow_id, profile, status, tool_version, summary_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("val-1", workflow_id, "quick", "passed", "test", '{"errors": 0}'),
        )
        await db.execute(
            """
            INSERT INTO validation_checks (validation_run_id, workflow_id, phase, check_name, status, severity, details_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("val-1", workflow_id, "phase_3_screening", "batch_contract", "pass", "warn", "{}"),
        )
        await db.commit()

    record = _RunRecord(run_id=workflow_id, topic="validation")
    record.db_path = str(db_path)
    _active_runs[workflow_id] = record
    try:
        summary = await api_client.get(f"/api/workflow/{workflow_id}/validation/summary")
        assert summary.status_code == 200
        summary_data = summary.json()
        assert summary_data["latest_run"]["validation_run_id"] == "val-1"

        checks = await api_client.get(f"/api/workflow/{workflow_id}/validation/checks")
        assert checks.status_code == 200
        checks_data = checks.json()
        assert checks_data["validation_run_id"] == "val-1"
        assert len(checks_data["checks"]) == 1
        assert checks_data["checks"][0]["check_name"] == "batch_contract"
    finally:
        _active_runs.pop(workflow_id, None)
