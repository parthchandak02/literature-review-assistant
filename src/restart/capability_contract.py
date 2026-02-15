"""Defines non-negotiable capabilities for the restart architecture."""

from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class CapabilityContract:
    """Required feature flags that must remain true after refactors."""

    requires_prisma: bool = True
    requires_citation_validation: bool = True
    requires_checkpoint_resume: bool = True
    requires_sectioned_writing: bool = True
    required_sections: tuple[str, ...] = (
        "introduction",
        "methods",
        "results",
        "discussion",
        "abstract",
    )


@dataclass(frozen=True)
class CapabilityContractValidation:
    """Validation result for a contract check."""

    is_valid: bool
    missing_capabilities: tuple[str, ...]


DEFAULT_CAPABILITY_CONTRACT = CapabilityContract()


def _has_sections(manuscript_sections: Mapping[str, str], expected: Iterable[str]) -> bool:
    for section in expected:
        content = manuscript_sections.get(section, "")
        if not isinstance(content, str) or not content.strip():
            return False
    return True


def validate_capability_contract(
    state: Mapping[str, object],
    contract: CapabilityContract = DEFAULT_CAPABILITY_CONTRACT,
) -> CapabilityContractValidation:
    """Checks state against required system capabilities."""

    missing: list[str] = []

    if contract.requires_prisma and not state.get("prisma_diagram_path"):
        missing.append("prisma_diagram")

    if contract.requires_citation_validation and not state.get("citation_validation_passed", False):
        missing.append("citation_validation")

    if contract.requires_checkpoint_resume and not state.get("checkpoint_resume_enabled", False):
        missing.append("checkpoint_resume")

    if contract.requires_sectioned_writing:
        sections = state.get("manuscript_sections", {})
        if not isinstance(sections, Mapping):
            missing.append("sectioned_writing")
        elif not _has_sections(sections, contract.required_sections):
            missing.append("required_sections")

    return CapabilityContractValidation(
        is_valid=not missing,
        missing_capabilities=tuple(missing),
    )
