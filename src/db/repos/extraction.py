"""Data extraction and synthesis results repository."""

from __future__ import annotations

import json
import logging

import aiosqlite
from pydantic import ValidationError

from src.models import ExtractionRecord
from src.models.enums import PrimaryStudyStatus
from src.synthesis.feasibility import SynthesisFeasibility
from src.synthesis.narrative import NarrativeSynthesis

_logger = logging.getLogger(__name__)


class ExtractionRepo:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def get_extraction_record_ids(self, workflow_id: str) -> set[str]:
        """Paper IDs already in extraction_records."""
        cursor = await self.db.execute(
            """
            SELECT paper_id FROM extraction_records WHERE workflow_id = ?
            """,
            (workflow_id,),
        )
        rows = await cursor.fetchall()
        return {str(row[0]) for row in rows}

    async def load_extraction_records(self, workflow_id: str) -> list[ExtractionRecord]:
        """Load all extraction records for a workflow.

        Skips malformed or legacy records (ValidationError) to allow resume of
        old runs with schema changes.
        """
        cursor = await self.db.execute(
            """
            SELECT paper_id, primary_study_status, data
            FROM extraction_records
            WHERE workflow_id = ?
            """,
            (workflow_id,),
        )
        rows = await cursor.fetchall()
        records: list[ExtractionRecord] = []
        for row in rows:
            paper_id = str(row[0]) if row else "unknown"
            column_status = str(row[1]) if len(row) > 1 and row[1] is not None else "unknown"
            data_json = str(row[2]) if len(row) > 2 else str(row[1])
            try:
                record = ExtractionRecord.model_validate_json(data_json)
            except (ValidationError, ValueError) as exc:
                _logger.warning(
                    "Skipping malformed extraction record for paper %s: %s",
                    paper_id,
                    exc,
                )
                continue
            json_status = record.primary_study_status.value
            effective_status = (
                column_status if column_status != "unknown" else json_status
            )
            if effective_status != json_status:
                try:
                    record.primary_study_status = PrimaryStudyStatus(effective_status)
                except ValueError as exc:
                    _logger.warning(
                        "Invalid primary_study_status column value %r for paper %s; "
                        "falling back to JSON-derived status %r: %s",
                        effective_status,
                        paper_id,
                        json_status,
                        exc,
                    )
            records.append(record)
        return records

    async def save_extraction_record(self, workflow_id: str, record: ExtractionRecord) -> None:
        await self.db.execute(
            """
            INSERT INTO extraction_records (
                workflow_id, paper_id, study_design, primary_study_status, extraction_source, data
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(workflow_id, paper_id) DO UPDATE SET
                study_design = excluded.study_design,
                primary_study_status = excluded.primary_study_status,
                extraction_source = excluded.extraction_source,
                data = excluded.data
            """,
            (
                workflow_id,
                record.paper_id,
                record.study_design.value,
                record.primary_study_status.value,
                (record.extraction_source or "text"),
                record.model_dump_json(),
            ),
        )
        await self.db.commit()

    async def save_synthesis_result(
        self,
        workflow_id: str,
        feasibility: SynthesisFeasibility,
        narrative: NarrativeSynthesis,
    ) -> None:
        """Persist synthesis results to DB as the canonical typed source of truth."""
        await self.db.execute(
            """
            INSERT INTO synthesis_results (
                workflow_id, outcome_name, feasibility_data, narrative_data
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(workflow_id, outcome_name) DO UPDATE SET
                feasibility_data = excluded.feasibility_data,
                narrative_data = excluded.narrative_data
            """,
            (
                workflow_id,
                narrative.outcome_name,
                json.dumps(feasibility.model_dump()),
                json.dumps(narrative.model_dump()),
            ),
        )
        await self.db.commit()

    async def load_synthesis_result(self, workflow_id: str) -> tuple[SynthesisFeasibility, NarrativeSynthesis] | None:
        """Load the most recent synthesis result for a workflow.

        Returns a typed (SynthesisFeasibility, NarrativeSynthesis) pair, or None
        if no result has been saved (e.g. older DB without synthesis_results table).
        """
        try:
            cursor = await self.db.execute(
                """
                SELECT feasibility_data, narrative_data
                FROM synthesis_results
                WHERE workflow_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (workflow_id,),
            )
            row = await cursor.fetchone()
        except Exception:
            return None
        if row is None:
            return None
        try:
            feasibility = SynthesisFeasibility.model_validate(json.loads(str(row[0])))
            narrative = NarrativeSynthesis.model_validate(json.loads(str(row[1])))
            return feasibility, narrative
        except Exception:
            return None
