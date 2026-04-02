"""Canonical runtime.db ownership and stat precedence rules.

This module centralizes which table is authoritative for product-facing metrics.
Keeping this in code (not docs) prevents drift across API handlers.
"""

from __future__ import annotations

from dataclasses import dataclass

TABLE_OWNERSHIP: dict[str, str] = {
    "event_log": "activity_feed",
    "cost_records": "llm_cost_accounting",
    "dual_screening_results": "screening_outcomes",
    "screening_decisions": "screening_rationales_and_reasons",
    "search_results": "search_identification_counts",
    "extraction_records": "structured_extracted_evidence",
    "study_cohort_membership": "canonical_study_cohort_membership",
    "section_drafts": "manuscript_section_state",
    "manuscript_sections": "manuscript_section_state_canonical",
    "manuscript_blocks": "manuscript_block_state_canonical",
    "manuscript_assets": "manuscript_asset_state_canonical",
    "manuscript_assemblies": "manuscript_render_state_canonical",
    "checkpoints": "phase_resume_markers",
    "gate_results": "quality_gate_evaluations",
    "manuscript_audit_runs": "phase_7_audit_summary",
    "manuscript_audit_findings": "phase_7_audit_findings",
}


@dataclass(frozen=True)
class RunStatsPrecedence:
    """Precedence for run-level sidebar/history summary numbers."""

    # Source of included studies count:
    # 1) study_cohort_membership synthesis included_primary (canonical cohort)
    # 2) dual_screening_results fulltext include/uncertain (durable factual table)
    # 3) phase_3_screening phase_done summary.included (historical fallback)
    # 4) extraction_records count (legacy fallback)
    papers_included_order: tuple[str, ...] = (
        "study_cohort_membership_synthesis_included_primary",
        "dual_screening_results_fulltext",
        "event_log_phase_done_phase_3_screening",
        "extraction_records",
    )
    # Source of total cost:
    # 1) cost_records SUM(cost_usd)
    total_cost_order: tuple[str, ...] = ("cost_records_sum",)
    # Source of manuscript content for product read-paths:
    # 1) manuscript_assemblies latest per format
    # 2) file artifact fallback (doc_manuscript.md/.tex)
    manuscript_content_order: tuple[str, ...] = (
        "manuscript_assemblies_latest",
        "artifact_file_fallback",
    )
    # Source of PRISMA screening counts:
    # 1) repositories.get_prisma_screening_counts() using cohort fulltext_status
    #    as canonical when available
    # 2) legacy dual_screening_results + screening_decisions fallback
    prisma_screening_counts_order: tuple[str, ...] = (
        "repositories_get_prisma_screening_counts_canonical",
        "legacy_dual_and_screening_decisions_fallback",
    )


RUN_STATS_PRECEDENCE = RunStatsPrecedence()
