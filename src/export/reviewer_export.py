"""Reviewer-facing formatting for PRISMA supplementary CSV exports."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from src.prisma.diagram import _format_source_label

_API_HOST_FRAGMENTS = (
    "api.elsevier.com",
    "api.semanticscholar.org",
    "api.openalex.org",
    "api.crossref.org",
    "localhost",
    "127.0.0.1",
)

_DOI_PREFIX_RE = re.compile(r"^https?://(dx\.)?doi\.org/", re.IGNORECASE)


def format_information_source(source_database: str | None) -> str:
    """Human-readable bibliographic source name for supplementary tables."""
    if not source_database or not str(source_database).strip():
        return "Other"
    return _format_source_label(str(source_database))


def format_identification_type(source_category: str | None) -> str:
    """PRISMA 2020 identification column label."""
    if str(source_category or "").strip().lower() == "other_source":
        return "Other source"
    return "Database"


def _clean_doi_token(doi: str | None) -> str | None:
    if not doi or not str(doi).strip():
        return None
    cleaned = str(doi).strip()
    cleaned = _DOI_PREFIX_RE.sub("", cleaned)
    return cleaned.strip() or None


def _is_api_or_internal_url(url: str) -> bool:
    lowered = url.strip().lower()
    if not lowered.startswith(("http://", "https://")):
        return True
    try:
        host = (urlparse(lowered).netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        return any(fragment in host for fragment in _API_HOST_FRAGMENTS)
    except Exception:
        return True


def _doi_from_url(url: str) -> str | None:
    """Extract DOI from scopus inward URI or other query-string DOI parameters."""
    try:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        for key in ("doi", "DOI"):
            if key in query and query[key]:
                return _clean_doi_token(query[key][0])
    except Exception:
        pass
    return None


def reviewer_record_link(
    *,
    doi: str | None,
    url: str | None,
    openalex_id: str | None = None,
) -> str:
    """Return a reviewer-friendly persistent link (DOI preferred; no API endpoints)."""
    doi_token = _clean_doi_token(doi)
    if doi_token:
        return f"https://doi.org/{doi_token}"

    if url and not _is_api_or_internal_url(url):
        url_doi = _doi_from_url(url)
        if url_doi:
            return f"https://doi.org/{url_doi}"
        return url.strip()

    if openalex_id and str(openalex_id).strip():
        oid = str(openalex_id).strip()
        if oid.startswith("http"):
            if not _is_api_or_internal_url(oid):
                return oid
        else:
            work_id = oid if oid.startswith("W") else f"W{oid}"
            return f"https://openalex.org/{work_id}"

    return ""
