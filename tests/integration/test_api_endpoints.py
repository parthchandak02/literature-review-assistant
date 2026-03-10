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
from src.web.app import _active_runs, _RunRecord, app

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
            (workflow_id, "latest", "md", "# Title\n\nDB assembly content.", '{"sections":[{"section_key":"results","version":1,"order":0}]}'),
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
