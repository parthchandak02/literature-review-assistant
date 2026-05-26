"""Checkpoints, workflow steps, and recovery policies repository."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import aiosqlite

from src.models import RecoveryPolicyRecord, WorkflowStepRecord

_logger = logging.getLogger(__name__)


class WorkflowStateRepo:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def get_checkpoints(self, workflow_id: str) -> dict[str, str]:
        """Return phase -> status for all checkpoints of this workflow."""
        cursor = await self.db.execute(
            """
            SELECT phase, status FROM checkpoints WHERE workflow_id = ?
            """,
            (workflow_id,),
        )
        rows = await cursor.fetchall()
        return {str(row[0]): str(row[1]) for row in rows}

    async def save_checkpoint(
        self,
        workflow_id: str,
        phase: str,
        papers_processed: int = 0,
        status: str = "completed",
    ) -> None:
        _logger.debug(
            "save_checkpoint: workflow_id=%s, phase=%s, papers_processed=%s",
            workflow_id,
            phase,
            papers_processed,
        )
        await self.db.execute(
            """
            INSERT INTO checkpoints (workflow_id, phase, status, papers_processed)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(workflow_id, phase) DO UPDATE SET
                status = CASE
                    WHEN excluded.status = 'completed' THEN 'completed'
                    WHEN checkpoints.status = 'completed' THEN 'completed'
                    ELSE excluded.status
                END,
                papers_processed = CASE
                    WHEN excluded.status = 'completed' THEN excluded.papers_processed
                    ELSE MAX(checkpoints.papers_processed, excluded.papers_processed)
                END
            """,
            (workflow_id, phase, status, papers_processed),
        )
        await self.db.commit()

    async def delete_checkpoints_for_phases(self, workflow_id: str, phases: list[str]) -> None:
        """Delete checkpoints for the given phases. Used when resuming from a specific phase."""
        if not phases:
            return
        placeholders = ",".join("?" * len(phases))
        await self.db.execute(
            f"""
            DELETE FROM checkpoints
            WHERE workflow_id = ? AND phase IN ({placeholders})
            """,
            (workflow_id, *phases),
        )
        await self.db.commit()

    async def has_checkpoint_integrity(self, workflow_id: str) -> bool:
        cursor = await self.db.execute(
            "SELECT COUNT(*) FROM workflows WHERE workflow_id = ?",
            (workflow_id,),
        )
        workflow_row = await cursor.fetchone()
        if workflow_row is None or int(workflow_row[0]) == 0:
            return False
        return True

    async def create_workflow(self, workflow_id: str, topic: str, config_hash: str) -> None:
        await self.db.execute(
            """
            INSERT INTO workflows (workflow_id, topic, config_hash, status)
            VALUES (?, ?, ?, 'running')
            ON CONFLICT(workflow_id) DO UPDATE SET
                topic = excluded.topic,
                config_hash = excluded.config_hash,
                status = 'running',
                updated_at = CURRENT_TIMESTAMP
            """,
            (workflow_id, topic, config_hash),
        )
        await self.db.commit()

    async def update_workflow_status(self, workflow_id: str, status: str) -> None:
        """Update the status column in the local runtime.db workflows table."""
        await self.db.execute(
            "UPDATE workflows SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE workflow_id = ?",
            (status, workflow_id),
        )
        await self.db.commit()

    # ------------------------------------------------------------------
    # Step-level execution journal
    # ------------------------------------------------------------------

    async def save_workflow_step(self, record: WorkflowStepRecord) -> None:
        """Upsert a step execution record into the workflow journal."""
        await self.db.execute(
            """
            INSERT INTO workflow_steps (
                step_id, workflow_id, phase, step_name, status,
                attempt_number, max_attempts, paper_id, input_hash,
                output_hash, error_message, failure_category,
                recovery_action, parent_step_id, duration_ms,
                meta_json, started_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(step_id) DO UPDATE SET
                status = excluded.status,
                attempt_number = excluded.attempt_number,
                output_hash = excluded.output_hash,
                error_message = excluded.error_message,
                failure_category = excluded.failure_category,
                recovery_action = excluded.recovery_action,
                duration_ms = excluded.duration_ms,
                meta_json = excluded.meta_json,
                completed_at = excluded.completed_at
            """,
            (
                record.step_id,
                record.workflow_id,
                record.phase,
                record.step_name,
                record.status.value,
                record.attempt_number,
                record.max_attempts,
                record.paper_id,
                record.input_hash,
                record.output_hash,
                record.error_message,
                record.failure_category.value if record.failure_category else None,
                record.recovery_action.value if record.recovery_action else None,
                record.parent_step_id,
                record.duration_ms,
                record.meta_json,
                record.started_at.isoformat(),
                record.completed_at.isoformat() if record.completed_at else None,
            ),
        )
        await self.db.commit()

    async def reconcile_stale_running_steps(
        self,
        workflow_id: str,
        phase: str,
        step_name: str,
        *,
        replacement_step_id: str | None = None,
        completion_note: str = "superseded by a newer attempt",
    ) -> int:
        """Mark orphaned running rows as skipped before a replacement attempt starts."""
        conditions = [
            "workflow_id = ?",
            "phase = ?",
            "step_name = ?",
            "status = 'running'",
        ]
        params: list[object] = [workflow_id, phase, step_name]
        if replacement_step_id:
            conditions.append("step_id != ?")
            params.append(replacement_step_id)
        now = datetime.now(UTC).isoformat()
        cursor = await self.db.execute(
            f"""
            UPDATE workflow_steps
            SET status = 'skipped',
                error_message = ?,
                completed_at = COALESCE(completed_at, ?)
            WHERE {" AND ".join(conditions)}
            """,
            (completion_note, now, *params),
        )
        await self.db.commit()
        return int(cursor.rowcount or 0)

    async def get_step_history(
        self, workflow_id: str, phase: str | None = None, *, limit: int = 200
    ) -> list[WorkflowStepRecord]:
        """Return step records for a workflow, optionally filtered by phase."""
        if phase:
            cursor = await self.db.execute(
                """
                SELECT step_id, workflow_id, phase, step_name, status,
                       attempt_number, max_attempts, paper_id, input_hash,
                       output_hash, error_message, failure_category,
                       recovery_action, parent_step_id, duration_ms,
                       meta_json, started_at, completed_at
                FROM workflow_steps
                WHERE workflow_id = ? AND phase = ?
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (workflow_id, phase, limit),
            )
        else:
            cursor = await self.db.execute(
                """
                SELECT step_id, workflow_id, phase, step_name, status,
                       attempt_number, max_attempts, paper_id, input_hash,
                       output_hash, error_message, failure_category,
                       recovery_action, parent_step_id, duration_ms,
                       meta_json, started_at, completed_at
                FROM workflow_steps
                WHERE workflow_id = ?
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (workflow_id, limit),
            )
        rows = await cursor.fetchall()
        return [self._row_to_step_record(r) for r in rows]

    async def count_step_failures(self, workflow_id: str, phase: str | None = None) -> int:
        if phase:
            cursor = await self.db.execute(
                "SELECT COUNT(*) FROM workflow_steps WHERE workflow_id = ? AND phase = ? AND status = 'failed'",
                (workflow_id, phase),
            )
        else:
            cursor = await self.db.execute(
                "SELECT COUNT(*) FROM workflow_steps WHERE workflow_id = ? AND status = 'failed'",
                (workflow_id,),
            )
        row = await cursor.fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    async def get_step_summary(self, workflow_id: str) -> dict[str, dict[str, int]]:
        """Return {phase: {status: count}} aggregation for diagnostics."""
        cursor = await self.db.execute(
            """
            SELECT phase, status, COUNT(*) AS cnt
            FROM workflow_steps
            WHERE workflow_id = ?
            GROUP BY phase, status
            ORDER BY phase, status
            """,
            (workflow_id,),
        )
        rows = await cursor.fetchall()
        summary: dict[str, dict[str, int]] = {}
        for row in rows:
            phase_key = str(row[0])
            status_key = str(row[1])
            if phase_key not in summary:
                summary[phase_key] = {}
            summary[phase_key][status_key] = int(row[2])
        return summary

    async def count_running_steps(self, workflow_id: str, phase: str | None = None) -> int:
        if phase:
            cursor = await self.db.execute(
                "SELECT COUNT(*) FROM workflow_steps WHERE workflow_id = ? AND phase = ? AND status = 'running'",
                (workflow_id, phase),
            )
        else:
            cursor = await self.db.execute(
                "SELECT COUNT(*) FROM workflow_steps WHERE workflow_id = ? AND status = 'running'",
                (workflow_id,),
            )
        row = await cursor.fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    @staticmethod
    def _row_to_step_record(row: tuple[Any, ...]) -> WorkflowStepRecord:
        from src.models.enums import FailureCategory as FC
        from src.models.enums import RecoveryAction as RA
        from src.models.enums import StepStatus as SS

        started = datetime.fromisoformat(str(row[16])) if row[16] else datetime.now(UTC)
        completed = datetime.fromisoformat(str(row[17])) if row[17] else None
        fc_val = FC(str(row[11])) if row[11] else None
        ra_val = RA(str(row[12])) if row[12] else None
        return WorkflowStepRecord(
            step_id=str(row[0]),
            workflow_id=str(row[1]),
            phase=str(row[2]),
            step_name=str(row[3]),
            status=SS(str(row[4])),
            attempt_number=int(row[5]),
            max_attempts=int(row[6]),
            paper_id=str(row[7]) if row[7] else None,
            input_hash=str(row[8]) if row[8] else None,
            output_hash=str(row[9]) if row[9] else None,
            error_message=str(row[10]) if row[10] else None,
            failure_category=fc_val,
            recovery_action=ra_val,
            parent_step_id=str(row[13]) if row[13] else None,
            duration_ms=int(row[14]) if row[14] is not None else None,
            meta_json=str(row[15] or "{}"),
            started_at=started,
            completed_at=completed,
        )

    # ------------------------------------------------------------------
    # Bounded recovery policies
    # ------------------------------------------------------------------

    async def get_or_create_recovery_policy(
        self,
        workflow_id: str,
        phase: str,
        step_name: str,
        *,
        max_retries: int = 3,
        max_rewinds: int = 1,
        rewind_target_phase: str | None = None,
    ) -> RecoveryPolicyRecord:
        """Load existing policy or create with defaults. Never overwrites counts."""
        cursor = await self.db.execute(
            """
            SELECT workflow_id, phase, step_name, max_retries, max_rewinds,
                   current_retries, current_rewinds, rewind_target_phase,
                   policy_status, meta_json, created_at, updated_at
            FROM recovery_policies
            WHERE workflow_id = ? AND phase = ? AND step_name = ?
            """,
            (workflow_id, phase, step_name),
        )
        row = await cursor.fetchone()
        if row:
            return RecoveryPolicyRecord(
                workflow_id=str(row[0]),
                phase=str(row[1]),
                step_name=str(row[2]),
                max_retries=int(row[3]),
                max_rewinds=int(row[4]),
                current_retries=int(row[5]),
                current_rewinds=int(row[6]),
                rewind_target_phase=str(row[7]) if row[7] else None,
                policy_status=str(row[8]),
                meta_json=str(row[9] or "{}"),
                created_at=datetime.fromisoformat(str(row[10])) if row[10] else datetime.now(UTC),
                updated_at=datetime.fromisoformat(str(row[11])) if row[11] else datetime.now(UTC),
            )
        record = RecoveryPolicyRecord(
            workflow_id=workflow_id,
            phase=phase,
            step_name=step_name,
            max_retries=max_retries,
            max_rewinds=max_rewinds,
            rewind_target_phase=rewind_target_phase,
        )
        await self.db.execute(
            """
            INSERT INTO recovery_policies (
                workflow_id, phase, step_name, max_retries, max_rewinds,
                current_retries, current_rewinds, rewind_target_phase,
                policy_status, meta_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.workflow_id,
                record.phase,
                record.step_name,
                record.max_retries,
                record.max_rewinds,
                record.current_retries,
                record.current_rewinds,
                record.rewind_target_phase,
                record.policy_status,
                record.meta_json,
                record.created_at.isoformat(),
                record.updated_at.isoformat(),
            ),
        )
        await self.db.commit()
        return record

    async def increment_retry_count(self, workflow_id: str, phase: str, step_name: str) -> int:
        """Atomically increment current_retries; return new count."""
        await self.db.execute(
            """
            UPDATE recovery_policies
            SET current_retries = current_retries + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE workflow_id = ? AND phase = ? AND step_name = ?
            """,
            (workflow_id, phase, step_name),
        )
        await self.db.commit()
        cursor = await self.db.execute(
            "SELECT current_retries FROM recovery_policies WHERE workflow_id = ? AND phase = ? AND step_name = ?",
            (workflow_id, phase, step_name),
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def increment_rewind_count(self, workflow_id: str, phase: str, step_name: str) -> int:
        """Atomically increment current_rewinds; return new count."""
        await self.db.execute(
            """
            UPDATE recovery_policies
            SET current_rewinds = current_rewinds + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE workflow_id = ? AND phase = ? AND step_name = ?
            """,
            (workflow_id, phase, step_name),
        )
        await self.db.commit()
        cursor = await self.db.execute(
            "SELECT current_rewinds FROM recovery_policies WHERE workflow_id = ? AND phase = ? AND step_name = ?",
            (workflow_id, phase, step_name),
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0
