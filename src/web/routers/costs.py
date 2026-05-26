"""Cost analytics and export endpoints."""

from __future__ import annotations

import asyncio
import csv
import io
import pathlib
from typing import Any

import aiosqlite
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from src.db.workflow_registry import _open_registry as _open_registry_db
from src.web.shared import _parse_sqlite_ts
from src.web.state import _get_db_path

router = APIRouter(tags=["costs"])


# ---------------------------------------------------------------------------
# Helpers local to this router
# ---------------------------------------------------------------------------


def _build_cost_time_filter(start_ts: str | None, end_ts: str | None) -> tuple[str, list[str]]:
    clauses: list[str] = []
    params: list[str] = []
    if start_ts:
        clauses.append("datetime(created_at) >= datetime(?)")
        params.append(start_ts.strip())
    if end_ts:
        clauses.append("datetime(created_at) <= datetime(?)")
        params.append(end_ts.strip())
    if not clauses:
        return "", params
    return "WHERE " + " AND ".join(clauses), params


def _bucket_created_at(value: Any, granularity: str) -> str:
    ts = _parse_sqlite_ts(value)
    if ts is None:
        return "unknown"
    if granularity == "day":
        return ts.strftime("%Y-%m-%d")
    if granularity == "week":
        return f"{ts.strftime('%Y')}-W{ts.strftime('%W')}"
    if granularity == "month":
        return ts.strftime("%Y-%m")
    raise ValueError(f"unsupported granularity: {granularity}")


def _merge_cost_group_row(
    groups: dict[str, dict[str, Any]],
    key: str,
    *,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    calls: int = 1,
) -> None:
    current = groups.setdefault(
        key,
        {"calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0},
    )
    current["calls"] += calls
    current["tokens_in"] += tokens_in
    current["tokens_out"] += tokens_out
    current["cost_usd"] += cost_usd


async def _fetch_registry_cost_rows(
    run_root: str,
    *,
    start_ts: str | None,
    end_ts: str | None,
    include_archived: bool,
) -> list[dict[str, Any]]:
    registry = pathlib.Path(run_root) / "workflows_registry.db"
    if not registry.exists():
        return []

    async with _open_registry_db(str(registry)) as reg_db:
        reg_db.row_factory = aiosqlite.Row
        where_archived = "" if include_archived else "WHERE COALESCE(is_archived, 0) = 0"
        async with reg_db.execute(
            f"""
            SELECT workflow_id, topic, db_path
            FROM workflows_registry
            {where_archived}
            ORDER BY created_at DESC
            """
        ) as cur:
            registry_rows = await cur.fetchall()

    where_sql, where_params = _build_cost_time_filter(start_ts, end_ts)

    async def _fetch_for_db(entry: aiosqlite.Row) -> list[dict[str, Any]]:
        db_path = str(entry["db_path"] or "")
        if not db_path or not pathlib.Path(db_path).exists():
            return []
        workflow_id = str(entry["workflow_id"] or "")
        topic = str(entry["topic"] or "")
        try:
            async with aiosqlite.connect(db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    f"""
                    SELECT
                        COALESCE(NULLIF(workflow_id, ''), ?) AS workflow_id,
                        COALESCE(NULLIF(model, ''), 'unknown') AS model,
                        COALESCE(NULLIF(phase, ''), 'unknown') AS phase,
                        COALESCE(created_at, '') AS created_at,
                        COALESCE(tokens_in, 0) AS tokens_in,
                        COALESCE(tokens_out, 0) AS tokens_out,
                        COALESCE(cost_usd, 0.0) AS cost_usd
                    FROM cost_records
                    {where_sql}
                    """,
                    [workflow_id, *where_params],
                ) as cur:
                    rows = await cur.fetchall()
            return [
                {
                    "workflow_id": str(row["workflow_id"] or workflow_id or "unknown"),
                    "topic": topic,
                    "model": str(row["model"] or "unknown"),
                    "phase": str(row["phase"] or "unknown"),
                    "created_at": str(row["created_at"] or ""),
                    "tokens_in": int(row["tokens_in"] or 0),
                    "tokens_out": int(row["tokens_out"] or 0),
                    "cost_usd": float(row["cost_usd"] or 0.0),
                }
                for row in rows
            ]
        except Exception:
            return []

    per_db_rows = await asyncio.gather(*[_fetch_for_db(entry) for entry in registry_rows], return_exceptions=True)
    flattened: list[dict[str, Any]] = []
    for item in per_db_rows:
        if isinstance(item, list):
            flattened.extend(item)
    return flattened


def _build_global_cost_aggregates_payload(
    rows: list[dict[str, Any]],
    *,
    start_ts: str | None,
    end_ts: str | None,
) -> dict[str, Any]:
    totals = {"total_cost_usd": 0.0, "total_calls": 0, "total_tokens_in": 0, "total_tokens_out": 0}
    by_day: dict[str, dict[str, Any]] = {}
    by_week: dict[str, dict[str, Any]] = {}
    by_month: dict[str, dict[str, Any]] = {}
    by_workflow: dict[str, dict[str, Any]] = {}
    by_phase: dict[str, dict[str, Any]] = {}
    by_model: dict[str, dict[str, Any]] = {}

    for row in rows:
        tokens_in = int(row["tokens_in"])
        tokens_out = int(row["tokens_out"])
        cost_usd = float(row["cost_usd"])
        totals["total_cost_usd"] += cost_usd
        totals["total_calls"] += 1
        totals["total_tokens_in"] += tokens_in
        totals["total_tokens_out"] += tokens_out
        _merge_cost_group_row(
            by_day,
            _bucket_created_at(row["created_at"], "day"),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
        )
        _merge_cost_group_row(
            by_week,
            _bucket_created_at(row["created_at"], "week"),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
        )
        _merge_cost_group_row(
            by_month,
            _bucket_created_at(row["created_at"], "month"),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
        )
        _merge_cost_group_row(
            by_workflow, str(row["workflow_id"]), tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost_usd
        )
        _merge_cost_group_row(
            by_phase, str(row["phase"]), tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost_usd
        )
        _merge_cost_group_row(
            by_model, str(row["model"]), tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost_usd
        )

    return {
        "start_ts": start_ts,
        "end_ts": end_ts,
        "workflow_count": len({str(row["workflow_id"]) for row in rows}),
        "totals": totals,
        "by_day": [{"bucket": key, **value} for key, value in sorted(by_day.items(), key=lambda item: item[0])],
        "by_week": [{"bucket": key, **value} for key, value in sorted(by_week.items(), key=lambda item: item[0])],
        "by_month": [{"bucket": key, **value} for key, value in sorted(by_month.items(), key=lambda item: item[0])],
        "by_workflow": [
            {"group_key": key, **value}
            for key, value in sorted(by_workflow.items(), key=lambda item: item[1]["cost_usd"], reverse=True)
        ],
        "by_phase": [
            {"group_key": key, **value}
            for key, value in sorted(by_phase.items(), key=lambda item: item[1]["cost_usd"], reverse=True)
        ],
        "by_model": [
            {"group_key": key, **value}
            for key, value in sorted(by_model.items(), key=lambda item: item[1]["cost_usd"], reverse=True)
        ],
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/api/db/{run_id}/costs")
async def get_db_costs(run_id: str) -> dict[str, Any]:
    """Aggregated cost_records from the run's SQLite database."""
    import json as _json

    db_path = _get_db_path(run_id)
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT model, phase,
                          COUNT(*) as calls,
                          SUM(tokens_in) as tokens_in,
                          SUM(tokens_out) as tokens_out,
                          SUM(cost_usd) as cost_usd,
                          AVG(latency_ms) as avg_latency_ms
                   FROM cost_records
                   GROUP BY model, phase
                   ORDER BY cost_usd DESC"""
            ) as cur:
                rows = await cur.fetchall()
            async with db.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM cost_records") as cur:
                total_cost = float((await cur.fetchone())[0])  # type: ignore[index]
            async with db.execute(
                """
                SELECT rationale
                FROM decision_log
                WHERE decision_type = 'screening_metric'
                  AND phase = 'phase_3_screening'
                ORDER BY id ASC
                """
            ) as cur:
                metric_rows = await cur.fetchall()

            records = [dict(row) for row in rows]
            screening_metrics: dict[str, float] = {}
            for row in metric_rows:
                try:
                    payload = _json.loads(str(row["rationale"] or "{}"))
                except Exception:
                    continue
                metric_name = payload.get("metric")
                metric_value = payload.get("value")
                if not isinstance(metric_name, str):
                    continue
                if isinstance(metric_value, (int, float)):
                    screening_metrics[metric_name] = float(metric_value)
            screening_diagnostics = {
                "batch_parse_degraded": int(screening_metrics.get("batch_parse_degraded", 0.0)),
                "batch_id_mismatch": int(screening_metrics.get("batch_id_mismatch", 0.0)),
                "batch_missing_fallback": int(screening_metrics.get("batch_missing_fallback", 0.0)),
                "contract_violation_count": int(screening_metrics.get("contract_violation_count", 0.0)),
                "fast_path_include": int(screening_metrics.get("title_abstract_fast_path_include", 0.0)),
                "fast_path_exclude": int(screening_metrics.get("title_abstract_fast_path_exclude", 0.0)),
                "cross_reviewed": int(screening_metrics.get("title_abstract_cross_reviewed", 0.0)),
            }
            return {"total_cost": total_cost, "records": records, "screening_diagnostics": screening_diagnostics}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/db/{run_id}/costs/aggregates")
async def get_db_cost_aggregates(
    run_id: str,
    start_ts: str | None = None,
    end_ts: str | None = None,
) -> dict[str, Any]:
    """Return day/week/month plus workflow/phase/model cost aggregations."""
    db_path = _get_db_path(run_id)
    where_sql, where_params = _build_cost_time_filter(start_ts, end_ts)
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row

            async def _query_bucket(bucket_sql: str) -> list[dict[str, Any]]:
                query = f"""
                    SELECT {bucket_sql} AS bucket,
                           COUNT(*) AS calls,
                           COALESCE(SUM(tokens_in), 0) AS tokens_in,
                           COALESCE(SUM(tokens_out), 0) AS tokens_out,
                           COALESCE(SUM(cost_usd), 0.0) AS cost_usd
                    FROM cost_records
                    {where_sql}
                    GROUP BY bucket
                    ORDER BY bucket ASC
                """
                rows = await (await db.execute(query, where_params)).fetchall()
                return [dict(r) for r in rows]

            async def _query_group(group_sql: str) -> list[dict[str, Any]]:
                query = f"""
                    SELECT {group_sql} AS group_key,
                           COUNT(*) AS calls,
                           COALESCE(SUM(tokens_in), 0) AS tokens_in,
                           COALESCE(SUM(tokens_out), 0) AS tokens_out,
                           COALESCE(SUM(cost_usd), 0.0) AS cost_usd
                    FROM cost_records
                    {where_sql}
                    GROUP BY group_key
                    ORDER BY cost_usd DESC
                """
                rows = await (await db.execute(query, where_params)).fetchall()
                return [dict(r) for r in rows]

            total_row = await (
                await db.execute(
                    f"""
                    SELECT COALESCE(SUM(cost_usd), 0.0) AS total_cost_usd,
                           COUNT(*) AS total_calls,
                           COALESCE(SUM(tokens_in), 0) AS total_tokens_in,
                           COALESCE(SUM(tokens_out), 0) AS total_tokens_out
                    FROM cost_records
                    {where_sql}
                    """,
                    where_params,
                )
            ).fetchone()

            by_day = await _query_bucket("date(created_at)")
            by_week = await _query_bucket("strftime('%Y-W%W', created_at)")
            by_month = await _query_bucket("strftime('%Y-%m', created_at)")
            by_workflow = await _query_group("COALESCE(NULLIF(workflow_id, ''), 'unknown')")
            by_phase = await _query_group("COALESCE(NULLIF(phase, ''), 'unknown')")
            by_model = await _query_group("COALESCE(NULLIF(model, ''), 'unknown')")

            return {
                "run_id": run_id,
                "start_ts": start_ts,
                "end_ts": end_ts,
                "totals": dict(total_row) if total_row else {},
                "by_day": by_day,
                "by_week": by_week,
                "by_month": by_month,
                "by_workflow": by_workflow,
                "by_phase": by_phase,
                "by_model": by_model,
            }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/history/costs/aggregates")
async def get_history_cost_aggregates(
    run_root: str = "runs",
    start_ts: str | None = None,
    end_ts: str | None = None,
    include_archived: bool = True,
) -> dict[str, Any]:
    """Return cross-run cost aggregates from registry-linked runtime DBs."""
    try:
        rows = await _fetch_registry_cost_rows(
            run_root, start_ts=start_ts, end_ts=end_ts, include_archived=include_archived
        )
        payload = _build_global_cost_aggregates_payload(rows, start_ts=start_ts, end_ts=end_ts)
        payload["run_root"] = run_root
        payload["include_archived"] = include_archived
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/db/{run_id}/costs/export")
async def export_db_costs_csv(
    run_id: str,
    start_ts: str | None = None,
    end_ts: str | None = None,
    granularity: str = "day",
) -> StreamingResponse:
    """Export reconciliation-friendly grouped cost CSV for a run."""
    db_path = _get_db_path(run_id)
    where_sql, where_params = _build_cost_time_filter(start_ts, end_ts)
    bucket_by_granularity = {
        "day": "date(created_at)",
        "week": "strftime('%Y-W%W', created_at)",
        "month": "strftime('%Y-%m', created_at)",
    }
    if granularity not in bucket_by_granularity:
        raise HTTPException(status_code=400, detail="granularity must be one of: day, week, month")

    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            query = f"""
                SELECT {bucket_by_granularity[granularity]} AS timestamp_bucket,
                       COALESCE(NULLIF(workflow_id, ''), 'unknown') AS workflow_id,
                       COALESCE(NULLIF(phase, ''), 'unknown') AS phase,
                       COALESCE(NULLIF(model, ''), 'unknown') AS model,
                       COUNT(*) AS call_count,
                       COALESCE(SUM(tokens_in), 0) AS tokens_in,
                       COALESCE(SUM(tokens_out), 0) AS tokens_out,
                       COALESCE(SUM(cost_usd), 0.0) AS cost_usd
                FROM cost_records
                {where_sql}
                GROUP BY timestamp_bucket, workflow_id, phase, model
                ORDER BY timestamp_bucket ASC, cost_usd DESC
            """
            rows = await (await db.execute(query, where_params)).fetchall()

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            ["timestamp_bucket", "workflow_id", "phase", "model", "call_count", "tokens_in", "tokens_out", "cost_usd"]
        )
        for row in rows:
            writer.writerow(
                [
                    row["timestamp_bucket"],
                    row["workflow_id"],
                    row["phase"],
                    row["model"],
                    row["call_count"],
                    row["tokens_in"],
                    row["tokens_out"],
                    row["cost_usd"],
                ]
            )
        filename = f"cost_export_{run_id}_{granularity}.csv"
        return StreamingResponse(
            iter([buffer.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/history/costs/export")
async def export_history_costs_csv(
    run_root: str = "runs",
    start_ts: str | None = None,
    end_ts: str | None = None,
    granularity: str = "day",
    include_archived: bool = True,
) -> StreamingResponse:
    """Export cross-run cost CSV grouped over registry-linked runtime DBs."""
    if granularity not in {"day", "week", "month"}:
        raise HTTPException(status_code=400, detail="granularity must be one of: day, week, month")
    try:
        rows = await _fetch_registry_cost_rows(
            run_root, start_ts=start_ts, end_ts=end_ts, include_archived=include_archived
        )
        grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        for row in rows:
            bucket = _bucket_created_at(row["created_at"], granularity)
            key = (bucket, str(row["workflow_id"]), str(row["phase"]), str(row["model"]))
            current = grouped.setdefault(
                key,
                {
                    "timestamp_bucket": bucket,
                    "workflow_id": str(row["workflow_id"]),
                    "phase": str(row["phase"]),
                    "model": str(row["model"]),
                    "call_count": 0,
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "cost_usd": 0.0,
                },
            )
            current["call_count"] += 1
            current["tokens_in"] += int(row["tokens_in"])
            current["tokens_out"] += int(row["tokens_out"])
            current["cost_usd"] += float(row["cost_usd"])

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            ["timestamp_bucket", "workflow_id", "phase", "model", "call_count", "tokens_in", "tokens_out", "cost_usd"]
        )
        for row in sorted(grouped.values(), key=lambda item: (str(item["timestamp_bucket"]), -float(item["cost_usd"]))):
            writer.writerow(
                [
                    row["timestamp_bucket"],
                    row["workflow_id"],
                    row["phase"],
                    row["model"],
                    row["call_count"],
                    row["tokens_in"],
                    row["tokens_out"],
                    row["cost_usd"],
                ]
            )
        filename = f"history_cost_export_{granularity}.csv"
        return StreamingResponse(
            iter([buffer.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
