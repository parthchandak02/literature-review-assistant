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
import io
import json
import zipfile
from pathlib import Path

import aiosqlite
import httpx
import pytest
import pytest_asyncio

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.db.workflow_registry import REGISTRY_SCHEMA
from src.search.pdf_retrieval import PDFRetrievalResult
from src.web.app import _active_runs, _fetch_run_stats, _inject_csv_paths_into_yaml, _RunRecord, app

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
    assert response.headers.get("cache-control") == "no-store, no-cache, must-revalidate, max-age=0"
    assert response.headers.get("pragma") == "no-cache"
    assert response.headers.get("expires") == "0"


@pytest.mark.asyncio
async def test_history_running_row_with_terminal_evidence_not_marked_stale(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "runs"
    run_dir = run_root / "2026-03-10" / "wf-1000-topic" / "run_01-00-00PM"
    db_path = run_dir / "runtime.db"
    run_dir.mkdir(parents=True, exist_ok=True)
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            ("wf-1000", "Topic", "hash", "completed"),
        )
        await db.execute(
            "INSERT INTO event_log (workflow_id, event_type, payload, ts) VALUES (?, ?, ?, ?)",
            (
                "wf-1000",
                "done",
                json.dumps({"type": "done", "outputs": {"status": "completed"}, "ts": "2026-03-10T10:00:00.000Z"}),
                "2026-03-10T10:00:00.000Z",
            ),
        )
        await db.commit()

    registry_path = run_root / "workflows_registry.db"
    async with aiosqlite.connect(str(registry_path)) as reg_db:
        await reg_db.executescript(REGISTRY_SCHEMA)
        try:
            await reg_db.execute("ALTER TABLE workflows_registry ADD COLUMN notes TEXT")
        except Exception:
            pass
        await reg_db.execute(
            """
            INSERT INTO workflows_registry
                (workflow_id, topic, config_hash, db_path, status, created_at, updated_at, heartbeat_at)
            VALUES (?, ?, ?, ?, ?, datetime('now','-20 minutes'), datetime('now','-20 minutes'), NULL)
            """,
            ("wf-1000", "Topic", "hash", str(db_path), "running"),
        )
        await reg_db.commit()

    response = await client.get(f"/api/history?run_root={run_root}")
    assert response.status_code == 200
    rows = response.json()
    row = next(r for r in rows if r["workflow_id"] == "wf-1000")
    assert row["status"] == "completed"

    async with aiosqlite.connect(str(registry_path)) as reg_db:
        async with reg_db.execute(
            "SELECT status FROM workflows_registry WHERE workflow_id = ?",
            ("wf-1000",),
        ) as cur:
            repaired = await cur.fetchone()
    assert repaired is not None
    assert repaired[0] == "completed"


@pytest.mark.asyncio
async def test_history_running_row_without_terminal_evidence_marked_stale(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "runs"
    run_dir = run_root / "2026-03-10" / "wf-1001-topic" / "run_01-00-00PM"
    db_path = run_dir / "runtime.db"
    run_dir.mkdir(parents=True, exist_ok=True)
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            ("wf-1001", "Topic", "hash", "running"),
        )
        await db.commit()

    registry_path = run_root / "workflows_registry.db"
    async with aiosqlite.connect(str(registry_path)) as reg_db:
        await reg_db.executescript(REGISTRY_SCHEMA)
        try:
            await reg_db.execute("ALTER TABLE workflows_registry ADD COLUMN notes TEXT")
        except Exception:
            pass
        await reg_db.execute(
            """
            INSERT INTO workflows_registry
                (workflow_id, topic, config_hash, db_path, status, created_at, updated_at, heartbeat_at)
            VALUES (?, ?, ?, ?, ?, datetime('now','-20 minutes'), datetime('now','-20 minutes'), NULL)
            """,
            ("wf-1001", "Topic", "hash", str(db_path), "running"),
        )
        await reg_db.commit()

    response = await client.get(f"/api/history?run_root={run_root}")
    assert response.status_code == 200
    rows = response.json()
    row = next(r for r in rows if r["workflow_id"] == "wf-1001")
    assert row["status"] == "stale"


@pytest.mark.asyncio
async def test_history_archive_restore_and_delete_flow(client: httpx.AsyncClient, tmp_path: Path) -> None:
    run_root = tmp_path / "runs"
    run_dir = run_root / "2026-03-10" / "wf-2000-topic" / "run_01-00-00PM"
    db_path = run_dir / "runtime.db"
    run_dir.mkdir(parents=True, exist_ok=True)

    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            ("wf-2000", "Archive Topic", "hash", "completed"),
        )
        await db.commit()

    registry_path = run_root / "workflows_registry.db"
    async with aiosqlite.connect(str(registry_path)) as reg_db:
        await reg_db.executescript(REGISTRY_SCHEMA)
        await reg_db.execute(
            """
            INSERT INTO workflows_registry
                (workflow_id, topic, config_hash, db_path, status, created_at, updated_at, heartbeat_at)
            VALUES (?, ?, ?, ?, ?, datetime('now','-5 minutes'), datetime('now','-5 minutes'), NULL)
            """,
            ("wf-2000", "Archive Topic", "hash", str(db_path), "completed"),
        )
        await reg_db.commit()

    archive_res = await client.post(f"/api/history/wf-2000/archive?run_root={run_root}")
    assert archive_res.status_code == 200
    assert archive_res.json().get("ok") is True

    history_after_archive = await client.get(f"/api/history?run_root={run_root}")
    assert history_after_archive.status_code == 200
    archived_row = next(r for r in history_after_archive.json() if r["workflow_id"] == "wf-2000")
    assert archived_row["is_archived"] is True
    assert archived_row["archived_at"] is not None

    restore_res = await client.post(f"/api/history/wf-2000/restore?run_root={run_root}")
    assert restore_res.status_code == 200
    assert restore_res.json().get("ok") is True

    history_after_restore = await client.get(f"/api/history?run_root={run_root}")
    assert history_after_restore.status_code == 200
    restored_row = next(r for r in history_after_restore.json() if r["workflow_id"] == "wf-2000")
    assert restored_row["is_archived"] is False
    assert restored_row["archived_at"] is None

    delete_res = await client.delete(f"/api/history/wf-2000?run_root={run_root}")
    assert delete_res.status_code == 200
    assert delete_res.json().get("ok") is True
    assert not run_dir.exists()

    history_after_delete = await client.get(f"/api/history?run_root={run_root}")
    assert history_after_delete.status_code == 200
    assert all(r["workflow_id"] != "wf-2000" for r in history_after_delete.json())


# ---------------------------------------------------------------------------
# Test 8: GET /api/stream/{run_id} for unknown run_id returns 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_unknown_run_returns_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/stream/nonexistent-run-id")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Test 9b: GET /api/db/{run_id}/rag-diagnostics returns persisted diagnostics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_db_rag_diagnostics_returns_records(client: httpx.AsyncClient, tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.db"
    async with get_db(str(db_path)) as db:
        await db.execute(
            """
            INSERT INTO rag_retrieval_diagnostics (
                workflow_id, section, query_type, rerank_enabled, candidate_k, final_k,
                retrieved_count, status, selected_chunks_json, error_message, latency_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "wf-test-rag",
                "methods",
                "hyde",
                1,
                20,
                8,
                8,
                "success",
                '[{"chunk_id":"c1","paper_id":"p1","citekey":"RefA2020","score":0.9}]',
                None,
                41,
            ),
        )
        await db.commit()

    run_id = "ragdiag01"
    _active_runs[run_id] = _RunRecord(run_id=run_id, topic="RAG diag")
    _active_runs[run_id].db_path = str(db_path)
    _active_runs[run_id].workflow_id = "wf-test-rag"
    _active_runs[run_id].done = True
    try:
        response = await client.get(f"/api/db/{run_id}/rag-diagnostics")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        rec = body["records"][0]
        assert rec["section"] == "methods"
        assert rec["status"] == "success"
        assert rec["retrieved_count"] == 8
        assert rec["selected_chunks"][0]["chunk_id"] == "c1"
    finally:
        _active_runs.pop(run_id, None)


@pytest.mark.asyncio
async def test_db_costs_aggregates_returns_grouped_payload(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    run_id = "cost-agg-run"
    workflow_id = "wf-cost-agg"
    db_path = tmp_path / "runtime_cost_agg.db"
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            (workflow_id, "Cost topic", "hash", "completed"),
        )
        await db.execute(
            """
            INSERT INTO cost_records
                (workflow_id, model, tokens_in, tokens_out, cost_usd, latency_ms, phase, cache_read_tokens, cache_write_tokens)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (workflow_id, "google-gla:gemini-2.5-flash", 120, 80, 0.0123, 1200, "phase_3_screening", 0, 0),
        )
        await db.execute(
            """
            INSERT INTO cost_records
                (workflow_id, model, tokens_in, tokens_out, cost_usd, latency_ms, phase, cache_read_tokens, cache_write_tokens)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (workflow_id, "google-gla:gemini-2.5-pro", 200, 140, 0.055, 1800, "phase_6_writing", 0, 0),
        )
        await db.commit()

    record = _RunRecord(run_id, "Cost topic")
    record.db_path = str(db_path)
    record.workflow_id = workflow_id
    record.done = True
    _active_runs[run_id] = record
    try:
        response = await client.get(f"/api/db/{run_id}/costs/aggregates")
        assert response.status_code == 200
        payload = response.json()
        assert payload["run_id"] == run_id
        assert "totals" in payload
        assert payload["totals"]["total_calls"] == 2
        assert len(payload["by_phase"]) >= 2
        assert len(payload["by_model"]) >= 2
        assert isinstance(payload["by_day"], list)
    finally:
        _active_runs.pop(run_id, None)


@pytest.mark.asyncio
async def test_db_costs_aggregates_unknown_run_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/db/unknown-run/costs/aggregates")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_db_costs_export_returns_csv(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    run_id = "cost-export-run"
    workflow_id = "wf-cost-export"
    db_path = tmp_path / "runtime_cost_export.db"
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            (workflow_id, "Cost export topic", "hash", "completed"),
        )
        await db.execute(
            """
            INSERT INTO cost_records
                (workflow_id, model, tokens_in, tokens_out, cost_usd, latency_ms, phase, cache_read_tokens, cache_write_tokens)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (workflow_id, "google-gla:gemini-2.5-flash", 42, 28, 0.005, 900, "phase_4_extraction", 0, 0),
        )
        await db.commit()

    record = _RunRecord(run_id, "Cost export topic")
    record.db_path = str(db_path)
    record.workflow_id = workflow_id
    record.done = True
    _active_runs[run_id] = record
    try:
        response = await client.get(f"/api/db/{run_id}/costs/export?granularity=day")
        assert response.status_code == 200
        assert response.headers.get("content-type", "").startswith("text/csv")
        disposition = response.headers.get("content-disposition", "")
        assert f"cost_export_{run_id}_day.csv" in disposition
        lines = [ln for ln in response.text.splitlines() if ln.strip()]
        assert lines
        assert lines[0] == "timestamp_bucket,workflow_id,phase,model,call_count,tokens_in,tokens_out,cost_usd"
        assert any("phase_4_extraction" in line for line in lines[1:])
    finally:
        _active_runs.pop(run_id, None)


@pytest.mark.asyncio
async def test_db_costs_export_invalid_granularity_400(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    run_id = "cost-export-bad-granularity"
    workflow_id = "wf-cost-export-invalid"
    db_path = tmp_path / "runtime_cost_export_invalid.db"
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            (workflow_id, "Topic", "hash", "completed"),
        )
        await db.commit()

    record = _RunRecord(run_id, "Topic")
    record.db_path = str(db_path)
    record.workflow_id = workflow_id
    record.done = True
    _active_runs[run_id] = record
    try:
        response = await client.get(f"/api/db/{run_id}/costs/export?granularity=hour")
        assert response.status_code == 400
    finally:
        _active_runs.pop(run_id, None)


@pytest.mark.asyncio
async def test_history_costs_aggregates_returns_cross_run_payload(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "runs"
    run_root.mkdir(parents=True, exist_ok=True)
    db_a = run_root / "runtime_a.db"
    db_b = run_root / "runtime_b.db"

    async def _seed_runtime_db(db_path: Path, workflow_id: str, topic: str, cost_rows: list[tuple[str, str, int, int, float, str]]) -> None:
        async with get_db(str(db_path)) as db:
            await db.execute(
                "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
                (workflow_id, topic, "hash", "completed"),
            )
            for created_at, model, tokens_in, tokens_out, cost_usd, phase in cost_rows:
                await db.execute(
                    """
                    INSERT INTO cost_records
                        (workflow_id, model, tokens_in, tokens_out, cost_usd, latency_ms, phase, created_at, cache_read_tokens, cache_write_tokens)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (workflow_id, model, tokens_in, tokens_out, cost_usd, 1000, phase, created_at, 0, 0),
                )
            await db.commit()

    await _seed_runtime_db(
        db_a,
        "wf-cost-a",
        "Topic A",
        [
            ("2026-03-28 10:00:00", "google-gla:gemini-2.5-flash", 100, 50, 0.0100, "phase_3_screening"),
            ("2026-03-29 11:00:00", "google-gla:gemini-2.5-pro", 120, 60, 0.0200, "phase_6_writing"),
        ],
    )
    await _seed_runtime_db(
        db_b,
        "wf-cost-b",
        "Topic B",
        [
            ("2026-03-29 12:00:00", "google-gla:gemini-2.5-flash", 90, 40, 0.0300, "phase_4_extraction"),
        ],
    )

    registry_path = run_root / "workflows_registry.db"
    async with aiosqlite.connect(str(registry_path)) as reg_db:
        await reg_db.executescript(REGISTRY_SCHEMA)
        await reg_db.execute(
            """
            INSERT INTO workflows_registry
                (workflow_id, topic, config_hash, db_path, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            ("wf-cost-a", "Topic A", "hash", str(db_a), "completed"),
        )
        await reg_db.execute(
            """
            INSERT INTO workflows_registry
                (workflow_id, topic, config_hash, db_path, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            ("wf-cost-b", "Topic B", "hash", str(db_b), "completed"),
        )
        await reg_db.commit()

    response = await client.get(
        "/api/history/costs/aggregates",
        params={
            "run_root": str(run_root),
            "start_ts": "2026-03-28 00:00:00",
            "end_ts": "2026-03-30 23:59:59",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow_count"] == 2
    assert payload["totals"]["total_calls"] == 3
    assert payload["totals"]["total_cost_usd"] == pytest.approx(0.06)
    assert len(payload["by_day"]) == 2
    assert payload["by_workflow"][0]["group_key"] in {"wf-cost-a", "wf-cost-b"}


@pytest.mark.asyncio
async def test_history_costs_export_returns_csv(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "runs"
    run_root.mkdir(parents=True, exist_ok=True)
    db_path = run_root / "runtime_export.db"
    workflow_id = "wf-history-export"

    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            (workflow_id, "Topic Export", "hash", "completed"),
        )
        await db.execute(
            """
            INSERT INTO cost_records
                (workflow_id, model, tokens_in, tokens_out, cost_usd, latency_ms, phase, created_at, cache_read_tokens, cache_write_tokens)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workflow_id,
                "google-gla:gemini-2.5-flash",
                33,
                22,
                0.0042,
                800,
                "phase_4_extraction",
                "2026-03-28 09:30:00",
                0,
                0,
            ),
        )
        await db.commit()

    registry_path = run_root / "workflows_registry.db"
    async with aiosqlite.connect(str(registry_path)) as reg_db:
        await reg_db.executescript(REGISTRY_SCHEMA)
        await reg_db.execute(
            """
            INSERT INTO workflows_registry
                (workflow_id, topic, config_hash, db_path, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            (workflow_id, "Topic Export", "hash", str(db_path), "completed"),
        )
        await reg_db.commit()

    response = await client.get(
        "/api/history/costs/export",
        params={
            "run_root": str(run_root),
            "granularity": "day",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("text/csv")
    disposition = response.headers.get("content-disposition", "")
    assert "history_cost_export_day.csv" in disposition
    lines = [ln for ln in response.text.splitlines() if ln.strip()]
    assert lines[0] == "timestamp_bucket,workflow_id,phase,model,call_count,tokens_in,tokens_out,cost_usd"
    assert any("wf-history-export" in line for line in lines[1:])


@pytest.mark.asyncio
async def test_db_papers_all_supports_primary_status_filter(client: httpx.AsyncClient, tmp_path: Path) -> None:
    db_path = tmp_path / "runtime_primary_status.db"
    workflow_id = "wf-primary-status"
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            (workflow_id, "Topic", "hash", "completed"),
        )
        await db.execute(
            """
            INSERT INTO papers (paper_id, title, authors, year, source_database, doi, abstract, url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("p-primary", "Primary paper", '["A Author"]', 2024, "openalex", "10.1000/primary", "A", "https://x"),
        )
        await db.execute(
            """
            INSERT INTO papers (paper_id, title, authors, year, source_database, doi, abstract, url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "p-secondary",
                "Secondary review paper",
                '["B Author"]',
                2024,
                "openalex",
                "10.1000/secondary",
                "B",
                "https://y",
            ),
        )
        await db.execute(
            """
            INSERT INTO extraction_records
                (workflow_id, paper_id, study_design, primary_study_status, extraction_source, data)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                workflow_id,
                "p-primary",
                "rct",
                "primary",
                "text",
                json.dumps({"paper_id": "p-primary", "study_design": "rct", "primary_study_status": "primary"}),
            ),
        )
        await db.execute(
            """
            INSERT INTO extraction_records
                (workflow_id, paper_id, study_design, primary_study_status, extraction_source, data)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                workflow_id,
                "p-secondary",
                "narrative_review",
                "secondary_review",
                "text",
                json.dumps(
                    {
                        "paper_id": "p-secondary",
                        "study_design": "narrative_review",
                        "primary_study_status": "secondary_review",
                    }
                ),
            ),
        )
        await db.commit()

    run_id = "run-primary-status"
    _active_runs[run_id] = _RunRecord(run_id=run_id, topic="Primary status test")
    _active_runs[run_id].db_path = str(db_path)
    _active_runs[run_id].workflow_id = workflow_id
    _active_runs[run_id].done = True
    try:
        response = await client.get(f"/api/db/{run_id}/papers-all?primary_status=primary")
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        row = payload["papers"][0]
        assert row["paper_id"] == "p-primary"
        assert row["primary_study_status"] == "primary"
    finally:
        _active_runs.pop(run_id, None)


@pytest.mark.asyncio
async def test_history_stats_prefer_canonical_cohort_count(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime_history_stats.db"
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            ("wf-cohort", "Topic", "hash", "completed"),
        )
        await db.execute(
            "INSERT INTO papers (paper_id, title, authors, source_database) VALUES (?, ?, ?, ?)",
            ("p1", "Paper 1", '["A"]', "openalex"),
        )
        await db.execute(
            "INSERT INTO papers (paper_id, title, authors, source_database) VALUES (?, ?, ?, ?)",
            ("p2", "Paper 2", '["B"]', "openalex"),
        )
        await db.execute(
            """
            INSERT INTO dual_screening_results (workflow_id, paper_id, stage, agreement, final_decision, adjudication_needed)
            VALUES (?, ?, 'fulltext', 1, 'include', 0)
            """,
            ("wf-cohort", "p1"),
        )
        await db.execute(
            """
            INSERT INTO dual_screening_results (workflow_id, paper_id, stage, agreement, final_decision, adjudication_needed)
            VALUES (?, ?, 'fulltext', 1, 'include', 0)
            """,
            ("wf-cohort", "p2"),
        )
        await db.execute(
            """
            INSERT INTO study_cohort_membership (
                workflow_id, paper_id, screening_status, fulltext_status, synthesis_eligibility, source_phase
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("wf-cohort", "p1", "included", "assessed", "included_primary", "phase_4_extraction_quality"),
        )
        await db.commit()
    stats = await _fetch_run_stats(str(db_path))
    assert stats["papers_included"] == 1
    assert stats["papers_included_source"] == "study_cohort_membership_synthesis_included_primary"


@pytest.mark.asyncio
async def test_history_stats_falls_back_to_dual_when_cohort_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime_history_stats_dual.db"
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            ("wf-dual-fallback", "Topic", "hash", "completed"),
        )
        await db.execute(
            "INSERT INTO papers (paper_id, title, authors, source_database) VALUES (?, ?, ?, ?)",
            ("p1", "Paper 1", '["A"]', "openalex"),
        )
        await db.execute(
            """
            INSERT INTO dual_screening_results (workflow_id, paper_id, stage, agreement, final_decision, adjudication_needed)
            VALUES (?, ?, 'fulltext', 1, 'include', 0)
            """,
            ("wf-dual-fallback", "p1"),
        )
        await db.commit()
    stats = await _fetch_run_stats(str(db_path))
    assert stats["papers_included"] == 1
    assert stats["papers_included_source"] == "dual_screening_results_fulltext"


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


@pytest.mark.asyncio
async def test_papers_reference_cohort_path_returns_included_rows(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    run_id = "run-papers-reference-cohort"
    workflow_id = "wf-papers-reference-cohort"
    run_dir = tmp_path / "2026-03-10" / "wf-papers-reference-cohort-topic" / "run_01-00-00PM"
    db_path = run_dir / "runtime.db"
    run_dir.mkdir(parents=True, exist_ok=True)

    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            (workflow_id, "Topic", "hash", "completed"),
        )
        await db.execute(
            """
            INSERT INTO papers (paper_id, title, authors, year, source_database, doi, url, country)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("paper-1", "Paper One", "Author A", 2024, "testdb", "10.1000/test", "https://example.org/p1", "US"),
        )
        await db.execute(
            """
            INSERT INTO study_cohort_membership (
                workflow_id, paper_id, screening_status, fulltext_status, synthesis_eligibility, source_phase
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (workflow_id, "paper-1", "included", "assessed", "included_primary", "phase_4_extraction_quality"),
        )
        await db.commit()

    record = _RunRecord(run_id, "Topic")
    record.db_path = str(db_path)
    record.workflow_id = workflow_id
    record.done = True
    _active_runs[run_id] = record
    try:
        response = await client.get(f"/api/run/{run_id}/papers-reference")
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert payload["papers"][0]["paper_id"] == "paper-1"
    finally:
        _active_runs.pop(run_id, None)


@pytest.mark.asyncio
async def test_studies_files_zip_unknown_run_returns_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/run/abcd1234/studies-files.zip")
    assert response.status_code == 404
    assert "Run not found" in response.json().get("detail", "")


@pytest.mark.asyncio
async def test_studies_files_zip_returns_zip_for_included_files(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    run_id = "run-studies-zip-ok"
    workflow_id = "wf-studies-zip-ok"
    run_dir = tmp_path / "2026-03-10" / "wf-studies-zip-ok-topic" / "run_01-00-00PM"
    db_path = run_dir / "runtime.db"
    run_dir.mkdir(parents=True, exist_ok=True)

    papers_dir = run_dir / "papers"
    papers_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = papers_dir / "paper-1.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 test")

    manifest_path = run_dir / "data_papers_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "paper-1": {
                    "title": "Paper One",
                    "file_path": str(pdf_path),
                    "file_type": "pdf",
                }
            }
        ),
        encoding="utf-8",
    )

    async with get_db(str(db_path)) as db:
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
            INSERT INTO dual_screening_results
                (workflow_id, paper_id, stage, agreement, final_decision, adjudication_needed)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (workflow_id, "paper-1", "fulltext", 1, "include", 0),
        )
        await db.commit()

    record = _RunRecord(run_id, "Topic")
    record.db_path = str(db_path)
    record.workflow_id = workflow_id
    record.done = True
    _active_runs[run_id] = record
    try:
        response = await client.get(f"/api/run/{run_id}/studies-files.zip")
        assert response.status_code == 200
        assert response.headers.get("content-type", "").startswith("application/zip")
        disposition = response.headers.get("content-disposition", "")
        assert "studies-files.zip" in disposition

        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            names = sorted(zf.namelist())
            assert names == ["paper-1.pdf"]
            assert zf.read("paper-1.pdf") == b"%PDF-1.4 test"
    finally:
        _active_runs.pop(run_id, None)


@pytest.mark.asyncio
async def test_studies_files_zip_no_files_returns_404(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    run_id = "run-studies-zip-empty"
    workflow_id = "wf-studies-zip-empty"
    run_dir = tmp_path / "2026-03-10" / "wf-studies-zip-empty-topic" / "run_01-00-00PM"
    db_path = run_dir / "runtime.db"
    run_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = run_dir / "data_papers_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "paper-1": {
                    "title": "Paper One",
                    "file_path": str(run_dir / "papers" / "missing.pdf"),
                    "file_type": "pdf",
                }
            }
        ),
        encoding="utf-8",
    )

    async with get_db(str(db_path)) as db:
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
            INSERT INTO dual_screening_results
                (workflow_id, paper_id, stage, agreement, final_decision, adjudication_needed)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (workflow_id, "paper-1", "fulltext", 1, "include", 0),
        )
        await db.commit()

    record = _RunRecord(run_id, "Topic")
    record.db_path = str(db_path)
    record.workflow_id = workflow_id
    record.done = True
    _active_runs[run_id] = record
    try:
        response = await client.get(f"/api/run/{run_id}/studies-files.zip")
        assert response.status_code == 404
        assert "No downloadable study files found" in response.json().get("detail", "")
    finally:
        _active_runs.pop(run_id, None)


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
async def test_start_run_with_masterlist_valid_payload_accepted(client: httpx.AsyncClient) -> None:
    import yaml

    review_payload = {
        "research_question": "Does simulation training improve outcomes?",
        "review_type": "systematic",
        "pico": {
            "population": "medical students",
            "intervention": "simulation training",
            "comparison": "standard curriculum",
            "outcome": "skill performance",
        },
        "keywords": ["simulation", "medical education"],
        "domain": "medical education",
        "scope": "",
        "inclusion_criteria": ["empirical studies"],
        "exclusion_criteria": ["non-empirical"],
        "date_range_start": 2015,
        "date_range_end": 2026,
        "target_databases": ["unsupported_db"],
    }
    csv_content = (
        "Authors,Title,Year,Source title,DOI,Link,Abstract,Author Keywords\n"
        "A. Author,Paper A,2024,Journal A,10.1000/a,https://example.org/a,Abstract A,keyword\n"
    )
    response = await client.post(
        "/api/run-with-masterlist",
        data={
            "review_yaml": yaml.safe_dump(review_payload),
            "gemini_api_key": "fake-key-for-test",
            "run_root": "/tmp/litreview_test_runs",
        },
        files={"csv_file": ("master.csv", csv_content.encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 200
    data = response.json()
    assert "run_id" in data
    assert "topic" in data


@pytest.mark.asyncio
async def test_start_run_with_masterlist_rejects_invalid_csv(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/run-with-masterlist",
        data={
            "review_yaml": "research_question: test\n",
            "gemini_api_key": "fake-key-for-test",
            "run_root": "/tmp/litreview_test_runs",
        },
        files={"csv_file": ("master.csv", b"Authors,Year\nA,2024\n", "text/csv")},
    )
    assert response.status_code == 400
    assert "Invalid master list CSV" in response.text


@pytest.mark.asyncio
async def test_start_run_with_masterlist_rejects_empty_file(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/run-with-masterlist",
        data={
            "review_yaml": "research_question: test\n",
            "gemini_api_key": "fake-key-for-test",
            "run_root": "/tmp/litreview_test_runs",
        },
        files={"csv_file": ("master.csv", b"", "text/csv")},
    )
    assert response.status_code == 400
    assert "empty" in response.text.lower()


@pytest.mark.asyncio
async def test_start_run_with_supplementary_csv_valid_payload_accepted(client: httpx.AsyncClient) -> None:
    import yaml

    review_payload = {
        "research_question": "Does blended learning improve retention?",
        "review_type": "systematic",
        "pico": {
            "population": "medical students",
            "intervention": "blended learning",
            "comparison": "traditional teaching",
            "outcome": "knowledge retention",
        },
        "keywords": ["blended learning", "medical education"],
        "domain": "medical education",
        "scope": "",
        "inclusion_criteria": ["peer reviewed"],
        "exclusion_criteria": ["opinion pieces"],
        "date_range_start": 2015,
        "date_range_end": 2026,
        "target_databases": ["unsupported_db"],
    }
    csv_content = (
        "Authors,Title,Year,Source title,DOI,Link,Abstract,Author Keywords\n"
        "A. Author,Supplementary Paper,2023,Journal S,10.1000/s,https://example.org/s,Abstract S,keyword\n"
    )
    response = await client.post(
        "/api/run-with-supplementary-csv",
        data={
            "review_yaml": yaml.safe_dump(review_payload),
            "gemini_api_key": "fake-key-for-test",
            "run_root": "/tmp/litreview_test_runs",
        },
        files={"csv_file": ("supplementary.csv", csv_content.encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 200
    data = response.json()
    assert "run_id" in data
    assert "topic" in data


def test_inject_csv_paths_replaces_staged_supplementary_paths() -> None:
    import yaml

    review_yaml = yaml.safe_dump(
        {
            "research_question": "RQ",
            "supplementary_csv_paths": [
                "/tmp/lit_runs/staging/oldrun/supplementary.csv",
                "/tmp/manual/supplementary_extra.csv",
            ],
        }
    )
    merged_yaml = _inject_csv_paths_into_yaml(
        review_yaml,
        supplementary_csv_paths=["/tmp/lit_runs/staging/newrun/supplementary.csv"],
        run_root="/tmp/lit_runs",
        replace_staged_supplementary_paths=True,
    )
    payload = yaml.safe_load(merged_yaml)
    paths = payload.get("supplementary_csv_paths", [])
    assert paths == [
        str(Path("/tmp/manual/supplementary_extra.csv").resolve()),
        str(Path("/tmp/lit_runs/staging/newrun/supplementary.csv").resolve()),
    ]


@pytest.mark.asyncio
async def test_start_run_with_supplementary_csv_drops_old_staged_paths(client: httpx.AsyncClient) -> None:
    import yaml

    review_payload = {
        "research_question": "Does blended learning improve retention?",
        "review_type": "systematic",
        "pico": {
            "population": "medical students",
            "intervention": "blended learning",
            "comparison": "traditional teaching",
            "outcome": "knowledge retention",
        },
        "keywords": ["blended learning", "medical education"],
        "domain": "medical education",
        "scope": "",
        "inclusion_criteria": ["peer reviewed"],
        "exclusion_criteria": ["opinion pieces"],
        "date_range_start": 2015,
        "date_range_end": 2026,
        "target_databases": ["unsupported_db"],
        "supplementary_csv_paths": ["/tmp/litreview_test_runs/staging/older/supplementary.csv"],
    }
    csv_content = (
        "Authors,Title,Year,Source title,DOI,Link,Abstract,Author Keywords\n"
        "A. Author,Supplementary Paper,2023,Journal S,10.1000/s,https://example.org/s,Abstract S,keyword\n"
    )
    response = await client.post(
        "/api/run-with-supplementary-csv",
        data={
            "review_yaml": yaml.safe_dump(review_payload),
            "gemini_api_key": "fake-key-for-test",
            "run_root": "/tmp/litreview_test_runs",
        },
        files={"csv_file": ("supplementary.csv", csv_content.encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 200
    run_id = response.json()["run_id"]
    record = _active_runs[run_id]
    merged_yaml = yaml.safe_load(record.review_yaml)
    paths = merged_yaml.get("supplementary_csv_paths", [])
    assert len(paths) == 1
    assert "/tmp/litreview_test_runs/staging/" in paths[0]
    assert paths[0].endswith("/supplementary.csv")


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
        await repo.update_workflow_status("wf-9999", "interrupted")

    registry_path = run_root / "workflows_registry.db"
    async with aiosqlite.connect(str(registry_path)) as reg_db:
        await reg_db.executescript(REGISTRY_SCHEMA)
        await reg_db.execute(
            """
            INSERT OR REPLACE INTO workflows_registry (workflow_id, topic, config_hash, db_path, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("wf-9999", "Test topic", "hash-1", str(db_path), "interrupted"),
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
async def test_fetch_pdfs_emits_reason_codes(
    client: httpx.AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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


@pytest.mark.asyncio
async def test_history_attach_runs_runtime_db_migrations(client: httpx.AsyncClient, tmp_path: Path) -> None:
    """Attaching historical runs should migrate legacy runtime.db schemas."""
    db_path = tmp_path / "legacy_runtime.db"
    async with aiosqlite.connect(str(db_path)) as db:
        # Minimal legacy schema snapshot: decision_log without workflow_id.
        await db.executescript(
            """
            CREATE TABLE workflows (workflow_id TEXT PRIMARY KEY, topic TEXT, config_hash TEXT, status TEXT);
            CREATE TABLE event_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                ts TEXT NOT NULL
            );
            CREATE TABLE decision_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decision_type TEXT NOT NULL,
                paper_id TEXT,
                decision TEXT NOT NULL,
                rationale TEXT NOT NULL,
                actor TEXT NOT NULL,
                phase TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE cost_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model TEXT NOT NULL,
                tokens_in INTEGER NOT NULL,
                tokens_out INTEGER NOT NULL,
                cost_usd REAL NOT NULL,
                latency_ms INTEGER NOT NULL,
                phase TEXT NOT NULL
            );
            """
        )
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            ("wf-legacy", "Legacy Topic", "hash", "completed"),
        )
        await db.commit()

    resp = await client.post(
        "/api/history/attach",
        json={
            "workflow_id": "wf-legacy",
            "topic": "Legacy Topic",
            "db_path": str(db_path),
            "status": "completed",
        },
    )
    assert resp.status_code == 200

    async with aiosqlite.connect(str(db_path)) as db:
        cols = await (await db.execute("PRAGMA table_info(decision_log)")).fetchall()
    col_names = {str(r[1]) for r in cols}
    assert "workflow_id" in col_names


@pytest.mark.asyncio
async def test_attach_history_stale_request_uses_terminal_evidence_and_skips_fake_stale_error(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "attach_terminal.db"
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            ("wf-attach-ok", "Topic", "hash", "completed"),
        )
        await db.execute(
            "INSERT INTO event_log (workflow_id, event_type, payload, ts) VALUES (?, ?, ?, ?)",
            (
                "wf-attach-ok",
                "done",
                json.dumps({"type": "done", "outputs": {"status": "completed"}, "ts": "2026-03-10T10:00:00.000Z"}),
                "2026-03-10T10:00:00.000Z",
            ),
        )
        await db.commit()

    resp = await client.post(
        "/api/history/attach",
        json={
            "workflow_id": "wf-attach-ok",
            "topic": "Topic",
            "db_path": str(db_path),
            "status": "stale",
        },
    )
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]
    events_resp = await client.get(f"/api/run/{run_id}/events")
    assert events_resp.status_code == 200
    payload = events_resp.json()
    messages = [e.get("msg", "") for e in payload["events"] if isinstance(e, dict)]
    assert not any("Run ended with status: stale" in m for m in messages)


@pytest.mark.asyncio
async def test_attach_history_true_stale_injects_orphaned_message(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "attach_stale.db"
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            ("wf-attach-stale", "Topic", "hash", "running"),
        )
        await db.commit()

    resp = await client.post(
        "/api/history/attach",
        json={
            "workflow_id": "wf-attach-stale",
            "topic": "Topic",
            "db_path": str(db_path),
            "status": "stale",
        },
    )
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]
    events_resp = await client.get(f"/api/run/{run_id}/events")
    assert events_resp.status_code == 200
    payload = events_resp.json()
    messages = [e.get("msg", "") for e in payload["events"] if isinstance(e, dict)]
    assert any("Workflow appears orphaned" in m for m in messages)


@pytest.mark.asyncio
async def test_attach_history_preserves_reason_fields_in_events(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "attach_reason_fields.db"
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            ("wf-reason", "Topic", "hash", "completed"),
        )
        await db.execute(
            "INSERT INTO event_log (workflow_id, event_type, payload, ts) VALUES (?, ?, ?, ?)",
            (
                "wf-reason",
                "screening_decision",
                json.dumps(
                    {
                        "type": "screening_decision",
                        "paper_id": "p-1",
                        "stage": "title_abstract",
                        "decision": "exclude",
                        "reason_code": "keyword_filter",
                        "reason_label": "Skipped: no intervention keyword match",
                        "action": "exclude",
                        "entity_type": "paper",
                        "entity_id": "p-1",
                        "ts": "2026-03-10T10:00:00.000Z",
                    }
                ),
                "2026-03-10T10:00:00.000Z",
            ),
        )
        await db.commit()

    resp = await client.post(
        "/api/history/attach",
        json={
            "workflow_id": "wf-reason",
            "topic": "Topic",
            "db_path": str(db_path),
            "status": "completed",
        },
    )
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]
    events_resp = await client.get(f"/api/run/{run_id}/events")
    assert events_resp.status_code == 200
    payload = events_resp.json()
    decision = next(e for e in payload["events"] if e.get("type") == "screening_decision")
    assert decision["reason_code"] == "keyword_filter"
    assert decision["reason_label"] == "Skipped: no intervention keyword match"
    assert decision["action"] == "exclude"
    assert decision["entity_type"] == "paper"
    assert decision["entity_id"] == "p-1"


@pytest.mark.asyncio
async def test_attach_history_injects_event_id_when_missing_in_payload(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "attach_event_id_fallback.db"
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            ("wf-event-id-fallback", "Topic", "hash", "completed"),
        )
        await db.execute(
            "INSERT INTO event_log (workflow_id, event_type, payload, ts) VALUES (?, ?, ?, ?)",
            (
                "wf-event-id-fallback",
                "status",
                json.dumps({"type": "status", "message": "hello", "ts": "2026-03-10T10:00:00.000Z"}),
                "2026-03-10T10:00:00.000Z",
            ),
        )
        await db.execute(
            "INSERT INTO event_log (workflow_id, event_type, payload, ts) VALUES (?, ?, ?, ?)",
            (
                "wf-event-id-fallback",
                "status",
                json.dumps(
                    {
                        "id": "evt-existing-1",
                        "type": "status",
                        "message": "already has id",
                        "ts": "2026-03-10T10:00:01.000Z",
                    }
                ),
                "2026-03-10T10:00:01.000Z",
            ),
        )
        await db.commit()

    resp = await client.post(
        "/api/history/attach",
        json={
            "workflow_id": "wf-event-id-fallback",
            "topic": "Topic",
            "db_path": str(db_path),
            "status": "completed",
        },
    )
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]

    events_resp = await client.get(f"/api/run/{run_id}/events")
    assert events_resp.status_code == 200
    payload = events_resp.json()
    events = payload["events"]
    assert len(events) == 2
    assert str(events[0].get("id", "")).startswith("db-")
    assert events[1]["id"] == "evt-existing-1"


@pytest.mark.asyncio
async def test_export_endpoint_accepts_workflow_identifier_via_resolver(
    client: httpx.AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_id = "wf-export-fallback"
    run_dir = tmp_path / "2026-03-17" / "wf-export-fallback-topic" / "run_01-00-00PM"
    db_path = run_dir / "runtime.db"
    submission_dir = run_dir / "submission"
    study_pdfs_dir = submission_dir / "study_pdfs"
    run_dir.mkdir(parents=True, exist_ok=True)
    submission_dir.mkdir(parents=True, exist_ok=True)
    study_pdfs_dir.mkdir(parents=True, exist_ok=True)
    (submission_dir / "manuscript.tex").write_text("tex", encoding="utf-8")
    (submission_dir / "references.bib").write_text("bib", encoding="utf-8")
    (submission_dir / "manuscript.docx").write_bytes(b"docx")
    (run_dir / "run_summary.json").write_text(
        json.dumps(
            {
                "workflow_id": workflow_id,
                "output_dir": str(run_dir),
                "artifacts": {},
            }
        ),
        encoding="utf-8",
    )

    async def _resolve(_identifier: str, _run_root: str = "runs") -> str:
        return str(db_path)

    monkeypatch.setattr("src.web.app._resolve_db_path_from_run_or_workflow", _resolve)

    response = await client.post(f"/api/run/{workflow_id}/export?run_root={tmp_path}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["submission_dir"] == str(submission_dir)
    assert any(path.endswith("manuscript.docx") for path in payload["files"])


@pytest.mark.asyncio
async def test_submission_zip_endpoint_accepts_workflow_identifier_via_resolver(
    client: httpx.AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_id = "wf-submission-fallback"
    run_dir = tmp_path / "2026-03-17" / "wf-submission-fallback-topic" / "run_01-00-00PM"
    db_path = run_dir / "runtime.db"
    submission_dir = run_dir / "submission"
    run_dir.mkdir(parents=True, exist_ok=True)
    submission_dir.mkdir(parents=True, exist_ok=True)
    (submission_dir / "manuscript.tex").write_text("tex", encoding="utf-8")
    (run_dir / "run_summary.json").write_text(
        json.dumps(
            {
                "workflow_id": workflow_id,
                "output_dir": str(run_dir),
                "artifacts": {},
            }
        ),
        encoding="utf-8",
    )

    async def _resolve(_identifier: str, _run_root: str = "runs") -> str:
        return str(db_path)

    async def _topic(_db_path: str) -> str:
        return "Topic"

    monkeypatch.setattr("src.web.app._resolve_db_path_from_run_or_workflow", _resolve)
    monkeypatch.setattr("src.web.app._get_topic_for_db", _topic)

    response = await client.get(f"/api/run/{workflow_id}/submission.zip")
    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("application/zip")
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        assert "manuscript.tex" in zf.namelist()


@pytest.mark.asyncio
async def test_manuscript_docx_endpoint_accepts_workflow_identifier_via_resolver(
    client: httpx.AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_id = "wf-docx-fallback"
    run_dir = tmp_path / "2026-03-17" / "wf-docx-fallback-topic" / "run_01-00-00PM"
    db_path = run_dir / "runtime.db"
    submission_dir = run_dir / "submission"
    run_dir.mkdir(parents=True, exist_ok=True)
    submission_dir.mkdir(parents=True, exist_ok=True)
    (submission_dir / "manuscript.docx").write_bytes(b"docx")
    (run_dir / "run_summary.json").write_text(
        json.dumps(
            {
                "workflow_id": workflow_id,
                "output_dir": str(run_dir),
                "artifacts": {},
            }
        ),
        encoding="utf-8",
    )

    async def _resolve(_identifier: str, _run_root: str = "runs") -> str:
        return str(db_path)

    async def _topic(_db_path: str) -> str:
        return "Topic"

    monkeypatch.setattr("src.web.app._resolve_db_path_from_run_or_workflow", _resolve)
    monkeypatch.setattr("src.web.app._get_topic_for_db", _topic)

    response = await client.get(f"/api/run/{workflow_id}/manuscript.docx")
    assert response.status_code == 200
    assert (
        response.headers.get("content-type", "")
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


@pytest.mark.asyncio
async def test_attach_history_ignores_app_jsonl_when_event_log_empty(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "2026-03-10" / "wf-clean" / "run_01-00-00PM"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = run_dir / "runtime.db"
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            ("wf-clean", "Topic", "hash", "completed"),
        )
        await db.commit()
    # Legacy sibling log should be ignored now for DB-only replay.
    (run_dir / "app.jsonl").write_text(
        '{"event":"phase","action":"start","phase":"phase_1_setup","timestamp":"2026-03-10T10:00:00.000Z"}\n',
        encoding="utf-8",
    )

    resp = await client.post(
        "/api/history/attach",
        json={
            "workflow_id": "wf-clean",
            "topic": "Topic",
            "db_path": str(db_path),
            "status": "completed",
        },
    )
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]
    events_resp = await client.get(f"/api/run/{run_id}/events")
    assert events_resp.status_code == 200
    payload = events_resp.json()
    assert payload["events"] == []


@pytest.mark.asyncio
async def test_stream_replay_respects_last_event_id_and_includes_terminal_event(client: httpx.AsyncClient) -> None:
    run_id = "run-stream-replay"
    record = _RunRecord(run_id=run_id, topic="Replay Test")
    record.done = True
    record.event_log = [
        {"type": "status", "msg": "phase-start"},
        {"type": "status", "msg": "phase-progress"},
        {"type": "done", "outputs": {"ok": True}},
    ]
    _active_runs[run_id] = record
    try:
        response = await client.get(
            f"/api/stream/{run_id}",
            headers={"Last-Event-ID": "0"},
        )
        assert response.status_code == 200
        body = response.text
        assert "id: 1" in body
        assert "phase-progress" in body
        assert "id: 2" in body
        assert '"type":"done"' in body or '"type": "done"' in body
        assert "id: 0" not in body
    finally:
        _active_runs.pop(run_id, None)


@pytest.mark.asyncio
async def test_manuscript_endpoint_prefers_db_assembly(client: httpx.AsyncClient, tmp_path: Path) -> None:
    run_id = "run-manuscript-assembly"
    workflow_id = "wf-manuscript-assembly"
    run_dir = tmp_path / "2026-03-10" / "wf-manuscript-assembly-topic" / "run_01-00-00PM"
    db_path = run_dir / "runtime.db"
    run_dir.mkdir(parents=True, exist_ok=True)

    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            (workflow_id, "Topic", "hash", "completed"),
        )
        await db.execute(
            """
            INSERT INTO manuscript_sections
                (workflow_id, section_key, section_order, version, title, status, source,
                 boundary_confidence, content_hash, content)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (workflow_id, "results", 0, 1, "Results", "draft", "parser", 1.0, "hash", "Section content"),
        )
        await db.execute(
            """
            INSERT INTO manuscript_assemblies
                (workflow_id, assembly_id, target_format, content, manifest_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                workflow_id,
                "latest",
                "md",
                "# Title\n\nDB assembly content.",
                '{"sections":[{"section_key":"results","version":1,"order":0}]}',
            ),
        )
        await db.commit()

    record = _RunRecord(run_id, "Topic")
    record.db_path = str(db_path)
    record.workflow_id = workflow_id
    record.done = True
    _active_runs[run_id] = record
    try:
        resp = await client.get(f"/api/run/{run_id}/manuscript?fmt=md")
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "assembly"
        assert "DB assembly content." in data["content"]
    finally:
        _active_runs.pop(run_id, None)


@pytest.mark.asyncio
async def test_generate_config_stream_includes_topic_routing_metadata(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_generate_config_yaml(
        research_question: str,
        progress_cb=None,
    ) -> str:
        assert research_question
        if progress_cb is not None:
            progress_cb({"step": "web_research"})
            progress_cb(
                {
                    "step": "topic_routing",
                    "domain": "ambiguous",
                    "confidence": 0.41,
                    "policy": "low_confidence_fallback",
                }
            )
            progress_cb({"step": "finalizing"})
        return 'research_question: "x"\nreview_type: "systematic"\n'

    monkeypatch.setattr(
        "src.web.config_generator.generate_config_yaml",
        _fake_generate_config_yaml,
    )

    resp = await client.post(
        "/api/config/generate/stream",
        json={"research_question": "test question", "gemini_api_key": "test-key"},
    )
    assert resp.status_code == 200
    payloads: list[dict[str, object]] = []
    for line in resp.text.splitlines():
        if line.startswith("data: "):
            payloads.append(json.loads(line[6:]))

    routing_events = [
        p
        for p in payloads
        if p.get("type") == "progress" and p.get("step") == "topic_routing"
    ]
    assert len(routing_events) == 1
    routing = routing_events[0]
    assert routing.get("domain") == "ambiguous"
    assert routing.get("policy") == "low_confidence_fallback"
    assert routing.get("confidence") == 0.41


@pytest.mark.asyncio
async def test_generate_config_stream_done_event_includes_quality_metrics(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_generate_config_yaml(
        research_question: str,
        progress_cb=None,
    ) -> str:
        assert research_question
        if progress_cb is not None:
            progress_cb({"step": "structuring"})
            progress_cb({"step": "finalizing"})
        return """
research_question: "What is the impact of robotic dispensing systems?"
review_type: "systematic"
pico:
  population: "University health centers"
  intervention: "Robotic dispensing systems"
  comparison: "Manual dispensing"
  outcome: "Accuracy and cost"
keywords:
  - "robotic dispensing"
  - "automated dispensing cabinets"
  - "omnicell"
  - "scriptpro"
  - "university health centers"
  - "dispensing accuracy"
  - "operational costs"
  - "medication errors"
  - "staff workload"
  - "pharmacy workflow"
  - "manual dispensing"
  - "prescription turnaround"
  - "automation tools"
  - "pharmacy operations"
  - "workflow efficiency"
domain: "Pharmacy automation in healthcare settings"
scope: "Robotic dispensing impact on accuracy and operational costs."
inclusion_criteria:
  - "Empirical studies."
  - "Comparative design."
  - "Healthcare settings."
  - "Quantitative outcomes."
exclusion_criteria:
  - "Opinion pieces."
  - "No measurable outcomes."
  - "No intervention details."
target_databases:
  - openalex
  - scopus
search_overrides:
  openalex: "robotic dispensing university health center dispensing accuracy operational costs"
"""

    monkeypatch.setattr(
        "src.web.config_generator.generate_config_yaml",
        _fake_generate_config_yaml,
    )

    resp = await client.post(
        "/api/config/generate/stream",
        json={"research_question": "test question", "gemini_api_key": "test-key"},
    )
    assert resp.status_code == 200
    payloads: list[dict[str, object]] = []
    for line in resp.text.splitlines():
        if line.startswith("data: "):
            payloads.append(json.loads(line[6:]))

    done_events = [p for p in payloads if p.get("type") == "done"]
    assert len(done_events) == 1
    done = done_events[0]
    quality = done.get("quality")
    assert isinstance(quality, dict)
    assert "total" in quality
    assert "keyword_quality" in quality
    assert "database_relevance" in quality


@pytest.mark.asyncio
async def test_prisma_checklist_endpoint_returns_missing_artifact_state(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    run_id = "run-prisma-missing"
    workflow_id = "wf-prisma-missing"
    run_dir = tmp_path / "2026-03-17" / "wf-prisma-missing-topic" / "run_01-00-00PM"
    db_path = run_dir / "runtime.db"
    run_dir.mkdir(parents=True, exist_ok=True)

    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            (workflow_id, "Topic", "hash", "completed"),
        )
        await db.commit()

    record = _RunRecord(run_id, "Topic")
    record.db_path = str(db_path)
    record.workflow_id = workflow_id
    record.done = True
    _active_runs[run_id] = record
    try:
        response = await client.get(f"/api/run/{run_id}/prisma-checklist")
        assert response.status_code == 200
        payload = response.json()
        assert payload["source_state"] == "artifact_missing"
        assert payload["total"] == 27
        assert payload["item_total"] >= 40
        assert len(payload["items"]) == payload["item_total"]
    finally:
        _active_runs.pop(run_id, None)


@pytest.mark.asyncio
async def test_prisma_checklist_endpoint_reads_markdown_artifact(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    run_id = "run-prisma-md"
    workflow_id = "wf-prisma-md"
    run_dir = tmp_path / "2026-03-17" / "wf-prisma-md-topic" / "run_01-00-00PM"
    db_path = run_dir / "runtime.db"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "doc_manuscript.md").write_text(
        (
            "# A systematic review of robotic dispensing\n\n"
            "## Abstract\n\n"
            "Objective Methods Results Conclusion\n\n"
            "## Methods\n\n"
            "Eligibility criteria and search strategy used PubMed.\n\n"
            "## Results\n\n"
            "PRISMA flow and included studies were reported.\n"
        ),
        encoding="utf-8",
    )

    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            (workflow_id, "Topic", "hash", "completed"),
        )
        await db.commit()

    record = _RunRecord(run_id, "Topic")
    record.db_path = str(db_path)
    record.workflow_id = workflow_id
    record.done = True
    _active_runs[run_id] = record
    try:
        response = await client.get(f"/api/run/{run_id}/prisma-checklist")
        assert response.status_code == 200
        payload = response.json()
        assert payload["source_state"] == "validated_md"
        assert payload["item_total"] >= 40
        assert any(item["item_id"] == "1" for item in payload["items"])
    finally:
        _active_runs.pop(run_id, None)


@pytest.mark.asyncio
async def test_workflow_manuscript_audit_endpoints_return_expected_shapes(
    client: httpx.AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_id = "wf-audit-shape"
    run_dir = tmp_path / "2026-03-17" / "wf-audit-shape-topic" / "run_01-00-00PM"
    db_path = run_dir / "runtime.db"
    run_dir.mkdir(parents=True, exist_ok=True)
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            (workflow_id, "Topic", "hash", "completed"),
        )
        await db.execute(
            """
            INSERT INTO manuscript_audit_runs (
                audit_run_id, workflow_id, mode, verdict, passed, selected_profiles_json, summary,
                total_findings, major_count, minor_count, note_count, blocking_count, total_cost_usd
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "audit-001",
                workflow_id,
                "observe",
                "minor_revisions",
                1,
                json.dumps(["general_systematic_review"]),
                "Looks mostly good",
                1,
                0,
                1,
                0,
                0,
                0.031,
            ),
        )
        await db.execute(
            """
            INSERT INTO manuscript_audit_findings (
                audit_run_id, workflow_id, finding_id, profile, severity, category, section, evidence,
                recommendation, owner_module, blocking
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "audit-001",
                workflow_id,
                "general_systematic_review-1",
                "general_systematic_review",
                "minor",
                "reporting",
                "Methods",
                "Eligibility details are short",
                "Expand inclusion criteria details",
                "writing",
                0,
            ),
        )
        await db.commit()

    async def _resolve(_identifier: str, _run_root: str = "runs") -> str:
        return str(db_path)

    monkeypatch.setattr("src.web.app._resolve_db_path_from_run_or_workflow", _resolve)

    summary_resp = await client.get(f"/api/workflow/{workflow_id}/manuscript-audit/summary")
    assert summary_resp.status_code == 200
    summary_payload = summary_resp.json()
    assert summary_payload["workflow_id"] == workflow_id
    assert summary_payload["latest_run"]["audit_run_id"] == "audit-001"
    assert isinstance(summary_payload["history"], list)
    assert summary_payload["history"][0]["selected_profiles"] == ["general_systematic_review"]

    findings_resp = await client.get(f"/api/workflow/{workflow_id}/manuscript-audit/findings")
    assert findings_resp.status_code == 200
    findings_payload = findings_resp.json()
    assert findings_payload["audit_run_id"] == "audit-001"
    assert len(findings_payload["findings"]) == 1
    assert findings_payload["findings"][0]["owner_module"] == "writing"


@pytest.mark.asyncio
async def test_workflow_manuscript_audit_findings_returns_empty_for_unknown_or_wrong_scope(
    client: httpx.AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_id = "wf-audit-empty"
    run_dir = tmp_path / "2026-03-17" / "wf-audit-empty-topic" / "run_01-00-00PM"
    db_path = run_dir / "runtime.db"
    run_dir.mkdir(parents=True, exist_ok=True)
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            (workflow_id, "Topic", "hash", "completed"),
        )
        await db.execute(
            """
            INSERT INTO manuscript_audit_runs (
                audit_run_id, workflow_id, mode, verdict, passed, selected_profiles_json, summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "audit-other",
                "wf-different",
                "observe",
                "accept",
                1,
                "[]",
                "other workflow run",
            ),
        )
        await db.commit()

    async def _resolve(_identifier: str, _run_root: str = "runs") -> str:
        return str(db_path)

    monkeypatch.setattr("src.web.app._resolve_db_path_from_run_or_workflow", _resolve)

    latest_resp = await client.get(f"/api/workflow/{workflow_id}/manuscript-audit/findings")
    assert latest_resp.status_code == 200
    latest_payload = latest_resp.json()
    assert latest_payload == {"workflow_id": workflow_id, "audit_run_id": None, "findings": []}

    scoped_resp = await client.get(f"/api/workflow/{workflow_id}/manuscript-audit/findings?audit_run_id=audit-other")
    assert scoped_resp.status_code == 200
    scoped_payload = scoped_resp.json()
    assert scoped_payload == {"workflow_id": workflow_id, "audit_run_id": None, "findings": []}


@pytest.mark.asyncio
async def test_run_manuscript_audit_endpoint_returns_empty_payload_when_no_audit_data(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    run_id = "run-audit-empty"
    workflow_id = "wf-audit-empty-run"
    run_dir = tmp_path / "2026-03-17" / "wf-audit-empty-run-topic" / "run_01-00-00PM"
    db_path = run_dir / "runtime.db"
    run_dir.mkdir(parents=True, exist_ok=True)

    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            (workflow_id, "Topic", "hash", "completed"),
        )
        await db.commit()

    record = _RunRecord(run_id, "Topic")
    record.db_path = str(db_path)
    record.workflow_id = workflow_id
    record.done = True
    _active_runs[run_id] = record
    try:
        response = await client.get(f"/api/run/{run_id}/manuscript-audit")
        assert response.status_code == 200
        payload = response.json()
        assert payload["run_id"] == run_id
        assert payload["workflow_id"] == workflow_id
        assert payload["latest_run"] is None
        assert payload["history"] == []
        assert payload["findings"] == []
    finally:
        _active_runs.pop(run_id, None)


@pytest.mark.asyncio
async def test_workflow_manuscript_audit_endpoints_graceful_when_audit_tables_missing(
    client: httpx.AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_id = "wf-audit-legacy"
    run_dir = tmp_path / "2026-03-17" / "wf-audit-legacy-topic" / "run_01-00-00PM"
    db_path = run_dir / "runtime.db"
    run_dir.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute(
            """
            CREATE TABLE workflows (
                workflow_id TEXT PRIMARY KEY,
                topic TEXT NOT NULL,
                config_hash TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            (workflow_id, "Topic", "hash", "completed"),
        )
        await db.commit()

    async def _resolve(_identifier: str, _run_root: str = "runs") -> str:
        return str(db_path)

    monkeypatch.setattr("src.web.app._resolve_db_path_from_run_or_workflow", _resolve)

    summary_resp = await client.get(f"/api/workflow/{workflow_id}/manuscript-audit/summary")
    assert summary_resp.status_code == 200
    assert summary_resp.json() == {"workflow_id": workflow_id, "latest_run": None, "history": []}

    findings_resp = await client.get(f"/api/workflow/{workflow_id}/manuscript-audit/findings")
    assert findings_resp.status_code == 200
    assert findings_resp.json() == {"workflow_id": workflow_id, "audit_run_id": None, "findings": []}


@pytest.mark.asyncio
async def test_run_manuscript_audit_endpoint_graceful_when_audit_tables_missing(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    run_id = "run-audit-legacy"
    workflow_id = "wf-audit-legacy-run"
    run_dir = tmp_path / "2026-03-17" / "wf-audit-legacy-run-topic" / "run_01-00-00PM"
    db_path = run_dir / "runtime.db"
    run_dir.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute(
            """
            CREATE TABLE workflows (
                workflow_id TEXT PRIMARY KEY,
                topic TEXT NOT NULL,
                config_hash TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            (workflow_id, "Topic", "hash", "completed"),
        )
        await db.commit()

    record = _RunRecord(run_id, "Topic")
    record.db_path = str(db_path)
    record.workflow_id = workflow_id
    record.done = True
    _active_runs[run_id] = record
    try:
        response = await client.get(f"/api/run/{run_id}/manuscript-audit")
        assert response.status_code == 200
        payload = response.json()
        assert payload["run_id"] == run_id
        assert payload["workflow_id"] == workflow_id
        assert payload["latest_run"] is None
        assert payload["history"] == []
        assert payload["findings"] == []
    finally:
        _active_runs.pop(run_id, None)
