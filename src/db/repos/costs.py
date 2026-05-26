"""Cost records and performance summary repository."""

from __future__ import annotations

import logging

import aiosqlite

from src.models import CostRecord

_logger = logging.getLogger(__name__)


class CostsRepo:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def save_cost_record(self, record: CostRecord) -> None:
        await self.db.execute(
            """
            INSERT INTO cost_records
                (workflow_id, model, tokens_in, tokens_out, cost_usd, latency_ms, phase,
                 cache_read_tokens, cache_write_tokens)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.workflow_id,
                record.model,
                record.tokens_in,
                record.tokens_out,
                record.cost_usd,
                record.latency_ms,
                record.phase,
                record.cache_read_tokens,
                record.cache_write_tokens,
            ),
        )
        await self.db.commit()

    async def get_total_cost(self, workflow_id: str | None = None) -> float:
        if workflow_id:
            cursor = await self.db.execute(
                "SELECT COALESCE(SUM(cost_usd), 0.0) FROM cost_records WHERE workflow_id = ?",
                (workflow_id,),
            )
        else:
            cursor = await self.db.execute("SELECT COALESCE(SUM(cost_usd), 0.0) FROM cost_records")
        row = await cursor.fetchone()
        return float(row[0]) if row is not None else 0.0

    async def get_phase_performance_summary(self, workflow_id: str) -> list[dict[str, int | float | str]]:
        """Return per-phase wall time + token/cost summary for diagnostics."""
        cursor = await self.db.execute(
            """
            WITH step_perf AS (
                SELECT
                    phase,
                    COALESCE(SUM(duration_ms), 0) AS duration_ms,
                    COUNT(*) AS step_attempts
                FROM workflow_steps
                WHERE workflow_id = ?
                GROUP BY phase
            ),
            cost_perf AS (
                SELECT
                    phase,
                    COUNT(*) AS llm_calls,
                    COALESCE(SUM(tokens_in), 0) AS tokens_in,
                    COALESCE(SUM(tokens_out), 0) AS tokens_out,
                    COALESCE(SUM(cost_usd), 0.0) AS cost_usd,
                    COALESCE(SUM(latency_ms), 0) AS llm_latency_ms
                FROM cost_records
                WHERE workflow_id = ?
                GROUP BY phase
            ),
            phases AS (
                SELECT phase FROM step_perf
                UNION
                SELECT phase FROM cost_perf
            )
            SELECT
                phases.phase AS phase,
                COALESCE(step_perf.duration_ms, 0) AS duration_ms,
                COALESCE(step_perf.step_attempts, 0) AS step_attempts,
                COALESCE(cost_perf.llm_calls, 0) AS llm_calls,
                COALESCE(cost_perf.tokens_in, 0) AS tokens_in,
                COALESCE(cost_perf.tokens_out, 0) AS tokens_out,
                COALESCE(cost_perf.cost_usd, 0.0) AS cost_usd,
                COALESCE(cost_perf.llm_latency_ms, 0) AS llm_latency_ms
            FROM phases
            LEFT JOIN step_perf ON step_perf.phase = phases.phase
            LEFT JOIN cost_perf ON cost_perf.phase = phases.phase
            ORDER BY duration_ms DESC, cost_usd DESC
            """,
            (workflow_id, workflow_id),
        )
        rows = await cursor.fetchall()
        return [
            {
                "phase": str(row[0]),
                "duration_ms": int(row[1] or 0),
                "step_attempts": int(row[2] or 0),
                "llm_calls": int(row[3] or 0),
                "tokens_in": int(row[4] or 0),
                "tokens_out": int(row[5] or 0),
                "cost_usd": float(row[6] or 0.0),
                "llm_latency_ms": int(row[7] or 0),
            }
            for row in rows
        ]
