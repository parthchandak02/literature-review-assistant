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
    convert_to_numbered_citations,
    extract_citekeys_in_order,
)
from src.export.submission_packager import _build_number_to_citekey
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
        await repo.create_workflow("wf-prisma", "test-review-topic", "hash")

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
        "The intervention improved primary outcomes in adults [Smith2023].\n\n"
        "## Methods\n\n"
        "A systematic search was conducted [Jones2022].\n\n"
        "## Results\n\n"
        "Ten studies met inclusion criteria [Brown2021].\n"
    )
    manuscript_path = tmp_path / "manuscript.md"

    # citation_rows: (citation_id, citekey, doi, title, authors_json, year, journal, bibtex, url)
    citation_rows = [
        ("cid-1", "Smith2023", "10.1000/s", "Intervention efficacy study", '["Smith, J."]', "2023", "J Health Res", "", None),
        ("cid-2", "Jones2022", "10.1000/j", "Systematic review methods", '["Jones, A."]', "2022", "J Health", "", None),
        ("cid-3", "Brown2021", "10.1000/b", "Outcome analysis study", '["Brown, B."]', "2021", "J Qual", "", None),
    ]

    result = assemble_submission_manuscript(
        body=body,
        manuscript_path=manuscript_path,
        artifacts={},
        citation_rows=citation_rows,
        research_question="What is the effect of the intervention on the primary outcome?",
    )

    assert isinstance(result, str)
    assert len(result) > 100
    # Title block should be present
    assert "Systematic Review" in result or "intervention" in result.lower()
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
    # (citation_id, citekey, doi, title, authors_json, year, journal, bibtex, url)
    citation_rows = [
        (
            "cid-1",
            "Smith2023",
            "10.1000/s",
            "Intervention effectiveness study",
            '["Smith, J.", "Doe, A."]',
            "2023",
            "Journal of Health Research",
            "",
            None,
        ),
        ("cid-2", "Jones2022", "10.1000/j", "Outcome measurement review", '["Jones, B."]', "2022", "Health Informatics", "", None),
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
    appendix_path.write_text("## Appendix B: Search Strategies\n\nPubMed query: intervention[tiab] AND outcome[tiab]", encoding="utf-8")

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


# ---------------------------------------------------------------------------
# Test 8: _build_number_to_citekey DOI-only (standard case)
# ---------------------------------------------------------------------------


def test_build_number_to_citekey_doi_match() -> None:
    """Standard case: DOI present -> mapped correctly."""
    citations = [
        ("cid-1", "Smith2023", "10.1000/s", "Intervention efficacy study", '["Smith, J."]', 2023, "J Health Res", "", None),
    ]
    md = (
        "## Introduction\n\nSee [1].\n\n"
        "## References\n\n"
        "[1] Smith, J., \"Intervention efficacy study,\" J Health Res, 2023. doi: 10.1000/s\n"
    )
    num_to_ck = _build_number_to_citekey(md, citations)
    assert num_to_ck.get("1") == "Smith2023"


# ---------------------------------------------------------------------------
# Test 9: _build_number_to_citekey URL fallback
# ---------------------------------------------------------------------------


def test_build_number_to_citekey_url_fallback() -> None:
    """URL-only paper (no DOI) is still mapped via the URL fallback."""
    citations = [
        ("cid-2", "ClinTrial2022", None, "Clinical Trial", '["Anon"]', 2022, None, "", "https://clinicaltrials.gov/ct2/show/NCT123"),
    ]
    md = (
        "## Introduction\n\nSee [1].\n\n"
        "## References\n\n"
        "[1] Anon, \"Clinical Trial,\" 2022. https://clinicaltrials.gov/ct2/show/NCT123\n"
    )
    num_to_ck = _build_number_to_citekey(md, citations)
    assert num_to_ck.get("1") == "ClinTrial2022"


# ---------------------------------------------------------------------------
# Test 10: _build_number_to_citekey title-based fallback
# ---------------------------------------------------------------------------


def test_build_number_to_citekey_title_fallback() -> None:
    """Paper with neither DOI nor URL is mapped via title-based fuzzy match."""
    citations = [
        ("cid-3", "Grey2021", None, "Grey literature study on outcomes", '["Grey, A."]', 2021, None, "", None),
    ]
    md = (
        "## Introduction\n\nSee [1].\n\n"
        "## References\n\n"
        "[1] Grey, A., \"Grey literature study on outcomes,\" 2021.\n"
    )
    num_to_ck = _build_number_to_citekey(md, citations)
    assert num_to_ck.get("1") == "Grey2021"


# ---------------------------------------------------------------------------
# Test 11: convert_to_numbered_citations handles multi-key groups
# ---------------------------------------------------------------------------


def test_convert_to_numbered_multi_key() -> None:
    """[Smith2023, Jones2024] -> [1], [2] (comma-separated individual numbers)."""
    citations = [
        ("cid-1", "Smith2023", "10.1000/s", "Title A", '["Smith"]', 2023, "J", "", None),
        ("cid-2", "Jones2024", "10.1000/j", "Title B", '["Jones"]', 2024, "J", "", None),
    ]
    body = "Both studies confirmed this [Smith2023, Jones2024]."
    numbered_body, ordered_rows = convert_to_numbered_citations(body, citations)
    assert "[1]" in numbered_body
    assert "[2]" in numbered_body
    assert "Smith2023" not in numbered_body
    assert len(ordered_rows) == 2


def test_convert_to_numbered_semicolon_separator() -> None:
    """[Smith2023; Jones2024] (semicolon style) is also handled."""
    citations = [
        ("cid-1", "Smith2023", "10.1000/s", "Title A", '["Smith"]', 2023, "J", "", None),
        ("cid-2", "Jones2024", "10.1000/j", "Title B", '["Jones"]', 2024, "J", "", None),
    ]
    body = "See [Smith2023; Jones2024] for evidence."
    numbered_body, _ = convert_to_numbered_citations(body, citations)
    assert "[1]" in numbered_body
    assert "[2]" in numbered_body


# ---------------------------------------------------------------------------
# Test 12: assemble_submission_manuscript with DOI-less paper
# ---------------------------------------------------------------------------


def test_assemble_manuscript_doi_less_paper(tmp_path: Path) -> None:
    """A citation_rows entry with doi=None but url present appears in References."""
    body = (
        "## Introduction\n\nSome claim [NoDoiPaper2020].\n\n"
        "## Results\n\nResults confirmed [NoDoiPaper2020].\n"
    )
    citation_rows = [
        ("cid-1", "NoDoiPaper2020", None, "A Grey Literature Report", '["Author, A."]', 2020, None, "", "https://example.org/report"),
    ]
    result = assemble_submission_manuscript(
        body=body,
        manuscript_path=tmp_path / "ms.md",
        artifacts={},
        citation_rows=citation_rows,
        research_question="Does the intervention work?",
    )
    assert isinstance(result, str)
    assert "Author" in result
    assert "Grey Literature" in result
    assert "[1]" in result
