"""Export normalize_doi must build clean https://doi.org/ links."""

from __future__ import annotations

import pytest

from src.export.markdown_utils import normalize_doi


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "https://DOI.org/10.1186/s12909-025-06913-5",
            "https://doi.org/10.1186/s12909-025-06913-5",
        ),
        (
            "http://DOI.org/10.1000/xyz",
            "https://doi.org/10.1000/xyz",
        ),
        (
            "https://doi.org/10.1000/abc",
            "https://doi.org/10.1000/abc",
        ),
        (
            "doi: 10.1186/s12909-025-06913-5",
            "https://doi.org/10.1186/s12909-025-06913-5",
        ),
        (
            "DOI:10.1000/xyz",
            "https://doi.org/10.1000/xyz",
        ),
        (
            "doi.org/10.1000/abc",
            "https://doi.org/10.1000/abc",
        ),
        (
            "DOI.org/10.1000/abc",
            "https://doi.org/10.1000/abc",
        ),
        ("10.1000/abc", "https://doi.org/10.1000/abc"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_doi_handles_case_and_whitespace(raw: str | None, expected: str) -> None:
    assert normalize_doi(raw) == expected


def test_normalize_doi_mixed_case_host_is_not_doubled() -> None:
    """Regression: case-sensitive split left the full URL as the path."""
    result = normalize_doi("https://DOI.org/10.1186/s12909-025-06913-5")
    assert "https://doi.org/https://" not in result
    assert result == "https://doi.org/10.1186/s12909-025-06913-5"
