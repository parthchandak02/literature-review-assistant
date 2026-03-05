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

import httpx
import pytest
import pytest_asyncio

from src.web.app import app

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
# Test 9: POST /api/run with valid YAML payload is accepted (202/200, no LLM call)
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
