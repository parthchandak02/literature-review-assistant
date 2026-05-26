"""Decision log, fallback events, and RAG diagnostics repository."""

from __future__ import annotations

import json
import logging

import aiosqlite

from src.models import (
    DecisionLogEntry,
    FallbackEventRecord,
    RagRetrievalDiagnostic,
)

_logger = logging.getLogger(__name__)


class EventsRepo:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def _get_writing_generation(self, workflow_id: str) -> int:
        cursor = await self.db.execute(
            "SELECT writing_generation FROM workflows WHERE workflow_id = ?",
            (workflow_id,),
        )
        row = await cursor.fetchone()
        if row and row[0] is not None:
            return max(1, int(row[0]))
        return 1

    async def _resolve_writing_generation(self, workflow_id: str, generation: int | None) -> int:
        if generation is not None and generation > 0:
            return int(generation)
        return await self._get_writing_generation(workflow_id)

    async def append_decision_log(self, entry: DecisionLogEntry) -> None:
        await self.db.execute(
            """
            INSERT INTO decision_log (workflow_id, decision_type, paper_id, decision, rationale, actor, phase)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.workflow_id,
                entry.decision_type,
                entry.paper_id,
                entry.decision,
                entry.rationale,
                entry.actor,
                entry.phase,
            ),
        )
        await self.db.commit()

    async def save_fallback_event(self, record: FallbackEventRecord) -> None:
        generation = await self._resolve_writing_generation(record.workflow_id, record.generation)
        existing = await (
            await self.db.execute(
                """
                SELECT id
                FROM fallback_events
                WHERE workflow_id = ?
                  AND phase = ?
                  AND module = ?
                  AND fallback_type = ?
                  AND reason = ?
                  AND COALESCE(paper_id, '') = COALESCE(?, '')
                  AND generation = ?
                LIMIT 1
                """,
                (
                    record.workflow_id,
                    record.phase,
                    record.module,
                    record.fallback_type,
                    record.reason,
                    record.paper_id,
                    generation,
                ),
            )
        ).fetchone()
        if existing:
            await self.db.execute(
                "UPDATE fallback_events SET details_json = ? WHERE id = ?",
                (record.details_json, int(existing[0])),
            )
            await self.db.commit()
            return
        await self.db.execute(
            """
            INSERT INTO fallback_events (
                workflow_id, phase, module, fallback_type, reason, paper_id, generation, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.workflow_id,
                record.phase,
                record.module,
                record.fallback_type,
                record.reason,
                record.paper_id,
                generation,
                record.details_json,
            ),
        )
        await self.db.commit()

    async def count_fallback_events(self, workflow_id: str) -> int:
        generation = await self._get_writing_generation(workflow_id)
        cursor = await self.db.execute(
            "SELECT COUNT(*) FROM fallback_events WHERE workflow_id = ? AND generation = ?",
            (workflow_id, generation),
        )
        row = await cursor.fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    async def get_fallback_event_summary(self, workflow_id: str) -> list[dict[str, object]]:
        generation = await self._get_writing_generation(workflow_id)
        cursor = await self.db.execute(
            """
            SELECT phase, module, fallback_type, COUNT(*) AS event_count
            FROM fallback_events
            WHERE workflow_id = ? AND generation = ?
            GROUP BY phase, module, fallback_type
            ORDER BY event_count DESC, phase ASC, module ASC
            """,
            (workflow_id, generation),
        )
        rows = await cursor.fetchall()
        return [
            {
                "phase": str(row[0]),
                "module": str(row[1]),
                "fallback_type": str(row[2]),
                "event_count": int(row[3]),
            }
            for row in rows
        ]

    async def save_rag_retrieval_diagnostic(self, record: RagRetrievalDiagnostic) -> None:
        """Persist per-section RAG retrieval diagnostics for auditability."""
        await self.db.execute(
            """
            INSERT INTO rag_retrieval_diagnostics (
                workflow_id, section, query_type, rerank_enabled, candidate_k, final_k,
                retrieved_count, status, selected_chunks_json, error_message, latency_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.workflow_id,
                record.section,
                record.query_type,
                1 if record.rerank_enabled else 0,
                record.candidate_k,
                record.final_k,
                record.retrieved_count,
                record.status,
                record.selected_chunks_json,
                record.error_message,
                record.latency_ms,
            ),
        )
        await self.db.commit()

    async def get_rag_retrieval_diagnostics(self, workflow_id: str) -> list[RagRetrievalDiagnostic]:
        """Load per-section RAG diagnostics ordered by creation time."""
        cursor = await self.db.execute(
            """
            SELECT section, query_type, rerank_enabled, candidate_k, final_k,
                   retrieved_count, status, selected_chunks_json, error_message,
                   latency_ms, created_at
            FROM rag_retrieval_diagnostics
            WHERE workflow_id = ?
            ORDER BY created_at ASC
            """,
            (workflow_id,),
        )
        rows = await cursor.fetchall()
        out: list[RagRetrievalDiagnostic] = []
        for row in rows:
            out.append(
                RagRetrievalDiagnostic(
                    workflow_id=workflow_id,
                    section=str(row[0]),
                    query_type=str(row[1]),
                    rerank_enabled=bool(row[2]),
                    candidate_k=int(row[3]),
                    final_k=int(row[4]),
                    retrieved_count=int(row[5]),
                    status=str(row[6]),
                    selected_chunks_json=str(row[7] or "[]"),
                    error_message=str(row[8]) if row[8] else None,
                    latency_ms=int(row[9]) if row[9] is not None else None,
                    created_at=str(row[10]),
                )
            )
        return out

    async def get_last_event_of_type(self, workflow_id: str, event_type: str) -> dict | None:
        """Return the JSON payload of the most recent event_log row of a given type.

        Returns None if no such event exists for this workflow. Used to source
        structured counts (e.g. batch_screen_done.excluded) that are not
        reflected in row-count queries across dual_screening_results.
        """
        cursor = await self.db.execute(
            """
            SELECT payload FROM event_log
            WHERE workflow_id = ? AND event_type = ?
            ORDER BY ts DESC
            LIMIT 1
            """,
            (workflow_id, event_type),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        try:
            return json.loads(row[0]) if isinstance(row[0], str) else row[0]
        except Exception:
            return None
