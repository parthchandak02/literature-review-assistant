"""Simple async rate limiter keyed by model tier."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable
from typing import Deque, Dict


class RateLimiter:
    def __init__(
        self,
        flash_rpm: int = 10,
        flash_lite_rpm: int = 15,
        pro_rpm: int = 5,
        on_waiting: Callable[[str, int, int], None] | None = None,
    ):
        self._limits = {
            "flash-lite": flash_lite_rpm,
            "flash": flash_rpm,
            "pro": pro_rpm,
        }
        self._calls: Dict[str, Deque[float]] = {tier: deque() for tier in self._limits}
        self._last_request_time: Dict[str, float] = {tier: 0.0 for tier in self._limits}
        self._on_waiting = on_waiting
        self._last_wait_log: Dict[str, float] = {}
        self._wait_log_interval = 30.0

    async def acquire(self, tier: str) -> None:
        normalized = tier.lower()
        if normalized not in self._limits:
            return
        window = 60.0
        limit = self._limits[normalized]
        min_interval = window / limit
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
                return
            last = self._last_wait_log.get(normalized, 0.0)
            if self._on_waiting and (now - last) >= self._wait_log_interval:
                self._on_waiting(normalized, len(queue), limit)
                self._last_wait_log[normalized] = now
            await asyncio.sleep(0.05)
