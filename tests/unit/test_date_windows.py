"""Eligibility date-window helpers used by writing and export grounding."""

from __future__ import annotations

import pytest

from src.writing.date_windows import (
    format_search_eligibility_window,
    normalize_criteria_date_windows,
)


@pytest.mark.parametrize(
    ("date_start", "date_end", "expected"),
    [
        ("2000", "2026", "2000-2026"),
        ("2000", None, "2000-present"),
        ("2000", "", "2000-present"),
        (None, "2026", ""),
        ("", "", ""),
        (None, None, ""),
        (2000, 2026, "2000-2026"),
    ],
)
def test_format_search_eligibility_window(
    date_start: object | None,
    date_end: object | None,
    expected: str,
) -> None:
    assert format_search_eligibility_window(date_start, date_end) == expected


def test_normalize_criteria_date_windows_no_canonical_keeps_nonempty() -> None:
    assert normalize_criteria_date_windows(
        ["  Studies from 2000 to 2020  ", "", "  ", None],  # type: ignore[list-item]
        "",
    ) == ["Studies from 2000 to 2020"]


def test_normalize_criteria_replaces_between_and_from_to_phrases() -> None:
    criteria = [
        "Published between January 2000 and December 2020",
        "Included from January 2010 to December 2022",
        "Records from January 1, 2015 to December 31, 2024",
    ]
    out = normalize_criteria_date_windows(criteria, "2000-2026")
    assert out == [
        "Published 2000-2026",
        "Included 2000-2026",
        "Records 2000-2026",
    ]


def test_normalize_criteria_replaces_year_ranges_including_dash_variants() -> None:
    en_dash = "\u2013"
    em_dash = "\u2014"
    criteria = [
        "Years 2010-2020 were eligible",
        f"Years 2010{en_dash}2020 were eligible",
        f"Years 2010{em_dash}present were eligible",
        "Years 2010 to the present were eligible",
    ]
    out = normalize_criteria_date_windows(criteria, "2000-2026")
    assert out == [
        "Years 2000-2026 were eligible",
        "Years 2000-2026 were eligible",
        "Years 2000-2026 were eligible",
        "Years 2000-2026 were eligible",
    ]


def test_normalize_criteria_rewrites_standalone_since_and_published_after() -> None:
    criteria = [
        "Studies published since 2018",
        "Papers published after 2015 in English",
        "from 2012 onwards",
    ]
    out = normalize_criteria_date_windows(criteria, "2000-2026")
    assert out == [
        "Studies published since 2000-2026",
        "Papers published after 2000-2026 in English",
        "from 2000-2026 onwards",
    ]


def test_normalize_criteria_collapses_extra_whitespace() -> None:
    out = normalize_criteria_date_windows(
        ["Eligible  between   2010  and  2020   only"],
        "2000-2026",
    )
    assert out == ["Eligible 2000-2026 only"]


def test_normalize_criteria_does_not_double_append_after_from_or_since_range() -> None:
    en_dash = "\u2013"
    criteria = [
        "Published from 2010-2024",
        "Studies since 2010 to present",
        f"Records from 2010{en_dash}2020 in English",
        "published since 2015",
    ]
    out = normalize_criteria_date_windows(criteria, "2010-2024")
    assert out == [
        "Published from 2010-2024",
        "Studies since 2010-2024",
        "Records from 2010-2024 in English",
        "published since 2010-2024",
    ]
    assert normalize_criteria_date_windows(["Studies since 2010 to present"], "2010-present") == [
        "Studies since 2010-present"
    ]
