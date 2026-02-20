from __future__ import annotations

import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.extraction.study_classifier import (
    StudyClassificationLLMClient,
    StudyClassifier,
)
from src.llm.provider import LLMProvider
from src.models import (
    CandidatePaper,
    ReviewConfig,
    ReviewType,
    SettingsConfig,
    StudyDesign,
)


class _StubLLMClient(StudyClassificationLLMClient):
    def __init__(self, response: str):
        self.response = response

    async def complete_json(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
    ) -> str:
        _ = (prompt, agent_name, model, temperature)
        return self.response


def _review() -> ReviewConfig:
    return ReviewConfig(
        research_question="How do AI tutors impact learning outcomes?",
        review_type=ReviewType.SYSTEMATIC,
        pico={
            "population": "students",
            "intervention": "ai tutor",
            "comparison": "traditional",
            "outcome": "learning outcomes",
        },
        keywords=["ai tutor", "health education"],
        domain="education",
        scope="health sciences",
        inclusion_criteria=["related to ai tutoring"],
        exclusion_criteria=["not peer reviewed"],
        date_range_start=2015,
        date_range_end=2026,
        target_databases=["openalex"],
    )


def _settings() -> SettingsConfig:
    return SettingsConfig(
        agents={
            "quality_assessment": {
                "model": "google-gla:gemini-2.5-pro",
                "temperature": 0.1,
            }
        }
    )


@pytest.mark.asyncio
async def test_high_confidence_keeps_predicted_design(tmp_path) -> None:
    async with get_db(str(tmp_path / "classifier_high.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf1", "topic", "hash")
        provider = LLMProvider(_settings(), repo)
        classifier = StudyClassifier(
            provider=provider,
            repository=repo,
            review=_review(),
            llm_client=_StubLLMClient(
                '{"study_design":"rct","confidence":0.92,"reasoning":"Randomized trial methods."}'
            ),
            low_confidence_threshold=0.70,
        )
        paper = CandidatePaper(title="Randomized AI tutor trial", authors=["A"], source_database="openalex")
        design = await classifier.classify("wf1", paper)
        assert design == StudyDesign.RCT


@pytest.mark.asyncio
async def test_low_confidence_falls_back_to_non_randomized(tmp_path) -> None:
    async with get_db(str(tmp_path / "classifier_low.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf2", "topic", "hash")
        provider = LLMProvider(_settings(), repo)
        classifier = StudyClassifier(
            provider=provider,
            repository=repo,
            review=_review(),
            llm_client=_StubLLMClient(
                '{"study_design":"qualitative","confidence":0.55,"reasoning":"Weak signal."}'
            ),
            low_confidence_threshold=0.70,
        )
        paper = CandidatePaper(title="Interview-based AI tutor study", authors=["B"], source_database="pubmed")
        design = await classifier.classify("wf2", paper)
        assert design == StudyDesign.NON_RANDOMIZED


@pytest.mark.asyncio
async def test_malformed_output_falls_back_and_logs_decision(tmp_path) -> None:
    async with get_db(str(tmp_path / "classifier_malformed.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf3", "topic", "hash")
        provider = LLMProvider(_settings(), repo)
        classifier = StudyClassifier(
            provider=provider,
            repository=repo,
            review=_review(),
            llm_client=_StubLLMClient("NOT_JSON"),
            low_confidence_threshold=0.70,
        )
        paper = CandidatePaper(title="Observational tutoring analysis", authors=["C"], source_database="crossref")
        design = await classifier.classify("wf3", paper)
        assert design == StudyDesign.NON_RANDOMIZED

        cursor = await db.execute(
            "SELECT decision, rationale FROM decision_log WHERE decision_type='study_design_classification'"
        )
        row = await cursor.fetchone()
        assert row is not None
        assert str(row[0]) == StudyDesign.NON_RANDOMIZED.value
        assert "predicted=parse_error" in str(row[1])
