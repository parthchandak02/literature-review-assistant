from src.web.diagnostics_utils import summarize_phase_performance


def test_summarize_phase_performance_aggregates_totals_and_rankings() -> None:
    rows = [
        {
            "phase": "phase_3_screening",
            "duration_ms": 1000,
            "llm_calls": 10,
            "tokens_in": 100,
            "tokens_out": 50,
            "cost_usd": 0.01,
        },
        {
            "phase": "phase_6_writing",
            "duration_ms": 4000,
            "llm_calls": 4,
            "tokens_in": 500,
            "tokens_out": 300,
            "cost_usd": 0.09,
        },
        {
            "phase": "phase_4_extraction_quality",
            "duration_ms": 2000,
            "llm_calls": 3,
            "tokens_in": 70,
            "tokens_out": 30,
            "cost_usd": 0.02,
        },
    ]

    payload = summarize_phase_performance(rows)

    assert payload["totals"]["duration_ms"] == 7000
    assert payload["totals"]["llm_calls"] == 17
    assert payload["totals"]["tokens"] == 1050
    assert payload["totals"]["llm_cost_usd"] == 0.12
    assert payload["top_duration_phases"][0]["phase"] == "phase_6_writing"
    assert payload["top_cost_phases"][0]["phase"] == "phase_6_writing"
    assert payload["rows"] == rows
