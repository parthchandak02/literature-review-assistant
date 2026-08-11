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
async def test_validation_summary_include_checks(api_client: httpx.AsyncClient, tmp_path) -> None:
    db_path = tmp_path / "validation_include_checks.db"
    workflow_id = "wf-validation-include-checks"
    async with get_db(str(db_path)) as db:
        await db.execute(
            """
            INSERT INTO validation_runs (validation_run_id, workflow_id, profile, status, tool_version, summary_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("val-include-1", workflow_id, "quick", "passed", "test", '{"errors": 0}'),
        )
        await db.execute(
            """
            INSERT INTO validation_checks (validation_run_id, workflow_id, phase, check_name, status, severity, details_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("val-include-1", workflow_id, "phase_3_screening", "batch_contract", "pass", "warn", "{}"),
        )
        await db.commit()

    record = _RunRecord(run_id=workflow_id, topic="validation")
    record.db_path = str(db_path)
    _active_runs[workflow_id] = record
    try:
        without_include = await api_client.get(f"/api/workflow/{workflow_id}/validation/summary")
        assert without_include.status_code == 200
        without_include_data = without_include.json()
        assert "checks" not in without_include_data

        with_include = await api_client.get(
            f"/api/workflow/{workflow_id}/validation/summary",
            params={"include": "checks"},
        )
        assert with_include.status_code == 200
        with_include_data = with_include.json()
        assert "checks" in with_include_data
        assert len(with_include_data["checks"]) == 1
        assert with_include_data["checks"][0]["check_name"] == "batch_contract"

        checks_endpoint = await api_client.get(f"/api/workflow/{workflow_id}/validation/checks")
        assert checks_endpoint.status_code == 200
        assert with_include_data["checks"] == checks_endpoint.json()["checks"]
    finally:
        _active_runs.pop(workflow_id, None)
