from __future__ import annotations

import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.models import CandidatePaper, GateStatus, SettingsConfig, StudyDesign
from src.models.extraction import ExtractionRecord
from src.orchestration.gates import GateRunner
from src.quality.grade import GradeAssessor
from src.quality.rob2 import Rob2Assessor
from src.quality.robins_i import RobinsIAssessor
from src.quality.study_router import StudyRouter


def _settings() -> SettingsConfig:
    return SettingsConfig(
        agents={
            "quality_assessment": {
                "model": "google-gla:gemini-2.5-pro",
                "temperature": 0.1,
            }
        }
    )


def _record(paper_id: str, design: StudyDesign, summary: str) -> ExtractionRecord:
    return ExtractionRecord(
        paper_id=paper_id,
        study_design=design,
        intervention_description="AI tutor intervention",
        outcomes=[{"name": "outcome_1", "description": "Exam performance"}],
        results_summary={"summary": summary, "source": "metadata"},
    )


@pytest.mark.asyncio
async def test_quality_pipeline_routes_assesses_and_persists(tmp_path) -> None:
    async with get_db(str(tmp_path / "quality_pipeline.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-quality", "topic", "hash")

        rct_paper = CandidatePaper(title="RCT study", authors=["A"], source_database="pubmed")
        nrs_paper = CandidatePaper(title="Cohort study", authors=["B"], source_database="crossref")
        await repo.save_paper(rct_paper)
        await repo.save_paper(nrs_paper)

        rct_record = _record(
            paper_id=rct_paper.paper_id,
            design=StudyDesign.RCT,
            summary="random protocol validated without missing data issues",
        )
        nrs_record = _record(
            paper_id=nrs_paper.paper_id,
            design=StudyDesign.NON_RANDOMIZED,
            summary="confounding and missing data were present in the cohort analysis",
        )
        await repo.save_extraction_record("wf-quality", rct_record)
        await repo.save_extraction_record("wf-quality", nrs_record)

        router = StudyRouter()
        rob2 = Rob2Assessor()
        robins_i = RobinsIAssessor()
        grade = GradeAssessor()

        assert router.route_tool(rct_record) == "rob2"
        assert router.route_tool(nrs_record) == "robins_i"

        rct_assessment = await rob2.assess(rct_record)
        nrs_assessment = await robins_i.assess(nrs_record)
        await repo.save_rob2_assessment("wf-quality", rct_assessment)
        await repo.save_robins_i_assessment("wf-quality", nrs_assessment)

        grade_row = grade.assess_outcome(
            outcome_name="knowledge_retention",
            number_of_studies=2,
            study_design=StudyDesign.RCT,
            risk_of_bias_downgrade=1,
        )
        await repo.save_grade_assessment("wf-quality", grade_row)

        gate_runner = GateRunner(repo, _settings())
        extraction_gate = await gate_runner.run_extraction_completeness_gate(
            workflow_id="wf-quality",
            phase="phase_4_extraction_quality",
            completeness_ratio=0.85,
        )
        citation_gate = await gate_runner.run_citation_lineage_gate(
            workflow_id="wf-quality",
            phase="phase_4_extraction_quality",
            unresolved_items=0,
        )
        assert extraction_gate.status == GateStatus.PASSED
        assert citation_gate.status == GateStatus.PASSED

        cursor = await db.execute("SELECT COUNT(*) FROM rob_assessments WHERE workflow_id = ?", ("wf-quality",))
        rob_count = await cursor.fetchone()
        assert int(rob_count[0]) == 2

        cursor = await db.execute("SELECT COUNT(*) FROM grade_assessments WHERE workflow_id = ?", ("wf-quality",))
        grade_count = await cursor.fetchone()
        assert int(grade_count[0]) == 1

        cursor = await db.execute(
            "SELECT COUNT(*) FROM gate_results WHERE workflow_id = ? AND phase = ?",
            ("wf-quality", "phase_4_extraction_quality"),
        )
        gate_count = await cursor.fetchone()
        assert int(gate_count[0]) >= 2
