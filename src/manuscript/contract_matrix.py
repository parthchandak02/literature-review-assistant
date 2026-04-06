"""Phase-aware contract expectations: artifacts, policies, and categories."""

from __future__ import annotations

from typing import Literal

ContractPhaseName = Literal["phase_7_audit", "finalize", "export"]

# Phases where TeX and Bib are optional for strict compliance (FinalizeNode writes them).
PHASES_TEX_OPTIONAL: frozenset[str] = frozenset({"phase_7_audit"})

# Artifacts that FinalizeNode or export normally materialize; phase_7 may reference paths early.
ARTIFACTS_FINALIZE_WRITTEN: tuple[str, ...] = (
    "manuscript_tex",
    "references_bib",
)


def tex_optional_for_phase(contract_phase: str) -> bool:
    return contract_phase in PHASES_TEX_OPTIONAL


def contract_phase_label(contract_phase: str) -> str:
    return contract_phase if contract_phase else "finalize"
