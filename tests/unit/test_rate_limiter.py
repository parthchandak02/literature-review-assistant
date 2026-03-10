"""Unit tests for rate limiter."""

from __future__ import annotations

import asyncio
import time

import pytest

from src.llm.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_enforces_minimum_spacing() -> None:
    """Sequential acquires should respect minimum interval between requests."""
    limiter = RateLimiter(flash_lite_rpm=60)
    min_interval = 60.0 / 60

    start = time.monotonic()
    for _ in range(3):
        await limiter.acquire("flash-lite")
    elapsed = time.monotonic() - start

    assert elapsed >= 2 * min_interval - 0.1


@pytest.mark.asyncio
async def test_rate_limiter_concurrent_callers_respect_limit() -> None:
    """Concurrent callers should all eventually acquire without exceeding limit."""
    limiter = RateLimiter(flash_lite_rpm=15)

    async def acquire_once() -> float:
        await limiter.acquire("flash-lite")
        return time.monotonic()

    results = await asyncio.gather(*[acquire_once() for _ in range(5)])
    assert len(results) == 5
    assert all(isinstance(t, float) for t in results)


@pytest.mark.asyncio
async def test_rate_limiter_unknown_tier_returns_immediately() -> None:
    """Unknown tier should not block."""
    limiter = RateLimiter(flash_lite_rpm=15)
    start = time.monotonic()
    await limiter.acquire("unknown-tier")
    elapsed = time.monotonic() - start
    assert elapsed < 0.1


@pytest.mark.asyncio
async def test_on_resolved_fires_after_wait() -> None:
    """on_resolved must fire exactly once after a real wait, with waited_seconds > 0."""
    resolved_calls: list[tuple[str, float]] = []

    def on_resolved(tier: str, waited_seconds: float) -> None:
        resolved_calls.append((tier, waited_seconds))

    # 60 RPM -> 1s min_interval; fill the queue to trigger the sliding-window wait.
    # Clearing both the deque AND last_request_time lets the next poll exit immediately.
    limiter = RateLimiter(flash_rpm=60, on_resolved=on_resolved)
    await limiter.acquire("flash")  # first: no wait, no on_resolved

    assert resolved_calls == [], "on_resolved must not fire on a non-waiting acquire"

    # Pack the call deque to its limit so the next acquire enters the wait loop.
    import time as _time

    now = _time.monotonic()
    for _ in range(59):
        limiter._calls["flash"].append(now)

    async def _fast_expire() -> None:
        # Give the acquire a moment to enter the wait loop, then clear the window
        # and reset last_request_time so the min_interval guard also passes.
        await asyncio.sleep(0.15)
        limiter._calls["flash"].clear()
        limiter._last_request_time["flash"] = 0.0

    await asyncio.gather(limiter.acquire("flash"), _fast_expire())

    assert len(resolved_calls) == 1, f"on_resolved should fire exactly once; got {resolved_calls}"
    tier, waited = resolved_calls[0]
    assert tier == "flash"
    assert waited > 0.0, f"waited_seconds should be positive; got {waited}"


@pytest.mark.asyncio
async def test_waited_seconds_passed_to_on_waiting() -> None:
    """on_waiting 4th arg must be a non-negative float representing elapsed wait time."""
    waiting_calls: list[tuple[str, int, int, float]] = []

    def on_waiting(tier: str, slots_used: int, limit: int, waited_seconds: float) -> None:
        waiting_calls.append((tier, slots_used, limit, waited_seconds))

    # 60 RPM; fill queue to trigger wait, force log interval to 0 so callback fires immediately.
    limiter = RateLimiter(flash_rpm=60, on_waiting=on_waiting, on_resolved=None)
    limiter._wait_log_interval = 0.0
    await limiter.acquire("flash")

    import time as _time

    now = _time.monotonic()
    for _ in range(59):
        limiter._calls["flash"].append(now)

    async def _fast_expire() -> None:
        await asyncio.sleep(0.15)
        limiter._calls["flash"].clear()
        limiter._last_request_time["flash"] = 0.0

    await asyncio.gather(limiter.acquire("flash"), _fast_expire())

    assert waiting_calls, "on_waiting should have been called at least once"
    tier, slots_used, limit, waited_seconds = waiting_calls[0]
    assert tier == "flash"
    assert limit == 60
    assert isinstance(waited_seconds, float)
    assert waited_seconds >= 0.0
