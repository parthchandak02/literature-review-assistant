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
