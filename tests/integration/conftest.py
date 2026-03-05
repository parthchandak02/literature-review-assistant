"""Integration test fixtures and shared setup.

Key responsibility: reset global state that would otherwise leak between tests
and cause cross-test contamination.

Specifically, `src.utils.structured_log` uses a module-level `_configured`
guard so that `configure_run_logging` only runs once per process. This is
correct behavior in production (one process, one run), but in tests multiple
runs in the same process need independent log files.

The `reset_structured_log` autouse fixture clears that flag before every test,
guaranteeing that each test gets its own `app.jsonl` written to its own
`tmp_path` rather than silently inheriting a stale configuration from a
previous test.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def reset_structured_log() -> None:
    """Reset structured_log global state before each test.

    Without this, any test that starts a workflow (e.g. via the API endpoint
    test that calls POST /api/run) will configure the logger to write to that
    run's directory. Subsequent tests that also start workflows then silently
    skip re-configuration and never create their own app.jsonl, causing
    flaky failures that only appear when tests run in a specific order.
    """
    import src.utils.structured_log as sl

    sl._configured = False
    sl._logger = None
