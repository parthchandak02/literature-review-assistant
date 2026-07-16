"""Global concurrency gate for concurrent workflow runs via the web API."""

from __future__ import annotations

import asyncio

from fastapi import HTTPException

from src.config.loader import load_configs as _load_configs

_semaphore: asyncio.Semaphore | None = None
_limit: int | None = None
_acquire_lock: asyncio.Lock | None = None


def _get_acquire_lock() -> asyncio.Lock:
    global _acquire_lock
    if _acquire_lock is None:
        _acquire_lock = asyncio.Lock()
    return _acquire_lock


def _load_limit() -> int:
    global _limit
    if _limit is None:
        settings = _load_configs(settings_path="config/settings.yaml")[1]
        _limit = settings.web.max_concurrent_runs
    return _limit


def get_run_semaphore() -> asyncio.Semaphore:
    """Return the process-wide run concurrency semaphore."""
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(_load_limit())
    return _semaphore


def reset_run_concurrency_for_tests() -> None:
    """Clear cached limit/semaphore state (unit tests only)."""
    global _semaphore, _limit, _acquire_lock
    _semaphore = None
    _limit = None
    _acquire_lock = None


async def try_acquire_run_slot() -> bool:
    """Try to acquire a run slot without blocking."""
    semaphore = get_run_semaphore()
    async with _get_acquire_lock():
        if semaphore._value <= 0:
            return False
        await semaphore.acquire()
        return True


async def acquire_run_slot_or_raise() -> None:
    """Acquire a run slot or raise HTTP 429 when at capacity."""
    if not await try_acquire_run_slot():
        limit = _load_limit()
        raise HTTPException(
            status_code=429,
            detail=(
                f"Maximum concurrent runs ({limit}) reached. Wait for an active run to finish before starting another."
            ),
            headers={"Retry-After": "60"},
        )


def release_run_slot() -> None:
    """Release a previously acquired run slot."""
    semaphore = get_run_semaphore()
    limit = _load_limit()
    if semaphore._value < limit:
        semaphore.release()
