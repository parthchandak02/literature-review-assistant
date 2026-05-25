"""Shared markdown export utility helpers."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

_SUMMARY_HTML_BOILERPLATE_MARKERS = (
    "<!doctype html>",
    "<html",
    "<head>",
    "<body",
    "access denied",
    "just a moment",
)
_SUMMARY_PDF_METADATA_PREFIXES = (
    "pdf",
    "downloaded from",
    "copyright",
)
_SUMMARY_LLM_EXPLANATION_PHRASES = (
    "the provided text",
    "available excerpt",
)
_ABSTRACT_ONLY_SOURCES = frozenset({"text", "heuristic", None, ""})


def sanitize_summary_text(raw_text: str) -> str:
    summary = (raw_text or "").strip()
    if not summary:
        return "NR"
    summary_lower = summary.lower().lstrip()
    is_boilerplate = any(marker in summary_lower for marker in _SUMMARY_HTML_BOILERPLATE_MARKERS)
    is_pdf_metadata = any(summary_lower.startswith(pfx) for pfx in _SUMMARY_PDF_METADATA_PREFIXES)
    is_llm_explanation = any(phrase in summary_lower for phrase in _SUMMARY_LLM_EXPLANATION_PHRASES)
    if "doi.org/" in summary_lower or re.search(r"\bdoi:\s*10\.\S+", summary_lower):
        return "NR"
    if is_boilerplate or is_pdf_metadata or is_llm_explanation:
        return "NR"
    return summary


def clip_table_text(text: str, max_chars: int) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) <= max_chars:
        return cleaned
    window = cleaned[:max_chars].rstrip()
    sentence_break = max(window.rfind(". "), window.rfind("; "), window.rfind(": "))
    if sentence_break > int(max_chars * 0.6):
        window = window[: sentence_break + 1].rstrip()
    return window + "..."


def missing_result_display(rec: Any) -> str:
    source = getattr(rec, "extraction_source", None)
    if source in _ABSTRACT_ONLY_SOURCES:
        return "No extractable result reported (abstract/metadata only)."
    return "No extractable result reported in available text."


def ascii_citekey(key: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", key) if unicodedata.category(c) != "Mn")


def validate_doi_year(doi: str | None, cited_year: int | None) -> str | None:
    if not doi or not cited_year:
        return None
    m = re.search(r"10\.1016/\S+?\.(\d{4})\.\d", doi)
    if m:
        doi_year = int(m.group(1))
        if abs(doi_year - cited_year) > 1:
            return (
                f"DOI year mismatch: DOI encodes {doi_year} but citation year is {cited_year}. "
                f"Verify publication year for DOI {doi[:60]}."
            )
    return None


def normalize_doi(doi: str | None) -> str:
    if not doi:
        return ""
    doi = doi.strip()
    if not doi:
        return ""
    if doi.lower().startswith("https://doi.org/") or doi.lower().startswith("http://doi.org/"):
        return f"https://doi.org/{doi.split('doi.org/', 1)[-1]}"
    if doi.lower().startswith("doi.org/"):
        return f"https://{doi}"
    if doi.lower().startswith("doi:"):
        return f"https://doi.org/{doi[4:].lstrip('/')}"
    if doi.startswith("10."):
        return f"https://doi.org/{doi}"
    return doi
