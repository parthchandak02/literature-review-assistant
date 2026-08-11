"""Unit tests for workflow-scoped active-run announcement pub/sub."""

from __future__ import annotations

import asyncio

import pytest

from src.web.state import WorkflowActiveRunBroadcaster, _announce_workflow_active_run


@pytest.mark.asyncio
async def test_subscribe_receives_announce() -> None:
    broadcaster = WorkflowActiveRunBroadcaster()
    queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()
    broadcaster.subscribe("wf-test", queue)

    payload = {"workflow_id": "wf-test", "run_id": "abc12345", "topic": "Test topic"}
    broadcaster.announce("wf-test", payload)

    received = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert received == payload


@pytest.mark.asyncio
async def test_announce_does_not_cross_workflows() -> None:
    broadcaster = WorkflowActiveRunBroadcaster()
    queue_a: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()
    queue_b: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()
    broadcaster.subscribe("wf-a", queue_a)
    broadcaster.subscribe("wf-b", queue_b)

    broadcaster.announce("wf-a", {"workflow_id": "wf-a", "run_id": "run-a", "topic": "A"})

    received = await asyncio.wait_for(queue_a.get(), timeout=1.0)
    assert received["run_id"] == "run-a"
    assert queue_b.empty()


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery() -> None:
    broadcaster = WorkflowActiveRunBroadcaster()
    queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()
    broadcaster.subscribe("wf-test", queue)
    broadcaster.unsubscribe("wf-test", queue)

    broadcaster.announce("wf-test", {"workflow_id": "wf-test", "run_id": "gone", "topic": "T"})
    assert queue.empty()


@pytest.mark.asyncio
async def test_full_queue_is_dropped() -> None:
    broadcaster = WorkflowActiveRunBroadcaster()
    queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue(maxsize=1)
    queue.put_nowait({"workflow_id": "wf-test", "run_id": "old", "topic": "Old"})
    broadcaster.subscribe("wf-test", queue)

    broadcaster.announce("wf-test", {"workflow_id": "wf-test", "run_id": "new", "topic": "New"})

    assert queue.qsize() == 1
    assert (await queue.get())["run_id"] == "old"


def test_announce_helper_builds_payload() -> None:
    broadcaster = WorkflowActiveRunBroadcaster()
    queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()
    broadcaster.subscribe("wf-helper", queue)

    import src.web.state as state_module

    original = state_module._workflow_active_run_broadcaster
    state_module._workflow_active_run_broadcaster = broadcaster
    try:
        _announce_workflow_active_run("wf-helper", "run1234", "Helper topic")
    finally:
        state_module._workflow_active_run_broadcaster = original

    payload = queue.get_nowait()
    assert payload == {
        "workflow_id": "wf-helper",
        "run_id": "run1234",
        "topic": "Helper topic",
    }
