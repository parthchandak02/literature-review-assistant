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
def clear_pydantic_ai_http_cache() -> None:
    """Clear PydanticAI's cached httpx client before and after each test.

    PydanticAI caches a shared httpx.AsyncClient via _cached_async_http_client
    (a functools.cache wrapper). The transport inside that client holds a direct
    reference to the event loop it was created on. When pytest-asyncio creates a
    new event loop for the next test, the cached transport's loop is already
    closed, triggering RuntimeError: Event loop is closed.

    Clearing the cache before each test forces PydanticAI to create a fresh
    client (and transport) bound to the current event loop.
    """
    from pydantic_ai.models import _cached_async_http_client

    _cached_async_http_client.cache_clear()
    yield
    _cached_async_http_client.cache_clear()


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
