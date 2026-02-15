from src.restart.capability_contract import (
    CapabilityContract,
    validate_capability_contract,
)


def test_capability_contract_passes_for_valid_state():
    state = {
        "prisma_diagram_path": "out/prisma.png",
        "citation_validation_passed": True,
        "checkpoint_resume_enabled": True,
        "manuscript_sections": {
            "introduction": "intro",
            "methods": "methods",
            "results": "results",
            "discussion": "discussion",
            "abstract": "abstract",
        },
    }
    result = validate_capability_contract(state, CapabilityContract())
    assert result.is_valid is True
    assert result.missing_capabilities == ()


def test_capability_contract_reports_missing_fields():
    result = validate_capability_contract({})
    assert result.is_valid is False
    assert "prisma_diagram" in result.missing_capabilities
    assert "citation_validation" in result.missing_capabilities
