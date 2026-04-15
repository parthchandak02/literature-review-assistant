from __future__ import annotations

import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.models import OutlineNode, SectionOutline


@pytest.mark.asyncio
async def test_rollback_from_writing_clears_section_outlines(tmp_path) -> None:
    async with get_db(str(tmp_path / "rollback_writing.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-outline", "topic", "hash")
        await repo.save_section_outline(
            "wf-outline",
            SectionOutline(
                section_key="results",
                nodes=[
                    OutlineNode(
                        node_id="study_selection",
                        heading="Study Selection",
                        intent="Cover PRISMA flow.",
                        required_citekeys=[],
                        evidence_chunk_ids=[],
                    )
                ],
                grounding_hash="abc123",
            ),
        )

        assert set((await repo.load_section_outlines("wf-outline")).keys()) == {"results"}
        await repo.rollback_phase_data("wf-outline", "phase_6_writing")
        assert await repo.load_section_outlines("wf-outline") == {}


@pytest.mark.asyncio
async def test_rollback_from_finalize_keeps_section_outlines(tmp_path) -> None:
    async with get_db(str(tmp_path / "rollback_finalize.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-outline-finalize", "topic", "hash")
        await repo.save_section_outline(
            "wf-outline-finalize",
            SectionOutline(
                section_key="discussion",
                nodes=[
                    OutlineNode(
                        node_id="principal_findings",
                        heading="Principal Findings",
                        intent="Interpret the main evidence pattern.",
                        required_citekeys=[],
                        evidence_chunk_ids=[],
                    )
                ],
                grounding_hash="def456",
            ),
        )

        await repo.rollback_phase_data("wf-outline-finalize", "finalize")
        assert set((await repo.load_section_outlines("wf-outline-finalize")).keys()) == {"discussion"}
