"""PROSPERO registration ID format validation."""

from __future__ import annotations

import re

_PROSPERO_ID_PATTERN = re.compile(r"^CRD\d{9,}$")


def validate_prospero_id(value: str) -> str:
    """Return normalized PROSPERO ID or raise ValueError when format is invalid."""
    normalized = str(value or "").strip().upper()
    if not _PROSPERO_ID_PATTERN.fullmatch(normalized):
        raise ValueError("PROSPERO registration number must match CRD followed by at least 9 digits")
    return normalized
