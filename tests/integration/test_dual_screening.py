from __future__ import annotations

import json

import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.llm.provider import LLMProvider
from src.models import CandidatePaper, ReviewConfig, ReviewType, SettingsConfig
from src.models.config import ScreeningConfig
from src.screening.dual_screener import DualReviewerScreener, ScreeningLLMClient
from src.screening.reliability import (
    compute_cohens_kappa,
    generate_disagreements_report,
    log_reliability_to_decision_log,
)


class _SequenceClient(ScreeningLLMClient):
    def __init__(self, responses: list[dict[str, object]]):
        self.responses = responses

    async def complete_json(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
    ) -> str:
        _ = (prompt, agent_name, model, temperature)
        return json.dumps(self.responses.pop(0))


def _review() -> ReviewConfig:
    return ReviewConfig(
        research_question="How do AI tutors impact outcomes?",
        review_type=ReviewType.SYSTEMATIC,
        pico={
            "population": "students",
            "intervention": "ai tutor",
            "comparison": "traditional",
            "outcome": "knowledge retention",
        },
        keywords=["ai tutor", "health education"],
        domain="education",
        scope="health science",
        inclusion_criteria=["related to ai tutoring"],
        exclusion_criteria=["not peer reviewed"],
        date_range_start=2015,
        date_range_end=2026,
        target_databases=["openalex"],
    )


def _settings() -> SettingsConfig:
    return SettingsConfig(
        agents={
            "screening_reviewer_a": {"model": "google-gla:gemini-2.5-flash-lite", "temperature": 0.1},
            "screening_reviewer_b": {"model": "google-gla:gemini-2.5-flash-lite", "temperature": 0.3},
            "screening_adjudicator": {"model": "google-gla:gemini-2.5-pro", "temperature": 0.2},
        },
        screening=ScreeningConfig(stage1_include_threshold=1.0, stage1_exclude_threshold=1.0),
    )


@pytest.mark.asyncio
async def test_dual_screening_pipeline_with_reliability(tmp_path) -> None:
    papers = [
        CandidatePaper(title="Paper 1", authors=["A"], source_database="openalex", abstract="A"),
        CandidatePaper(title="Paper 2", authors=["B"], source_database="openalex", abstract="B"),
    ]
    responses = [
        {"decision": "include", "confidence": 0.9, "reasoning": "keep"},
        {"decision": "include", "confidence": 0.85, "reasoning": "keep"},
        {"decision": "include", "confidence": 0.8, "reasoning": "keep"},
        {"decision": "exclude", "confidence": 0.8, "reasoning": "exclude", "exclusion_reason": "wrong_population"},
        {"decision": "include", "confidence": 0.7, "reasoning": "adjudicate include"},
    ]
    async with get_db(str(tmp_path / "dual_integration.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-int", "topic", "hash")
        provider = LLMProvider(_settings(), repo)
        screener = DualReviewerScreener(
            repository=repo,
            provider=provider,
            review=_review(),
            settings=_settings(),
            llm_client=_SequenceClient(responses),
        )
        finals = await screener.screen_batch("wf-int", "title_abstract", papers)
        assert len(finals) == 2

        cursor = await db.execute("SELECT COUNT(*) FROM dual_screening_results WHERE workflow_id = ?", ("wf-int",))
        dual_count = await cursor.fetchone()
        assert int(dual_count[0]) == 2

        cursor = await db.execute("SELECT paper_id, reviewer_type, decision, confidence FROM screening_decisions WHERE workflow_id = ?", ("wf-int",))
        rows = await cursor.fetchall()
        by_paper: dict[str, list[tuple[str, str, float]]] = {}
        for row in rows:
            by_paper.setdefault(str(row[0]), []).append((str(row[1]), str(row[2]), float(row[3])))
        assert len(by_paper[papers[0].paper_id]) == 2
        assert len(by_paper[papers[1].paper_id]) == 3

        # Build typed results from persisted decisions to validate kappa/reporting end-to-end.
        from src.models import ReviewerType, ScreeningDecision, ScreeningDecisionType
        from src.models.screening import DualScreeningResult

        typed_results: list[DualScreeningResult] = []
        for paper in papers:
            entries = by_paper[paper.paper_id]
            reviewer_a = next(item for item in entries if item[0] == ReviewerType.REVIEWER_A.value)
            reviewer_b = next(item for item in entries if item[0] == ReviewerType.REVIEWER_B.value)
            final = finals[0] if finals[0].paper_id == paper.paper_id else finals[1]
            typed_results.append(
                DualScreeningResult(
                    paper_id=paper.paper_id,
                    reviewer_a=ScreeningDecision(
                        paper_id=paper.paper_id,
                        decision=ScreeningDecisionType(reviewer_a[1]),
                        reviewer_type=ReviewerType.REVIEWER_A,
                        confidence=reviewer_a[2],
                    ),
                    reviewer_b=ScreeningDecision(
                        paper_id=paper.paper_id,
                        decision=ScreeningDecisionType(reviewer_b[1]),
                        reviewer_type=ReviewerType.REVIEWER_B,
                        confidence=reviewer_b[2],
                    ),
                    agreement=reviewer_a[1] == reviewer_b[1],
                    final_decision=final.decision,
                )
            )

        reliability = compute_cohens_kappa(typed_results, stage="title_abstract")
        await log_reliability_to_decision_log(repo, reliability)
        report_path = generate_disagreements_report(
            str(tmp_path / "disagreements_report.md"),
            typed_results,
            stage="title_abstract",
        )
        assert report_path.exists()
