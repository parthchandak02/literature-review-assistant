"""Integration gate: FastAPI routers must match Section 10.1 endpoint parity."""

from __future__ import annotations

from pathlib import Path

from scripts.lib.check_api_docs import run_parity_check

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_live_app_endpoint_parity_with_spec() -> None:
    exit_code = run_parity_check(
        REPO_ROOT / "docs" / "API.md",
        REPO_ROOT / "src" / "web" / "app.py",
    )
    assert exit_code == 0, "Endpoint parity check failed — run scripts/check.py api"
