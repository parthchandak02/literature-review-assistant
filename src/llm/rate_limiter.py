"""Simple async rate limiter keyed by model tier."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable


class RateLimiter:
    def __init__(
        self,
        flash_rpm: int = 10,
        flash_lite_rpm: int = 15,
        pro_rpm: int = 5,
        on_waiting: Callable[[str, int, int, float], None] | None = None,
        on_resolved: Callable[[str, float], None] | None = None,
    ):
        self._limits = {
            "flash-lite": flash_lite_rpm,
            "flash": flash_rpm,
            "pro": pro_rpm,
        }
        self._calls: dict[str, deque[float]] = {tier: deque() for tier in self._limits}
        self._last_request_time: dict[str, float] = {tier: 0.0 for tier in self._limits}
        self._on_waiting = on_waiting
        self._on_resolved = on_resolved
        self._last_wait_log: dict[str, float] = {}
        # Reduced from 30s to 10s so short waits are visible in the Activity log.
        self._wait_log_interval = 10.0
        # Tracks when we started waiting per tier (None = not currently waiting).
        self._wait_start_times: dict[str, float | None] = {tier: None for tier in self._limits}

    async def acquire(self, tier: str) -> None:
        normalized = tier.lower()
        if normalized not in self._limits:
            return
        window = 60.0
        limit = self._limits[normalized]
        min_interval = window / limit
        _was_waiting = False
        while True:
            now = time.monotonic()
            queue = self._calls[normalized]
            while queue and (now - queue[0]) > window:
                queue.popleft()
            if len(queue) < limit:
                last_t = self._last_request_time.get(normalized, 0.0)
                if last_t > 0 and (now - last_t) < min_interval:
                    sleep_for = min_interval - (now - last_t)
                    await asyncio.sleep(sleep_for)
                    now = time.monotonic()
                queue.append(now)
                self._last_request_time[normalized] = now
                # Fire on_resolved if we were waiting this iteration.
                if _was_waiting and self._on_resolved:
                    start = self._wait_start_times.get(normalized)
                    waited = (now - start) if start is not None else 0.0
                    self._on_resolved(normalized, waited)
                    self._wait_start_times[normalized] = None
                return
            # Track when we first entered the wait for this tier.
            if self._wait_start_times.get(normalized) is None:
                self._wait_start_times[normalized] = now
            _was_waiting = True
            wait_start = self._wait_start_times[normalized]
            waited_so_far = (now - wait_start) if wait_start is not None else 0.0
            # Use -inf as sentinel so the first wait always fires immediately.
            last = self._last_wait_log.get(normalized, float("-inf"))
            if self._on_waiting and (now - last) >= self._wait_log_interval:
                self._on_waiting(normalized, len(queue), limit, waited_so_far)
                self._last_wait_log[normalized] = now
            await asyncio.sleep(0.05)
