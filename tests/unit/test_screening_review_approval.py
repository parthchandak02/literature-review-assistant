"""Screening review summary and approval: cohort carry-forward, idempotency, final decisions."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.models.papers import CandidatePaper
from src.web.routers import screening_review
from src.web.shared import ApproveScreeningRequest, ScreeningOverride

_WF = "wf-hitl"


async def _seed(db_path: Path, *, with_fulltext: bool = False) -> None:
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            (_WF, "Topic", "hash", "awaiting_review"),
        )
        repo = WorkflowRepository(db)
        for pid in ("p1", "p2", "p3", "p4"):
            await repo.save_paper(
                CandidatePaper(paper_id=pid, title=f"Paper {pid}", authors=["A"], source_database="crossref")
            )
        ta = {"p1": "include", "p2": "uncertain", "p3": "include", "p4": "exclude"}
        for pid, decision in ta.items():
            await db.execute(
                "INSERT INTO screening_decisions (workflow_id, paper_id, stage, decision, reason, exclusion_reason,"
                " reviewer_type, confidence) VALUES (?, ?, 'title_abstract', ?, 'ai reason', ?, 'reviewer_a', 0.9)",
                (_WF, pid, decision, "wrong_population" if decision == "exclude" else None),
            )
            await db.execute(
                "INSERT INTO dual_screening_results (workflow_id, paper_id, stage, agreement, final_decision,"
                " adjudication_needed) VALUES (?, ?, 'title_abstract', 1, ?, 0)",
                (_WF, pid, decision),
            )
        if with_fulltext:
            for pid, decision in {"p1": "include", "p2": "exclude", "p3": "include"}.items():
                await db.execute(
                    "INSERT INTO screening_decisions (workflow_id, paper_id, stage, decision, reason,"
                    " exclusion_reason, reviewer_type, confidence)"
                    " VALUES (?, ?, 'fulltext', ?, 'ft reason', ?, 'adjudicator', 0.8)",
                    (_WF, pid, decision, "wrong_outcome" if decision == "exclude" else None),
                )
                await db.execute(
                    "INSERT INTO dual_screening_results (workflow_id, paper_id, stage, agreement, final_decision,"
                    " adjudication_needed) VALUES (?, ?, 'fulltext', 1, ?, 0)",
                    (_WF, pid, decision),
                )
        await db.commit()


@pytest.fixture()
def patched_router(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    db_path = tmp_path / "runtime.db"

    async def _resolve(_run_id: str, *_a, **_k) -> str:
        return str(db_path)

    async def _registry(*_a, **_k):
        return SimpleNamespace(topic="Topic")

    async def _no_refine(*_a, **_k):
        return []

    async def _start_resume(*_a, **_k):
        return None

    async def _update_status(*_a, **_k):
        return None

    monkeypatch.setattr(screening_review, "resolve_runtime_db", _resolve)
    monkeypatch.setattr(screening_review, "resolve_registry_entry", _registry)
    monkeypatch.setattr("src.screening.criteria_refinement.refine_criteria_from_corrections", _no_refine)
    monkeypatch.setattr("src.db.workflow_registry.update_status", _update_status)
    monkeypatch.setattr(screening_review._lifecycle_coordinator, "find_active_by_workflow", lambda _wf: None)
    monkeypatch.setattr(screening_review._lifecycle_coordinator, "start_resume", _start_resume)
    return db_path


async def _resume_cohort(db_path: Path) -> set[str]:
    """Mirror the cohort resolution in src/orchestration/resume.py and hitl_runner.py."""
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        ids = await repo.get_included_paper_ids(_WF)
        if not ids:
            ids = await repo.get_title_abstract_include_ids(_WF)
        return ids


def _body(*pairs: tuple[str, str]) -> ApproveScreeningRequest:
    return ApproveScreeningRequest(overrides=[ScreeningOverride(paper_id=p, decision=d) for p, d in pairs])


@pytest.mark.asyncio
async def test_approval_without_fulltext_keeps_whole_cohort(patched_router: Path) -> None:
    await _seed(patched_router)
    await screening_review.approve_screening("run1", _body(("p3", "exclude"), ("p4", "include")))
    assert await _resume_cohort(patched_router) == {"p1", "p2", "p4"}


@pytest.mark.asyncio
async def test_approval_with_fulltext_applies_overrides_on_fulltext(patched_router: Path) -> None:
    await _seed(patched_router, with_fulltext=True)
    await screening_review.approve_screening("run1", _body(("p2", "include"), ("p3", "exclude")))
    assert await _resume_cohort(patched_router) == {"p1", "p2"}


@pytest.mark.asyncio
async def test_repeated_approval_is_idempotent(patched_router: Path) -> None:
    await _seed(patched_router)
    body = _body(("p3", "exclude"), ("p4", "include"))
    await screening_review.approve_screening("run1", body)
    await screening_review.approve_screening("run1", body)
    async with get_db(str(patched_router)) as db:
        cur = await db.execute(
            "SELECT paper_id, COUNT(*) FROM screening_decisions"
            " WHERE workflow_id = ? AND reviewer_type = 'human_override' GROUP BY paper_id",
            (_WF,),
        )
        counts = dict(await cur.fetchall())
        cur = await db.execute("SELECT COUNT(*) FROM screening_corrections WHERE workflow_id = ?", (_WF,))
        corrections = (await cur.fetchone())[0]
        cur = await db.execute(
            "SELECT ai_decision FROM screening_corrections WHERE workflow_id = ? AND paper_id = 'p3'", (_WF,)
        )
        ai_decision = (await cur.fetchone())[0]
    assert counts == {"p3": 1, "p4": 1}
    assert corrections == 2
    assert ai_decision == "include"
    assert await _resume_cohort(patched_router) == {"p1", "p2", "p4"}


@pytest.mark.asyncio
async def test_summary_returns_one_final_decision_per_paper(patched_router: Path) -> None:
    await _seed(patched_router, with_fulltext=True)
    result = await screening_review.get_screening_summary("run1")
    by_id = {p["paper_id"]: p for p in result["papers"]}
    assert result["total"] == 4 == len(by_id)
    assert by_id["p1"]["final_decision"] == "include" and by_id["p1"]["stage"] == "fulltext"
    assert by_id["p2"]["final_decision"] == "exclude"
    assert by_id["p2"]["exclusion_reason"] == "wrong_outcome"
    assert by_id["p4"]["final_decision"] == "exclude" and by_id["p4"]["stage"] == "title_abstract"
    assert by_id["p4"]["exclusion_reason"] == "wrong_population"
    assert by_id["p1"]["decision"] == by_id["p1"]["final_decision"]
    assert by_id["p1"]["decided_by"] == "adjudicator"
    legacy = {"title", "authors", "year", "source_database", "doi", "abstract", "reason", "confidence"}
    assert legacy <= set(by_id["p1"])
    assert [p["final_decision"] for p in result["papers"]] == ["include", "include", "exclude", "exclude"]


@pytest.mark.asyncio
async def test_summary_reflects_human_override(patched_router: Path) -> None:
    await _seed(patched_router)
    await screening_review.approve_screening("run1", _body(("p4", "include")))
    result = await screening_review.get_screening_summary("run1")
    p4 = next(p for p in result["papers"] if p["paper_id"] == "p4")
    assert p4["final_decision"] == "include"
    assert p4["decided_by"] == "human_override"


@pytest.mark.asyncio
async def test_summary_thresholds_prefer_calibration_record(patched_router: Path) -> None:
    await _seed(patched_router)
    async with get_db(str(patched_router)) as db:
        await db.execute(
            "INSERT INTO event_log (workflow_id, event_type, payload, ts) VALUES (?, 'screening_calibration', ?, ?)",
            (_WF, '{"type": "screening_calibration", "include_threshold": 0.8, "exclude_threshold": 0.75}', "t"),
        )
        await db.commit()
    result = await screening_review.get_screening_summary("run1")
    assert result["thresholds"] == {"include": 0.8, "exclude": 0.75, "source": "calibration"}


@pytest.mark.asyncio
async def test_summary_thresholds_fall_back_to_settings(patched_router: Path) -> None:
    await _seed(patched_router)
    result = await screening_review.get_screening_summary("run1")
    assert result["thresholds"]["source"] == "settings"
    assert 0.0 <= result["thresholds"]["exclude"] <= result["thresholds"]["include"] <= 1.0


@pytest.mark.asyncio
async def test_approval_rejects_unknown_override_decision(patched_router: Path) -> None:
    from fastapi import HTTPException

    await _seed(patched_router)
    with pytest.raises(HTTPException) as exc:
        await screening_review.approve_screening("run1", _body(("p1", "maybe")))
    assert exc.value.status_code == 422
