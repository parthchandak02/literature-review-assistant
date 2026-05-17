from __future__ import annotations

import pytest

from src.models.diagrams import DiagramBriefPack, DiagramEvidenceClaim, ResearchDiagramBrief
from src.visualization.research_diagram_placement import plan_inline_diagram_placements


@pytest.mark.asyncio
async def test_plan_inline_diagram_placements_falls_back_when_agent_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _raise(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    monkeypatch.setattr("src.visualization.research_diagram_placement.PydanticAIClient.complete_validated", _raise)

    brief_pack = DiagramBriefPack(
        workflow_id="wf-0083",
        source_included_count=3,
        source_file_count=3,
        diagrams=[
            ResearchDiagramBrief(
                diagram_id="d01",
                diagram_type="method_flow",
                title="Method flow overview",
                objective="Show how studies move through extraction and synthesis.",
                required_labels=["Search", "Screen", "Extract"],
                evidence_claims=[
                    DiagramEvidenceClaim(claim="Screening removes ineligible studies.", supporting_paper_ids=["p1"])
                ],
            ),
            ResearchDiagramBrief(
                diagram_id="d02",
                diagram_type="evidence_map",
                title="Evidence map",
                objective="Summarize themes and outcomes from included studies.",
                required_labels=["Theme", "Outcome"],
            ),
        ],
    )
    body = (
        "## Introduction\nBackground text.\n\n"
        "## Methods\nMethods paragraph.\n\n"
        "## Results\nResults paragraph.\n\n"
        "## Discussion\nDiscussion paragraph.\n"
    )
    plan, usage = await plan_inline_diagram_placements(
        workflow_id="wf-0083",
        brief_pack=brief_pack,
        manuscript_body=body,
        model="google-gla:gemini-2.5-flash-lite",
    )

    assert plan.workflow_id == "wf-0083"
    assert len(plan.decisions) == 2
    assert any("failed" in warning for warning in plan.warnings)
    assert usage["tokens_in"] == 0
    assert usage["tokens_out"] == 0
    assert {d.target_section for d in plan.decisions}.issubset(
        {"introduction", "methods", "results", "discussion", "conclusion"}
    )
