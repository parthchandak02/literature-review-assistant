#!/usr/bin/env python3
"""One-time workflow funnel balance audit with guardrails.

Usage:
  uv run python scripts/check_workflow_balance.py --workflow-id wf-0021
  uv run python scripts/check_workflow_balance.py --workflow-id wf-0021 --compare-workflow-id wf-0022
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

console = Console()


@dataclass
class Guardrails:
    ranked_over_deduped_min: float = 0.10
    ranked_over_deduped_max: float = 0.50
    screened_over_ranked_min: float = 0.70
    screened_over_ranked_max: float = 1.00
    included_over_screened_min: float = 0.10
    included_over_screened_max: float = 0.70


@dataclass
class BalanceMetrics:
    workflow_id: str
    db_path: str
    total_records: int
    deduped: int
    to_llm_ranked: int
    to_dual_review_screened: int
    final_include: int
    final_exclude: int
    final_uncertain: int
    final_total: int
    ranked_over_deduped: float | None
    screened_over_ranked: float | None
    included_over_screened: float | None


def _ratio(num: int, den: int) -> float | None:
    if den <= 0:
        return None
    return num / den


def _resolve_db_path(run_root: Path, workflow_id: str) -> Path:
    registry = run_root / "workflows_registry.db"
    if not registry.exists():
        raise RuntimeError(f"Registry database not found: {registry}")
    with sqlite3.connect(str(registry)) as conn:
        row = conn.execute(
            "SELECT db_path FROM workflows_registry WHERE workflow_id = ?",
            (workflow_id,),
        ).fetchone()
    if not row or not row[0]:
        raise RuntimeError(f"Workflow not found in registry: {workflow_id}")
    return Path(str(row[0]))


def _phase_event_payload(conn: sqlite3.Connection, event_type: str, key: str, value: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT payload
        FROM event_log
        WHERE event_type = ?
          AND payload LIKE ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (event_type, f'%"{key}": "{value}"%'),
    ).fetchone()
    if not row:
        return {}
    try:
        return json.loads(str(row[0]))
    except Exception:
        return {}


def _single_event_payload(conn: sqlite3.Connection, event_type: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT payload FROM event_log WHERE event_type = ? ORDER BY id DESC LIMIT 1",
        (event_type,),
    ).fetchone()
    if not row:
        return {}
    try:
        return json.loads(str(row[0]))
    except Exception:
        return {}


def _max_progress_total(conn: sqlite3.Connection, phase: str) -> int:
    rows = conn.execute(
        "SELECT payload FROM event_log WHERE event_type = 'progress' AND payload LIKE ?",
        (f'%\"phase\": \"{phase}\"%',),
    ).fetchall()
    max_total = 0
    for row in rows:
        try:
            payload = json.loads(str(row[0]))
        except Exception:
            continue
        total = int(payload.get("total", 0) or 0)
        if total > max_total:
            max_total = total
    return max_total


def _load_metrics(workflow_id: str, db_path: Path) -> BalanceMetrics:
    if not db_path.exists():
        raise RuntimeError(f"runtime.db not found: {db_path}")
    with sqlite3.connect(str(db_path)) as conn:
        phase2 = _phase_event_payload(conn, "phase_done", "phase", "phase_2_search")
        prefilter = _single_event_payload(conn, "screening_prefilter_done")
        batch = _single_event_payload(conn, "batch_screen_done")

        phase3_total = _max_progress_total(conn, "phase_3_screening")

        final_rows = conn.execute(
            """
            WITH finals AS (
              SELECT id, paper_id, decision
              FROM decision_log
              WHERE decision_type IN ('dual_screening_final', 'screening_adjudication', 'screening_protocol_heuristic')
                AND paper_id IS NOT NULL
            ),
            latest AS (
              SELECT f.paper_id, f.decision
              FROM finals f
              JOIN (
                SELECT paper_id, MAX(id) AS max_id
                FROM finals
                GROUP BY paper_id
              ) m ON f.paper_id = m.paper_id AND f.id = m.max_id
            )
            SELECT decision, COUNT(*) FROM latest GROUP BY decision
            """
        ).fetchall()

    summary = phase2.get("summary", {}) if isinstance(phase2, dict) else {}
    total_records = int(summary.get("total_records", 0) or 0)
    deduped = int(summary.get("papers", 0) or 0)
    to_llm = int(prefilter.get("to_llm", 0) or 0)
    if to_llm <= 0 and phase3_total > 0:
        to_llm = phase3_total
    to_dual = int(batch.get("forwarded", 0) or 0)
    if to_dual <= 0 and phase3_total > 0:
        to_dual = phase3_total

    include = 0
    exclude = 0
    uncertain = 0
    for decision, count in final_rows:
        if decision == "include":
            include = int(count)
        elif decision == "exclude":
            exclude = int(count)
        elif decision == "uncertain":
            uncertain = int(count)

    final_total = include + exclude + uncertain

    return BalanceMetrics(
        workflow_id=workflow_id,
        db_path=str(db_path),
        total_records=total_records,
        deduped=deduped,
        to_llm_ranked=to_llm,
        to_dual_review_screened=to_dual,
        final_include=include,
        final_exclude=exclude,
        final_uncertain=uncertain,
        final_total=final_total,
        ranked_over_deduped=_ratio(to_llm, deduped),
        screened_over_ranked=_ratio(to_dual, to_llm),
        included_over_screened=_ratio(include, to_dual),
    )


def _check_guardrails(metrics: BalanceMetrics, guardrails: Guardrails) -> list[tuple[str, str, str]]:
    checks: list[tuple[str, str, str]] = []

    def _status(value: float | None, low: float, high: float) -> str:
        if value is None:
            return "NO_DATA"
        if low <= value <= high:
            return "PASS"
        return "FAIL"

    checks.append(
        (
            "ranked_over_deduped",
            _status(
                metrics.ranked_over_deduped,
                guardrails.ranked_over_deduped_min,
                guardrails.ranked_over_deduped_max,
            ),
            f"[{guardrails.ranked_over_deduped_min:.2f}, {guardrails.ranked_over_deduped_max:.2f}]",
        )
    )
    checks.append(
        (
            "screened_over_ranked",
            _status(
                metrics.screened_over_ranked,
                guardrails.screened_over_ranked_min,
                guardrails.screened_over_ranked_max,
            ),
            f"[{guardrails.screened_over_ranked_min:.2f}, {guardrails.screened_over_ranked_max:.2f}]",
        )
    )
    checks.append(
        (
            "included_over_screened",
            _status(
                metrics.included_over_screened,
                guardrails.included_over_screened_min,
                guardrails.included_over_screened_max,
            ),
            f"[{guardrails.included_over_screened_min:.2f}, {guardrails.included_over_screened_max:.2f}]",
        )
    )
    return checks


def _fmt_ratio(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value:.3f}"


def _print_metrics(metrics: BalanceMetrics, guardrails: Guardrails) -> None:
    table = Table(title=f"Workflow Balance Audit: {metrics.workflow_id}")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("db_path", metrics.db_path)
    table.add_row("total_records", str(metrics.total_records))
    table.add_row("deduped", str(metrics.deduped))
    table.add_row("ranked (to_llm)", str(metrics.to_llm_ranked))
    table.add_row("screened (to_dual_review)", str(metrics.to_dual_review_screened))
    table.add_row("final_include", str(metrics.final_include))
    table.add_row("final_exclude", str(metrics.final_exclude))
    table.add_row("final_uncertain", str(metrics.final_uncertain))
    table.add_row("ranked_over_deduped", _fmt_ratio(metrics.ranked_over_deduped))
    table.add_row("screened_over_ranked", _fmt_ratio(metrics.screened_over_ranked))
    table.add_row("included_over_screened", _fmt_ratio(metrics.included_over_screened))
    console.print(table)

    checks = _check_guardrails(metrics, guardrails)
    check_table = Table(title="Guardrail Checks")
    check_table.add_column("Ratio")
    check_table.add_column("Status")
    check_table.add_column("Expected Range")
    for ratio_name, status, expected in checks:
        check_table.add_row(ratio_name, status, expected)
    console.print(check_table)


def _print_comparison(left: BalanceMetrics, right: BalanceMetrics) -> None:
    table = Table(title=f"Workflow Comparison: {left.workflow_id} vs {right.workflow_id}")
    table.add_column("Metric")
    table.add_column(left.workflow_id, justify="right")
    table.add_column(right.workflow_id, justify="right")
    table.add_row("deduped", str(left.deduped), str(right.deduped))
    table.add_row("ranked", str(left.to_llm_ranked), str(right.to_llm_ranked))
    table.add_row("screened", str(left.to_dual_review_screened), str(right.to_dual_review_screened))
    table.add_row("final_include", str(left.final_include), str(right.final_include))
    table.add_row("ranked_over_deduped", _fmt_ratio(left.ranked_over_deduped), _fmt_ratio(right.ranked_over_deduped))
    table.add_row("screened_over_ranked", _fmt_ratio(left.screened_over_ranked), _fmt_ratio(right.screened_over_ranked))
    table.add_row("included_over_screened", _fmt_ratio(left.included_over_screened), _fmt_ratio(right.included_over_screened))
    console.print(table)


def _write_json_report(
    output_path: Path,
    primary: BalanceMetrics,
    guardrails: Guardrails,
    secondary: BalanceMetrics | None,
) -> None:
    payload: dict[str, Any] = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "primary": asdict(primary),
        "guardrails": asdict(guardrails),
        "primary_checks": _check_guardrails(primary, guardrails),
    }
    if secondary is not None:
        payload["secondary"] = asdict(secondary)
        payload["secondary_checks"] = _check_guardrails(secondary, guardrails)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit workflow funnel balance and compare against guardrails.")
    parser.add_argument("--workflow-id", required=True, help="Workflow id, for example wf-0021")
    parser.add_argument("--compare-workflow-id", default=None, help="Optional second workflow id for side-by-side")
    parser.add_argument("--run-root", default="runs", help="Run root containing workflows_registry.db")
    parser.add_argument("--output-json", default=None, help="Optional path for JSON report")
    args = parser.parse_args()

    run_root = Path(args.run_root)
    guardrails = Guardrails()

    left_db = _resolve_db_path(run_root, args.workflow_id)
    left_metrics = _load_metrics(args.workflow_id, left_db)
    _print_metrics(left_metrics, guardrails)

    right_metrics: BalanceMetrics | None = None
    if args.compare_workflow_id:
        right_db = _resolve_db_path(run_root, args.compare_workflow_id)
        right_metrics = _load_metrics(args.compare_workflow_id, right_db)
        _print_metrics(right_metrics, guardrails)
        _print_comparison(left_metrics, right_metrics)

    if args.output_json:
        out_path = Path(args.output_json)
    else:
        stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        out_path = run_root / f"balance_audit_{args.workflow_id}_{stamp}.json"
    _write_json_report(out_path, left_metrics, guardrails, right_metrics)
    console.print(f"JSON report: {out_path}")


if __name__ == "__main__":
    main()
