"""Canonical phase order definitions for orchestration, UI, and rollback."""

from __future__ import annotations

PHASE_ORDER: list[str] = [
    "phase_2_search",
    "phase_3_screening",
    "phase_4_extraction_quality",
    "phase_4b_embedding",
    "phase_5_synthesis",
    "phase_5b_knowledge_graph",
    "phase_5c_pre_writing_gate",
    "phase_6_writing",
    "phase_7_audit",
    "finalize",
]

USER_RESUMABLE_PHASE_ORDER: list[str] = [phase for phase in PHASE_ORDER if phase != "phase_7_audit"]

# UI timeline phase order (matches frontend PHASE_ORDER + phase_7_audit before finalize).
UI_TIMELINE_PHASE_ORDER: tuple[str, ...] = (
    "phase_2_search",
    "phase_3_screening",
    "fulltext_pdf_retrieval",
    "phase_4_extraction_quality",
    "phase_4b_embedding",
    "phase_5_synthesis",
    "phase_5b_knowledge_graph",
    "phase_5c_pre_writing_gate",
    "phase_6_writing",
    "phase_7_audit",
    "finalize",
)

PRE_WRITING_PHASE_ORDER: tuple[str, ...] = (
    "phase_4_extraction_quality",
    "phase_4b_embedding",
    "phase_5_synthesis",
    "phase_5b_knowledge_graph",
    "phase_5c_pre_writing_gate",
    "phase_6_writing",
    "finalize",
)

# Mid-phase checkpoints not in PHASE_ORDER; cleared when parent phase is re-run.
SUB_PHASE_CHECKPOINTS: dict[str, list[str]] = {
    "phase_3_screening": ["phase_3b_fulltext"],
    "phase_6_writing": [
        "phase_6a_hyde",
        "phase_6a2_outline",
        "phase_6b_phase_a",
        "phase_6c_phase_b",
        "phase_6d_assembly",
        "phase_6e_concepts",
        "phase_6f_custom_diagrams",
    ],
}


def rollback_cascade_for(phase: str) -> list[str]:
    """Return phases to clear when rewinding to ``phase`` (inclusive)."""
    try:
        idx = PHASE_ORDER.index(phase)
    except ValueError:
        return []
    return list(PHASE_ORDER[idx:])
