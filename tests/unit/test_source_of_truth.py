from __future__ import annotations

from src.db.source_of_truth import RUN_STATS_PRECEDENCE, TABLE_OWNERSHIP


def test_table_ownership_includes_fallback_events() -> None:
    assert TABLE_OWNERSHIP["fallback_events"] == "degraded_mode_execution_tracking"


def test_run_stats_precedence_prefers_canonical_included_count() -> None:
    assert RUN_STATS_PRECEDENCE.papers_included_order[0] == "study_cohort_membership_synthesis_included_primary"
    assert RUN_STATS_PRECEDENCE.total_cost_order == ("cost_records_sum",)
