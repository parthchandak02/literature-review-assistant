from __future__ import annotations

import json

import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.llm.provider import LLMProvider
from src.models import (
    CandidatePaper,
    ExclusionReason,
    ReviewConfig,
    ReviewType,
    ScreeningDecisionType,
    SettingsConfig,
)
from src.screening.dual_screener import DualReviewerScreener, ScreeningLLMClient


class _ScriptedClient(ScreeningLLMClient):
    def __init__(self, responses: list[dict[str, object]]):
        self._responses = responses

    async def complete_json(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
    ) -> str:
        _ = (prompt, agent_name, model, temperature)
        payload = self._responses.pop(0)
        return json.dumps(payload)


def _review() -> ReviewConfig:
    return ReviewConfig(
        research_question="rq",
        review_type=ReviewType.SYSTEMATIC,
        pico={
            "population": "students",
            "intervention": "ai tutor",
            "comparison": "standard",
            "outcome": "learning",
        },
        keywords=["ai tutor"],
        domain="education",
        scope="health education",
        inclusion_criteria=["include if related"],
        exclusion_criteria=["exclude if unrelated"],
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
        }
    )


@pytest.mark.asyncio
async def test_dual_screener_adjudicates_disagreement(tmp_path) -> None:
    paper = CandidatePaper(title="A", authors=["X"], source_database="openalex", abstract="text")
    responses = [
        {"decision": "include", "confidence": 0.9, "reasoning": "A includes"},
        {"decision": "exclude", "confidence": 0.8, "reasoning": "B excludes", "exclusion_reason": "wrong_population"},
        {"decision": "include", "confidence": 0.7, "reasoning": "adjudicator include"},
    ]
    async with get_db(str(tmp_path / "screening.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-screen", "topic", "hash")
        provider = LLMProvider(_settings(), repo)
        screener = DualReviewerScreener(
            repository=repo,
            provider=provider,
            review=_review(),
            settings=_settings(),
            llm_client=_ScriptedClient(responses),
        )
        final = await screener.screen_title_abstract("wf-screen", paper)
        assert final.decision == ScreeningDecisionType.INCLUDE
        cursor = await db.execute("SELECT COUNT(*) FROM screening_decisions WHERE workflow_id = ?", ("wf-screen",))
        row = await cursor.fetchone()
        assert int(row[0]) == 3
        cursor = await db.execute(
            "SELECT agreement, final_decision, adjudication_needed FROM dual_screening_results WHERE workflow_id = ?",
            ("wf-screen",),
        )
        dual_row = await cursor.fetchone()
        assert int(dual_row[0]) == 0
        assert str(dual_row[1]) == "include"
        assert int(dual_row[2]) == 1


@pytest.mark.asyncio
async def test_fulltext_exclusion_requires_reason(tmp_path) -> None:
    paper = CandidatePaper(title="B", authors=["Y"], source_database="openalex", abstract="conference abstract")
    responses = [
        {"decision": "exclude", "confidence": 0.91, "reasoning": "exclude no reason"},
        {"decision": "exclude", "confidence": 0.92, "reasoning": "exclude no reason"},
    ]
    async with get_db(str(tmp_path / "screening_fulltext.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-fulltext", "topic", "hash")
        provider = LLMProvider(_settings(), repo)
        screener = DualReviewerScreener(
            repository=repo,
            provider=provider,
            review=_review(),
            settings=_settings(),
            llm_client=_ScriptedClient(responses),
        )
        final = await screener.screen_full_text("wf-fulltext", paper, "full text content")
        assert final.decision == ScreeningDecisionType.EXCLUDE
        assert final.exclusion_reason == ExclusionReason.OTHER
