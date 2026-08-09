"""Unit tests for CSV/URL source inference."""

from __future__ import annotations

import pytest

from src.models.enums import SourceCategory
from src.search.source_inference import (
    detect_csv_export_format,
    infer_csv_row_source,
    infer_source_from_url,
)


@pytest.mark.parametrize(
    "url,expected",
    [
        (
            "https://www.scopus.com/inward/record.uri?eid=2-s2.0-105027545920&doi=10.54079/jpmi.39.4.3759",
            "scopus",
        ),
        ("https://pubmed.ncbi.nlm.nih.gov/12345678/", "pubmed"),
        ("https://pmc.ncbi.nlm.nih.gov/articles/PMC12058729/", "pubmed"),
        ("https://ieeexplore.ieee.org/document/12345678", "ieee_xplore"),
        ("https://www.semanticscholar.org/paper/abc123", "semantic_scholar"),
        ("https://openalex.org/W12345678", "openalex"),
        ("https://arxiv.org/abs/2401.12345", "arxiv"),
    ],
)
def test_infer_source_from_url_index_patterns(url: str, expected: str) -> None:
    db, cat = infer_source_from_url(url)
    assert db == expected
    assert cat == SourceCategory.DATABASE


def test_doi_resolver_uses_file_hint_not_crossref() -> None:
    db, cat = infer_source_from_url(
        "http://dx.doi.org/10.1186/s12909-024-05892-3",
        file_hint="scopus",
    )
    assert db == "scopus"
    assert cat == SourceCategory.DATABASE


def test_doi_resolver_without_hint_is_crossref() -> None:
    db, _ = infer_source_from_url("http://dx.doi.org/10.1186/s12909-024-05892-3")
    assert db == "crossref"


def test_empty_url_uses_file_hint() -> None:
    db, cat = infer_source_from_url(None, file_hint="scopus")
    assert db == "scopus"
    assert cat == SourceCategory.DATABASE


def test_detect_scopus_export_format() -> None:
    fieldnames = ["Authors", "Title", "Year", "Source title", "DOI", "Link", "Abstract", "Author Keywords"]
    samples = [
        "https://www.scopus.com/inward/record.uri?eid=2-s2.0-105027545920",
        "http://dx.doi.org/10.1186/s12909-024-05892-3",
    ]
    assert detect_csv_export_format(fieldnames, samples) == "scopus"


def test_infer_csv_row_scopus_inward_uri() -> None:
    row = {
        "Link": "https://www.scopus.com/inward/record.uri?eid=2-s2.0-1",
        "DOI": "10.1000/abc",
        "Source title": "Journal X",
    }
    fieldnames = list(row.keys()) + ["Author Keywords"]
    db, cat = infer_csv_row_source(
        url=row["Link"],
        doi=row["DOI"],
        explicit_database=None,
        row=row,
        fieldnames=fieldnames,
        file_hint=None,
    )
    assert db == "scopus"
    assert cat == SourceCategory.DATABASE


def test_infer_csv_row_doi_only_scopus_export() -> None:
    row = {"Link": "http://dx.doi.org/10.1186/s12909-024-05892-3", "DOI": "10.1186/s12909-024-05892-3"}
    fieldnames = ["Authors", "Title", "Year", "Source title", "DOI", "Link", "Abstract", "Author Keywords"]
    db, cat = infer_csv_row_source(
        url=row["Link"],
        doi=row["DOI"],
        explicit_database=None,
        row=row,
        fieldnames=fieldnames,
        file_hint="scopus",
    )
    assert db == "scopus"
    assert cat == SourceCategory.DATABASE


def test_infer_csv_row_empty_link_scopus_export() -> None:
    row = {"Link": "", "DOI": ""}
    fieldnames = ["Authors", "Title", "Year", "Source title", "DOI", "Link", "Abstract", "Author Keywords"]
    db, cat = infer_csv_row_source(
        url=None,
        doi=None,
        explicit_database=None,
        row=row,
        fieldnames=fieldnames,
        file_hint="scopus",
    )
    assert db == "scopus"
    assert cat == SourceCategory.DATABASE


def test_infer_csv_row_other_last_resort() -> None:
    row = {"Link": "", "DOI": ""}
    fieldnames = ["Title", "Authors"]
    db, cat = infer_csv_row_source(
        url=None,
        doi=None,
        explicit_database=None,
        row=row,
        fieldnames=fieldnames,
        file_hint=None,
    )
    assert db == "other"
    assert cat == SourceCategory.OTHER_SOURCE


def test_infer_csv_row_bare_doi_without_hint_is_other() -> None:
    """CSV imports must not attribute bare DOI to Crossref for PRISMA database counts."""
    row = {"Link": "", "DOI": "10.1186/s12909-024-05892-3"}
    fieldnames = ["Title", "Authors", "DOI", "Link"]
    db, cat = infer_csv_row_source(
        url=None,
        doi=row["DOI"],
        explicit_database=None,
        row=row,
        fieldnames=fieldnames,
        file_hint=None,
    )
    assert db == "other"
    assert cat == SourceCategory.OTHER_SOURCE
