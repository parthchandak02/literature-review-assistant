"""Shared helpers for protocol eligibility date-window normalization."""

from __future__ import annotations

import re


def format_search_eligibility_window(date_start: object | None, date_end: object | None) -> str:
    """Return canonical eligibility window string from config values."""
    start = str(date_start or "").strip()
    end = str(date_end or "").strip()
    if start and end:
        return f"{start}-{end}"
    if start:
        return f"{start}-present"
    return ""


def normalize_criteria_date_windows(criteria: list[str], canonical_window: str) -> list[str]:
    """Normalize free-text criteria date phrases to one canonical window."""
    if not canonical_window:
        return [str(item or "").strip() for item in criteria if str(item or "").strip()]

    month = (
        r"(?:January|February|March|April|May|June|"
        r"July|August|September|October|November|December)\s+"
    )
    range_patterns = (
        # "between 2000 and 2026" / "between January 2000 and December 2026"
        re.compile(
            r"\bbetween\s+(?:" + month + r")?\d{4}\s+and\s+(?:" + month + r")?(?:\d{4}|present|the present)\b",
            flags=re.IGNORECASE,
        ),
        # "from 2000 to 2026" / "from January 1, 2000 to December 31, 2026"
        re.compile(
            r"\bfrom\s+(?:" + month + r")?(?:\d{1,2},?\s+)?\d{4}\s+to\s+(?:" + month + r")?"
            r"(?:\d{1,2},?\s+)?(?:\d{4}|present|the present)\b",
            flags=re.IGNORECASE,
        ),
        # "2000-2026", "2000 to 2026", "2000 to present"
        re.compile(
            r"\b\d{4}\s*(?:to|-|[\u2013\u2014])\s*(?:\d{4}|present|the present)\b",
            flags=re.IGNORECASE,
        ),
    )
    standalone_year_re = re.compile(
        r"\b(?P<prefix>published\s+(?:after|from|since)|from|since)\s+(?P<year>\d{4})\b",
        flags=re.IGNORECASE,
    )
    normalized: list[str] = []
    for item in criteria:
        txt = str(item or "").strip()
        if not txt:
            continue
        for pat in range_patterns:
            txt = pat.sub(canonical_window, txt)
        txt = standalone_year_re.sub(lambda m: f"{m.group('prefix')} {canonical_window}", txt)
        normalized.append(re.sub(r"\s{2,}", " ", txt).strip())
    return normalized
