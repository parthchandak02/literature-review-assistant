#!/usr/bin/env python3
"""Compare Jev against the LLM reviewer B and final decisions from a run's runtime.db.

Offline by default: reads jev_decisions, screening_decisions, dual_screening_results,
study_cohort_membership and cost_records (read-only, immutable). ``--live-sample N``
re-screens N papers through Jev and the configured LLM reviewer B; it refuses to run
without ``--confirm-live`` and never writes to the run database.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sqlite3
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from scripts.lib._paths import ensure_repo_on_path

ensure_repo_on_path()

INCLUDE_LIKE = {"include", "uncertain"}
THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.99)


@dataclass
class ScreeningRow:
    paper_id: str
    jev_choice: str | None
    jev_confidence: float | None
    llm_b: str | None
    final_ta: str | None
    included_final: bool
    jev_latency_ms: int | None = None
    jev_cost_usd: float | None = None
    llm_latency_ms: int | None = None
    llm_cost_usd: float | None = None
    jev_error: str | None = None


def _binary(decision: str | None) -> bool | None:
    if decision is None or decision == "":
        return None
    return decision.lower() in INCLUDE_LIKE


def cohen_kappa(pairs: list[tuple[bool, bool]]) -> float | None:
    n = len(pairs)
    if n == 0:
        return None
    po = sum(1 for a, b in pairs if a == b) / n
    pa = sum(1 for a, _ in pairs if a) / n
    pb = sum(1 for _, b in pairs if b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    if pe >= 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


def binary_metrics(pred: list[bool | None], truth: list[bool | None]) -> dict[str, Any]:
    """Include is the positive class. Pairs with a missing side are skipped."""
    pairs = [(p, t) for p, t in zip(pred, truth, strict=True) if p is not None and t is not None]
    tp = sum(1 for p, t in pairs if p and t)
    fp = sum(1 for p, t in pairs if p and not t)
    fn = sum(1 for p, t in pairs if not p and t)
    tn = sum(1 for p, t in pairs if not p and not t)
    n = len(pairs)
    return {
        "n": n,
        "agreement": round((tp + tn) / n, 4) if n else None,
        "recall_include": round(tp / (tp + fn), 4) if (tp + fn) else None,
        "precision_include": round(tp / (tp + fp), 4) if (tp + fp) else None,
        "kappa": _round(cohen_kappa(pairs)),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
    }


def _round(value: float | None, ndigits: int = 4) -> float | None:
    return None if value is None else round(value, ndigits)


def _latency_summary(values: list[int]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]
    return {
        "n": len(ordered),
        "mean_ms": round(statistics.fmean(ordered), 1),
        "p50_ms": statistics.median(ordered),
        "p95_ms": p95,
        "max_ms": ordered[-1],
    }


def threshold_sweep(
    rows: list[ScreeningRow], include_threshold: float | None = None, exclude_thresholds: tuple[float, ...] = THRESHOLDS
) -> list[dict[str, Any]]:
    """Coverage (share Jev would decide alone) and error vs final TA at each exclude threshold."""
    scored = [r for r in rows if r.jev_choice and r.jev_confidence is not None and r.final_ta]
    out: list[dict[str, Any]] = []
    for tau in exclude_thresholds:
        inc_tau = include_threshold if include_threshold is not None else tau
        routed = [
            r
            for r in scored
            if (r.jev_confidence or 0.0) >= (tau if r.jev_choice.lower() == "exclude" else inc_tau)
        ]
        wrong = [r for r in routed if _binary(r.jev_choice) != _binary(r.final_ta)]
        false_excl = [r for r in routed if r.jev_choice.lower() == "exclude" and _binary(r.final_ta)]
        out.append(
            {
                "exclude_threshold": tau,
                "coverage": round(len(routed) / len(scored), 4) if scored else None,
                "routed": len(routed),
                "error_rate": round(len(wrong) / len(routed), 4) if routed else None,
                "false_excludes": len(false_excl),
            }
        )
    return out


def compute_screening_metrics(
    rows: list[ScreeningRow], *, route_confidence: float = 0.6, exclude_confidence: float = 0.85
) -> dict[str, Any]:
    with_jev = [r for r in rows if r.jev_choice]
    jev_b = [_binary(r.jev_choice) for r in with_jev]
    three_class = [r for r in with_jev if r.llm_b]
    routed_live = [
        r
        for r in with_jev
        if (r.jev_confidence or 0.0)
        >= (exclude_confidence if (r.jev_choice or "").lower() == "exclude" else route_confidence)
    ]
    return {
        "n_rows": len(rows),
        "n_jev_answers": len(with_jev),
        "n_jev_errors": sum(1 for r in rows if r.jev_error),
        "jev_vs_llm_b": binary_metrics(jev_b, [_binary(r.llm_b) for r in with_jev]),
        "jev_vs_llm_b_3class_agreement": _round(
            sum(1 for r in three_class if r.jev_choice.lower() == r.llm_b.lower()) / len(three_class)
        )
        if three_class
        else None,
        "jev_vs_final_ta": binary_metrics(jev_b, [_binary(r.final_ta) for r in with_jev]),
        "llm_b_vs_final_ta": binary_metrics(
            [_binary(r.llm_b) for r in with_jev], [_binary(r.final_ta) for r in with_jev]
        ),
        "jev_vs_final_included": binary_metrics(jev_b, [r.included_final for r in with_jev]),
        "llm_b_vs_final_included": binary_metrics(
            [_binary(r.llm_b) for r in with_jev], [r.included_final for r in with_jev]
        ),
        "live_routing_at_current_thresholds": {
            "route_confidence": route_confidence,
            "exclude_confidence": exclude_confidence,
            "coverage": _round(len(routed_live) / len(with_jev)) if with_jev else None,
            "vs_final_ta": binary_metrics(
                [_binary(r.jev_choice) for r in routed_live], [_binary(r.final_ta) for r in routed_live]
            ),
        },
        "exclude_threshold_sweep": threshold_sweep(with_jev, include_threshold=route_confidence),
        "jev_latency": _latency_summary([r.jev_latency_ms for r in with_jev if r.jev_latency_ms is not None]),
        "llm_b_latency": _latency_summary([r.llm_latency_ms for r in rows if r.llm_latency_ms is not None]),
        "jev_cost_usd": round(sum(r.jev_cost_usd or 0.0 for r in rows), 6),
        "llm_b_cost_usd": round(sum(r.llm_cost_usd or 0.0 for r in rows), 6),
    }


def open_readonly(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path.resolve()}?immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _details(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _final_maps(conn: sqlite3.Connection) -> tuple[dict[str, str], set[str]]:
    final_ta: dict[str, str] = {}
    if _table_exists(conn, "dual_screening_results"):
        for row in conn.execute(
            "SELECT paper_id, final_decision FROM dual_screening_results WHERE stage = 'title_abstract'"
        ):
            final_ta[row["paper_id"]] = str(row["final_decision"]).lower()
    included: set[str] = set()
    if _table_exists(conn, "study_cohort_membership"):
        included = {
            row["paper_id"]
            for row in conn.execute(
                "SELECT paper_id FROM study_cohort_membership WHERE synthesis_eligibility = 'included_primary'"
            )
        }
    return final_ta, included


def _llm_reviewer_b(conn: sqlite3.Connection) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in conn.execute(
        """
        SELECT paper_id, decision FROM screening_decisions
        WHERE stage = 'title_abstract' AND reviewer_type = 'reviewer_b'
          AND COALESCE(reason, '') NOT LIKE 'Jev screening%'
        ORDER BY id
        """
    ):
        out[row["paper_id"]] = str(row["decision"]).lower()
    return out


def load_screening_rows(conn: sqlite3.Connection) -> list[ScreeningRow]:
    """Latest jev_decisions row per paper for reviewer B, joined with LLM B and final decisions."""
    if not _table_exists(conn, "jev_decisions"):
        return []
    final_ta, included = _final_maps(conn)
    llm_b = _llm_reviewer_b(conn)
    latest: dict[str, sqlite3.Row] = {}
    for row in conn.execute(
        "SELECT * FROM jev_decisions WHERE surface = 'screening_reviewer_b' AND paper_id IS NOT NULL ORDER BY id"
    ):
        latest[row["paper_id"]] = row
    rows: list[ScreeningRow] = []
    for paper_id, row in latest.items():
        details = _details(row["details_json"])
        errored = str(row["routed"]) in {"error", "shadow_error"}
        rows.append(
            ScreeningRow(
                paper_id=paper_id,
                jev_choice=None if errored else (str(row["choice"] or "").lower() or None),
                jev_confidence=None if errored else row["confidence"],
                llm_b=(details.get("llm_decision") or llm_b.get(paper_id)),
                final_ta=final_ta.get(paper_id),
                included_final=paper_id in included,
                jev_latency_ms=details.get("latency_ms"),
                jev_cost_usd=details.get("cost_usd"),
                jev_error=details.get("reason") if errored else None,
            )
        )
    return rows


def surface_summaries(conn: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists(conn, "jev_decisions"):
        return {}
    out: dict[str, Any] = {}
    for surface_row in conn.execute("SELECT DISTINCT surface FROM jev_decisions ORDER BY surface").fetchall():
        surface = surface_row["surface"]
        rows = conn.execute("SELECT * FROM jev_decisions WHERE surface = ? ORDER BY id", (surface,)).fetchall()
        details = [_details(r["details_json"]) for r in rows]
        routed: dict[str, int] = {}
        for r in rows:
            routed[str(r["routed"])] = routed.get(str(r["routed"]), 0) + 1
        summary: dict[str, Any] = {
            "rows": len(rows),
            "routed": routed,
            "modes": sorted({str(d.get("mode", "unknown")) for d in details}),
            "latency": _latency_summary([int(d["latency_ms"]) for d in details if d.get("latency_ms") is not None]),
            "cost_usd": round(sum(float(d.get("cost_usd") or 0.0) for d in details), 6),
        }
        if surface == "batch_pre_rank":
            vals = [float(d["forward_agreement"]) for d in details if d.get("forward_agreement") is not None]
            summary["mean_forward_agreement"] = _round(statistics.fmean(vals)) if vals else None
        if surface == "rag_rerank":
            vals = [float(d["overlap_at_k"]) for d in details if d.get("overlap_at_k") is not None]
            summary["mean_overlap_at_k"] = _round(statistics.fmean(vals)) if vals else None
        if surface == "study_design_classifier":
            pairs = [(d.get("mapped"), d.get("llm_decision")) for d in details if d.get("llm_decision")]
            summary["agreement_with_llm"] = (
                _round(sum(1 for a, b in pairs if a == b) / len(pairs)) if pairs else None
            )
        out[surface] = summary
    return out


def cost_phase_summary(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _table_exists(conn, "cost_records"):
        return []
    rows = conn.execute(
        """
        SELECT phase, model, COUNT(*) AS calls, SUM(cost_usd) AS cost_usd, AVG(latency_ms) AS avg_latency_ms
        FROM cost_records
        WHERE phase LIKE '%jev%' OR phase IN ('phase_3_screening', 'screening_batch_ranker',
                                               'phase_4_extraction_quality', 'phase_6_rerank')
        GROUP BY phase, model ORDER BY phase
        """
    ).fetchall()
    return [
        {
            "phase": r["phase"],
            "model": r["model"],
            "calls": r["calls"],
            "cost_usd": round(float(r["cost_usd"] or 0.0), 6),
            "avg_latency_ms": round(float(r["avg_latency_ms"] or 0.0), 1),
        }
        for r in rows
    ]


def evaluate_db(db_path: Path, *, route_confidence: float = 0.6, exclude_confidence: float = 0.85) -> dict[str, Any]:
    conn = open_readonly(db_path)
    try:
        rows = load_screening_rows(conn)
        return {
            "db": str(db_path),
            "source": "jev_decisions",
            "screening": compute_screening_metrics(
                rows, route_confidence=route_confidence, exclude_confidence=exclude_confidence
            ),
            "surfaces": surface_summaries(conn),
            "cost_records": cost_phase_summary(conn),
        }
    finally:
        conn.close()


def select_live_sample(conn: sqlite3.Connection, n: int, seed: int = 13) -> list[str]:
    """Papers that reached LLM reviewer B at title/abstract; all final includes first, then random excludes."""
    final_ta, _ = _final_maps(conn)
    candidates = sorted(
        pid
        for pid in _llm_reviewer_b(conn)
        if pid in final_ta
    )
    with_abstract = {
        r["paper_id"]
        for r in conn.execute("SELECT paper_id FROM papers WHERE COALESCE(abstract, '') <> ''")
    }
    candidates = [pid for pid in candidates if pid in with_abstract]
    includes = [pid for pid in candidates if final_ta[pid] in INCLUDE_LIKE]
    others = [pid for pid in candidates if final_ta[pid] not in INCLUDE_LIKE]
    rng = random.Random(seed)
    rng.shuffle(includes)
    rng.shuffle(others)
    picked = includes[: max(1, n // 2)] if includes else []
    picked += others[: n - len(picked)]
    if len(picked) < n:
        picked += [pid for pid in includes if pid not in picked][: n - len(picked)]
    return picked[:n]


def _load_papers(conn: sqlite3.Connection, paper_ids: list[str]) -> list[Any]:
    from src.models import CandidatePaper

    out = []
    for pid in paper_ids:
        r = conn.execute("SELECT * FROM papers WHERE paper_id = ?", (pid,)).fetchone()
        if r is None:
            continue
        try:
            authors = json.loads(r["authors"]) if r["authors"] else []
        except json.JSONDecodeError:
            authors = [str(r["authors"])]
        out.append(
            CandidatePaper(
                paper_id=r["paper_id"],
                title=r["title"],
                authors=authors if isinstance(authors, list) else [str(authors)],
                year=r["year"],
                source_database=r["source_database"],
                doi=r["doi"],
                abstract=r["abstract"],
            )
        )
    return out


async def run_live_sample(
    db_path: Path, n: int, *, review_path: Path, settings_path: Path, concurrency: int
) -> dict[str, Any]:
    """Makes ~2N external calls: N Jev + N LLM reviewer B. Writes nothing to the run DB."""
    from src.config.loader import load_configs
    from src.llm.provider import LLMProvider
    from src.screening.gemini_client import PydanticAIScreeningClient
    from src.screening.jev_screening import call_jev_screening
    from src.screening.prompts import reviewer_b_prompt

    review, settings = load_configs(review_path=str(review_path), settings_path=str(settings_path))
    jev = settings.jev
    agent = settings.agents["screening_reviewer_b"]
    client = PydanticAIScreeningClient()
    conn = open_readonly(db_path)
    try:
        final_ta, included = _final_maps(conn)
        papers = _load_papers(conn, select_live_sample(conn, n))
    finally:
        conn.close()
    llm_slots = asyncio.Semaphore(max(1, concurrency))
    jev_slots = asyncio.Semaphore(max(1, concurrency))

    async def _llm(paper: Any) -> tuple[str | None, int, float]:
        started = time.perf_counter()
        try:
            async with llm_slots:
                parsed, tok_in, tok_out, cw, cr = await client.complete_screening_response_with_usage(
                    reviewer_b_prompt(review, paper, "title_abstract", None),
                    agent_name="screening_reviewer_b",
                    model=agent.model,
                    temperature=agent.temperature,
                )
            cost = LLMProvider.estimate_cost_usd(agent.model, tok_in, tok_out, cache_write=cw, cache_read=cr)
            return parsed.decision.value, int((time.perf_counter() - started) * 1000), cost
        except Exception as exc:
            print(f"LLM reviewer B failed for {paper.paper_id}: {exc}", file=sys.stderr)
            return None, int((time.perf_counter() - started) * 1000), 0.0

    async def _jev(paper: Any) -> Any:
        async with jev_slots:
            return await call_jev_screening(review=review, paper=paper, jev=jev)

    async def _one(paper: Any) -> ScreeningRow:
        call, (llm_decision, llm_ms, llm_cost) = await asyncio.gather(_jev(paper), _llm(paper))
        tok_in = int(call.result.usage.get("input_tokens", 0)) if call.result else 0
        tok_out = int(call.result.usage.get("output_tokens", 0)) if call.result else 0
        return ScreeningRow(
            paper_id=paper.paper_id,
            jev_choice=(call.choice.lower() or None) if call.error is None else None,
            jev_confidence=call.confidence if call.error is None else None,
            llm_b=llm_decision,
            final_ta=final_ta.get(paper.paper_id),
            included_final=paper.paper_id in included,
            jev_latency_ms=call.result.latency_ms if call.result else None,
            jev_cost_usd=jev.cost_usd(tok_in, tok_out) if call.result else None,
            llm_latency_ms=llm_ms,
            llm_cost_usd=llm_cost,
            jev_error=call.error,
        )

    rows = list(await asyncio.gather(*(_one(p) for p in papers)))
    return {
        "db": str(db_path),
        "source": "live_sample",
        "sample_size": len(rows),
        "jev_model": jev.model,
        "llm_b_model": agent.model,
        "jev_price_configured": bool(jev.price_per_call_usd or jev.price_input_per_mtok or jev.price_output_per_mtok),
        "screening": compute_screening_metrics(
            rows, route_confidence=jev.route_confidence, exclude_confidence=jev.exclude_confidence
        ),
        "rows": [asdict(r) for r in rows],
    }


def _format_text(report: dict[str, Any]) -> str:
    s = report["screening"]
    lines = [f"Jev eval ({report['source']}): {report['db']}"]
    if not s["n_rows"] and report["source"] == "jev_decisions":
        lines.append("  no jev_decisions screening rows in this DB (pre-shadow run?); use --live-sample N --confirm-live")
    lines.append(f"  screening rows={s['n_rows']} jev_answers={s['n_jev_answers']} jev_errors={s['n_jev_errors']}")
    for key in ("jev_vs_llm_b", "jev_vs_final_ta", "llm_b_vs_final_ta", "jev_vs_final_included", "llm_b_vs_final_included"):
        m = s[key]
        lines.append(
            f"  {key:<24} n={m['n']:<4} agree={m['agreement']} recall_inc={m['recall_include']} "
            f"prec_inc={m['precision_include']} kappa={m['kappa']}"
        )
    live = s["live_routing_at_current_thresholds"]
    lines.append(
        f"  live routing @ route={live['route_confidence']} exclude={live['exclude_confidence']}: "
        f"coverage={live['coverage']} recall_inc={live['vs_final_ta']['recall_include']} "
        f"agree={live['vs_final_ta']['agreement']}"
    )
    lines.append("  exclude-threshold sweep (coverage / error / false excludes):")
    for t in s["exclude_threshold_sweep"]:
        lines.append(
            f"    tau={t['exclude_threshold']:<5} coverage={t['coverage']} error={t['error_rate']} "
            f"false_excludes={t['false_excludes']}"
        )
    lines.append(f"  jev latency {s['jev_latency']}  cost=${s['jev_cost_usd']}")
    if s["llm_b_latency"].get("n"):
        lines.append(f"  llm_b latency {s['llm_b_latency']}  cost=${s['llm_b_cost_usd']}")
    for surface, summary in report.get("surfaces", {}).items():
        lines.append(f"  surface {surface}: {json.dumps(summary, sort_keys=True)}")
    for c in report.get("cost_records", []):
        lines.append(
            f"  cost {c['phase']:<36} {c['model'][-28:]:<28} calls={c['calls']:<4} "
            f"usd={c['cost_usd']} avg_ms={c['avg_latency_ms']}"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="check.py jev-eval", description=__doc__.splitlines()[0])
    parser.add_argument("--db", required=True, help="Path to a completed run's runtime.db")
    parser.add_argument("--json", action="store_true", help="Print the full JSON report")
    parser.add_argument("--live-sample", type=int, default=0, help="Re-screen N papers via Jev + LLM reviewer B")
    parser.add_argument("--confirm-live", action="store_true", help="Required to make external API calls")
    parser.add_argument("--review", default="", help="Review YAML for live sample (default: config_snapshot.yaml next to --db)")
    parser.add_argument("--settings", default="config/settings.yaml", help="Settings YAML for live sample")
    parser.add_argument("--concurrency", type=int, default=4, help="Max in-flight calls per provider in live sample")
    parser.add_argument("--out", default="", help="Also write the JSON report to this path")
    parser.add_argument("--route-confidence", type=float, default=0.6, help="Offline: include/uncertain threshold")
    parser.add_argument("--exclude-confidence", type=float, default=0.85, help="Offline: exclude threshold")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Missing database: {db_path}", file=sys.stderr)
        return 1
    if args.live_sample > 0:
        if not args.confirm_live:
            print(
                f"Refusing live sample: would make about {2 * args.live_sample} external calls "
                f"({args.live_sample} Jev + {args.live_sample} LLM reviewer B). Re-run with --confirm-live.",
                file=sys.stderr,
            )
            return 2
        review_path = Path(args.review) if args.review else db_path.parent / "config_snapshot.yaml"
        report = asyncio.run(
            run_live_sample(
                db_path,
                args.live_sample,
                review_path=review_path,
                settings_path=Path(args.settings),
                concurrency=args.concurrency,
            )
        )
    else:
        report = evaluate_db(
            db_path, route_confidence=args.route_confidence, exclude_confidence=args.exclude_confidence
        )
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, default=str) if args.json else _format_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
