from __future__ import annotations

import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.extraction.extractor import ExtractionService
from src.llm.provider import LLMProvider
from src.models import (
    CandidatePaper,
    ReviewConfig,
    ReviewType,
    SettingsConfig,
    StudyDesign,
)
from src.screening.dual_screener import DualReviewerScreener


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
            "quality_assessment": {"model": "google-gla:gemini-2.5-pro", "temperature": 0.1},
        }
    )


@pytest.mark.asyncio
async def test_extraction_pipeline_persists_typed_record(tmp_path) -> None:
    async with get_db(str(tmp_path / "extraction_pipeline.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-extract", "topic", "hash")
        paper = CandidatePaper(
            title="Randomized AI tutoring trial",
            authors=["A Author"],
            source_database="pubmed",
            abstract="Trial reporting positive learning outcomes.",
        )
        await repo.save_paper(paper)
        extractor = ExtractionService(repository=repo)

        record = await extractor.extract(
            workflow_id="wf-extract",
            paper=paper,
            study_design=StudyDesign.RCT,
            full_text="Methods and validated outcomes were reported for all participants.",
        )

        assert record.paper_id == paper.paper_id
        assert record.study_design == StudyDesign.RCT
        assert record.results_summary["source"] == "full_text"
        assert record.results_summary["summary"] != ""
        assert record.source_spans["title"] == paper.title

        cursor = await db.execute(
            "SELECT study_design, data FROM extraction_records WHERE workflow_id = ? AND paper_id = ?",
            ("wf-extract", paper.paper_id),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert str(row[0]) == StudyDesign.RCT.value
        assert "\"source\"" in str(row[1])


@pytest.mark.asyncio
async def test_fulltext_coverage_report_is_logged_and_written(tmp_path) -> None:
    async with get_db(str(tmp_path / "fulltext_coverage.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-coverage", "topic", "hash")
        provider = LLMProvider(_settings(), repo)
        screener = DualReviewerScreener(
            repository=repo,
            provider=provider,
            review=_review(),
            settings=_settings(),
        )
        papers = [
            CandidatePaper(title="Paper 1", authors=["A"], source_database="openalex", abstract="A"),
            CandidatePaper(title="Paper 2", authors=["B"], source_database="openalex", abstract="B"),
        ]
        report_path = tmp_path / "fulltext_retrieval_coverage.md"
        decisions = await screener.screen_batch(
            workflow_id="wf-coverage",
            stage="fulltext",
            papers=papers,
            full_text_by_paper={
                papers[0].paper_id: "Retrieved full text body.",
                papers[1].paper_id: "",
            },
            coverage_report_path=str(report_path),
        )

        assert len(decisions) == 2
        assert report_path.exists()
        report_body = report_path.read_text(encoding="utf-8")
        assert "Attempted: 2" in report_body
        assert "Succeeded: 1" in report_body
        assert "Failed: 1" in report_body

        cursor = await db.execute(
            "SELECT decision, rationale FROM decision_log WHERE decision_type = 'fulltext_retrieval_coverage'"
        )
        row = await cursor.fetchone()
        assert row is not None
        assert str(row[0]) == "partial"
        assert "attempted=2" in str(row[1])
