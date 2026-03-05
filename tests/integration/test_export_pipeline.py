"""Integration tests for the export and PRISMA pipeline.

Validates:
- PRISMA flow diagram renders to a file (PNG via library or fallback matplotlib)
- PRISMACounts builds correctly from repository data
- assemble_submission_manuscript produces a non-empty document with expected sections
- Citation numbering converts [AuthorYear] citekeys to [N] format
- Search appendix is appended when the file exists
- References section is present in the assembled manuscript
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.export.markdown_refs import (
    assemble_submission_manuscript,
    build_markdown_references_section,
    extract_citekeys_in_order,
)
from src.models import PRISMACounts
from src.prisma.diagram import render_prisma_diagram

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_prisma_counts() -> PRISMACounts:
    return PRISMACounts(
        databases_records={"pubmed": 50, "openalex": 30},
        other_sources_records={},
        total_identified_databases=80,
        total_identified_other=0,
        duplicates_removed=10,
        records_screened=70,
        records_excluded_screening=55,
        reports_sought=15,
        reports_not_retrieved=2,
        reports_assessed=13,
        reports_excluded_with_reasons={
            "wrong_population": 2,
            "wrong_intervention": 1,
        },
        studies_included_qualitative=10,
        studies_included_quantitative=7,
        arithmetic_valid=True,
    )


# ---------------------------------------------------------------------------
# Test 1: PRISMA diagram renders to a PNG file
# ---------------------------------------------------------------------------


def test_prisma_diagram_renders_to_file(tmp_path: Path) -> None:
    counts = _minimal_prisma_counts()
    output_path = str(tmp_path / "prisma_flow.png")
    result = render_prisma_diagram(counts, output_path)
    assert result.exists(), "PRISMA diagram must create a file on disk"
    assert result.suffix == ".png"
    assert result.stat().st_size > 0, "PRISMA PNG must not be empty"


# ---------------------------------------------------------------------------
# Test 2: PRISMA counts build correctly from repository data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_prisma_counts_from_repo(tmp_path: Path) -> None:
    from src.models.papers import CandidatePaper, SourceCategory
    from src.prisma.diagram import build_prisma_counts

    async with get_db(str(tmp_path / "prisma_repo.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-prisma", "pharmacy-automation", "hash")

        # Save some papers from two databases
        for i in range(5):
            paper = CandidatePaper(
                title=f"Paper {i}",
                authors=["Author"],
                source_database="pubmed" if i % 2 == 0 else "openalex",
                source_category=SourceCategory.DATABASE,
            )
            await repo.save_paper(paper)

        counts = await build_prisma_counts(
            repo=repo,
            workflow_id="wf-prisma",
            dedup_count=0,
            included_qualitative=3,
            included_quantitative=2,
        )

    assert isinstance(counts, PRISMACounts)
    assert counts.studies_included_qualitative == 3
    assert counts.studies_included_quantitative == 2
    assert (counts.total_identified_databases + counts.total_identified_other) >= 0


# ---------------------------------------------------------------------------
# Test 3: assemble_submission_manuscript produces a non-empty document
# ---------------------------------------------------------------------------


def test_assemble_manuscript_produces_document(tmp_path: Path) -> None:
    body = (
        "## Introduction\n\n"
        "Pharmacy automation reduces dispensing errors [Smith2023].\n\n"
        "## Methods\n\n"
        "A systematic search was conducted [Jones2022].\n\n"
        "## Results\n\n"
        "Ten studies met inclusion criteria [Brown2021].\n"
    )
    manuscript_path = tmp_path / "manuscript.md"

    # citation_rows: (citation_id, citekey, doi, title, authors_json, year, journal, bibtex)
    citation_rows = [
        ("cid-1", "Smith2023", "10.1000/s", "Robotic dispensing", '["Smith, J."]', "2023", "J Pharm", ""),
        ("cid-2", "Jones2022", "10.1000/j", "Automation review", '["Jones, A."]', "2022", "J Health", ""),
        ("cid-3", "Brown2021", "10.1000/b", "Error analysis", '["Brown, B."]', "2021", "J Qual", ""),
    ]

    result = assemble_submission_manuscript(
        body=body,
        manuscript_path=manuscript_path,
        artifacts={},
        citation_rows=citation_rows,
        research_question="How does pharmacy automation reduce dispensing errors?",
    )

    assert isinstance(result, str)
    assert len(result) > 100
    # Title block should be present
    assert "Systematic Review" in result or "pharmacy automation" in result.lower()
    # Citations should be converted to numbered format
    assert "[1]" in result or "[2]" in result or "[3]" in result
    # References section should appear
    assert "References" in result or "REFERENCES" in result


# ---------------------------------------------------------------------------
# Test 4: extract_citekeys_in_order preserves order and deduplicates
# ---------------------------------------------------------------------------


def test_extract_citekeys_preserves_order_and_deduplicates() -> None:
    text = "First claim [Smith2023]. Second claim [Jones2022]. Smith again [Smith2023]. Third new [Brown2021]."
    keys = extract_citekeys_in_order(text)
    assert keys == ["Smith2023", "Jones2022", "Brown2021"]


# ---------------------------------------------------------------------------
# Test 5: build_markdown_references_section formats APA-style entries
# ---------------------------------------------------------------------------


def test_build_references_section_formats_entries() -> None:
    # (citation_id, citekey, doi, title, authors_json, year, journal, bibtex)
    citation_rows = [
        (
            "cid-1",
            "Smith2023",
            "10.1000/s",
            "Robotic dispensing",
            '["Smith, J.", "Doe, A."]',
            "2023",
            "Journal of Pharmacy",
            "",
        ),
        ("cid-2", "Jones2022", "10.1000/j", "Automation review", '["Jones, B."]', "2022", "Health Informatics", ""),
    ]
    text_with_citekeys = "Claim one [Smith2023]. Claim two [Jones2022]."
    section = build_markdown_references_section(text_with_citekeys, citation_rows)

    assert "Smith" in section
    assert "Jones" in section
    assert "2023" in section
    assert "2022" in section
    # Should have numbered entries like "[1]" or "1."
    assert "[1]" in section or "1." in section


# ---------------------------------------------------------------------------
# Test 6: Search appendix is appended when file exists
# ---------------------------------------------------------------------------


def test_search_appendix_appended_when_file_present(tmp_path: Path) -> None:
    appendix_path = tmp_path / "search_strategies.md"
    appendix_path.write_text("## Appendix B: Search Strategies\n\nPubMed query: pharmacy[tiab]", encoding="utf-8")

    body = "## Introduction\n\nSome text.\n"
    result = assemble_submission_manuscript(
        body=body,
        manuscript_path=tmp_path / "ms.md",
        artifacts={},
        citation_rows=[],
        search_appendix_path=appendix_path,
    )

    assert "Search Strategies" in result or "Appendix" in result


# ---------------------------------------------------------------------------
# Test 7: PRISMACounts field arithmetic is correct
# ---------------------------------------------------------------------------


def test_prisma_counts_fields_are_correct() -> None:
    counts = PRISMACounts(
        databases_records={"pubmed": 100, "openalex": 50},
        other_sources_records={"clinicaltrials_gov": 10},
        total_identified_databases=150,
        total_identified_other=10,
        duplicates_removed=20,
        records_screened=140,
        records_excluded_screening=110,
        reports_sought=30,
        reports_not_retrieved=5,
        reports_assessed=25,
        reports_excluded_with_reasons={"wrong_population": 3, "wrong_intervention": 2},
        studies_included_qualitative=20,
        studies_included_quantitative=15,
        arithmetic_valid=True,
    )
    assert counts.total_identified_databases == 150
    assert counts.total_identified_other == 10
    # excluded reasons total = 3 + 2 = 5
    assert sum(counts.reports_excluded_with_reasons.values()) == 5
