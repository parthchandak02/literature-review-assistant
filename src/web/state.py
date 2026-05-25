"""State containers for web-layer mutable registries."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any


class RunRegistry:
    """Thin wrapper around the in-memory active run map."""

    def __init__(self, backing: dict[str, Any] | None = None) -> None:
        self._runs: dict[str, Any] = backing if backing is not None else {}

    def get(self, run_id: str) -> Any | None:
        return self._runs.get(run_id)

    def set(self, run_id: str, record: Any) -> None:
        self._runs[run_id] = record

    def pop(self, run_id: str, default: Any = None) -> Any:
        return self._runs.pop(run_id, default)

    def values(self) -> Iterator[Any]:
        return self._runs.values()

    def items(self) -> Iterator[tuple[str, Any]]:
        return self._runs.items()

    def as_dict(self) -> dict[str, Any]:
        return self._runs


class NotesBroadcaster:
    """Broadcast notes update payloads to subscribed queues."""

    def __init__(self, subscribers: set[asyncio.Queue[dict[str, Any] | None]] | None = None) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any] | None]] = subscribers if subscribers is not None else set()

    def subscribe(self, queue: asyncio.Queue[dict[str, Any] | None]) -> None:
        self._subscribers.add(queue)

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any] | None]) -> None:
        self._subscribers.discard(queue)

    def subscribers(self) -> set[asyncio.Queue[dict[str, Any] | None]]:
        return self._subscribers
