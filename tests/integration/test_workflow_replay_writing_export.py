from __future__ import annotations

from pathlib import Path

import pytest

from src.db.database import get_db
from src.db.repositories import CitationRepository, WorkflowRepository
from src.manuscript.contracts import run_manuscript_contracts


async def test_real_workflow_writing_export_contracts(real_workflow_target: tuple[str, Path]) -> None:
    workflow_id, runtime_db = real_workflow_target
    run_dir = runtime_db.parent
    md_path = run_dir / "doc_manuscript.md"
    if not md_path.exists():
        pytest.skip("Workflow does not have doc_manuscript.md yet.")

    tex_path = run_dir / "doc_manuscript.tex"
    async with get_db(str(runtime_db)) as db:
        repo = WorkflowRepository(db)
        citation_repo = CitationRepository(db)
        result = await run_manuscript_contracts(
            repository=repo,
            citation_repository=citation_repo,
            workflow_id=workflow_id,
            manuscript_md_path=str(md_path),
            manuscript_tex_path=str(tex_path) if tex_path.exists() else None,
            mode="observe",
        )
        assert result.passed, f"manuscript contracts failed with {len(result.violations)} violation(s)"
