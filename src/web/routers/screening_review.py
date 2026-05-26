"""Human-in-the-loop screening review endpoints."""

from __future__ import annotations

import pathlib

import aiosqlite
from fastapi import APIRouter, HTTPException

from src.web.shared import ApproveScreeningRequest
from src.web.state import _get_db_path

router = APIRouter(tags=["screening_review"])


@router.get("/api/run/{run_id}/screening-summary")
async def get_screening_summary(run_id: str) -> dict:
    """Return screened papers and AI decisions for human review."""
    db_path = _get_db_path(run_id)
    if not pathlib.Path(db_path).exists():
        raise HTTPException(status_code=404, detail="Run database not found")

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT
                p.paper_id,
                p.title,
                p.authors,
                p.year,
                p.source_database,
                p.doi,
                p.abstract,
                sd.stage,
                sd.decision,
                sd.reason,
                sd.confidence
            FROM papers p
            JOIN screening_decisions sd ON p.paper_id = sd.paper_id
            WHERE sd.decision IN ('include', 'uncertain')
            ORDER BY sd.stage, p.year DESC
            """,
        )
        rows = await cursor.fetchall()
        papers = [dict(row) for row in rows]

    return {
        "run_id": run_id,
        "total": len(papers),
        "papers": papers,
        "instructions": (
            "Review AI screening decisions below. POST /api/run/{run_id}/approve-screening to proceed with extraction."
        ),
    }


@router.post("/api/run/{run_id}/approve-screening")
async def approve_screening(
    run_id: str,
    body: ApproveScreeningRequest | None = None,
) -> dict[str, str]:
    """Approve AI screening decisions and resume the workflow."""
    db_path = _get_db_path(run_id)
    if not pathlib.Path(db_path).exists():
        raise HTTPException(status_code=404, detail="Run database not found")

    from src.db.workflow_registry import find_by_workflow_id_fallback
    from src.db.workflow_registry import update_status as _update_status

    async with aiosqlite.connect(db_path) as _raw_db:
        cursor = await _raw_db.execute("SELECT workflow_id FROM workflows LIMIT 1")
        row = await cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="No workflow found in run database")

    workflow_id = row[0]
    run_root = str(pathlib.Path(db_path).parent.parent.parent.parent)

    overrides = (body.overrides if body else []) or []
    if overrides:
        try:
            import logging as _logging

            from src.db.database import get_db as _get_run_db
            from src.screening.criteria_refinement import (
                ScreeningCorrection,
                refine_criteria_from_corrections,
                save_corrections,
                save_learned_criteria,
            )

            corrections = [
                ScreeningCorrection(
                    paper_id=o.paper_id,
                    ai_decision="unknown",
                    human_decision=o.decision,
                    human_reason=o.reason,
                )
                for o in overrides
            ]

            async with _get_run_db(db_path) as _corr_db:
                for corr in corrections:
                    async with _corr_db.execute(
                        """
                        SELECT decision FROM screening_decisions
                        WHERE paper_id = ? ORDER BY created_at DESC LIMIT 1
                        """,
                        (corr.paper_id,),
                    ) as _sd_cur:
                        _sd_row = await _sd_cur.fetchone()
                        if _sd_row:
                            corr.ai_decision = _sd_row[0]

                paper_titles: dict[str, str] = {}
                async with _corr_db.execute(
                    "SELECT paper_id, title FROM papers WHERE paper_id IN ({})".format(
                        ",".join("?" * len(corrections))
                    ),
                    [c.paper_id for c in corrections],
                ) as _t_cur:
                    async for _t_row in _t_cur:
                        paper_titles[_t_row[0]] = _t_row[1] or ""

                await save_corrections(_corr_db, workflow_id, corrections)

                for _ov in overrides:
                    await _corr_db.execute(
                        """
                        INSERT INTO screening_decisions
                            (workflow_id, paper_id, stage, decision, reason,
                             exclusion_reason, reviewer_type, confidence)
                        VALUES (?, ?, 'fulltext', ?, ?, NULL, 'human_override', 1.0)
                        """,
                        (workflow_id, _ov.paper_id, _ov.decision, _ov.reason or "human override"),
                    )
                    await _corr_db.execute(
                        """
                        INSERT INTO dual_screening_results
                            (workflow_id, paper_id, stage, agreement, final_decision, adjudication_needed)
                        VALUES (?, ?, 'fulltext', 1, ?, 0)
                        ON CONFLICT(workflow_id, paper_id, stage) DO UPDATE SET
                            final_decision = excluded.final_decision,
                            agreement = excluded.agreement,
                            adjudication_needed = excluded.adjudication_needed
                        """,
                        (workflow_id, _ov.paper_id, _ov.decision),
                    )
                await _corr_db.commit()

                try:
                    import os as _os

                    from src.config.loader import load_configs as _load_cfgs
                    from src.db.repositories import WorkflowRepository as _WorkflowRepository

                    _refine_model: str | None = None
                    try:
                        _, _refine_settings = _load_cfgs(settings_path="config/settings.yaml")
                        _adjudicator_cfg = _refine_settings.agents.get("screening_adjudicator")
                        if _adjudicator_cfg:
                            _refine_model = _adjudicator_cfg.model
                    except Exception:
                        pass
                    if not _refine_model:
                        raise ValueError("screening_adjudicator model not resolved from settings.yaml")
                    learned = await refine_criteria_from_corrections(
                        corrections,
                        paper_titles,
                        model_name=_refine_model,
                        api_key=_os.environ.get("GEMINI_API_KEY", ""),
                        repository=_WorkflowRepository(_corr_db),
                        workflow_id=workflow_id,
                    )
                    if learned:
                        await save_learned_criteria(_corr_db, workflow_id, learned)
                except Exception as _rf_exc:
                    _logging.getLogger(__name__).warning("Criteria refinement failed (non-fatal): %s", _rf_exc)
        except Exception as _al_exc:
            import logging as _al_log

            _al_log.getLogger(__name__).warning("Active learning processing failed (non-fatal): %s", _al_exc)

    entry = await find_by_workflow_id_fallback(run_root, workflow_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Workflow not found in registry")

    await _update_status(run_root, workflow_id, "running")

    return {
        "status": "approved",
        "workflow_id": workflow_id,
        "overrides_processed": str(len(overrides)),
        "message": "Screening approved. Extraction will resume shortly.",
    }
