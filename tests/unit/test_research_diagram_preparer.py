from __future__ import annotations

import pytest

from src.models.diagrams import DiagramBriefPack, DiagramEvidenceClaim, ResearchDiagramBrief
from src.visualization import research_diagram_preparer as preparer


@pytest.mark.asyncio
async def test_prepare_research_diagram_briefs_falls_back_on_client_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _boom(self, *args, **kwargs):  # noqa: ANN001, ANN002, ARG001
        raise RuntimeError("forced failure")

    monkeypatch.setattr(preparer.PydanticAIClient, "complete_validated", _boom)

    pack, usage = await preparer.prepare_research_diagram_briefs(
        workflow_id="wf-0083",
        review_topic="Topic",
        research_question="Question",
        included_studies=[{"paper_id": "p1", "title": "Paper 1", "year": 2024}],
        extraction_summaries=[],
        manifest_entries={"p1": {"file_path": "papers/p1.pdf", "file_type": "pdf"}},
        model="google:gemini-2.5-flash-lite",
    )

    assert isinstance(pack, DiagramBriefPack)
    assert pack.workflow_id == "wf-0083"
    assert len(pack.diagrams) == 2
    assert usage["tokens_in"] == 0


@pytest.mark.asyncio
async def test_prepare_research_diagram_briefs_normalizes_returned_pack(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = DiagramBriefPack(
        workflow_id="wrong-id",
        source_included_count=99,
        source_file_count=99,
        diagrams=[
            ResearchDiagramBrief(
                diagram_id="diag_1",
                diagram_type="method_flow",
                title="Title 1",
                objective="Objective one for diagram.",
                required_labels=["A", "B", "C"],
                evidence_claims=[DiagramEvidenceClaim(claim="claim one", supporting_paper_ids=["p1"])],
            ),
            ResearchDiagramBrief(
                diagram_id="diag_2",
                diagram_type="evidence_map",
                title="Title 2",
                objective="Objective two for diagram.",
                required_labels=["A", "B", "C"],
                evidence_claims=[DiagramEvidenceClaim(claim="claim two", supporting_paper_ids=["p2"])],
            ),
        ],
    )

    async def _ok(self, *args, **kwargs):  # noqa: ANN001, ANN002, ARG001
        return fake, 10, 20, 1, 2, 0

    monkeypatch.setattr(preparer.PydanticAIClient, "complete_validated", _ok)

    pack, usage = await preparer.prepare_research_diagram_briefs(
        workflow_id="wf-0083",
        review_topic="Topic",
        research_question="Question",
        included_studies=[{"paper_id": "p1"}, {"paper_id": "p2"}],
        extraction_summaries=[],
        manifest_entries={"p1": {"file_path": "papers/p1.pdf", "file_type": "pdf"}},
        model="google:gemini-2.5-flash-lite",
    )

    assert pack.workflow_id == "wf-0083"
    assert pack.source_included_count == 2
    assert usage["tokens_in"] == 10
