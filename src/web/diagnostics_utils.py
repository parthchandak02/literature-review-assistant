"""Shared diagnostics shaping helpers for web responses."""

from __future__ import annotations

from typing import Any


def summarize_phase_performance(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_duration_ms = sum(int(row.get("duration_ms") or 0) for row in rows)
    total_llm_cost_usd = sum(float(row.get("cost_usd") or 0.0) for row in rows)
    total_llm_calls = sum(int(row.get("llm_calls") or 0) for row in rows)
    total_tokens = sum(int(row.get("tokens_in") or 0) + int(row.get("tokens_out") or 0) for row in rows)
    top_duration = sorted(rows, key=lambda row: int(row.get("duration_ms") or 0), reverse=True)[:3]
    top_cost = sorted(rows, key=lambda row: float(row.get("cost_usd") or 0.0), reverse=True)[:3]
    return {
        "totals": {
            "duration_ms": total_duration_ms,
            "llm_cost_usd": round(total_llm_cost_usd, 6),
            "llm_calls": total_llm_calls,
            "tokens": total_tokens,
        },
        "top_duration_phases": top_duration,
        "top_cost_phases": top_cost,
        "rows": rows,
    }
