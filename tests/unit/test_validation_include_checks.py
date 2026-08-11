from __future__ import annotations

from src.web.routers.validation import _parse_include_param


def test_parse_include_param_empty_or_absent() -> None:
    assert _parse_include_param(None) == set()
    assert _parse_include_param("") == set()


def test_parse_include_param_checks() -> None:
    assert _parse_include_param("checks") == {"checks"}
    assert _parse_include_param(" checks ") == {"checks"}
    assert _parse_include_param("checks,other") == {"checks", "other"}
    assert _parse_include_param("checks, other , ") == {"checks", "other"}
