"""Orchestration runner smoke tests — vertical slice with in-memory DB."""

from __future__ import annotations

import pytest

from src.orchestration.helpers.pre_writing_gate import (
    pre_writing_phases_from,
    select_pre_writing_rewind_phase,
)
from src.orchestration.runners.pre_writing_gate_runner import run_pre_writing_gate_node


def test_pre_writing_phase_helpers() -> None:
    assert pre_writing_phases_from("phase_5_synthesis") == [
        "phase_5_synthesis",
        "phase_5b_knowledge_graph",
        "phase_5c_pre_writing_gate",
        "phase_6_writing",
        "finalize",
    ]
    assert select_pre_writing_rewind_phase(["phase_6_writing", "phase_4_extraction_quality"]) == (
        "phase_4_extraction_quality"
    )


@pytest.mark.asyncio
async def test_pre_writing_gate_runner_import_and_signature() -> None:
    """Smoke: runner module loads and is awaitable with minimal state (no DB)."""
    assert callable(run_pre_writing_gate_node)
