"""Multimodal PDF table extraction and full-text retrieval.

Full-text retrieval uses a 3-tier chain:
  1. ScienceDirect Article Retrieval API -- confirmed returning 100KB+ full text
     for Elsevier open-access papers using the standard SCOPUS_API_KEY.
  2. Unpaywall open-access PDF -- covers ~50% of recent papers, no auth needed.
  3. PubMed Central XML -- covers NIH-funded OA papers via the NCBI E-utilities.
  Fallback: empty string (caller uses paper.abstract instead).

Table extraction uses Gemini vision to parse quantitative outcome data from PDF
bytes returned by Unpaywall. Falls back gracefully if no PDF is available or
the API call fails.

Every LLM call is the caller's responsibility for cost tracking.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Optional

import aiohttp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants for the full-text retrieval tiers
# ---------------------------------------------------------------------------
_SD_BASE = "https://api.elsevier.com/content/article/doi"
_UNPAYWALL_BASE = "https://api.unpaywall.org/v2"
_PMC_FETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
_PMC_SEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
_FT_TIMEOUT = 20  # seconds per tier
# ScienceDirect returns non-OA papers as <500 chars -- treat as miss.
_SD_MIN_CHARS = 500


@dataclass
class FullTextResult:
    """Result from a full-text retrieval attempt."""

    text: str
    source: str  # "sciencedirect" | "unpaywall_text" | "pmc" | "abstract"
    pdf_bytes: Optional[bytes] = None  # set only when Unpaywall returns a PDF


# ---------------------------------------------------------------------------
# Tier 1: ScienceDirect Article Retrieval API
# ---------------------------------------------------------------------------

async def _fetch_sciencedirect(doi: str, api_key: str) -> Optional[FullTextResult]:
    """Fetch full text from ScienceDirect using the Elsevier Article Retrieval API.

    Returns None when: API key missing, DOI missing, response too small (non-OA),
    or any network/parse error.
    """
    if not doi or not api_key:
        return None
    url = f"{_SD_BASE}/{doi}"
    headers = {"X-ELS-APIKey": api_key, "Accept": "application/json"}
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=_FT_TIMEOUT)) as resp:
                if resp.status != 200:
                    logger.debug("ScienceDirect: HTTP %d for doi=%s", resp.status, doi)
                    return None
                payload = await resp.json(content_type=None)
        orig = payload.get("full-text-retrieval-response", {}).get("originalText", "")
        if isinstance(orig, str) and len(orig) >= _SD_MIN_CHARS:
            return FullTextResult(text=orig, source="sciencedirect")
        # dict form means non-OA metadata stub -- treat as miss
        return None
    except Exception as exc:
        logger.debug("ScienceDirect fetch error for doi=%s: %s", doi, exc)
        return None


# ---------------------------------------------------------------------------
# Tier 2: Unpaywall open-access PDF
# ---------------------------------------------------------------------------

async def _fetch_unpaywall(doi: str) -> Optional[FullTextResult]:
    """Fetch open-access PDF bytes via Unpaywall.

    Returns None when: DOI missing, no OA PDF found, or network error.
    The pdf_bytes field is populated; callers pass it to extract_tables_from_pdf.
    """
    if not doi:
        return None
    meta_url = f"{_UNPAYWALL_BASE}/{doi}?email=litreview@app.local"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                meta_url, timeout=aiohttp.ClientTimeout(total=_FT_TIMEOUT)
            ) as resp:
                if resp.status != 200:
                    return None
                meta = await resp.json(content_type=None)

            best = meta.get("best_oa_location") or {}
            pdf_url = best.get("url_for_pdf") or best.get("url") or ""
            if not pdf_url or not pdf_url.startswith("http"):
                # Try first OA location
                for loc in meta.get("oa_locations", []):
                    candidate = loc.get("url_for_pdf") or ""
                    if candidate.startswith("http"):
                        pdf_url = candidate
                        break
            if not pdf_url:
                return None

            async with session.get(
                pdf_url, timeout=aiohttp.ClientTimeout(total=30)
            ) as presp:
                if presp.status != 200:
                    return None
                ct = presp.headers.get("Content-Type", "")
                pdf_bytes = await presp.read()
                if not pdf_bytes:
                    return None
                if "pdf" in ct.lower() or pdf_url.endswith(".pdf"):
                    return FullTextResult(
                        text="",
                        source="unpaywall_pdf",
                        pdf_bytes=pdf_bytes,
                    )
                # HTML/text response -- use as plain text
                text = pdf_bytes.decode("utf-8", errors="replace")
                if len(text) >= _SD_MIN_CHARS:
                    return FullTextResult(text=text, source="unpaywall_text")
                return None
    except Exception as exc:
        logger.debug("Unpaywall fetch error for doi=%s: %s", doi, exc)
        return None


# ---------------------------------------------------------------------------
# Tier 3: PubMed Central full text
# ---------------------------------------------------------------------------

async def _fetch_pmc(doi: str, pmid: Optional[str] = None) -> Optional[FullTextResult]:
    """Fetch full text from PubMed Central via NCBI E-utilities.

    First resolves DOI to PMCID via esearch, then fetches XML via efetch.
    Returns None when: no PMC record, parse error, or network error.
    """
    if not doi and not pmid:
        return None
    pmcid: Optional[str] = None
    try:
        async with aiohttp.ClientSession() as session:
            # Resolve DOI -> PMCID
            search_params = {
                "db": "pmc",
                "term": f"{doi}[DOI]" if doi else f"{pmid}[PMID]",
                "retmode": "json",
                "retmax": "1",
            }
            async with session.get(
                _PMC_SEARCH_URL,
                params=search_params,
                timeout=aiohttp.ClientTimeout(total=_FT_TIMEOUT),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)
            ids = data.get("esearchresult", {}).get("idlist", [])
            if not ids:
                return None
            pmcid = ids[0]

            # Fetch full text XML
            fetch_params = {
                "db": "pmc",
                "id": pmcid,
                "rettype": "xml",
                "retmode": "xml",
            }
            async with session.get(
                _PMC_FETCH_URL,
                params=fetch_params,
                timeout=aiohttp.ClientTimeout(total=_FT_TIMEOUT),
            ) as fresp:
                if fresp.status != 200:
                    return None
                xml_bytes = await fresp.read()

        xml_text = xml_bytes.decode("utf-8", errors="replace")
        # Strip XML tags -- good enough for LLM consumption
        plain = re.sub(r"<[^>]+>", " ", xml_text)
        plain = re.sub(r"\s{2,}", " ", plain).strip()
        if len(plain) >= _SD_MIN_CHARS:
            return FullTextResult(text=plain, source="pmc")
        return None
    except Exception as exc:
        logger.debug("PMC fetch error for doi=%s pmid=%s: %s", doi, pmid, exc)
        return None


# ---------------------------------------------------------------------------
# Public: 3-tier full-text retrieval
# ---------------------------------------------------------------------------

async def fetch_full_text(
    doi: Optional[str] = None,
    url: Optional[str] = None,
    pmid: Optional[str] = None,
    scopus_api_key: Optional[str] = None,
    use_sciencedirect: bool = True,
    use_unpaywall: bool = True,
    use_pmc: bool = True,
) -> FullTextResult:
    """Retrieve full text for a paper using a 3-tier priority chain.

    Priority:
      1. ScienceDirect API (Elsevier OA papers, requires SCOPUS_API_KEY)
      2. Unpaywall open-access PDF (~50% of recent papers, no key needed)
      3. PubMed Central XML (NIH-funded OA papers, no key needed)
      Fallback: empty FullTextResult(text="", source="abstract")

    Args:
        doi: Paper DOI (preferred identifier for all tiers).
        url: Paper URL (used as DOI source if doi missing and url is DOI-like).
        pmid: PubMed ID (fallback for PMC lookup when DOI is absent).
        scopus_api_key: Elsevier API key. Falls back to SCOPUS_API_KEY env var.
        use_sciencedirect: Enable tier 1 (ScienceDirect).
        use_unpaywall: Enable tier 2 (Unpaywall).
        use_pmc: Enable tier 3 (PMC).

    Returns:
        FullTextResult with text (and optionally pdf_bytes for Unpaywall PDFs).
    """
    key = scopus_api_key or os.environ.get("SCOPUS_API_KEY", "")
    effective_doi = doi or ""

    # Tier 1: ScienceDirect
    if use_sciencedirect and effective_doi and key:
        result = await _fetch_sciencedirect(effective_doi, key)
        if result:
            logger.info(
                "fetch_full_text: tier 1 ScienceDirect success for doi=%s (%d chars)",
                effective_doi, len(result.text),
            )
            return result

    # Tier 2: Unpaywall
    if use_unpaywall and effective_doi:
        result = await _fetch_unpaywall(effective_doi)
        if result:
            logger.info(
                "fetch_full_text: tier 2 Unpaywall success for doi=%s source=%s",
                effective_doi, result.source,
            )
            return result

    # Tier 3: PMC
    if use_pmc and (effective_doi or pmid):
        result = await _fetch_pmc(effective_doi, pmid)
        if result:
            logger.info(
                "fetch_full_text: tier 3 PMC success for doi=%s (%d chars)",
                effective_doi, len(result.text),
            )
            return result

    logger.debug(
        "fetch_full_text: all tiers missed for doi=%s -- using abstract fallback",
        effective_doi,
    )
    return FullTextResult(text="", source="abstract")

_TABLE_EXTRACTION_PROMPT = """\
You are a systematic review data extractor specializing in clinical trial result tables.

Examine ALL tables in this document and extract structured outcome data.
For each table row that reports a quantitative result, output one JSON object with:
  - name: outcome measure name (exact from paper, e.g. "HbA1c reduction", "30-day mortality")
  - description: brief description of the outcome
  - effect_size: the reported effect (e.g. "SMD=0.45", "OR=2.1 (95% CI 1.3-3.4)", "MD=-0.8")
  - se: standard error if reported (numeric string, e.g. "0.12")
  - n: sample size for this outcome (e.g. "120")
  - p_value: p-value if reported (e.g. "0.032", "<0.001")
  - ci_lower: lower bound of 95% CI (numeric string)
  - ci_upper: upper bound of 95% CI (numeric string)
  - group: intervention group label if applicable

Return a JSON array of outcome objects. If no quantitative tables are found, return [].
Return ONLY valid JSON -- no markdown, no explanation.
"""


def _extract_tables_sync(
    pdf_bytes: bytes,
    model_name: str,
    api_key: str,
) -> list[dict[str, str]]:
    """Synchronous Gemini vision call -- run in executor."""
    try:
        import google.generativeai as genai  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("google-generativeai not installed; skipping table extraction")
        return []

    if not api_key:
        logger.warning("No GEMINI_API_KEY; skipping table extraction")
        return []

    genai.configure(api_key=api_key)

    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(
            [
                {"mime_type": "application/pdf", "data": pdf_bytes},
                _TABLE_EXTRACTION_PROMPT,
            ]
        )
        raw = response.text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        if isinstance(data, list):
            return [
                {k: str(v) for k, v in item.items() if isinstance(v, (str, int, float))}
                for item in data
                if isinstance(item, dict)
            ]
    except json.JSONDecodeError as exc:
        logger.warning("Table extraction: JSON parse error: %s", exc)
    except Exception as exc:
        logger.warning("Table extraction: vision API error: %s", exc)

    return []


async def extract_tables_from_pdf(
    pdf_bytes: Optional[bytes],
    model_name: str = "gemini-2.5-flash",
    api_key: Optional[str] = None,
) -> list[dict[str, str]]:
    """Extract quantitative outcome tables from PDF bytes via Gemini vision.

    Args:
        pdf_bytes: Raw PDF bytes. If None, returns empty list.
        model_name: Gemini model to use for vision extraction.
        api_key: Gemini API key. Falls back to GEMINI_API_KEY env var.

    Returns:
        List of outcome dicts with keys: name, description, effect_size,
        se, n, p_value, ci_lower, ci_upper, group.
    """
    if not pdf_bytes:
        return []

    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        return []

    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _extract_tables_sync, pdf_bytes, model_name, key
    )


def merge_outcomes(
    text_outcomes: list[dict[str, str]],
    vision_outcomes: list[dict[str, str]],
) -> tuple[list[dict[str, str]], str]:
    """Merge text-extracted and vision-extracted outcomes, deduplicating by name.

    Returns (merged_outcomes, extraction_source) where extraction_source is one
    of 'text', 'pdf_vision', or 'hybrid'.
    """
    if not vision_outcomes:
        return text_outcomes, "text"
    if not text_outcomes:
        return vision_outcomes, "pdf_vision"

    # Merge: vision outcomes take precedence for numeric fields when both exist
    name_to_outcome: dict[str, dict[str, str]] = {}
    for o in text_outcomes:
        name = o.get("name", "").lower().strip()
        if name:
            name_to_outcome[name] = dict(o)

    for o in vision_outcomes:
        name = o.get("name", "").lower().strip()
        if not name:
            continue
        if name in name_to_outcome:
            existing = name_to_outcome[name]
            # Vision takes precedence for effect_size, se, ci_lower, ci_upper, p_value
            for key in ("effect_size", "se", "ci_lower", "ci_upper", "p_value", "n"):
                if o.get(key) and o[key] not in ("", "not reported"):
                    existing[key] = o[key]
        else:
            name_to_outcome[name] = dict(o)

    return list(name_to_outcome.values()), "hybrid"
