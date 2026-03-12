from __future__ import annotations

from scripts.check_spec_endpoint_parity import (
    Endpoint,
    compare_endpoint_sets,
    extract_fastapi_endpoints,
    parse_spec_endpoints,
)


def test_parse_spec_endpoints_reads_only_10_1_table() -> None:
    spec_text = """
## 10. API Contract

### 10.1 REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/run | Start run |
| GET | /api/health | Health |

### 10.1.1 Endpoint Parity Checklist

Not part of the table.
""".strip()
    endpoints = parse_spec_endpoints(spec_text)
    assert endpoints == {
        Endpoint(method="POST", path="/api/run"),
        Endpoint(method="GET", path="/api/health"),
    }


def test_extract_fastapi_endpoints_applies_ignore_rules() -> None:
    app_source = """
from fastapi import FastAPI

app = FastAPI()

@app.post("/api/run")
async def start():
    return {}

@app.get("/api/internal", include_in_schema=False)
async def internal():
    return {}

@app.get("/{full_path:path}", include_in_schema=False)
async def catch_all():
    return {}

@app.get("/health")
async def health():
    return {}

@app.api_route("/api/multi", methods=["GET", "POST"])
async def multi():
    return {}
""".strip()
    endpoints = extract_fastapi_endpoints(app_source)
    assert endpoints == {
        Endpoint(method="POST", path="/api/run"),
        Endpoint(method="GET", path="/api/multi"),
        Endpoint(method="POST", path="/api/multi"),
    }


def test_compare_endpoint_sets_reports_missing_and_stale() -> None:
    spec_endpoints = {
        Endpoint(method="POST", path="/api/run"),
        Endpoint(method="GET", path="/api/obsolete"),
    }
    app_endpoints = {
        Endpoint(method="POST", path="/api/run"),
        Endpoint(method="GET", path="/api/new"),
    }

    diff = compare_endpoint_sets(spec_endpoints, app_endpoints)

    assert diff.missing_in_docs == {Endpoint(method="GET", path="/api/new")}
    assert diff.stale_in_docs == {Endpoint(method="GET", path="/api/obsolete")}
    assert not diff.ok
