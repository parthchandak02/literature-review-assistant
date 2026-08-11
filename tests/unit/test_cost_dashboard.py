"""Unit tests for cost-dashboard helpers."""

from __future__ import annotations

import json

import pytest

from src.web.routers.costs import (
    _build_screening_diagnostics_from_metrics,
    _format_cost_group_rows,
    _format_cost_totals,
)


def test_format_cost_totals_from_aggregate_row() -> None:
    totals = _format_cost_totals(
        {
            "total_cost_usd": 1.25,
            "total_calls": 3,
            "total_tokens_in": 300,
            "total_tokens_out": 150,
        }
    )
    assert totals == {
        "calls": 3,
        "tokens_in": 300,
        "tokens_out": 150,
        "cost_usd": 1.25,
    }


def test_format_cost_totals_from_dashboard_row() -> None:
    totals = _format_cost_totals(
        {
            "cost_usd": 0.5,
            "calls": 2,
            "tokens_in": 80,
            "tokens_out": 40,
        }
    )
    assert totals == {
        "calls": 2,
        "tokens_in": 80,
        "tokens_out": 40,
        "cost_usd": 0.5,
    }


def test_format_cost_totals_empty() -> None:
    assert _format_cost_totals(None) == {
        "calls": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "cost_usd": 0.0,
    }


def test_format_cost_group_rows_renames_group_key() -> None:
    rows = _format_cost_group_rows(
        [
            {
                "group_key": "phase_3_screening",
                "calls": 4,
                "tokens_in": 120,
                "tokens_out": 60,
                "cost_usd": 0.04,
            }
        ],
        "phase",
    )
    assert rows == [
        {
            "phase": "phase_3_screening",
            "calls": 4,
            "tokens_in": 120,
            "tokens_out": 60,
            "cost_usd": 0.04,
        }
    ]


def test_format_cost_group_rows_preserves_existing_label() -> None:
    rows = _format_cost_group_rows(
        [
            {
                "model": "google:gemini-2.5-flash",
                "calls": 1,
                "tokens_in": 10,
                "tokens_out": 5,
                "cost_usd": 0.01,
            }
        ],
        "model",
    )
    assert rows[0]["model"] == "google:gemini-2.5-flash"


def test_build_screening_diagnostics_from_metrics() -> None:
    metric_rows = [
        {"rationale": json.dumps({"metric": "batch_parse_degraded", "value": 2})},
        {"rationale": json.dumps({"metric": "title_abstract_cross_reviewed", "value": 5})},
        {"rationale": "not-json"},
        {"rationale": json.dumps({"metric": 123, "value": 1})},
    ]
    diagnostics = _build_screening_diagnostics_from_metrics(metric_rows)
    assert diagnostics["batch_parse_degraded"] == 2
    assert diagnostics["cross_reviewed"] == 5
    assert diagnostics["batch_id_mismatch"] == 0
    assert diagnostics["fast_path_include"] == 0


@pytest.mark.parametrize(
    "label_key",
    ["phase", "model"],
)
def test_format_cost_group_rows_defaults_unknown(label_key: str) -> None:
    rows = _format_cost_group_rows([{"calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0}], label_key)
    assert rows[0][label_key] == "unknown"
