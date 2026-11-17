from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from src.models.enums import SourceCategory
from src.models.papers import CandidatePaper
from src.search.csv_import import _clean_doi, parse_masterlist_csv, validate_csv_file
from src.search.deduplication import deduplicate_papers


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("doi:10.1000/xyz", "10.1000/xyz"),
        ("DOI:10.1000/XYZ", "10.1000/XYZ"),
        ("https://doi.org/10.1000/abc", "10.1000/abc"),
        ("https://dx.doi.org/10.1000/abc", "10.1000/abc"),
        ("10.1000/abc", "10.1000/abc"),
        ("", None),
    ],
)
def test_clean_doi_strips_label_and_resolver_urls(raw: str, expected: str | None) -> None:
    assert _clean_doi(raw) == expected


def test_parse_masterlist_csv_parses_scopus_headers(tmp_path: Path) -> None:
    csv_path = tmp_path / "masterlist.csv"
    csv_path.write_text(
        "Authors,Title,Year,Source title,DOI,Link,Abstract,Author Keywords\n"
        '"A. Author; B. Author","Test Paper",2024,"Journal X","10.1000/abc",'
        '"https://www.scopus.com/inward/record.uri?eid=2-s2.0-123","Some abstract","kw1; kw2"\n',
        encoding="utf-8",
    )

    results = parse_masterlist_csv(str(csv_path), workflow_id="wf-test")
    assert len(results) == 1
    result = results[0]
    assert result.records_retrieved == 1
    assert result.database_name == "scopus"
    assert result.papers[0].title == "Test Paper"
    assert result.papers[0].doi == "10.1000/abc"
    assert result.papers[0].journal == "Journal X"
    assert result.papers[0].source_database == "scopus"
    assert result.papers[0].source_category == SourceCategory.DATABASE


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
        "A. Author;Therapy efficacy;2023;Journal Y;10.1000/xyz;"
        "https://www.scopus.com/inward/record.uri?eid=2-s2.0-456;Summary;term1,term2\n"
    )
    csv_path.write_bytes(content.encode("cp1252"))

    results = parse_masterlist_csv(str(csv_path), workflow_id="wf-test")
    assert results[0].records_retrieved == 1
    assert results[0].papers[0].title == "Therapy efficacy"


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


def test_deduplicate_treats_doi_url_and_token_as_same() -> None:
    as_url = CandidatePaper(
        paper_id="u1",
        title="Automation in outpatient pharmacy",
        authors=["A. One"],
        year=2024,
        source_database="openalex",
        doi="https://doi.org/10.1000/shared",
        abstract="URL DOI format",
    )
    as_token = CandidatePaper(
        paper_id="u2",
        title="Automation in outpatient pharmacy",
        authors=["A. One", "B. Two"],
        year=2024,
        source_database="pubmed",
        doi="10.1000/shared",
        abstract="Token DOI format with richer metadata.",
        url="https://example.org/paper",
    )

    deduped, duplicates = deduplicate_papers([as_url, as_token])
    assert duplicates == 1
    assert len(deduped) == 1
    assert deduped[0].doi in {"10.1000/shared", "https://doi.org/10.1000/shared"}


def _paper(
    paper_id: str,
    *,
    title: str = "Effects of Automation on Pharmacy Safety",
    authors: list[str] | None = None,
    year: int = 2020,
    source_database: str = "pubmed",
    doi: str | None = None,
    pmid: str | None = None,
    abstract: str | None = None,
    url: str | None = None,
    keywords: list[str] | None = None,
) -> CandidatePaper:
    return CandidatePaper(
        paper_id=paper_id,
        title=title,
        authors=["A. Author"] if authors is None else authors,
        year=year,
        source_database=source_database,
        doi=doi,
        pmid=pmid,
        abstract=abstract,
        url=url,
        keywords=keywords,
    )


def test_deduplicate_keeps_doi_when_richer_record_has_none() -> None:
    """A longer abstract must not drop a DOI, PMID, URL, or keywords held by the other record."""
    long_abstract = (
        "A longer abstract covering the cohort, the intervention, "
        "and the measured safety outcomes in outpatient pharmacy practice."
    )
    thin = _paper(paper_id="thin-doi", doi="10.1000/abc", pmid="123456", abstract="Short.")
    rich = _paper(
        paper_id="rich-nodoi",
        authors=["A. Author", "B. Author", "C. Author"],
        year=2021,
        source_database="scopus",
        doi=None,
        abstract=long_abstract,
        url="https://example.org/pharmacy-safety",
        keywords=["automation", "safety"],
    )

    deduped, duplicates = deduplicate_papers([thin, rich])
    assert duplicates == 1
    assert len(deduped) == 1
    kept = deduped[0]
    assert kept.doi == "10.1000/abc"
    assert kept.pmid == "123456"
    assert kept.abstract == long_abstract
    assert kept.url == "https://example.org/pharmacy-safety"
    assert kept.keywords == ["automation", "safety"]


def test_deduplicate_keeps_longer_abstract_when_doi_record_is_richer() -> None:
    long_abstract = "This abstract is long enough to beat a one-line summary on length alone."
    with_doi = _paper(
        paper_id="doi-richer",
        authors=["A. Author", "B. Author", "C. Author", "D. Author", "E. Author", "F. Author"],
        doi="10.1000/kept",
        abstract="Short.",
    )
    without_doi = _paper(
        paper_id="meta-only",
        source_database="openalex",
        abstract=long_abstract,
        pmid="999888",
        url="https://example.org/longer",
        keywords=["pharmacy"],
    )

    deduped, duplicates = deduplicate_papers([with_doi, without_doi])
    assert duplicates == 1
    assert len(deduped) == 1
    kept = deduped[0]
    assert kept.doi == "10.1000/kept"
    assert kept.abstract == long_abstract
    assert kept.pmid == "999888"
    assert kept.url == "https://example.org/longer"
    assert kept.keywords == ["pharmacy"]


def test_deduplicate_treats_doi_label_and_url_as_same() -> None:
    labeled = _paper(
        paper_id="labeled",
        title="Alpha Study of Outpatient Widgets",
        doi="doi:10.1000/abc",
        abstract="Labeled DOI.",
    )
    as_url = _paper(
        paper_id="url-form",
        title="Unrelated Beta Report on Supply Chains",
        source_database="openalex",
        doi="https://doi.org/10.1000/abc",
        abstract="URL DOI.",
    )
    as_dx = _paper(
        paper_id="dx-form",
        title="Gamma Note on Warehouse Routing",
        source_database="embase",
        doi="https://dx.doi.org/10.1000/abc",
        abstract="DX DOI.",
    )

    deduped, duplicates = deduplicate_papers([labeled, as_url, as_dx])
    assert duplicates == 2
    assert len(deduped) == 1


def test_deduplicate_keeps_doi_on_minhash_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.search.deduplication.BRUTE_FORCE_THRESHOLD", 0)
    long_abstract = "A longer abstract that should survive MinHash title clustering with the DOI intact."
    thin = _paper(paper_id="mh-thin", doi="10.1000/minhash", pmid="42", abstract="Short.")
    rich = _paper(
        paper_id="mh-rich",
        authors=["A. Author", "B. Author", "C. Author"],
        source_database="scopus",
        abstract=long_abstract,
        url="https://example.org/mh",
        keywords=["minhash"],
    )

    deduped, duplicates = deduplicate_papers([thin, rich])
    assert duplicates == 1
    assert len(deduped) == 1
    kept = deduped[0]
    assert kept.doi == "10.1000/minhash"
    assert kept.pmid == "42"
    assert kept.abstract == long_abstract
    assert kept.url == "https://example.org/mh"
    assert kept.keywords == ["minhash"]


def test_deduplicate_default_fuzzy_threshold_stays_90() -> None:
    default = inspect.signature(deduplicate_papers).parameters["fuzzy_threshold"].default
    assert default == 90
