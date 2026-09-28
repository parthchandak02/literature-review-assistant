"""Human-in-the-loop screening review endpoints."""

from __future__ import annotations

import json
import pathlib

import aiosqlite
from fastapi import APIRouter, HTTPException

from src.models.papers import decode_html_entities
from src.web.run_resolver import resolve_registry_entry, resolve_runtime_db
from src.web.shared import ApproveScreeningRequest, ResumeRequest
from src.web.state import _lifecycle_coordinator, _resume_wrapper

router = APIRouter(tags=["screening_review"])

_OVERRIDE_DECISIONS = frozenset({"include", "exclude", "uncertain"})


_FINAL_DECISION_SQL = """
WITH stages AS (
    SELECT paper_id, stage FROM dual_screening_results
    WHERE workflow_id = :wf AND stage IN ('title_abstract', 'fulltext')
    UNION
    SELECT paper_id, stage FROM screening_decisions
    WHERE workflow_id = :wf AND stage IN ('title_abstract', 'fulltext')
),
final_stage AS (
    SELECT paper_id,
           CASE WHEN MAX(stage = 'fulltext') = 1 THEN 'fulltext' ELSE 'title_abstract' END AS stage
    FROM stages
    GROUP BY paper_id
),
decision_ranked AS (
    SELECT paper_id, stage, decision, reason, exclusion_reason, confidence, reviewer_type,
           ROW_NUMBER() OVER (
               PARTITION BY paper_id, stage
               ORDER BY CASE reviewer_type
                            WHEN 'human_override' THEN 0
                            WHEN 'adjudicator' THEN 1
                            WHEN 'reviewer_a' THEN 2
                            WHEN 'reviewer_b' THEN 3
                            ELSE 4
                        END,
                        datetime(created_at) DESC, id DESC
           ) AS rn
    FROM screening_decisions
    WHERE workflow_id = :wf
)
SELECT
    p.paper_id, p.title, p.authors, p.year, p.source_database, p.doi, p.abstract,
    f.stage,
    COALESCE(d.final_decision, sd.decision) AS final_decision,
    sd.reason, sd.confidence, sd.exclusion_reason, sd.reviewer_type
FROM final_stage f
JOIN papers p ON p.paper_id = f.paper_id
LEFT JOIN dual_screening_results d
    ON d.workflow_id = :wf AND d.paper_id = f.paper_id AND d.stage = f.stage
LEFT JOIN decision_ranked sd ON sd.paper_id = f.paper_id AND sd.stage = f.stage AND sd.rn = 1
"""

_DECISION_ORDER = {"include": 0, "uncertain": 1, "exclude": 2}


def _normalize_final_decision(value: str | None) -> str:
    decision = str(value or "").strip().lower()
    if decision in ("include", "uncertain", "exclude"):
        return decision
    return "exclude"


async def _screening_thresholds(db: aiosqlite.Connection, workflow_id: str) -> dict | None:
    """Calibrated thresholds from the run's calibration event, else configured settings, else None."""
    try:
        cursor = await db.execute(
            """
            SELECT payload FROM event_log
            WHERE workflow_id = ? AND event_type = 'screening_calibration'
            ORDER BY ts DESC LIMIT 1
            """,
            (workflow_id,),
        )
        row = await cursor.fetchone()
        if row:
            payload = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            include = payload.get("include_threshold")
            exclude = payload.get("exclude_threshold")
            if include is not None and exclude is not None:
                return {"include": float(include), "exclude": float(exclude), "source": "calibration"}
    except Exception:
        pass
    try:
        from src.config.loader import load_configs

        _, settings = load_configs(settings_path="config/settings.yaml")
        return {
            "include": float(settings.screening.stage1_include_threshold),
            "exclude": float(settings.screening.stage1_exclude_threshold),
            "source": "settings",
        }
    except Exception:
        return None


@router.get("/api/run/{run_id}/screening-summary")
async def get_screening_summary(run_id: str) -> dict:
    """Return every screened paper with its final decision (AI or human) for review."""
    db_path = await resolve_runtime_db(run_id)
    if not pathlib.Path(db_path).exists():
        raise HTTPException(status_code=404, detail="Run database not found")

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT workflow_id FROM workflows LIMIT 1") as wf_cur:
            wf_row = await wf_cur.fetchone()
        workflow_id = str(wf_row[0]) if wf_row else ""
        cursor = await db.execute(_FINAL_DECISION_SQL, {"wf": workflow_id})
        rows = await cursor.fetchall()
        thresholds = await _screening_thresholds(db, workflow_id)

    papers = []
    for row in rows:
        final_decision = _normalize_final_decision(row["final_decision"])
        papers.append(
            {
                "paper_id": row["paper_id"],
                "title": decode_html_entities(row["title"] or ""),
                "authors": decode_html_entities(row["authors"] or ""),
                "year": row["year"],
                "source_database": row["source_database"],
                "doi": row["doi"],
                "abstract": decode_html_entities(row["abstract"]) if row["abstract"] else row["abstract"],
                "stage": row["stage"],
                "decision": final_decision,
                "final_decision": final_decision,
                "reason": row["reason"],
                "confidence": row["confidence"],
                "exclusion_reason": row["exclusion_reason"],
                "decided_by": row["reviewer_type"],
            }
        )
    papers.sort(key=lambda p: (_DECISION_ORDER[p["final_decision"]], -(p["year"] or 0), p["paper_id"]))

    return {
        "run_id": run_id,
        "total": len(papers),
        "papers": papers,
        "thresholds": thresholds,
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
    db_path = await resolve_runtime_db(run_id)
    if not pathlib.Path(db_path).exists():
        raise HTTPException(status_code=404, detail="Run database not found")

    from src.db.workflow_registry import run_root_from_db_path
    from src.db.workflow_registry import update_status as _update_status

    async with aiosqlite.connect(db_path) as _raw_db:
        cursor = await _raw_db.execute("SELECT workflow_id FROM workflows LIMIT 1")
        row = await cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="No workflow found in run database")

    workflow_id = row[0]
    run_root = run_root_from_db_path(db_path)

    overrides = (body.overrides if body else []) or []
    invalid = sorted({o.decision for o in overrides if o.decision not in _OVERRIDE_DECISIONS})
    if invalid:
        raise HTTPException(status_code=422, detail=f"Unsupported override decision(s): {', '.join(invalid)}")
    if overrides:
        from src.db.database import get_db as _get_run_db
        from src.db.repositories import WorkflowRepository as _OverrideRepository
        from src.screening.criteria_refinement import ScreeningCorrection, save_corrections

        async with _get_run_db(db_path) as _ov_db:
            _ov_repo = _OverrideRepository(_ov_db)
            corrections = [
                ScreeningCorrection(
                    paper_id=o.paper_id,
                    ai_decision=await _ov_repo.get_latest_ai_decision(workflow_id, o.paper_id) or "unknown",
                    human_decision=o.decision,
                    human_reason=o.reason,
                )
                for o in overrides
            ]
            await _ov_repo.apply_human_overrides(workflow_id, [(o.paper_id, o.decision, o.reason) for o in overrides])
            await _ov_db.commit()
            await save_corrections(_ov_db, workflow_id, corrections)

        try:
            import logging as _logging

            from src.screening.criteria_refinement import refine_criteria_from_corrections, save_learned_criteria

            async with _get_run_db(db_path) as _corr_db:
                paper_titles: dict[str, str] = {}
                async with _corr_db.execute(
                    "SELECT paper_id, title FROM papers WHERE paper_id IN ({})".format(
                        ",".join("?" * len(corrections))
                    ),
                    [c.paper_id for c in corrections],
                ) as _t_cur:
                    async for _t_row in _t_cur:
                        paper_titles[_t_row[0]] = _t_row[1] or ""

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

    entry = await resolve_registry_entry(workflow_id, run_root)

    active = _lifecycle_coordinator.find_active_by_workflow(workflow_id)
    if active is not None:
        await _update_status(run_root, workflow_id, "running")
        return {
            "status": "approved",
            "workflow_id": workflow_id,
            "overrides_processed": str(len(overrides)),
            "message": "Screening approved. Extraction will resume shortly.",
        }

    topic = entry.topic or "Untitled review"
    req = ResumeRequest(
        workflow_id=workflow_id,
        db_path=db_path,
        topic=topic,
    )
    await _lifecycle_coordinator.start_resume(req, resume_wrapper=_resume_wrapper)
    return {
        "status": "approved",
        "workflow_id": workflow_id,
        "overrides_processed": str(len(overrides)),
        "message": "Screening approved. Workflow resume started.",
    }
