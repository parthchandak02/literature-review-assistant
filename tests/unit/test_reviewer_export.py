"""Unit tests for reviewer-facing PRISMA export formatting."""

from __future__ import annotations

from src.export.reviewer_export import (
    format_identification_type,
    format_information_source,
    reviewer_record_link,
)


def test_format_information_source_labels() -> None:
    assert format_information_source("scopus") == "Scopus"
    assert format_information_source("ieee_xplore") == "IEEE Xplore"
    assert format_information_source("other") == "Other"


def test_format_identification_type_prisma_columns() -> None:
    assert format_identification_type("database") == "Database"
    assert format_identification_type("other_source") == "Other source"


def test_reviewer_record_link_prefers_doi() -> None:
    link = reviewer_record_link(
        doi="10.1186/s12909-025-06913-5",
        url="https://api.elsevier.com/content/abstract/scopus_id/123",
    )
    assert link == "https://doi.org/10.1186/s12909-025-06913-5"


def test_reviewer_record_link_strips_api_url_without_doi() -> None:
    link = reviewer_record_link(
        doi=None,
        url="https://api.elsevier.com/content/abstract/scopus_id/123",
    )
    assert link == ""


def test_reviewer_record_link_uses_public_publisher_url() -> None:
    link = reviewer_record_link(
        doi=None,
        url="https://ieeexplore.ieee.org/document/12345678",
    )
    assert link == "https://ieeexplore.ieee.org/document/12345678"


def test_reviewer_record_link_extracts_doi_from_scopus_inward_uri() -> None:
    link = reviewer_record_link(
        doi=None,
        url=(
            "https://www.scopus.com/inward/record.uri?eid=2-s2.0-1"
            "&doi=10.54079%2Fjpmi.39.4.3759"
        ),
    )
    assert link == "https://doi.org/10.54079/jpmi.39.4.3759"
