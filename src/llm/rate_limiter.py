"""Simple async rate limiter keyed by model tier."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Deque, Dict


class RateLimiter:
    def __init__(self, flash_rpm: int = 10, pro_rpm: int = 5):
        self._limits = {
            "flash-lite": flash_rpm,
            "flash": flash_rpm,
            "pro": pro_rpm,
        }
        self._calls: Dict[str, Deque[float]] = {tier: deque() for tier in self._limits}

    async def acquire(self, tier: str) -> None:
        normalized = tier.lower()
        if normalized not in self._limits:
            return
        window = 60.0
        while True:
            now = time.monotonic()
            queue = self._calls[normalized]
            while queue and (now - queue[0]) > window:
                queue.popleft()
            if len(queue) < self._limits[normalized]:
                queue.append(now)
                return
            await asyncio.sleep(0.05)
