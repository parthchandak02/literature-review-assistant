"""Unit tests for the four manuscript quality fixes.

Tests:
1. fulltext_paper_ids: Full Text Retrieved column uses file presence
2. _convert_sr_citekeys_to_text: hallucinated SR citekeys -> parenthetical text
3. _normalize_date_range: date range normalization in body text
4. build_picos_table date normalization: inclusion criteria text uses authoritative dates
5. assemble_submission_manuscript passes fulltext_paper_ids through the call chain
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from src.export.markdown_refs import (
    _convert_sr_citekeys_to_text,
    _normalize_date_range,
    assemble_submission_manuscript,
    build_picos_table,
    build_study_characteristics_table,
)
from src.models.extraction import ExtractionRecord
from src.models.papers import CandidatePaper, SourceCategory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_paper(paper_id: str, authors: list[str] | None = None, year: int = 2023) -> CandidatePaper:
    return CandidatePaper(
        paper_id=paper_id,
        title=f"Study {paper_id}",
        authors=authors or ["Author, A."],
        year=year,
        source_database="pubmed",
        source_category=SourceCategory.DATABASE,
        country=None,
    )


def _make_extraction(paper_id: str, extraction_source: str = "text") -> ExtractionRecord:
    return ExtractionRecord(
        paper_id=paper_id,
        study_design="non_randomized",
        participant_count=100,
        setting="Community clinic",
        intervention_description="Structured intervention program",
        results_summary={},
        extraction_source=extraction_source,
        confidence_score=0.9,
    )


# ---------------------------------------------------------------------------
# Fix 2: Full Text Retrieved column - fulltext_paper_ids
# ---------------------------------------------------------------------------


def test_full_text_retrieved_no_when_no_file_and_text_source():
    """extraction_source=text, not in fulltext_paper_ids -> No."""
    papers = [_make_paper("p1")]
    records = [_make_extraction("p1", extraction_source="text")]
    table = build_study_characteristics_table(papers, records, fulltext_paper_ids=None)
    assert "| No |" in table or "No" in table


def test_full_text_retrieved_yes_when_file_present_despite_text_source():
    """extraction_source=text BUT paper_id in fulltext_paper_ids -> Yes."""
    papers = [_make_paper("p1")]
    records = [_make_extraction("p1", extraction_source="text")]
    table = build_study_characteristics_table(papers, records, fulltext_paper_ids={"p1"})
    # Should show Yes because file exists on disk
    assert "Yes" in table


def test_full_text_retrieved_yes_when_pdf_vision_source():
    """extraction_source=pdf_vision (non-text) -> Yes regardless of fulltext_paper_ids."""
    papers = [_make_paper("p2")]
    records = [_make_extraction("p2", extraction_source="pdf_vision")]
    table = build_study_characteristics_table(papers, records, fulltext_paper_ids=None)
    assert "Yes" in table


def test_full_text_retrieved_no_when_id_not_in_fulltext_set():
    """Paper not in fulltext_paper_ids set and extraction_source=text -> No."""
    papers = [_make_paper("p3")]
    records = [_make_extraction("p3", extraction_source="text")]
    table = build_study_characteristics_table(papers, records, fulltext_paper_ids={"p999"})
    assert "No" in table


def test_full_text_retrieved_multiple_papers_mixed():
    """Mix of papers: some with files, some without."""
    papers = [_make_paper("p1"), _make_paper("p2")]
    records = [
        _make_extraction("p1", extraction_source="text"),
        _make_extraction("p2", extraction_source="text"),
    ]
    table = build_study_characteristics_table(papers, records, fulltext_paper_ids={"p1"})
    # p1 has file -> Yes; p2 does not -> No
    assert "Yes" in table
    assert "No" in table


# ---------------------------------------------------------------------------
# Fix 3: SR citekey conversion
# ---------------------------------------------------------------------------


def test_convert_bracketed_sr_citekey():
    """[Hanninen2021SR] becomes (Hanninen, 2021)."""
    result = _convert_sr_citekeys_to_text("Prior work [Hanninen2021SR] showed this.")
    assert "[Hanninen2021SR]" not in result
    assert "(Hanninen, 2021)" in result


def test_convert_unbracketed_sr_citekey():
    """Hanninen2021SR (no brackets) becomes (Hanninen, 2021)."""
    result = _convert_sr_citekeys_to_text("Earlier reviews including Hanninen2021SR and Momattin2021SR showed this.")
    assert "Hanninen2021SR" not in result
    assert "(Hanninen, 2021)" in result
    assert "(Momattin, 2021)" in result


def test_convert_sr_citekey_with_suffix_digit():
    """[Smith2022SR2] -> (Smith, 2022)."""
    result = _convert_sr_citekeys_to_text("See [Smith2022SR2] for details.")
    assert "[Smith2022SR2]" not in result
    assert "(Smith, 2022)" in result


def test_numbered_citation_not_touched():
    """Numbered citations [1], [2] must NOT be affected."""
    text = "Claim [1]. Another [2, 3]."
    result = _convert_sr_citekeys_to_text(text)
    assert result == text


def test_regular_citekey_not_touched():
    """Regular author-year citekeys [Smith2023] (no SR suffix) must NOT be converted."""
    text = "See [Smith2023] for details."
    result = _convert_sr_citekeys_to_text(text)
    assert result == text


def test_multiple_sr_citekeys_in_one_sentence():
    """Multiple SR citekeys in prose all get converted."""
    text = "Reviews by Hanninen2021SR, Momattin2021SR, and Alomi2018SR reached similar conclusions."
    result = _convert_sr_citekeys_to_text(text)
    assert "Hanninen2021SR" not in result
    assert "Momattin2021SR" not in result
    assert "Alomi2018SR" not in result
    assert "(Hanninen, 2021)" in result
    assert "(Momattin, 2021)" in result
    assert "(Alomi, 2018)" in result


# ---------------------------------------------------------------------------
# Fix 4: Date range normalization
# ---------------------------------------------------------------------------


def test_normalize_from_x_to_y_pattern():
    """'from 2000 to 2025' -> 'from 2000 to 2026'."""
    result = _normalize_date_range("Studies from 2000 to 2025 were included.", "2000", "2026")
    assert "from 2000 to 2026" in result
    assert "2025" not in result


def test_normalize_x_and_y_pattern():
    """'2000 and 2025' -> '2000 and 2026'."""
    result = _normalize_date_range("Research published between 2000 and 2025.", "2000", "2026")
    assert "2000 and 2026" in result
    assert "2025" not in result


def test_normalize_hyphen_range():
    """'2000-2025' -> '2000-2026'."""
    result = _normalize_date_range("Date range: 2000-2025.", "2000", "2026")
    assert "2000-2026" in result
    assert "2000-2025" not in result


def test_normalize_between_x_and_y():
    """'between 2000 and 2025' -> 'between 2000 and 2026'."""
    result = _normalize_date_range("Published between 2000 and 2025 were eligible.", "2000", "2026")
    assert "between 2000 and 2026" in result


def test_normalize_does_not_affect_unrelated_years():
    """Years not matching date_start should be left alone."""
    result = _normalize_date_range(
        "The hospital opened in 1985. Studies from 2000 to 2025 included.",
        "2000",
        "2026",
    )
    assert "1985" in result
    assert "from 2000 to 2026" in result


def test_normalize_already_correct_unchanged():
    """Already correct date range should not be double-replaced."""
    text = "Studies from 2000 to 2026 were included."
    result = _normalize_date_range(text, "2000", "2026")
    assert result == text


# ---------------------------------------------------------------------------
# Fix 4b: build_picos_table date normalization in inclusion criteria
# ---------------------------------------------------------------------------


def test_picos_table_inclusion_criteria_date_normalized():
    """Inclusion criteria text with wrong end year gets normalized."""
    config = SimpleNamespace(
        pico=SimpleNamespace(
            population="Adult participants",
            intervention="Structured intervention",
            comparison="Control condition",
            outcome="Primary outcome measure",
            study_design=None,
            study_designs=None,
        ),
        inclusion_criteria=["Research published between 2000 and 2025 is included."],
        exclusion_criteria=[],
        date_range_start=2000,
        date_range_end=2026,
        review_type="systematic",
        author_name="",
        protocol=SimpleNamespace(registered=False, registration_number=""),
        funding=SimpleNamespace(source=""),
        conflicts_of_interest="",
    )
    table = build_picos_table(config)
    assert "2026" in table
    assert "2025" not in table


# ---------------------------------------------------------------------------
# Fix 2 integration: assemble_submission_manuscript threads fulltext_paper_ids
# ---------------------------------------------------------------------------


def test_assemble_manuscript_with_fulltext_ids(tmp_path: Path) -> None:
    """assemble_submission_manuscript passes fulltext_paper_ids to the table builder."""
    body = "## Results\n\nFindings here.\n"
    papers = [_make_paper("p1")]
    records = [_make_extraction("p1", extraction_source="text")]

    result = assemble_submission_manuscript(
        body=body,
        manuscript_path=tmp_path / "ms.md",
        artifacts={},
        citation_rows=[],
        papers=papers,
        extraction_records=records,
        fulltext_paper_ids={"p1"},
    )
    # p1 has a file -> Full Text Retrieved should say Yes in the study table
    assert "Yes" in result


def test_assemble_manuscript_without_fulltext_ids_shows_no(tmp_path: Path) -> None:
    """Without fulltext_paper_ids and extraction_source=text -> Full Text Retrieved: No."""
    body = "## Results\n\nFindings here.\n"
    papers = [_make_paper("p1")]
    records = [_make_extraction("p1", extraction_source="text")]

    result = assemble_submission_manuscript(
        body=body,
        manuscript_path=tmp_path / "ms.md",
        artifacts={},
        citation_rows=[],
        papers=papers,
        extraction_records=records,
        fulltext_paper_ids=None,
    )
    assert "No" in result
