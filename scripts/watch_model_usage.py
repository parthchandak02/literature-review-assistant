#!/usr/bin/env python3
"""Summarize LLM model usage from a workflow runtime.db (cost_records)."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


def _classify_model(model: str) -> str:
    lowered = model.lower()
    if lowered.startswith("deepseek:") or "deepseek" in lowered:
        return "deepseek"
    if lowered.startswith("google:") or "gemini" in lowered or lowered.startswith("google-"):
        return "gemini"
    if lowered.startswith("sentence-transformers:"):
        return "local_embed"
    if lowered.startswith("openai:"):
        return "openai"
    if lowered.startswith("anthropic:"):
        return "anthropic"
    if lowered.startswith("openrouter:"):
        return "openrouter"
    return "other"


def summarize(db_path: Path) -> int:
    if not db_path.exists():
        print(f"Missing database: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT model, phase, COUNT(*) AS calls,
               SUM(tokens_in) AS tokens_in,
               SUM(tokens_out) AS tokens_out,
               ROUND(SUM(cost_usd), 6) AS cost_usd
        FROM cost_records
        GROUP BY model, phase
        ORDER BY cost_usd DESC
        """
    ).fetchall()
    conn.close()

    if not rows:
        print("No cost_records yet.")
        return 0

    by_provider: dict[str, dict[str, float | int]] = {}
    print(f"{'model':<42} {'phase':<28} {'calls':>6} {'cost_usd':>10}")
    print("-" * 92)
    for row in rows:
        model = row["model"] or ""
        provider = _classify_model(model)
        bucket = by_provider.setdefault(
            provider,
            {"calls": 0, "cost_usd": 0.0, "tokens_in": 0, "tokens_out": 0},
        )
        bucket["calls"] += int(row["calls"])
        bucket["cost_usd"] += float(row["cost_usd"] or 0)
        bucket["tokens_in"] += int(row["tokens_in"] or 0)
        bucket["tokens_out"] += int(row["tokens_out"] or 0)
        print(f"{model:<42} {row['phase']:<28} {row['calls']:>6} {float(row['cost_usd'] or 0):>10.4f}")

    print("\nBy provider family:")
    for provider, stats in sorted(by_provider.items(), key=lambda x: -x[1]["cost_usd"]):
        print(
            f"  {provider:<14} calls={stats['calls']:>4}  "
            f"cost=${stats['cost_usd']:.4f}  "
            f"tokens_in={stats['tokens_in']}  tokens_out={stats['tokens_out']}"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize model usage from runtime.db")
    parser.add_argument("db_path", type=Path, help="Path to runtime.db")
    args = parser.parse_args()
    return summarize(args.db_path)


if __name__ == "__main__":
    raise SystemExit(main())
