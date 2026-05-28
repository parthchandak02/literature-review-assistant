"""Pydantic contract matrix for workflow and writing models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.models.claims import ClaimRecord
from src.models.cohort import CohortMembershipRecord
from src.models.workflow import SectionQualityScore, WorkflowStepRecord
from src.models.writing import OutlineNode, SectionOutline


@pytest.mark.parametrize(
    "payload",
    [
        {"hard_issue_count": "not-int"},
        {"soft_issue_count": "bad"},
    ],
)
def test_section_quality_score_rejects_invalid(payload: dict) -> None:
    with pytest.raises(ValidationError):
        SectionQualityScore.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"workflow_id": "wf-1"},
    ],
)
def test_workflow_step_record_requires_fields(payload: dict) -> None:
    with pytest.raises(ValidationError):
        WorkflowStepRecord.model_validate(payload)


def test_section_outline_validates_nodes() -> None:
    with pytest.raises(ValidationError):
        SectionOutline.model_validate(
            {
                "section_key": "introduction",
                "nodes": [{"heading": "Background"}],
            },
        )

    outline = SectionOutline.model_validate(
        {
            "section_key": "introduction",
            "nodes": [
                {
                    "node_id": "n1",
                    "heading": "Background",
                    "intent": "context",
                },
            ],
        },
    )
    assert isinstance(outline.nodes[0], OutlineNode)


@pytest.mark.parametrize(
    "payload",
    [
        {"paper_id": "p1"},
        {"workflow_id": "wf-1"},
    ],
)
def test_cohort_membership_requires_ids(payload: dict) -> None:
    with pytest.raises(ValidationError):
        CohortMembershipRecord.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"claim_text": "x"},
        {"section": "results"},
    ],
)
def test_claim_record_requires_fields(payload: dict) -> None:
    with pytest.raises(ValidationError):
        ClaimRecord.model_validate(payload)
