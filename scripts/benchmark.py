#!/usr/bin/env python3
"""Validation benchmark: compare tool outputs against a gold-standard corpus.

Measures three quality dimensions:
  1. Screening recall -- fraction of gold-standard included studies also included by tool
  2. Extraction accuracy -- field-level hit rate vs gold-standard extracted data
  3. RoB agreement -- Cohen kappa between tool RoB judgments and published assessments

Usage:
    uv run python scripts/benchmark.py --run-dir <path> --gold <gold.json>
    uv run python scripts/benchmark.py --run-dir <path> --gold <gold.json> --out runs/benchmark_results.md

Gold-standard JSON format:
    {
      "review_title": "...",
      "included_dois": ["10.xxxx/...", ...],
      "extractions": [
        {"doi": "10.xxxx/...", "sample_size": 120,
         "intervention": "...", "outcome": "...",
         "effect_size": 0.45, "rob_overall": "low"}
      ]
    }
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console
from rich.table import Table
from rich import box

console = Console()


# ---------------------------------------------------------------------------
# Gold-standard schema
# ---------------------------------------------------------------------------

@dataclass
class GoldExtraction:
    doi: str
    sample_size: int | None = None
    intervention: str | None = None
    outcome: str | None = None
    effect_size: float | None = None
    rob_overall: str | None = None


@dataclass
class GoldStandard:
    review_title: str
    included_dois: list[str]
    extractions: list[GoldExtraction] = field(default_factory=list)


def load_gold(path: pathlib.Path) -> GoldStandard:
    raw = json.loads(path.read_text())
    extractions = [GoldExtraction(**e) for e in raw.get("extractions", [])]
    return GoldStandard(
        review_title=raw.get("review_title", path.stem),
        included_dois=[d.lower().strip() for d in raw.get("included_dois", [])],
        extractions=extractions,
    )


# ---------------------------------------------------------------------------
# DB loading
# ---------------------------------------------------------------------------

async def _load_run_data(db_path: pathlib.Path) -> dict[str, Any]:
    try:
        import aiosqlite
    except ImportError:
        console.print("[red]aiosqlite not installed -- run: uv add aiosqlite[/red]")
        sys.exit(1)

    result: dict[str, Any] = {
        "included_dois": set(),
        "extractions": {},
        "rob": {},
    }

    async with aiosqlite.connect(str(db_path)) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute(
            "SELECT doi FROM papers WHERE LOWER(final_decision) = 'include'"
        ) as cur:
            async for row in cur:
                doi = (row["doi"] or "").lower().strip()
                if doi:
                    result["included_dois"].add(doi)

        try:
            async with db.execute(
                "SELECT doi, sample_size, intervention, primary_outcome, "
                "effect_size, extraction_confidence FROM extraction_records"
            ) as cur:
                async for row in cur:
                    doi = (row["doi"] or "").lower().strip()
                    if doi:
                        result["extractions"][doi] = dict(row)
        except Exception:
            pass

        try:
            async with db.execute(
                "SELECT doi, overall_judgment FROM rob2_assessments"
            ) as cur:
                async for row in cur:
                    doi = (row["doi"] or "").lower().strip()
                    if doi:
                        result["rob"][doi] = (row["overall_judgment"] or "").lower()
        except Exception:
            pass

    return result


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _screening_recall(gold_dois: list[str], tool_dois: set[str]) -> dict[str, Any]:
    if not gold_dois:
        return {"recall": None, "tp": 0, "fn": 0, "gold_n": 0}
    tp = sum(1 for d in gold_dois if d in tool_dois)
    fn = len(gold_dois) - tp
    return {"recall": tp / len(gold_dois), "tp": tp, "fn": fn, "gold_n": len(gold_dois)}


def _normalize_rob(label: str) -> int:
    mapping = {"low": 0, "moderate": 1, "high": 2, "critical": 3, "serious": 2}
    return mapping.get(label.lower().strip(), -1)


def _cohens_kappa(ratings_a: list[int], ratings_b: list[int]) -> float | None:
    n = len(ratings_a)
    if n == 0:
        return None
    categories = sorted(set(ratings_a) | set(ratings_b))
    p_o = sum(a == b for a, b in zip(ratings_a, ratings_b)) / n
    p_e = sum(
        (ratings_a.count(c) / n) * (ratings_b.count(c) / n)
        for c in categories
    )
    if p_e >= 1.0:
        return 1.0
    return (p_o - p_e) / (1.0 - p_e)


def _extraction_accuracy(
    gold_extractions: list[GoldExtraction],
    tool_extractions: dict[str, dict],
) -> dict[str, Any]:
    numeric_fields = ["sample_size", "effect_size"]
    text_fields = ["intervention", "outcome"]
    hits: dict[str, list[bool]] = {f: [] for f in numeric_fields + text_fields}

    for ge in gold_extractions:
        tool = tool_extractions.get(ge.doi)
        for f in numeric_fields:
            gold_val = getattr(ge, f)
            if gold_val is None:
                continue
            if tool is None:
                hits[f].append(False)
                continue
            tool_val = tool.get(f)
            if tool_val is None:
                hits[f].append(False)
                continue
            try:
                pct_err = abs(float(tool_val) - float(gold_val)) / (abs(float(gold_val)) + 1e-9)
                hits[f].append(pct_err <= 0.20)
            except (TypeError, ValueError):
                hits[f].append(False)

        for f in text_fields:
            gold_val = getattr(ge, f) or ""
            if not gold_val.strip():
                continue
            if tool is None:
                hits[f].append(False)
                continue
            db_col = "intervention" if f == "intervention" else "primary_outcome"
            tool_val = tool.get(db_col) or ""
            hits[f].append(
                gold_val.lower().strip() in tool_val.lower()
                or tool_val.lower().strip() in gold_val.lower()
            )

    return {
        f: {"hit_rate": sum(bools) / len(bools) if bools else None, "n": len(bools)}
        for f, bools in hits.items()
    }


def _rob_agreement(
    gold_extractions: list[GoldExtraction],
    tool_rob: dict[str, str],
) -> dict[str, Any]:
    gold_ratings, tool_ratings = [], []
    for ge in gold_extractions:
        if ge.rob_overall is None:
            continue
        tool_label = tool_rob.get(ge.doi)
        if tool_label is None:
            continue
        g = _normalize_rob(ge.rob_overall)
        t = _normalize_rob(tool_label)
        if g < 0 or t < 0:
            continue
        gold_ratings.append(g)
        tool_ratings.append(t)
    return {"kappa": _cohens_kappa(gold_ratings, tool_ratings), "n_pairs": len(gold_ratings)}


# ---------------------------------------------------------------------------
# Report + display
# ---------------------------------------------------------------------------

def _render_report(
    gold: GoldStandard,
    screening: dict,
    extraction: dict,
    rob: dict,
    out_path: pathlib.Path | None,
) -> str:
    recall_str = f"{screening['recall']:.1%}" if screening["recall"] is not None else "N/A"
    lines = [
        "# Validation Benchmark Report",
        "",
        f"**Review:** {gold.review_title}",
        f"**Gold-standard included studies:** {len(gold.included_dois)}",
        "",
        "---",
        "",
        "## 1. Screening Recall",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Gold-standard N | {screening['gold_n']} |",
        f"| True positives (also included by tool) | {screening['tp']} |",
        f"| False negatives (missed by tool) | {screening['fn']} |",
        f"| **Recall** | **{recall_str}** |",
        "",
        "---",
        "",
        "## 2. Extraction Field Accuracy",
        "",
        "| Field | Hit Rate | N compared |",
        "|-------|----------|------------|",
    ]
    for fname, stats in extraction.items():
        hr = f"{stats['hit_rate']:.1%}" if stats["hit_rate"] is not None else "N/A"
        lines.append(f"| {fname} | {hr} | {stats['n']} |")

    kappa_str = f"{rob['kappa']:.3f}" if rob["kappa"] is not None else "N/A"
    if rob["kappa"] is not None:
        label = (
            "substantial" if rob["kappa"] >= 0.61
            else "moderate" if rob["kappa"] >= 0.41
            else "fair" if rob["kappa"] >= 0.21
            else "slight"
        )
        kappa_display = f"{kappa_str} ({label})"
    else:
        kappa_display = "N/A (insufficient pairs)"

    lines += [
        "",
        "---",
        "",
        "## 3. Risk of Bias Agreement (Cohen kappa)",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Pairs compared | {rob['n_pairs']} |",
        f"| **Cohen kappa** | **{kappa_display}** |",
        "",
        "---",
        "",
        "_Generated by scripts/benchmark.py_",
    ]
    report = "\n".join(lines)
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report)
        console.print(f"[green]Report written to:[/green] {out_path}")
    return report


def _print_rich_summary(screening: dict, extraction: dict, rob: dict) -> None:
    t = Table(title="Benchmark Summary", box=box.ROUNDED)
    t.add_column("Dimension", style="bold")
    t.add_column("Metric", style="cyan")
    t.add_column("Value", justify="right")

    recall_str = f"{screening['recall']:.1%}" if screening["recall"] is not None else "N/A"
    t.add_row("Screening", f"Recall (N={screening['gold_n']})", recall_str)

    for fname, stats in extraction.items():
        hr = f"{stats['hit_rate']:.1%}" if stats["hit_rate"] is not None else "N/A"
        t.add_row("Extraction", f"{fname} hit rate (N={stats['n']})", hr)

    kappa_str = f"{rob['kappa']:.3f}" if rob["kappa"] is not None else "N/A"
    t.add_row("RoB agreement", f"Cohen kappa (N={rob['n_pairs']} pairs)", kappa_str)

    console.print(t)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

async def _main(args: argparse.Namespace) -> None:
    run_dir = pathlib.Path(args.run_dir).expanduser().resolve()
    gold_path = pathlib.Path(args.gold).expanduser().resolve()
    out_path = pathlib.Path(args.out).expanduser().resolve() if args.out else None

    for p, label in [(run_dir, "Run directory"), (gold_path, "Gold-standard file")]:
        if not p.exists():
            console.print(f"[red]{label} not found:[/red] {p}")
            sys.exit(1)

    db_path = run_dir / "runtime.db"
    if not db_path.exists():
        console.print(f"[red]runtime.db not found in:[/red] {run_dir}")
        sys.exit(1)

    console.print(f"[bold]Loading gold standard:[/bold] {gold_path.name}")
    gold = load_gold(gold_path)
    console.print(f"  {len(gold.included_dois)} included DOIs, {len(gold.extractions)} extraction records")

    console.print(f"[bold]Loading run database:[/bold] {db_path}")
    run_data = await _load_run_data(db_path)
    console.print(
        f"  {len(run_data['included_dois'])} tool-included DOIs, "
        f"{len(run_data['extractions'])} extraction records, "
        f"{len(run_data['rob'])} RoB assessments"
    )

    screening = _screening_recall(gold.included_dois, run_data["included_dois"])
    extraction = _extraction_accuracy(gold.extractions, run_data["extractions"])
    rob = _rob_agreement(gold.extractions, run_data["rob"])

    _print_rich_summary(screening, extraction, rob)
    _render_report(gold, screening, extraction, rob, out_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare tool outputs against a gold-standard systematic review corpus.",
    )
    parser.add_argument("--run-dir", required=True,
                        help="Path to the run directory containing runtime.db")
    parser.add_argument("--gold", required=True,
                        help="Path to gold-standard JSON file")
    parser.add_argument("--out", default=None,
                        help="Output path for Markdown report")
    args = parser.parse_args()
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
