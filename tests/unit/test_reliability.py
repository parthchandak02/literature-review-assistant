from __future__ import annotations

import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.models import ReviewerType, ScreeningDecision, ScreeningDecisionType
from src.models.screening import DualScreeningResult
from src.screening.reliability import (
    compute_cohens_kappa,
    generate_disagreements_report,
    log_reliability_to_decision_log,
)


def _result(paper_id: str, a: ScreeningDecisionType, b: ScreeningDecisionType, final: ScreeningDecisionType) -> DualScreeningResult:
    return DualScreeningResult(
        paper_id=paper_id,
        reviewer_a=ScreeningDecision(
            paper_id=paper_id,
            decision=a,
            reviewer_type=ReviewerType.REVIEWER_A,
            confidence=0.9,
        ),
        reviewer_b=ScreeningDecision(
            paper_id=paper_id,
            decision=b,
            reviewer_type=ReviewerType.REVIEWER_B,
            confidence=0.8,
        ),
        agreement=a == b,
        final_decision=final,
    )


def test_compute_cohens_kappa_and_report(tmp_path) -> None:
    results = [
        _result("p1", ScreeningDecisionType.INCLUDE, ScreeningDecisionType.INCLUDE, ScreeningDecisionType.INCLUDE),
        _result("p2", ScreeningDecisionType.EXCLUDE, ScreeningDecisionType.INCLUDE, ScreeningDecisionType.EXCLUDE),
        _result("p3", ScreeningDecisionType.EXCLUDE, ScreeningDecisionType.EXCLUDE, ScreeningDecisionType.EXCLUDE),
    ]
    reliability = compute_cohens_kappa(results, stage="title_abstract")
    assert reliability.total_screened == 3
    assert reliability.total_disagreements == 1
    report = generate_disagreements_report(str(tmp_path / "disagreements_report.md"), results, "title_abstract")
    text = report.read_text(encoding="utf-8")
    assert "Disagreements Report" in text
    assert "Paper p2" in text


@pytest.mark.asyncio
async def test_log_reliability_to_decision_log(tmp_path) -> None:
    results = [_result("p1", ScreeningDecisionType.INCLUDE, ScreeningDecisionType.EXCLUDE, ScreeningDecisionType.INCLUDE)]
    reliability = compute_cohens_kappa(results, stage="title_abstract")
    async with get_db(str(tmp_path / "reliability.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-rel", "topic", "hash")
        await log_reliability_to_decision_log(repo, reliability)
        cursor = await db.execute(
            "SELECT COUNT(*) FROM decision_log WHERE decision_type = 'inter_rater_reliability'",
        )
        row = await cursor.fetchone()
        assert int(row[0]) == 1
