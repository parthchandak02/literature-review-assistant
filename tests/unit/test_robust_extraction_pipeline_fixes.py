from __future__ import annotations

import json

import pytest

from src.db.database import get_db
from src.db.repositories import CitationRepository, WorkflowRepository
from src.extraction.extractor import ExtractionService
from src.extraction.inference_utils import _is_substantive_finding, infer_country_from_text
from src.manuscript.contracts import run_manuscript_contracts
from src.models import (
    CandidatePaper,
    ExtractionRecord,
    GRADEOutcomeAssessment,
    ReviewConfig,
    ReviewType,
    SettingsConfig,
)
from src.models.enums import GRADECertainty, StudyDesign
from src.quality.grade import build_sof_table
from src.search.pdf_retrieval import _is_binary_garbage, _parse_pdf_bytes
from src.writing.evidence_assembler import ResultsEvidenceStudy, _study_result_sentence


class _ScriptedExtractionClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    async def complete(self, prompt: str, *, model: str, temperature: float, json_schema: dict | None = None) -> str:
        _ = (prompt, model, temperature, json_schema)
        return json.dumps(self._payload)


def _review() -> ReviewConfig:
    return ReviewConfig(
        research_question="How do registry systems change outcomes?",
        review_type=ReviewType.SYSTEMATIC,
        pico={
            "population": "children",
            "intervention": "digital registry",
            "comparison": "paper workflow",
            "outcome": "coverage and timeliness",
        },
        keywords=["digital registry"],
        domain="public health",
        scope="vaccination systems",
        inclusion_criteria=["primary studies"],
        exclusion_criteria=["commentaries"],
        date_range_start=2015,
        date_range_end=2026,
        target_databases=["openalex"],
    )


def _settings() -> SettingsConfig:
    return SettingsConfig(
        agents={
            "extraction": {"model": "google-gla:gemini-2.5-flash", "temperature": 0.1},
        }
    )


def test_binary_pdf_fallback_is_rejected() -> None:
    raw = b"%PDF-1.4\x00\x01 binary payload that is not real extracted prose"
    decoded = raw.decode("latin-1", errors="ignore")
    assert _is_binary_garbage(decoded) is True
    assert _parse_pdf_bytes(raw) == ""


def test_substantive_finding_heuristic_rejects_filler_and_accepts_real_result() -> None:
    assert (
        _is_substantive_finding("The provided text does not contain enough information to summarize the findings.")
        is False
    )
    assert _is_substantive_finding("Coverage increased from 61% to 84% across 240 participants.") is True


def test_infer_country_from_iso_alpha2_code() -> None:
    assert infer_country_from_text("Study setting: BZ") == "Belize"


@pytest.mark.asyncio
async def test_llm_extraction_synthesizes_summary_from_structured_outcomes(tmp_path) -> None:
    async with get_db(str(tmp_path / "outcome_fallback.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-outcome-fallback", "topic", "hash")
        paper = CandidatePaper(
            title="Belize registry effectiveness study",
            authors=["A Author"],
            source_database="pubmed",
            abstract="Registry effectiveness was evaluated across district clinics.",
        )
        await repo.save_paper(paper)
        extractor = ExtractionService(
            repository=repo,
            llm_client=_ScriptedExtractionClient(
                {
                    "study_duration": "12 months",
                    "setting": "district clinics",
                    "participant_count": "not reported",
                    "country": "BZ",
                    "participant_demographics": "children attending district clinics",
                    "intervention_description": "digital registry",
                    "comparator_description": "paper register",
                    "outcomes": [
                        {
                            "name": "Coverage",
                            "description": "vaccination coverage",
                            "effect_size": "RR=1.22",
                            "n": "240",
                        }
                    ],
                    "results_summary": "The provided text cannot summarize the findings from this excerpt.",
                    "funding_source": "not reported",
                    "conflicts_of_interest": "none declared",
                }
            ),
            settings=_settings(),
            review=_review(),
        )

        record = await extractor.extract(
            workflow_id="wf-outcome-fallback",
            paper=paper,
            study_design=StudyDesign.NON_RANDOMIZED,
            full_text="Coverage improved across district clinics after registry rollout.",
        )

        assert record.country == "Belize"
        assert record.results_summary["summary"].startswith("Reported outcomes:")
        assert "RR=1.22" in record.results_summary["summary"]
        assert "n=240" in record.results_summary["summary"]


def test_evidence_assembler_uses_generic_sentence_for_non_substantive_finding() -> None:
    sentence = _study_result_sentence(
        ResultsEvidenceStudy(
            title="Registry Study",
            study_design="non_randomized",
            participant_count=50,
            key_finding="The provided text does not contain enough information to summarize the findings.",
        )
    )
    assert "reported the following key finding" not in sentence
    assert "50 participants" in sentence


def test_build_sof_table_sanitizes_pipeline_jargon() -> None:
    assessment = GRADEOutcomeAssessment(
        outcome_name="Coverage",
        number_of_studies=2,
        study_designs="non_randomized",
        starting_certainty=GRADECertainty.LOW,
        risk_of_bias_downgrade=1,
        inconsistency_downgrade=0,
        indirectness_downgrade=0,
        imprecision_downgrade=0,
        publication_bias_downgrade=0,
        large_effect_upgrade=0,
        dose_response_upgrade=0,
        residual_confounding_upgrade=0,
        final_certainty=GRADECertainty.VERY_LOW,
        justification=(
            "RoB downgrade=1 (worst-case across 2 assessments). Computed from configured downgrade/upgrade factors."
        ),
    )
    table = build_sof_table([assessment])
    effect_summary = table.rows[0].effect_summary
    assert "downgrade=" not in effect_summary
    assert "configured downgrade" not in effect_summary
    assert "serious risk of bias" in effect_summary.lower()


@pytest.mark.asyncio
async def test_manuscript_contracts_catch_new_quality_failures(tmp_path) -> None:
    manuscript_path = tmp_path / "manuscript.md"
    manuscript_path.write_text(
        "\n".join(
            [
                "## Abstract",
                "",
                "**Background:** Background text.",
                "**Objectives:** Objective text.",
                "**Methods:** Methods text.",
                "**Results:** Results are presented in the synthesis section of the manuscript.",
                "**Conclusions:** Conclusions are discussed in the body of the review.",
                "",
                "## Introduction",
                "",
                "Intro text.",
                "",
                "## Methods",
                "",
                "Method text.",
                "",
                "## Results",
                "",
                "### Study Characteristics",
                "| Study (Year) | Country | Design | N | Key Finding |",
                "| --- | --- | --- | --- | --- |",
                "| Example (2024) | Belize | Non-randomized | 50 | The provided text does not contain enough information to summarize the findings. |",
                "",
                "## GRADE Summary of Findings",
                "",
                "| Outcome | N Studies | Study Design | Risk of Bias | Inconsistency | Indirectness | Imprecision | Other | Certainty | Effect / Reason |",
                "|---------|-----------|-------------|-------------|--------------|------------|------------|-------|-----------|----------------|",
                "| Coverage | 1 | non_randomized | serious | none | not assessed* | not serious | none | **LOW** | RoB downgrade=1 |",
                "",
                "## Quality Assessment",
                "",
                "| Domain | Note |",
                "| --- | --- |",
                "| CASP | Source text was corrupted and unreadable. |",
                "",
                "## Discussion",
                "",
                "Discussion text with enough words to remain substantive for the contract runner.",
                "",
                "## Conclusion",
                "",
                "Conclusion text with enough words to remain substantive for the contract runner.",
                "",
                "## Acknowledgments",
                "",
                "Thanks.",
                "",
                "## References",
                "",
                "[1] Example citation.",
            ]
        ),
        encoding="utf-8",
    )

    async with get_db(str(tmp_path / "contracts.db")) as db:
        repo = WorkflowRepository(db)
        citation_repo = CitationRepository(db)
        await repo.create_workflow("wf-contracts", "topic", "hash")
        paper = CandidatePaper(
            paper_id="paper-1",
            title="Belize registry study",
            authors=["A Author"],
            source_database="pubmed",
            abstract="Study abstract.",
        )
        await repo.save_paper(paper)
        await db.execute(
            """
            INSERT INTO study_cohort_membership (
                workflow_id, paper_id, screening_status, fulltext_status, synthesis_eligibility, source_phase
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("wf-contracts", paper.paper_id, "included", "retrieved", "included_primary", "extraction"),
        )
        await repo.save_extraction_record(
            "wf-contracts",
            ExtractionRecord(
                paper_id=paper.paper_id,
                study_design=StudyDesign.NON_RANDOMIZED,
                intervention_description="Digital registry",
                results_summary={
                    "summary": "The provided text does not contain enough information to summarize the findings."
                },
            ),
        )

        result = await run_manuscript_contracts(
            repository=repo,
            citation_repository=citation_repo,
            workflow_id="wf-contracts",
            manuscript_md_path=str(manuscript_path),
            manuscript_tex_path=None,
            mode="warning",
        )

    codes = {violation.code for violation in result.violations}
    assert "ABSTRACT_RESULTS_PLACEHOLDER" in codes
    assert "STUDY_TABLE_FILLER_LEAK" in codes
    assert "GRADE_TABLE_PIPELINE_JARGON" in codes
    assert "QUALITY_ASSESSMENT_CORRUPTED_INPUT" in codes
    assert "EXTRACTION_YIELD_LOW" in codes
