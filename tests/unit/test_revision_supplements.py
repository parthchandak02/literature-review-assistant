"""Unit tests for revision supplementary CSV exports."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.export.revision_supplements import export_revision_supplements
from src.models import CandidatePaper, ScreeningDecision
from src.models.enums import (
    ExclusionReason,
    GRADECertainty,
    ReviewerType,
    RiskOfBiasJudgment,
    RobinsIJudgment,
    ScreeningDecisionType,
    StudyDesign,
)
from src.models.extraction import ExtractionRecord, OutcomeRecord
from src.models.quality import RoB2Assessment, RobinsIAssessment
from src.quality.grade import GradeAssessor


@pytest.mark.asyncio
async def test_export_revision_supplements_writes_expected_csvs(tmp_path: Path) -> None:
    workflow_id = "wf-revision-supp"
    db_path = tmp_path / "runtime.db"
    supp_dir = tmp_path / "supplementary"

    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow(workflow_id, "Statin therapy review", "hash")

        paper = CandidatePaper(
            title="RCT on statins",
            authors=["Alice Smith"],
            year=2024,
            source_database="pubmed",
            doi="10.1000/example",
            url="https://example.com/paper",
            journal="Example Journal",
            abstract="Abstract text here.",
        )
        unretrieved = CandidatePaper(
            title="Unavailable full text",
            authors=["Bob Jones"],
            year=2023,
            source_database="openalex",
            doi="10.1000/missing",
            url="https://example.com/missing",
            journal="Other Journal",
            abstract="Could not retrieve PDF.",
        )
        nrs_paper = CandidatePaper(
            title="Cohort on statins",
            authors=["Carol Lee"],
            year=2022,
            source_database="crossref",
            doi="10.1000/cohort",
            url="https://example.com/cohort",
            journal="Cohort Journal",
            abstract="Cohort abstract.",
        )
        await repo.save_paper(paper)
        await repo.save_paper(nrs_paper)
        await repo.save_paper(unretrieved)

        record = ExtractionRecord(
            paper_id=paper.paper_id,
            study_design=StudyDesign.RCT,
            intervention_description="Statin intervention",
            outcomes=[
                OutcomeRecord(
                    name="ldl_reduction",
                    description="Change in LDL-C",
                    effect_size="-0.42",
                    n="120",
                    p_value="0.01",
                ),
                OutcomeRecord(name="mortality", description="All-cause mortality"),
            ],
        )
        await repo.save_extraction_record(workflow_id, record)

        await repo.save_rob2_assessment(
            workflow_id,
            RoB2Assessment(
                paper_id=paper.paper_id,
                domain_1_randomization=RiskOfBiasJudgment.LOW,
                domain_1_rationale="Adequate randomization.",
                domain_2_deviations=RiskOfBiasJudgment.SOME_CONCERNS,
                domain_2_rationale="Some deviations.",
                domain_3_missing_data=RiskOfBiasJudgment.LOW,
                domain_3_rationale="Complete data.",
                domain_4_measurement=RiskOfBiasJudgment.LOW,
                domain_4_rationale="Blinded outcomes.",
                domain_5_selection=RiskOfBiasJudgment.LOW,
                domain_5_rationale="Registered protocol.",
                overall_judgment=RiskOfBiasJudgment.SOME_CONCERNS,
                overall_rationale="Overall some concerns.",
            ),
        )
        await repo.save_robins_i_assessment(
            workflow_id,
            RobinsIAssessment(
                paper_id=nrs_paper.paper_id,
                domain_1_confounding=RobinsIJudgment.MODERATE,
                domain_1_rationale="Residual confounding possible.",
                domain_2_selection=RobinsIJudgment.LOW,
                domain_2_rationale="Representative cohort.",
                domain_3_classification=RobinsIJudgment.LOW,
                domain_3_rationale="Clear groups.",
                domain_4_deviations=RobinsIJudgment.SERIOUS,
                domain_4_rationale="Protocol deviations.",
                domain_5_missing_data=RobinsIJudgment.LOW,
                domain_5_rationale="Low attrition.",
                domain_6_measurement=RobinsIJudgment.LOW,
                domain_6_rationale="Validated measures.",
                domain_7_reported_result=RobinsIJudgment.LOW,
                domain_7_rationale="Pre-specified outcomes.",
                overall_judgment=RobinsIJudgment.MODERATE,
                overall_rationale="Moderate overall risk.",
            ),
        )

        grade = GradeAssessor()
        grade_row = grade.assess_outcome(
            outcome_name="ldl_reduction",
            number_of_studies=1,
            study_design=StudyDesign.RCT,
            risk_of_bias_downgrade=1,
        )
        await repo.save_grade_assessment(workflow_id, grade_row)

        await repo.save_screening_decision(
            workflow_id,
            "fulltext",
            ScreeningDecision(
                paper_id=unretrieved.paper_id,
                decision=ScreeningDecisionType.EXCLUDE,
                reason="Full text not retrievable.",
                exclusion_reason=ExclusionReason.NO_FULL_TEXT,
                reviewer_type=ReviewerType.ADJUDICATOR,
                confidence=1.0,
            ),
        )

    await export_revision_supplements(str(db_path), workflow_id, supp_dir)

    outcome_path = supp_dir / "extracted_data_by_outcome.csv"
    rob2_path = supp_dir / "rob2_assessments.csv"
    robins_path = supp_dir / "robins_i_assessments.csv"
    grade_path = supp_dir / "grade_sof.csv"
    unretrieved_path = supp_dir / "unretrieved_fulltext_reports.csv"

    for path in (outcome_path, rob2_path, robins_path, grade_path, unretrieved_path):
        assert path.exists()

    with outcome_path.open(encoding="utf-8") as f:
        outcome_rows = list(csv.DictReader(f))
    assert len(outcome_rows) == 2
    assert outcome_rows[0]["outcome_name"] == "ldl_reduction"
    assert outcome_rows[0]["effect_size"] == "-0.42"
    assert outcome_rows[1]["outcome_name"] == "mortality"

    with rob2_path.open(encoding="utf-8") as f:
        rob2_rows = list(csv.DictReader(f))
    assert len(rob2_rows) == 1
    assert rob2_rows[0]["domain_1_randomization"] == "low"
    assert rob2_rows[0]["overall_judgment"] == "some_concerns"

    with robins_path.open(encoding="utf-8") as f:
        robins_rows = list(csv.DictReader(f))
    assert len(robins_rows) == 1
    assert robins_rows[0]["domain_4_deviations"] == "serious"
    assert robins_rows[0]["overall_judgment"] == "moderate"

    with grade_path.open(encoding="utf-8") as f:
        grade_rows = list(csv.DictReader(f))
    assert len(grade_rows) == 1
    assert grade_rows[0]["topic"] == "Statin therapy review"
    assert grade_rows[0]["outcome_name"] == "ldl reduction"
    assert grade_rows[0]["certainty"] == GRADECertainty.MODERATE.value

    with unretrieved_path.open(encoding="utf-8") as f:
        unretrieved_rows = list(csv.DictReader(f))
    assert len(unretrieved_rows) == 1
    assert unretrieved_rows[0]["title"] == "Unavailable full text"
    assert unretrieved_rows[0]["exclusion_reason"] == "no_full_text"
    assert unretrieved_rows[0]["doi"] == "10.1000/missing"


@pytest.mark.asyncio
async def test_export_revision_supplements_writes_headers_when_empty(tmp_path: Path) -> None:
    workflow_id = "wf-revision-empty"
    db_path = tmp_path / "runtime.db"
    supp_dir = tmp_path / "supplementary"

    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow(workflow_id, "Empty review", "hash")

    await export_revision_supplements(str(db_path), workflow_id, supp_dir)

    with (supp_dir / "extracted_data_by_outcome.csv").open(encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0][0] == "paper_id"
    assert len(rows) == 1

    with (supp_dir / "grade_sof.csv").open(encoding="utf-8") as f:
        grade_rows = list(csv.reader(f))
    assert grade_rows[0][0] == "topic"
    assert len(grade_rows) == 1
