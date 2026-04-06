"""Reliability-focused tests: PRISMA disclosure grounding, gate policy, and phase matrix."""

from __future__ import annotations

from src.manuscript.contract_matrix import tex_optional_for_phase
from src.manuscript.prisma_disclosure import prisma_disclosure_gaps, should_use_db_prisma_flow_checks
from src.manuscript.violation_policy import (
    PHASE_7_AVAILABILITY_ONLY_CODES,
    hard_failure,
    violation_category,
)
from src.models.additional import PRISMACounts


def _minimal_prisma() -> PRISMACounts:
    return PRISMACounts(
        databases_records={"openalex": 100},
        other_sources_records={},
        total_identified_databases=100,
        total_identified_other=0,
        duplicates_removed=0,
        automation_excluded=0,
        records_screened=100,
        records_excluded_screening=0,
        reports_sought=103,
        reports_not_retrieved=63,
        reports_assessed=40,
        reports_excluded_with_reasons={},
        studies_included_qualitative=0,
        studies_included_quantitative=5,
        arithmetic_valid=True,
    )


def test_prisma_reports_sought_alternate_wording_passes_with_db_counts() -> None:
    """Regression: 'N reports sought, of which M could not be retrieved' must pass when counts match."""
    prisma = _minimal_prisma()
    assert should_use_db_prisma_flow_checks(prisma) is True
    md = """
## Methods
Independent reviewer screening was used.
Protocol registration: registered.
## Results
Of 103 reports sought for full-text review, 63 could not be retrieved and the remainder were assessed.
Risk of bias was assessed with RoB 2.
"""
    gaps = prisma_disclosure_gaps(md, prisma, use_db_flow_checks=True)
    assert "study_selection_reports_sought_sentence" not in gaps


def test_hard_failure_phase_7_does_not_block_on_figure_availability() -> None:
    for code in PHASE_7_AVAILABILITY_ONLY_CODES:
        assert hard_failure("strict", code, "phase_7_audit") is False
        assert hard_failure("soft", code, "phase_7_audit") is False


def test_hard_failure_finalize_still_blocks_figure_assets() -> None:
    assert hard_failure("strict", "FIGURE_ASSET_MISSING", "finalize") is True


def test_violation_category_availability_in_phase_7() -> None:
    assert violation_category("FIGURE_ASSET_MISSING", "phase_7_audit") == "artifact_availability"
    assert violation_category("FIGURE_ASSET_MISSING", "finalize") == "methodological_compliance"


def test_tex_optional_for_phase_7_audit() -> None:
    assert tex_optional_for_phase("phase_7_audit") is True
    assert tex_optional_for_phase("finalize") is False
