from __future__ import annotations

import pytest

from src.orchestration.phase_catalog import (
    PHASE_ORDER,
    PRE_WRITING_PHASE_ORDER,
    SUB_PHASE_CHECKPOINTS,
    UI_TIMELINE_PHASE_ORDER,
    USER_RESUMABLE_PHASE_ORDER,
    rollback_cascade_for,
)


@pytest.mark.parametrize(
    ("phase", "expected"),
    [
        ("phase_2_search", list(PHASE_ORDER)),
        ("phase_3_screening", PHASE_ORDER[1:]),
        ("phase_4_extraction_quality", PHASE_ORDER[2:]),
        ("phase_4b_embedding", PHASE_ORDER[3:]),
        ("phase_5_synthesis", PHASE_ORDER[4:]),
        ("phase_5b_knowledge_graph", PHASE_ORDER[5:]),
        ("phase_5c_pre_writing_gate", PHASE_ORDER[6:]),
        ("phase_6_writing", PHASE_ORDER[7:]),
        ("phase_7_audit", PHASE_ORDER[8:]),
        ("finalize", ["finalize"]),
    ],
)
def test_rollback_cascade_for_matrix(phase: str, expected: list[str]) -> None:
    assert rollback_cascade_for(phase) == expected
    assert phase in expected
    assert expected[0] == phase


def test_rollback_cascade_for_unknown_phase() -> None:
    assert rollback_cascade_for("phase_99_unknown") == []


def test_user_resumable_phase_order_excludes_audit() -> None:
    assert "phase_7_audit" in PHASE_ORDER
    assert "phase_7_audit" not in USER_RESUMABLE_PHASE_ORDER
    assert USER_RESUMABLE_PHASE_ORDER == [p for p in PHASE_ORDER if p != "phase_7_audit"]


def test_ui_timeline_includes_fulltext_pdf_retrieval() -> None:
    assert "fulltext_pdf_retrieval" in UI_TIMELINE_PHASE_ORDER
    assert "fulltext_pdf_retrieval" not in PHASE_ORDER


def test_pre_writing_phase_order_is_subsequence_of_phase_order() -> None:
    phase_indices = [PHASE_ORDER.index(phase) for phase in PRE_WRITING_PHASE_ORDER]
    assert phase_indices == sorted(phase_indices)


def test_sub_phase_checkpoint_keys_align_with_phase_order() -> None:
    for parent_phase, sub_phases in SUB_PHASE_CHECKPOINTS.items():
        assert parent_phase in PHASE_ORDER, f"{parent_phase!r} missing from PHASE_ORDER"
        assert sub_phases, f"{parent_phase!r} must list at least one sub-phase checkpoint"
        for sub_phase in sub_phases:
            assert sub_phase not in PHASE_ORDER, f"{sub_phase!r} should not appear in PHASE_ORDER (sub-phase only)"
