from __future__ import annotations

import json

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


class _ScriptedExtractionClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    async def complete(self, prompt: str, *, model: str, temperature: float, json_schema: dict | None = None) -> str:
        _ = (prompt, model, temperature, json_schema)
        return json.dumps(self._payload)


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
            "extraction": {"model": "google-gla:gemini-2.5-flash", "temperature": 0.1},
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
        assert record.results_summary["source"] == "heuristic"
        assert record.results_summary["summary"] != ""
        assert record.source_spans["title"] == paper.title

        cursor = await db.execute(
            "SELECT study_design, primary_study_status, data FROM extraction_records WHERE workflow_id = ? AND paper_id = ?",
            ("wf-extract", paper.paper_id),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert str(row[0]) == StudyDesign.RCT.value
        assert str(row[1]) == "primary"
        assert '"source"' in str(row[2])


@pytest.mark.asyncio
async def test_llm_extraction_salvages_participant_count_from_demographics(tmp_path) -> None:
    async with get_db(str(tmp_path / "extraction_salvage.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-extract-salvage", "topic", "hash")
        paper = CandidatePaper(
            title="Kenya digital registry usability study",
            authors=["A Author"],
            source_database="pubmed",
            abstract="The study interviewed 19 health care workers across 12 facilities.",
        )
        await repo.save_paper(paper)
        extractor = ExtractionService(
            repository=repo,
            llm_client=_ScriptedExtractionClient(
                {
                    "study_duration": "6 months",
                    "setting": "rural facilities",
                    "participant_count": "not reported",
                    "country": "Kenya",
                    "participant_demographics": "19 health care workers across 12 facilities",
                    "intervention_description": "tablet registry",
                    "comparator_description": "paper workflow",
                    "outcomes": [{"name": "usability", "description": "workflow usability"}],
                    "results_summary": "The study involved 19 health care workers and reported improved usability.",
                    "funding_source": "not reported",
                    "conflicts_of_interest": "none declared",
                }
            ),
            settings=_settings(),
            review=_review(),
        )

        record = await extractor.extract(
            workflow_id="wf-extract-salvage",
            paper=paper,
            study_design=StudyDesign.QUALITATIVE,
            full_text="Methods: We interviewed 19 health care workers across 12 facilities.",
        )

        assert record.participant_count == 19
        assert record.results_summary["source"] == "llm"


@pytest.mark.asyncio
async def test_llm_extraction_replaces_placeholder_summary_with_abstract(tmp_path) -> None:
    async with get_db(str(tmp_path / "extraction_summary_fallback.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-extract-summary", "topic", "hash")
        paper = CandidatePaper(
            title="Vietnam digital registry readiness study",
            authors=["A Author"],
            source_database="pubmed",
            abstract=(
                "This readiness assessment found that the digital immunization registry reduced planning time "
                "and improved reporting accuracy across participating facilities."
            ),
        )
        await repo.save_paper(paper)
        extractor = ExtractionService(
            repository=repo,
            llm_client=_ScriptedExtractionClient(
                {
                    "study_duration": "12 months",
                    "setting": "provincial immunization facilities",
                    "participant_count": "not reported",
                    "country": "Vietnam",
                    "participant_demographics": "health facility staff",
                    "intervention_description": "digital immunization registry",
                    "comparator_description": "paper workflow",
                    "outcomes": [{"name": "readiness", "description": "transition readiness"}],
                    "results_summary": "not reported in the provided text",
                    "funding_source": "not reported",
                    "conflicts_of_interest": "none declared",
                }
            ),
            settings=_settings(),
            review=_review(),
        )

        record = await extractor.extract(
            workflow_id="wf-extract-summary",
            paper=paper,
            study_design=StudyDesign.MIXED_METHODS,
            full_text="Journal header text that does not contain a usable findings summary.",
        )

        assert "reduced planning time" in record.results_summary["summary"]
        assert record.results_summary["source"] == "llm"


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
