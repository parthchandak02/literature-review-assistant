"""Fulltext DOI normalizer must strip labels and resolver URLs for API queries."""

from __future__ import annotations

import pytest

from src.fulltext.retrieval import _normalize_doi


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("doi:10.1000/xyz", "10.1000/xyz"),
        ("DOI:10.1000/XYZ", "10.1000/xyz"),
        ("https://doi.org/10.1000/abc", "10.1000/abc"),
        ("http://dx.doi.org/10.1000/abc", "10.1000/abc"),
        ("10.1000/abc", "10.1000/abc"),
        ("", ""),
    ],
)
def test_normalize_doi_strips_label_and_resolver_urls(raw: str, expected: str) -> None:
    assert _normalize_doi(raw) == expected
