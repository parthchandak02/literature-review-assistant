from __future__ import annotations

from pathlib import Path

import pytest

from src.db.database import get_db
from src.db.repositories import CitationRepository, WorkflowRepository
from src.manuscript.contracts import run_manuscript_contracts
from src.manuscript.readiness import compute_readiness_scorecard
from src.models import FallbackEventRecord


def _write_minimal_manuscript(md_path: Path, tex_path: Path) -> None:
    md_path.write_text(
        "\n".join(
            [
                "## Abstract",
                "**Background:** text",
                "**Objectives:** obj",
                "**Methods:** meth",
                "**Results:** res",
                "**Conclusions:** conc",
                "## Introduction",
                "Intro.",
                "## Methods",
                "Methods.",
                "## Results",
                "Results.",
                "## Discussion",
                "Discussion.",
                "## Conclusion",
                "Conclusion.",
                "## References",
                "[1] Ref",
            ]
        ),
        encoding="utf-8",
    )
    tex_path.write_text(
        "\\section{Abstract}\n\\section{Introduction}\n\\section{Methods}\n\\section{Results}\n"
        "\\section{Discussion}\n\\section{Conclusion}\n\\section{References}\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_contract_detects_deterministic_section_fallback(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime_contract_fallback.db"
    manuscript_md = tmp_path / "doc_manuscript.md"
    manuscript_tex = tmp_path / "doc_manuscript.tex"
    _write_minimal_manuscript(manuscript_md, manuscript_tex)

    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        cite_repo = CitationRepository(db)
        await repo.create_workflow("wf-fallback", "topic", "hash")
        await repo.save_fallback_event(
            FallbackEventRecord(
                workflow_id="wf-fallback",
                phase="phase_6_writing",
                module="writing.section_writer",
                fallback_type="deterministic_section_fallback",
                reason="section=results",
            )
        )
        result = await run_manuscript_contracts(
            repository=repo,
            citation_repository=cite_repo,
            workflow_id="wf-fallback",
            manuscript_md_path=str(manuscript_md),
            manuscript_tex_path=str(manuscript_tex),
            mode="strict",
        )

    assert any(v.code == "SECTION_DETERMINISTIC_FALLBACK" for v in result.violations)


@pytest.mark.asyncio
async def test_readiness_reports_fallback_event_count(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime_readiness.db"
    manuscript_md = tmp_path / "doc_manuscript.md"
    manuscript_tex = tmp_path / "doc_manuscript.tex"
    _write_minimal_manuscript(manuscript_md, manuscript_tex)

    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-ready", "topic", "hash")
        await repo.save_checkpoint("wf-ready", "finalize", 1)
        await repo.save_fallback_event(
            FallbackEventRecord(
                workflow_id="wf-ready",
                phase="phase_6_writing",
                module="rag.retrieval",
                fallback_type="empty_retrieval_context",
                reason="section=discussion",
            )
        )

    scorecard = await compute_readiness_scorecard(
        db_path=str(db_path),
        workflow_id="wf-ready",
        manuscript_md_path=str(manuscript_md),
        manuscript_tex_path=str(manuscript_tex),
        contract_mode="observe",
    )
    assert scorecard.fallback_event_count == 1
    assert scorecard.ready is False
    assert any(check.name == "fallback_events" for check in scorecard.checks)
