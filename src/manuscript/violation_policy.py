"""Deterministic mapping from contract violation codes to gate severity.

Centralizes behavior that was previously split across _hard_failure branches.
"""

from __future__ import annotations

# In "soft" gate profile, these codes still block (fail-closed for integrity).
SOFT_BLOCK_CODES: frozenset[str] = frozenset(
    {
        "PLACEHOLDER_LEAK",
        "UNRESOLVED_CITATIONS",
        "NON_PRIMARY_IN_TABLE",
        "INCLUDED_COUNT_MISMATCH",
        "HEADING_PARITY_MISMATCH",
        "MALFORMED_SECTION_HEADING",
        "PLACEHOLDER_FRAGMENT",
        "COUNT_DISCLOSURE_MISMATCH",
        "AI_LEAKAGE",
        "DUPLICATE_H2_SECTION",
        "REQUIRED_SECTION_MISSING",
        "SECTION_ORDER_INVALID",
        "PRISMA_STATEMENT_MISSING",
        "PROTOCOL_REGISTRATION_CONTRADICTION",
        "PROTOCOL_REGISTRATION_FUTURE_TENSE",
        "MODEL_ID_LEAKAGE",
        "META_FEASIBILITY_CONTRADICTION",
        "ABSTRACT_OVER_LIMIT",
        "ABSTRACT_STRUCTURE_MISSING_FIELDS",
        "UNUSED_BIB_ENTRY",
        "ARTIFACT_PLACEHOLDER_LEAK",
        "SECTION_CONTENT_INCOMPLETE",
        "IMPLICATIONS_MISPLACED",
        "ROB_FIGURE_CAPTION_MISMATCH",
        "FAILED_DB_DISCLOSURE_MISSING",
        "FAILED_DB_STATUS_MISCHARACTERIZED",
        "FIGURE_ASSET_MISSING",
        "FIGURE_NUMBERING_INVALID",
        "FIGURE_LATEX_MISMATCH",
        "SECTION_DETERMINISTIC_FALLBACK",
    }
)

# During phase_7_audit, missing optional finalize-time artifacts must not block
# the audit gate; they are availability observations until FinalizeNode runs.
PHASE_7_AVAILABILITY_ONLY_CODES: frozenset[str] = frozenset(
    {
        "FIGURE_ASSET_MISSING",
        "FIGURE_LATEX_MISMATCH",
        "HEADING_PARITY_MISMATCH",
        "UNUSED_BIB_ENTRY",
    }
)


def hard_failure(mode: str, code: str, contract_phase: str = "finalize") -> bool:
    """Return True when this violation should fail the contract gate in the given mode."""
    if mode == "observe":
        return False
    if mode == "soft":
        if contract_phase == "phase_7_audit" and code in PHASE_7_AVAILABILITY_ONLY_CODES:
            return False
        return code in SOFT_BLOCK_CODES
    # strict
    if contract_phase == "phase_7_audit" and code in PHASE_7_AVAILABILITY_ONLY_CODES:
        return False
    return True


def violation_category(code: str, contract_phase: str) -> str:
    """Label a violation as compliance vs availability for diagnostics."""
    if contract_phase == "phase_7_audit" and code in PHASE_7_AVAILABILITY_ONLY_CODES:
        return "artifact_availability"
    return "methodological_compliance"
