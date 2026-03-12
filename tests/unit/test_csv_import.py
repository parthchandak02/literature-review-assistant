from __future__ import annotations

from pathlib import Path

import pytest

from src.models.enums import SourceCategory
from src.models.papers import CandidatePaper
from src.search.csv_import import parse_masterlist_csv, validate_csv_file
from src.search.deduplication import deduplicate_papers


def test_parse_masterlist_csv_parses_scopus_headers(tmp_path: Path) -> None:
    csv_path = tmp_path / "masterlist.csv"
    csv_path.write_text(
        "Authors,Title,Year,Source title,DOI,Link,Abstract,Author Keywords\n"
        '"A. Author; B. Author","Test Paper",2024,"Journal X","10.1000/abc","https://example.org","Some abstract","kw1; kw2"\n',
        encoding="utf-8",
    )

    result = parse_masterlist_csv(str(csv_path), workflow_id="wf-test")
    assert result.records_retrieved == 1
    assert result.database_name == "CSV Import"
    assert result.papers[0].title == "Test Paper"
    assert result.papers[0].doi == "10.1000/abc"
    assert result.papers[0].source_category == SourceCategory.OTHER_SOURCE


def test_parse_masterlist_csv_missing_title_column_raises(tmp_path: Path) -> None:
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("Authors,Year\nA. Author,2024\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Title column"):
        parse_masterlist_csv(str(csv_path), workflow_id="wf-test")


def test_validate_csv_file_rejects_empty(tmp_path: Path) -> None:
    csv_path = tmp_path / "empty.csv"
    csv_path.write_bytes(b"")

    with pytest.raises(ValueError, match="empty"):
        validate_csv_file(str(csv_path))


def test_parse_masterlist_csv_handles_cp1252_and_semicolon(tmp_path: Path) -> None:
    csv_path = tmp_path / "latin.csv"
    content = (
        "Authors;Title;Year;Source title;DOI;Link;Abstract;Author Keywords\n"
        'A. Author;Therapy efficacy;2023;Journal Y;10.1000/xyz;https://example.org;Summary;"term1,term2"\n'
    )
    csv_path.write_bytes(content.encode("cp1252"))

    result = parse_masterlist_csv(str(csv_path), workflow_id="wf-test")
    assert result.records_retrieved == 1
    assert result.papers[0].title == "Therapy efficacy"


def test_deduplicate_prefers_richer_metadata_for_same_doi() -> None:
    poorer = CandidatePaper(
        paper_id="p1",
        title="Shared Title",
        authors=["A"],
        year=2022,
        source_database="scopus",
        doi="10.1000/shared",
        abstract=None,
        url=None,
        keywords=None,
    )
    richer = CandidatePaper(
        paper_id="p2",
        title="Shared Title",
        authors=["A", "B", "C"],
        year=2022,
        source_database="openalex",
        doi="10.1000/shared",
        abstract="This is a richer abstract with detail.",
        url="https://example.org",
        keywords=["k1", "k2"],
    )

    deduped, duplicates = deduplicate_papers([poorer, richer])
    assert duplicates == 1
    assert len(deduped) == 1
    assert deduped[0].abstract is not None
    assert deduped[0].url == "https://example.org"
