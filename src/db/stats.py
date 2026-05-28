"""Canonical run-level stats resolution for history and API surfaces."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import aiosqlite

from src.db.source_of_truth import RUN_STATS_PRECEDENCE

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IncludedStudyCount:
    count: int
    source_key: str


class RunStatsResolver:
    """Resolve sidebar/history aggregate numbers with documented precedence."""

    async def latest_workflow_id(self, db: aiosqlite.Connection) -> str:
        row = await (await db.execute("SELECT workflow_id FROM workflows ORDER BY rowid DESC LIMIT 1")).fetchone()
        return str(row[0]) if row and row[0] else ""

    async def papers_found(self, db: aiosqlite.Connection) -> int:
        row = await (await db.execute("SELECT COUNT(*) FROM papers")).fetchone()
        return int(row[0]) if row else 0

    async def papers_included(self, db: aiosqlite.Connection, *, workflow_id: str | None = None) -> IncludedStudyCount:
        wf_id = workflow_id or await self.latest_workflow_id(db)

        included_from_cohort = await (
            await db.execute(
                """
                SELECT COUNT(DISTINCT scm.paper_id)
                FROM study_cohort_membership scm
                WHERE scm.workflow_id = ?
                  AND scm.synthesis_eligibility = 'included_primary'
                """,
                (wf_id,),
            )
        ).fetchone()
        included_from_dual = await (
            await db.execute(
                """
                SELECT COUNT(DISTINCT paper_id)
                FROM dual_screening_results
                WHERE stage = 'fulltext' AND final_decision IN ('include', 'uncertain')
                """
            )
        ).fetchone()

        source_key = RUN_STATS_PRECEDENCE.papers_included_order[0]
        if included_from_cohort and included_from_cohort[0] is not None and int(included_from_cohort[0]) > 0:
            count = int(included_from_cohort[0])
        elif included_from_dual and included_from_dual[0] is not None and int(included_from_dual[0]) > 0:
            count = int(included_from_dual[0])
            source_key = "dual_screening_results_fulltext"
        else:
            included_from_event = await (
                await db.execute(
                    """
                    SELECT json_extract(payload, '$.summary.included')
                    FROM event_log
                    WHERE event_type = 'phase_done'
                      AND json_extract(payload, '$.phase') = 'phase_3_screening'
                    ORDER BY id DESC
                    LIMIT 1
                    """
                )
            ).fetchone()
            if included_from_event and included_from_event[0] is not None:
                count = int(included_from_event[0])
                source_key = "event_log_phase_done_phase_3_screening"
            else:
                fallback_row = await (await db.execute("SELECT COUNT(*) FROM extraction_records")).fetchone()
                count = int(fallback_row[0]) if fallback_row else 0
                source_key = "extraction_records"

        await self._log_divergence_if_needed(
            db,
            source_key=source_key,
            included_from_cohort=included_from_cohort,
            included_from_dual=included_from_dual,
        )
        return IncludedStudyCount(count=count, source_key=source_key)

    async def total_cost(self, db: aiosqlite.Connection) -> float:
        row = await (await db.execute("SELECT COALESCE(SUM(cost_usd), 0.0) FROM cost_records")).fetchone()
        return float(row[0]) if row else 0.0

    async def aggregate(self, db: aiosqlite.Connection) -> dict[str, Any]:
        wf_id = await self.latest_workflow_id(db)
        included = await self.papers_included(db, workflow_id=wf_id)
        return {
            "papers_found": await self.papers_found(db),
            "papers_included": included.count,
            "papers_included_source": included.source_key,
            "papers_included_precedence": list(RUN_STATS_PRECEDENCE.papers_included_order),
            "total_cost": await self.total_cost(db),
        }

    async def _log_divergence_if_needed(
        self,
        db: aiosqlite.Connection,
        *,
        source_key: str,
        included_from_cohort: Any,
        included_from_dual: Any,
    ) -> None:
        try:
            _event_inc_row = await (
                await db.execute(
                    """
                    SELECT json_extract(payload, '$.summary.included')
                    FROM event_log
                    WHERE event_type = 'phase_done'
                      AND json_extract(payload, '$.phase') = 'phase_3_screening'
                    ORDER BY id DESC
                    LIMIT 1
                    """
                )
            ).fetchone()
            _event_inc = int(_event_inc_row[0]) if (_event_inc_row and _event_inc_row[0] is not None) else None
            _cohort_inc = (
                int(included_from_cohort[0]) if (included_from_cohort and included_from_cohort[0] is not None) else 0
            )
            _dual_inc = int(included_from_dual[0]) if (included_from_dual and included_from_dual[0] is not None) else 0
            if (
                source_key == "dual_screening_results_fulltext"
                and _event_inc is not None
                and _dual_inc > 0
                and _event_inc != _dual_inc
            ):
                _logger.warning(
                    "run-stats divergence: dual_screening_results=%s event_log=%s",
                    _dual_inc,
                    _event_inc,
                )
            if source_key == "study_cohort_membership_synthesis_included_primary" and _cohort_inc > _dual_inc > 0:
                _logger.warning(
                    "run-stats divergence: cohort=%s exceeds dual_screening_results=%s",
                    _cohort_inc,
                    _dual_inc,
                )
        except Exception:
            pass
