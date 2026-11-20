"""Unit tests for src/orchestration/helpers/writing_manuscript.py."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.db.database import get_db
from src.db.repos.writing import WritingRepo
from src.db.repositories import CitationRepository, WorkflowRepository
from src.models import CitationEntryRecord, SectionDraft
from src.orchestration.helpers.writing_manuscript import (
    build_minimal_sections_for_zero_papers,
    refresh_manuscript_export_artifacts,
    validate_writing_persistence_invariant,
)

_WORKFLOW_ID = "wf-writing-manuscript-test"


def _cit(citekey: str, doi: str, title: str, author: str, year: int, journal: str | None = None) -> CitationEntryRecord:
    return CitationEntryRecord(citekey=citekey, doi=doi, title=title, authors=[author], year=year, journal=journal)


def _make_state(db_path: Path, md_path: Path, *, artifacts: dict[str, str] | None = None) -> SimpleNamespace:
    merged = {"manuscript_md": str(md_path), **(artifacts or {})}
    return SimpleNamespace(
        workflow_id=_WORKFLOW_ID,
        db_path=str(db_path),
        artifacts=merged,
        review=SimpleNamespace(author_name="Jane Doe"),
    )


async def _seed_workflow_db(db_path: Path, citations: list[CitationEntryRecord], *, with_section: bool = True) -> None:
    async with get_db(str(db_path)) as db:
        wf_repo = WorkflowRepository(db)
        await wf_repo.create_workflow(_WORKFLOW_ID, "Digital adherence reminders", "hash-1")
        if with_section:
            draft = SectionDraft(
                workflow_id=_WORKFLOW_ID,
                section="introduction",
                version=1,
                content="Digital reminders improved adherence.",
                word_count=4,
            )
            await wf_repo.save_section_artifacts_from_draft(draft, section_order=1)
        cit_repo = CitationRepository(db)
        for cit in citations:
            await cit_repo.register_citation(cit)


def test_validate_writing_persistence_invariant() -> None:
    assert validate_writing_persistence_invariant(
        ["abstract", "methods"], {"abstract", "methods", "results"}, ["results"]
    ) == (
        False,
        [],
    )
    assert validate_writing_persistence_invariant(["abstract", "results", "methods"], {"abstract"}, []) == (
        True,
        ["methods", "results"],
    )
    assert validate_writing_persistence_invariant(["abstract"], {"abstract"}, ["discussion"]) == (True, [])


def test_build_minimal_sections_for_zero_papers() -> None:
    sections = ["abstract", "introduction", "methods", "results", "discussion", "conclusion", "appendix"]
    rendered = build_minimal_sections_for_zero_papers("", "No studies included.", sections)
    assert len(rendered) == len(sections)
    assert "the research question" in rendered[0] and "0 studies met the eligibility criteria" in rendered[0]
    assert "the research question" in rendered[1]
    assert "registered protocol" in rendered[2]
    assert rendered[3] == "No studies included."
    assert "evidence gap" in rendered[4]
    assert "No conclusions can be drawn" in rendered[5]
    assert rendered[6] == "No studies included."


@pytest.mark.asyncio
async def test_refresh_manuscript_export_returns_none_when_markdown_missing(tmp_path: Path) -> None:
    state = _make_state(tmp_path / "runtime.db", tmp_path / "missing.md")
    assert await refresh_manuscript_export_artifacts(state, strict_export=True) is None
    assert "manuscript_tex" not in state.artifacts


@pytest.mark.asyncio
async def test_refresh_manuscript_export_strict_deduplicates_keys_and_persists_assembly(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.db"
    md_path = tmp_path / "doc_manuscript.md"
    fig_path = tmp_path / "fig_prisma_flow.png"
    fig_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    await _seed_workflow_db(
        db_path,
        [
            _cit("Smith-2024", "10.1000/first", "First Reminder Trial", "Alice Smith", 2024, "J Med"),
            _cit("Smith 2024", "10.1000/second", "Second Reminder Trial", "Bob Smith", 2024, "J Med"),
            _cit("Unused2020", "10.1000/unused", "Uncited Background Study", "Carol Lee", 2020),
        ],
    )
    md_path.write_text(
        "# Digital Reminders Review\n\n"
        "## Abstract\n\nShort abstract summarizing trial findings [1].\n\n"
        "## Introduction\n\nBoth trials improved adherence [1, 2].\n\n"
        "---\n\n## Figures\n\n![PRISMA Flow](fig_prisma_flow.png)\n\n"
        "## References\n\n"
        '[1] A. Smith, "First Reminder Trial," doi: 10.1000/first\n'
        '[2] B. Smith, "Second Reminder Trial," doi: 10.1000/second\n',
        encoding="utf-8",
    )

    state = _make_state(db_path, md_path, artifacts={"prisma_diagram": str(fig_path)})
    with patch("src.export.submission_packager.llm_resolve_unmatched_citations", new=AsyncMock()) as llm_mock:
        out_tex = await refresh_manuscript_export_artifacts(state, strict_export=True, persist_assembly=True)

    llm_mock.assert_not_called()
    assert out_tex == str(tmp_path / "doc_manuscript.tex")
    assert state.artifacts["manuscript_tex"] == out_tex
    assert state.artifacts["references_bib"] == str(tmp_path / "references.bib")

    tex_text = Path(out_tex).read_text(encoding="utf-8")
    bib_text = Path(state.artifacts["references_bib"]).read_text(encoding="utf-8")
    assert "\\author{Jane Doe}" in tex_text
    # "Smith 2024" sorts before "Smith-2024" in SQLite ORDER BY citekey, so [1] -> Smith_2024_2 and [2] -> Smith_2024.
    assert "\\cite{Smith_2024_2,Smith_2024}" in tex_text
    assert "\\includegraphics" in tex_text
    assert "Smith_2024," in bib_text and "Smith_2024_2," in bib_text and "Unused2020" not in bib_text

    async with get_db(str(db_path)) as db:
        cur = await db.execute(
            "SELECT target_format, manifest_json, content FROM manuscript_assemblies WHERE workflow_id = ?",
            (_WORKFLOW_ID,),
        )
        row = await cur.fetchone()
    assert row is not None and row[0] == "tex"
    assert json.loads(row[1])["sections"] == [{"section_key": "introduction", "version": 1, "order": 1}]
    assert "\\begin{document}" in row[2]


@pytest.mark.asyncio
async def test_refresh_manuscript_export_blocks_dropped_figures_and_unresolved_strict_cites(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.db"
    md_path = tmp_path / "doc_manuscript.md"
    await _seed_workflow_db(db_path, [_cit("Smith2024", "10.1000/first", "First Trial", "Alice Smith", 2024)])

    md_path.write_text(
        "# Review\n\n## Abstract\n\nText.\n\n## Introduction\n\nSee [Smith2024].\n\n"
        "---\n\n## Figures\n\n![PRISMA](fig_prisma_flow.png)\n",
        encoding="utf-8",
    )
    state_fig = _make_state(db_path, md_path, artifacts={"prisma_diagram": str(tmp_path / "missing.png")})
    with pytest.raises(RuntimeError, match="zero figures"):
        await refresh_manuscript_export_artifacts(state_fig, strict_export=True)
    assert not (tmp_path / "doc_manuscript.tex").exists()

    md_path.write_text(
        "# Review\n\n## Abstract\n\nText.\n\n## Introduction\n\nUnknown [Ghost2099] and [99].\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="strict export blocked"):
        await refresh_manuscript_export_artifacts(_make_state(db_path, md_path), strict_export=True)
    assert not (tmp_path / "doc_manuscript.tex").exists()


@pytest.mark.asyncio
async def test_refresh_manuscript_export_non_strict_uses_llm_fallback_and_ignores_assembly_error(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "runtime.db"
    md_path = tmp_path / "doc_manuscript.md"
    await _seed_workflow_db(
        db_path,
        [_cit("Jones2023", "10.1000/jones", "Fallback Trial", "Sam Jones", 2023)],
        with_section=False,
    )
    md_path.write_text(
        "# Review\n\n## Abstract\n\nSummary.\n\n## Introduction\n\nClaim [1].\n\n"
        "## References\n\n[1] Unmatched reference line\n",
        encoding="utf-8",
    )
    state = _make_state(db_path, md_path)
    llm_mock = AsyncMock(return_value={"1": "Jones2023"})
    with (
        patch("src.export.submission_packager.llm_resolve_unmatched_citations", new=llm_mock),
        patch.object(WritingRepo, "save_manuscript_assembly", new=AsyncMock(side_effect=RuntimeError("db fail"))),
    ):
        out_tex = await refresh_manuscript_export_artifacts(state, strict_export=False, persist_assembly=True)

    llm_mock.assert_awaited_once()
    assert out_tex == str(tmp_path / "doc_manuscript.tex")
    assert "\\cite{Jones2023}" in Path(out_tex).read_text(encoding="utf-8")
    assert "Jones2023," in Path(state.artifacts["references_bib"]).read_text(encoding="utf-8")
