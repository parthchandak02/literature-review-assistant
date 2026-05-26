"""Validation runs, checks, artifacts, and gate results repository."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import aiosqlite

from src.models import (
    GateResult,
    ValidationArtifactRecord,
    ValidationCheckRecord,
    ValidationRunRecord,
)

_logger = logging.getLogger(__name__)


class ValidationRepo:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def save_gate_result(self, result: GateResult) -> None:
        await self.db.execute(
            """
            INSERT INTO gate_results (
                workflow_id, gate_name, phase, status, details, threshold, actual_value
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.workflow_id,
                result.gate_name,
                result.phase,
                result.status.value,
                result.details,
                result.threshold,
                result.actual_value,
            ),
        )
        await self.db.commit()

    async def get_latest_gate_result(self, workflow_id: str, phase: str, gate_name: str) -> GateResult | None:
        """Return the most recent gate result for the given workflow, phase, and gate."""
        cursor = await self.db.execute(
            """
            SELECT workflow_id, gate_name, phase, status, details, threshold, actual_value
            FROM gate_results
            WHERE workflow_id = ? AND phase = ? AND gate_name = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (workflow_id, phase, gate_name),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        from src.models.enums import GateStatus

        return GateResult(
            workflow_id=str(row[0]),
            gate_name=str(row[1]),
            phase=str(row[2]),
            status=GateStatus(str(row[3])),
            details=str(row[4]),
            threshold=str(row[5]) if row[5] is not None else None,
            actual_value=str(row[6]) if row[6] is not None else None,
        )

    async def save_validation_run(self, record: ValidationRunRecord) -> None:
        """Insert or update a validation run metadata row."""
        await self.db.execute(
            """
            INSERT INTO validation_runs (
                validation_run_id, workflow_id, profile, status, tool_version, summary_json, started_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(validation_run_id) DO UPDATE SET
                status = excluded.status,
                summary_json = excluded.summary_json,
                completed_at = excluded.completed_at
            """,
            (
                record.validation_run_id,
                record.workflow_id,
                record.profile,
                record.status,
                record.tool_version,
                record.summary_json,
                record.started_at.isoformat(),
                record.completed_at.isoformat() if record.completed_at else None,
            ),
        )
        await self.db.commit()

    async def save_validation_check(self, record: ValidationCheckRecord) -> None:
        """Persist a single validation check row."""
        await self.db.execute(
            """
            INSERT INTO validation_checks (
                validation_run_id, workflow_id, phase, check_name, status, severity,
                metric_value, details_json, source_module, paper_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.validation_run_id,
                record.workflow_id,
                record.phase,
                record.check_name,
                record.status,
                record.severity,
                record.metric_value,
                record.details_json,
                record.source_module,
                record.paper_id,
                record.created_at.isoformat(),
            ),
        )
        await self.db.commit()

    async def save_validation_artifact(self, record: ValidationArtifactRecord) -> None:
        """Persist validation artifact metadata/content pointers."""
        await self.db.execute(
            """
            INSERT INTO validation_artifacts (
                validation_run_id, workflow_id, artifact_key, artifact_type,
                content_path, content_text, meta_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.validation_run_id,
                record.workflow_id,
                record.artifact_key,
                record.artifact_type,
                record.content_path,
                record.content_text,
                record.meta_json,
                record.created_at.isoformat(),
            ),
        )
        await self.db.commit()

    async def get_latest_validation_run(self, workflow_id: str) -> ValidationRunRecord | None:
        """Return latest validation run for a workflow, if present."""
        cursor = await self.db.execute(
            """
            SELECT validation_run_id, workflow_id, profile, status, tool_version, summary_json, started_at, completed_at
            FROM validation_runs
            WHERE workflow_id = ?
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (workflow_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        started = datetime.fromisoformat(str(row[6])) if row[6] else datetime.now(UTC)
        completed = datetime.fromisoformat(str(row[7])) if row[7] else None
        return ValidationRunRecord(
            validation_run_id=str(row[0]),
            workflow_id=str(row[1]),
            profile=str(row[2]),
            status=str(row[3]),
            tool_version=str(row[4]),
            summary_json=str(row[5] or "{}"),
            started_at=started,
            completed_at=completed,
        )

    async def get_validation_checks(self, validation_run_id: str) -> list[ValidationCheckRecord]:
        """Return ordered validation checks for a given validation run."""
        cursor = await self.db.execute(
            """
            SELECT validation_run_id, workflow_id, phase, check_name, status, severity,
                   metric_value, details_json, source_module, paper_id, created_at
            FROM validation_checks
            WHERE validation_run_id = ?
            ORDER BY id ASC
            """,
            (validation_run_id,),
        )
        rows = await cursor.fetchall()
        checks: list[ValidationCheckRecord] = []
        for row in rows:
            created_at = datetime.fromisoformat(str(row[10])) if row[10] else datetime.now(UTC)
            checks.append(
                ValidationCheckRecord(
                    validation_run_id=str(row[0]),
                    workflow_id=str(row[1]),
                    phase=str(row[2]),
                    check_name=str(row[3]),
                    status=str(row[4]),
                    severity=str(row[5]),
                    metric_value=float(row[6]) if row[6] is not None else None,
                    details_json=str(row[7] or "{}"),
                    source_module=str(row[8]) if row[8] else None,
                    paper_id=str(row[9]) if row[9] else None,
                    created_at=created_at,
                )
            )
        return checks

    async def load_validation_runs(self, workflow_id: str) -> list[ValidationRunRecord]:
        """Return all validation runs for a workflow, newest first."""
        cursor = await self.db.execute(
            """
            SELECT validation_run_id, workflow_id, profile, status, tool_version, summary_json, started_at, completed_at
            FROM validation_runs
            WHERE workflow_id = ?
            ORDER BY started_at DESC
            """,
            (workflow_id,),
        )
        rows = await cursor.fetchall()
        runs: list[ValidationRunRecord] = []
        for row in rows:
            started = datetime.fromisoformat(str(row[6])) if row[6] else datetime.now(UTC)
            completed = datetime.fromisoformat(str(row[7])) if row[7] else None
            runs.append(
                ValidationRunRecord(
                    validation_run_id=str(row[0]),
                    workflow_id=str(row[1]),
                    profile=str(row[2]),
                    status=str(row[3]),
                    tool_version=str(row[4]),
                    summary_json=str(row[5] or "{}"),
                    started_at=started,
                    completed_at=completed,
                )
            )
        return runs
