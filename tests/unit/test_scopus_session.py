"""Unit tests for Scopus session gateway helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.search.scopus_session import (
    _netscape_cookies_to_header,
    gateway_item_to_candidate,
    load_scopus_session_cookie,
)


def test_netscape_cookies_to_header_filters_domains() -> None:
    text = "\n".join(
        [
            "# Netscape HTTP Cookie File",
            ".scopus.com\tTRUE\t/\tTRUE\t0\tSCSessionID\tabc123",
            ".example.com\tTRUE\t/\tTRUE\t0\tignored\tvalue",
            ".elsevier.com\tTRUE\t/\tTRUE\t0\telsevier_cookie\txyz",
        ]
    )
    header = _netscape_cookies_to_header(text)
    assert header is not None
    assert "SCSessionID=abc123" in header
    assert "elsevier_cookie=xyz" in header
    assert "ignored=value" not in header


def test_raw_cookie_header_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "cookies.txt"
    path.write_text("SCSessionID=raw-header; JSESSIONID=abc", encoding="utf-8")
    monkeypatch.setenv("SCOPUS_SESSION_COOKIE_FILE", str(path))
    assert load_scopus_session_cookie() == "SCSessionID=raw-header; JSESSIONID=abc"


def test_gateway_item_to_candidate_maps_rich_fields() -> None:
    paper = gateway_item_to_candidate(
        {
            "title": "Pickleball and health",
            "doi": "10.1234/example",
            "eid": "2-s2.0-123",
            "pubYear": 2024,
            "abstractText": ["Objective <em>test</em> abstract"],
            "authors": [{"preferredName": {"full": "Smith J."}}],
            "source": {"title": "Sports Medicine"},
        }
    )
    assert paper.title == "Pickleball and health"
    assert paper.doi == "10.1234/example"
    assert paper.year == 2024
    assert paper.abstract == "Objective test abstract"
    assert paper.journal == "Sports Medicine"
    assert paper.url == "https://www.scopus.com/inward/record.uri?eid=2-s2.0-123"


def test_load_scopus_session_cookie_missing_file_returns_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    missing = tmp_path / "missing-cookies.txt"
    monkeypatch.setenv("SCOPUS_SESSION_COOKIE_FILE", str(missing))
    assert load_scopus_session_cookie() is None
