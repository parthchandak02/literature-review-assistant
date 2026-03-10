"""Integration tests for the FastAPI web backend.

Uses httpx.AsyncClient with the ASGI transport to call the real app routes
without spinning up a live server. The lifespan (eviction loop, registry
updates) runs as it would in production, keeping these tests honest.

Coverage:
- GET /api/health
- GET /api/runs (empty at startup)
- GET /api/results/{run_id} on unknown id -> 404
- POST /api/cancel/{run_id} on unknown id -> 404
- GET /api/config/review (reads config/review.yaml -- may 404 if missing)
- CORS headers present on all responses
- POST /api/run validates required fields (returns 422 on bad payload)
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import aiosqlite
import httpx
import pytest
import pytest_asyncio

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.db.workflow_registry import REGISTRY_SCHEMA
from src.search.pdf_retrieval import PDFRetrievalResult
from src.web.app import _RunRecord, _active_runs, app

# ---------------------------------------------------------------------------
# Shared fixture: async HTTP client bound to the FastAPI ASGI app
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def client():
    """Async HTTP client for the ASGI app. No live server required."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Test 1: Health endpoint always returns 200 + {"status": "ok"}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_returns_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "ok"


# ---------------------------------------------------------------------------
# Test 2: /api/runs returns an empty list when no runs exist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_runs_returns_list(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/runs")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)


# ---------------------------------------------------------------------------
# Test 3: /api/results/{run_id} returns 404 for an unknown run_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_results_unknown_run_returns_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/results/does-not-exist")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Test 4: /api/cancel/{run_id} returns 404 for an unknown run_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_unknown_run_returns_404(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/cancel/does-not-exist")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Test 5: POST /api/run with a missing required field returns 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_run_missing_fields_returns_422(client: httpx.AsyncClient) -> None:
    # review_yaml and gemini_api_key are required; sending neither
    response = await client.post("/api/run", json={})
    assert response.status_code == 422
    errors = response.json().get("detail", [])
    missing_fields = {e.get("loc", [""])[-1] for e in errors}
    assert "review_yaml" in missing_fields or "gemini_api_key" in missing_fields


# ---------------------------------------------------------------------------
# Test 6: CORS headers are set on all responses (even 404s)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cors_headers_present(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert "access-control-allow-origin" in response.headers


# ---------------------------------------------------------------------------
# Test 7: GET /api/history returns a list (even when empty)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_history_returns_list(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/history")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)


# ---------------------------------------------------------------------------
# Test 8: GET /api/stream/{run_id} for unknown run_id returns 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_unknown_run_returns_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/stream/nonexistent-run-id")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Test 9: GET /api/run/{run_id}/papers-reference returns 404 for unknown run_id
#         (not in _active_runs and not in workflows_registry)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_papers_reference_unknown_run_returns_404(client: httpx.AsyncClient) -> None:
    """References tab: unknown run_id (short UUID) returns 404."""
    response = await client.get("/api/run/abcd1234/papers-reference")
    assert response.status_code == 404
    assert "Run not found" in response.json().get("detail", "")


@pytest.mark.asyncio
async def test_papers_reference_unknown_workflow_returns_404(client: httpx.AsyncClient) -> None:
    """References tab: workflow_id not in registry returns 404 (registry fallback path)."""
    response = await client.get("/api/run/wf-9999/papers-reference")
    assert response.status_code == 404
    assert "Run not found" in response.json().get("detail", "")


# ---------------------------------------------------------------------------
# Test 10: POST /api/run with valid YAML payload is accepted (202/200, no LLM call)
#         The run is backgrounded -- we only verify the response shape, not completion.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_run_valid_payload_accepted(client: httpx.AsyncClient) -> None:
    import yaml

    review_payload = {
        "research_question": "Does test coverage improve software quality?",
        "review_type": "systematic",
        "pico": {
            "population": "software teams",
            "intervention": "high test coverage",
            "comparison": "low test coverage",
            "outcome": "defect rate",
        },
        "keywords": ["test coverage", "software quality"],
        "domain": "software engineering",
        "scope": "",
        "inclusion_criteria": ["peer reviewed"],
        "exclusion_criteria": ["opinion pieces"],
        "date_range_start": 2015,
        "date_range_end": 2026,
        "target_databases": ["unsupported_db"],  # no real API calls
    }
    req = {
        "review_yaml": yaml.safe_dump(review_payload),
        "gemini_api_key": "fake-key-for-test",
        "run_root": "/tmp/litreview_test_runs",
    }
    response = await client.post("/api/run", json=req)
    # 200 is accepted -- background task launched
    assert response.status_code == 200
    data = response.json()
    assert "run_id" in data
    assert "topic" in data
    assert len(data["run_id"]) > 0


@pytest.mark.asyncio
async def test_resume_does_not_flip_registry_failed_when_runtime_completed(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "runs"
    db_path = run_root / "2026-03-10" / "wf-9999-topic" / "run_01-00-00PM" / "runtime.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async with get_db(str(db_path)) as db:
        await db.executescript(Path("src/db/schema.sql").read_text())
        await db.commit()
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-9999", "Test topic", "hash-1")
        await repo.update_workflow_status("wf-9999", "running")

    registry_path = run_root / "workflows_registry.db"
    async with aiosqlite.connect(str(registry_path)) as reg_db:
        await reg_db.executescript(REGISTRY_SCHEMA)
        await reg_db.execute(
            """
            INSERT OR REPLACE INTO workflows_registry (workflow_id, topic, config_hash, db_path, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("wf-9999", "Test topic", "hash-1", str(db_path), "running"),
        )
        await reg_db.commit()

    async def _fake_run_workflow_resume(**kwargs):  # type: ignore[no-untyped-def]
        workflow_id = kwargs["workflow_id"]
        runtime_db = str(db_path)
        async with get_db(runtime_db) as db:
            await WorkflowRepository(db).update_workflow_status(workflow_id, "completed")
        run_summary = Path(runtime_db).parent / "run_summary.json"
        run_summary.write_text(json.dumps({"status": "done", "artifacts": {"dummy": "ok"}}), encoding="utf-8")
        raise RuntimeError("post-finalize logging failure")

    monkeypatch.setattr("src.web.app.run_workflow_resume", _fake_run_workflow_resume)

    resp = await client.post(
        "/api/history/resume",
        json={
            "workflow_id": "wf-9999",
            "db_path": str(db_path),
            "topic": "Test topic",
        },
    )
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]

    for _ in range(30):
        runs = (await client.get("/api/runs")).json()
        item = next((r for r in runs if r["run_id"] == run_id), None)
        if item and item["done"]:
            break
        await asyncio.sleep(0.1)

    async with aiosqlite.connect(str(registry_path)) as reg_db:
        async with reg_db.execute(
            "SELECT status FROM workflows_registry WHERE workflow_id = ?",
            ("wf-9999",),
        ) as cur:
            row = await cur.fetchone()
    assert row is not None
    assert row[0] == "completed"


@pytest.mark.asyncio
async def test_fetch_pdfs_emits_reason_codes(client: httpx.AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_id = "run-fetch-diag"
    workflow_id = "wf-fetch-diag"
    run_dir = tmp_path / "2026-03-10" / "wf-fetch-diag-topic" / "run_01-00-00PM"
    db_path = run_dir / "runtime.db"
    run_dir.mkdir(parents=True, exist_ok=True)

    async with get_db(str(db_path)) as db:
        await db.executescript(Path("src/db/schema.sql").read_text())
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            (workflow_id, "Topic", "hash", "completed"),
        )
        await db.execute(
            """
            INSERT INTO papers (paper_id, title, authors, year, source_database, doi, url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("paper-1", "Paper One", "Author A", 2024, "testdb", "10.1000/test", "https://example.org/p1"),
        )
        await db.execute(
            """
            INSERT INTO extraction_records (workflow_id, paper_id, study_design, data)
            VALUES (?, ?, ?, ?)
            """,
            (workflow_id, "paper-1", "rct", "{}"),
        )
        await db.commit()

    record = _RunRecord(run_id, "Topic")
    record.db_path = str(db_path)
    record.workflow_id = workflow_id
    _active_runs[run_id] = record

    async def _fake_retrieve(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        return PDFRetrievalResult(
            paper_id="paper-1",
            source="abstract",
            reason_code="publisher_403",
            diagnostics=["PublisherDirect: HTTP 403 for https://example.org/p1.pdf"],
            success=False,
            error="PublisherDirect: HTTP 403",
        )

    monkeypatch.setattr("src.search.pdf_retrieval.PDFRetriever.retrieve", _fake_retrieve)
    try:
        response = await client.post(f"/api/run/{run_id}/fetch-pdfs")
        assert response.status_code == 200
        payloads = []
        for line in response.text.splitlines():
            if line.startswith("data: "):
                payloads.append(json.loads(line[6:]))
        done = next(p for p in payloads if p.get("type") == "done")
        assert done["failed"] == 1
        assert done["reason_counts"]["publisher_403"] == 1
        assert done["results"][0]["reason_code"] == "publisher_403"
    finally:
        _active_runs.pop(run_id, None)
