"""Integration gate: FastAPI routers must match Section 10.1 endpoint parity."""

from __future__ import annotations

from pathlib import Path

from scripts.check_spec_endpoint_parity import run_parity_check

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_live_app_endpoint_parity_with_spec() -> None:
    exit_code = run_parity_check(
        REPO_ROOT / ".cursor" / "docs" / "API_ENDPOINTS.md",
        REPO_ROOT / "src" / "web" / "app.py",
    )
    assert exit_code == 0, "Endpoint parity check failed — run scripts/check_spec_endpoint_parity.py"
