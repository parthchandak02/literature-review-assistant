"""Multimodal PDF table extraction and full-text retrieval.

Full-text retrieval uses a tiered resolver (Unpaywall first, then publisher APIs):
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

import json
import logging
import os
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlparse, urlunparse

import aiohttp

from src.models.extraction import OutcomeRecord
from src.utils.ssl_context import tcp_connector_with_certifi

logger = logging.getLogger(__name__)


def _get_model_from_settings() -> str:
    try:
        from src.config.loader import load_configs

        _, s = load_configs(settings_path="config/settings.yaml")
        return s.agents["table_extraction"].model.replace("google-gla:", "").replace("google-vertex:", "")
    except Exception:
        from src.llm.model_fallback import get_fallback_model

        return get_fallback_model("lite").replace("google-gla:", "").replace("google-vertex:", "")


# ---------------------------------------------------------------------------
# Constants for the full-text retrieval tiers
# ---------------------------------------------------------------------------
_SD_BASE = "https://api.elsevier.com/content/article/doi"
_UNPAYWALL_BASE = "https://api.unpaywall.org/v2"
_PMC_FETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
_PMC_SEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
_CORE_SEARCH_URL = "https://api.core.ac.uk/v3/search/outputs"
_CORE_OUTPUT_URL = "https://api.core.ac.uk/v3/outputs"
_EUROPEPMC_SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
_EUROPEPMC_FULLTEXT_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/articles"
_S2_PAPER_URL = "https://api.semanticscholar.org/graph/v1/paper/DOI:"
_ARXIV_PDF_BASE = "https://arxiv.org/pdf"
_BIORXIV_PDF_BASE = "https://www.biorxiv.org/content"
_MEDRXIV_PDF_BASE = "https://www.medrxiv.org/content"
_OPENALEX_WORKS_URL = "https://api.openalex.org/works"
_OPENALEX_CONTENT_BASE = "https://content.openalex.org/works"
_CROSSREF_WORKS_URL = "https://api.crossref.org/works"
_FT_TIMEOUT = 20  # seconds per tier
# ScienceDirect returns non-OA papers as <500 chars -- treat as miss.
_SD_MIN_CHARS = 500
# Maximum chars returned from a landing-page HTML resolution.
_LP_MAX_CHARS = 32_000

# Elsevier/ScienceDirect DOI prefixes. Article API only works for these;
# non-Elsevier DOIs return 403/404. Skip to preserve API quota.
_ELSEVIER_PREFIXES = frozenset(
    {
        "10.1016",
        "10.1006",
        "10.1067",
        "10.1053",
        "10.1054",
        "10.1078",
        "10.4065",
        "10.1383",
        "10.1580",
        "10.1197",
        "10.1240",
        "10.1205",
        "10.3182",
        "10.3921",
        "10.1157",
        "10.1602",
        "10.2353",
        "10.1529",
        "10.3816",
        "10.1367",
    }
)


def _is_elsevier_doi(doi: str) -> bool:
    """True if DOI is likely Elsevier/ScienceDirect (Article API will work)."""
    if not doi:
        return False
    s = doi.strip().lower()
    if "doi.org/" in s:
        s = s.split("doi.org/")[-1]
    if "/" not in s:
        return False
    prefix = s.split("/")[0]
    return prefix in _ELSEVIER_PREFIXES


@dataclass
class FullTextResult:
    """Result from a full-text retrieval attempt."""

    text: str
    source: str  # "sciencedirect" | "unpaywall_text" | "pmc" | "abstract"
    pdf_bytes: bytes | None = None  # set only when Unpaywall returns a PDF


# ---------------------------------------------------------------------------
# Tier 1: ScienceDirect Article Retrieval API
# ---------------------------------------------------------------------------


def _append_diag(diagnostics: list[str] | None, tier: str, msg: str) -> None:
    """Append diagnostic message when diagnostics list is provided."""
    if diagnostics is not None:
        diagnostics.append(f"{tier}: {msg}")


async def _fetch_sciencedirect_pdf(
    doi: str,
    api_key: str,
    insttoken: str | None = None,
    ams_redirect: bool = True,
    diagnostics: list[str] | None = None,
) -> FullTextResult | None:
    """Fetch PDF from Article (Full Text) Retrieval API.

    Per Elsevier docs: request Accept: application/pdf. For subscribed content
    may need X-ELS-Insttoken. Use amsRedirect=true to get author-manuscript
    when not entitled to full PDF.
    Handles 303/307 redirects to the actual PDF URL.
    """
    if not doi or not api_key:
        return None
    url = f"{_SD_BASE}/{doi}"
    params = {"amsRedirect": "true"} if ams_redirect else {}
    headers = {
        "X-ELS-APIKey": api_key,
        "Accept": "application/pdf",
    }
    if insttoken:
        headers["X-ELS-Insttoken"] = insttoken
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=_FT_TIMEOUT),
                allow_redirects=True,
            ) as resp:
                if resp.status in (303, 307):
                    redirect_url = resp.headers.get("Location")
                    if redirect_url and redirect_url.startswith("http"):
                        async with session.get(
                            redirect_url,
                            timeout=aiohttp.ClientTimeout(total=30),
                        ) as r2:
                            if r2.status == 200:
                                body = await r2.read()
                                if body and len(body) > 1000:
                                    return FullTextResult(
                                        text="",
                                        source="sciencedirect_pdf",
                                        pdf_bytes=body,
                                    )
                    _append_diag(diagnostics, "ScienceDirect PDF", "redirect followed but no PDF")
                    return None
                if resp.status != 200:
                    _append_diag(diagnostics, "ScienceDirect PDF", f"HTTP {resp.status}")
                    logger.debug("ScienceDirect PDF: HTTP %d for doi=%s", resp.status, doi)
                    return None
                body = await resp.read()
        if body and len(body) > 1000:
            return FullTextResult(text="", source="sciencedirect_pdf", pdf_bytes=body)
        _append_diag(diagnostics, "ScienceDirect PDF", "response too small (<1KB)")
        return None
    except Exception as exc:
        _append_diag(diagnostics, "ScienceDirect PDF", str(exc))
        logger.debug("ScienceDirect PDF fetch error for doi=%s: %s", doi, exc)
        return None


async def _fetch_sciencedirect(
    doi: str, api_key: str, insttoken: str | None = None, diagnostics: list[str] | None = None
) -> FullTextResult | None:
    """Fetch full text from ScienceDirect using the Article (Full Text) Retrieval API.

    Workflow per Elsevier docs: try PDF first (Accept: application/pdf), then
    fall back to JSON originalText. PDF may work for OA or with insttoken;
    amsRedirect=true requests author-manuscript when not entitled to full PDF.
    """
    if not doi or not api_key:
        return None

    # Try PDF first (API key only; insttoken if available)
    result = await _fetch_sciencedirect_pdf(doi, api_key, insttoken, ams_redirect=True, diagnostics=diagnostics)
    if result:
        return result

    # Fall back to JSON originalText (Elsevier OA papers)
    url = f"{_SD_BASE}/{doi}"
    headers = {"X-ELS-APIKey": api_key, "Accept": "application/json"}
    if insttoken:
        headers["X-ELS-Insttoken"] = insttoken
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=_FT_TIMEOUT)) as resp:
                if resp.status != 200:
                    _append_diag(diagnostics, "ScienceDirect JSON", f"HTTP {resp.status}")
                    logger.debug("ScienceDirect: HTTP %d for doi=%s", resp.status, doi)
                    return None
                payload = await resp.json(content_type=None)
        orig = payload.get("full-text-retrieval-response", {}).get("originalText", "")
        if isinstance(orig, str) and len(orig) >= _SD_MIN_CHARS:
            return FullTextResult(text=orig, source="sciencedirect")
        _append_diag(diagnostics, "ScienceDirect JSON", f"originalText < {_SD_MIN_CHARS} chars")
        return None
    except Exception as exc:
        _append_diag(diagnostics, "ScienceDirect JSON", str(exc))
        logger.debug("ScienceDirect fetch error for doi=%s: %s", doi, exc)
        return None


# ---------------------------------------------------------------------------
# Tier 2: Unpaywall open-access PDF
# ---------------------------------------------------------------------------


async def _fetch_unpaywall(doi: str, diagnostics: list[str] | None = None) -> FullTextResult | None:
    """Fetch open-access PDF bytes via Unpaywall.

    Returns None when: DOI missing, no OA PDF found, or network error.
    The pdf_bytes field is populated; callers pass it to extract_tables_from_pdf.
    """
    if not doi:
        return None
    bare_doi = _normalize_doi(doi)
    if not bare_doi:
        return None
    meta_url = f"{_UNPAYWALL_BASE}/{bare_doi}?email=litreview@app.local"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(meta_url, timeout=aiohttp.ClientTimeout(total=_FT_TIMEOUT)) as resp:
                if resp.status != 200:
                    _append_diag(diagnostics, "Unpaywall", f"HTTP {resp.status}")
                    return None
                meta = await resp.json(content_type=None)

            # Collect candidate PDF URLs: best first, then oa_locations (some hosts less strict)
            candidates: list[str] = []
            best = meta.get("best_oa_location") or {}
            for key in ("url_for_pdf", "url"):
                u = best.get(key) or ""
                if u.startswith("http") and u not in candidates:
                    candidates.append(u)
            for loc in meta.get("oa_locations", []):
                for key in ("url_for_pdf", "url"):
                    u = loc.get(key) or ""
                    if u.startswith("http") and u not in candidates:
                        candidates.append(u)
            if not candidates:
                _append_diag(diagnostics, "Unpaywall", "no OA location")
                return None

            # Browser-like headers reduce 403 from publishers (JAMA, MDPI, etc.) that block scripts
            pdf_headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/pdf,*/*",
            }
            last_err = ""
            for pdf_url in candidates:
                try:
                    async with session.get(
                        pdf_url, timeout=aiohttp.ClientTimeout(total=30), headers=pdf_headers
                    ) as presp:
                        if presp.status != 200:
                            last_err = f"PDF fetch HTTP {presp.status}"
                            continue
                        ct = presp.headers.get("Content-Type", "")
                        pdf_bytes = await presp.read()
                        if not pdf_bytes:
                            last_err = "no PDF bytes"
                            continue
                        if "pdf" in ct.lower() or pdf_bytes[:4] == b"%PDF":
                            return FullTextResult(
                                text="",
                                source="unpaywall_pdf",
                                pdf_bytes=pdf_bytes,
                            )
                        # HTML landing pages are publisher paywalls / article wrappers,
                        # not actual article text.  Skip and let the landing-page
                        # resolver (Tier 6) handle them via citation_pdf_url meta.
                        if "text/html" in ct.lower() or "html" in ct.lower():
                            last_err = "HTML landing page skipped (not article text)"
                            continue
                        # XML / plain-text OA full-text (e.g. PubMed OA XML) is usable.
                        text = pdf_bytes.decode("utf-8", errors="replace")
                        if len(text) >= _SD_MIN_CHARS:
                            return FullTextResult(text=text, source="unpaywall_text")
                        last_err = "text response < 500 chars"
                except Exception as e:
                    last_err = str(e)
            _append_diag(diagnostics, "Unpaywall", last_err or "all locations failed")
            return None
    except Exception as exc:
        _append_diag(diagnostics, "Unpaywall", str(exc))
        logger.debug("Unpaywall fetch error for doi=%s: %s", doi, exc)
        return None


# ---------------------------------------------------------------------------
# Tier 2a: Semantic Scholar (openAccessPdf URL, optional API key)
# ---------------------------------------------------------------------------


async def _fetch_semanticscholar(doi: str, diagnostics: list[str] | None = None) -> FullTextResult | None:
    """Fetch full text from Semantic Scholar openAccessPdf URL.

    Gets PDF URL from S2 API, fetches and returns pdf_bytes for caller to parse.
    """
    if not doi:
        return None
    bare_doi = _normalize_doi(doi)
    if not bare_doi:
        return None
    s2_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    headers: dict[str, str] = {}
    if s2_key:
        headers["x-api-key"] = s2_key
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{_S2_PAPER_URL}{quote(bare_doi)}"
            async with session.get(
                url,
                params={"fields": "openAccessPdf"},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=_FT_TIMEOUT),
            ) as resp:
                if resp.status != 200:
                    _append_diag(diagnostics, "SemanticScholar", f"API HTTP {resp.status}")
                    return None
                payload = await resp.json(content_type=None)
            oa = payload.get("openAccessPdf") or {}
            pdf_url = oa.get("url")
            if not pdf_url or not str(pdf_url).startswith("http"):
                _append_diag(diagnostics, "SemanticScholar", "no openAccessPdf URL")
                return None

            pdf_headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/pdf,*/*",
            }
            async with session.get(
                pdf_url,
                headers=pdf_headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as presp:
                if presp.status != 200:
                    _append_diag(diagnostics, "SemanticScholar", f"PDF fetch HTTP {presp.status}")
                    return None
                pdf_bytes = await presp.read()
            if not pdf_bytes or len(pdf_bytes) < 1000:
                _append_diag(diagnostics, "SemanticScholar", "PDF too small or empty")
                return None
            return FullTextResult(text="", source="semanticscholar_pdf", pdf_bytes=pdf_bytes)
    except Exception as exc:
        _append_diag(diagnostics, "SemanticScholar", str(exc))
        logger.debug("Semantic Scholar fetch error for doi=%s: %s", doi, exc)
        return None


# ---------------------------------------------------------------------------
# Tier 2b: CORE (institutional repos, ~43M hosted full texts)
# ---------------------------------------------------------------------------


def _normalize_doi(doi: str) -> str:
    """Return bare DOI (e.g. 10.1016/j.test.2024.01.001) for API queries."""
    if not doi:
        return ""
    s = doi.strip()
    if "doi.org/" in s.lower():
        s = s.split("doi.org/")[-1]
    return s


async def _fetch_core(doi: str, api_key: str, diagnostics: list[str] | None = None) -> FullTextResult | None:
    """Fetch full text from CORE (institutional repos, different coverage than Unpaywall).

    Search by DOI, get output with full_text or download PDF. Requires CORE_API_KEY.
    """
    if not doi or not api_key:
        return None
    bare_doi = _normalize_doi(doi)
    if not bare_doi:
        return None
    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        async with aiohttp.ClientSession() as session:
            # Search by DOI
            async with session.get(
                _CORE_SEARCH_URL,
                params={"q": f'doi:"{bare_doi}"', "limit": 1},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=_FT_TIMEOUT),
            ) as resp:
                if resp.status != 200:
                    _append_diag(diagnostics, "CORE", f"search HTTP {resp.status}")
                    return None
                data = await resp.json(content_type=None)
            results = data.get("results") or []
            if not results:
                _append_diag(diagnostics, "CORE", "no output for DOI")
                return None
            out_id = results[0].get("id")
            if not out_id:
                _append_diag(diagnostics, "CORE", "no output id")
                return None

            # Get output (includes full_text, download_url)
            async with session.get(
                f"{_CORE_OUTPUT_URL}/{out_id}",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=_FT_TIMEOUT),
            ) as oresp:
                if oresp.status != 200:
                    _append_diag(diagnostics, "CORE", f"output HTTP {oresp.status}")
                    return None
                output = await oresp.json(content_type=None)

            full_text = output.get("full_text") or output.get("fullText") or ""
            if isinstance(full_text, str) and len(full_text) >= _SD_MIN_CHARS:
                return FullTextResult(text=full_text, source="core")

            # Try PDF download via CORE API if full_text not available
            async with session.get(
                f"{_CORE_OUTPUT_URL}/{out_id}/download",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as dresp:
                if dresp.status == 200:
                    body = await dresp.read()
                    if body and len(body) > 1000:
                        return FullTextResult(text="", source="core_pdf", pdf_bytes=body)
            _append_diag(diagnostics, "CORE", "no full text or PDF")
            return None
    except Exception as exc:
        _append_diag(diagnostics, "CORE", str(exc))
        logger.debug("CORE fetch error for doi=%s: %s", doi, exc)
        return None


# ---------------------------------------------------------------------------
# Tier 2c: Europe PMC (OA subset, 6.5M articles, no auth)
# ---------------------------------------------------------------------------


async def _fetch_europepmc(
    doi: str, pmid: str | None = None, diagnostics: list[str] | None = None
) -> FullTextResult | None:
    """Fetch full text from Europe PMC Open Access subset via fullTextXML.

    Resolves DOI/PMID to PMCID via search, then fetches fullTextXML.
    """
    if not doi and not pmid:
        return None
    bare_doi = _normalize_doi(doi) if doi else ""
    query = f"DOI:{bare_doi}" if bare_doi else f"EXT_ID:{pmid}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                _EUROPEPMC_SEARCH_URL,
                params={"query": query, "format": "json", "resultType": "core", "pageSize": 1},
                timeout=aiohttp.ClientTimeout(total=_FT_TIMEOUT),
            ) as resp:
                if resp.status != 200:
                    _append_diag(diagnostics, "EuropePMC", f"search HTTP {resp.status}")
                    return None
                data = await resp.json(content_type=None)
            hits = data.get("resultList", {}).get("result") or []
            if not hits:
                _append_diag(diagnostics, "EuropePMC", "no result for DOI/PMID")
                return None
            hit = hits[0] if isinstance(hits[0], dict) else {}
            pmcid = hit.get("pmcid") or hit.get("id")
            if not pmcid:
                _append_diag(diagnostics, "EuropePMC", "no pmcid in result")
                return None
            pmcid_str = str(pmcid).strip()
            if not pmcid_str.upper().startswith("PMC"):
                pmcid_str = f"PMC{pmcid_str}"

            async with session.get(
                f"{_EUROPEPMC_FULLTEXT_URL}/{pmcid_str}/fullTextXML",
                timeout=aiohttp.ClientTimeout(total=_FT_TIMEOUT),
            ) as ft_resp:
                if ft_resp.status != 200:
                    _append_diag(diagnostics, "EuropePMC", f"fullTextXML HTTP {ft_resp.status}")
                    return None
                xml_bytes = await ft_resp.read()
        xml_text = xml_bytes.decode("utf-8", errors="replace")
        plain = re.sub(r"<[^>]+>", " ", xml_text)
        plain = re.sub(r"\s{2,}", " ", plain).strip()
        if len(plain) >= _SD_MIN_CHARS:
            return FullTextResult(text=plain, source="europepmc")
        _append_diag(diagnostics, "EuropePMC", "parsed text < 500 chars")
        return None
    except Exception as exc:
        _append_diag(diagnostics, "EuropePMC", str(exc))
        logger.debug("Europe PMC fetch error for doi=%s: %s", doi, exc)
        return None


# ---------------------------------------------------------------------------
# Tier 1b: arXiv PDF (for papers from arXiv connector)
# ---------------------------------------------------------------------------


def _extract_arxiv_id(url: str | None) -> str | None:
    """Extract arXiv ID from URL like https://arxiv.org/abs/2401.12345 or .../2401.12345v1."""
    if not url or "arxiv.org" not in url:
        return None
    # Match /abs/XXYY.NNNNN or /abs/XXYY.NNNNNvN
    m = re.search(r"arxiv\.org/abs/([\d]+\.[\d]+(?:v\d+)?)", url, re.IGNORECASE)
    return m.group(1) if m else None


async def _fetch_arxiv(
    url: str | None,
    diagnostics: list[str] | None = None,
) -> FullTextResult | None:
    """Fetch PDF from arXiv when paper URL is an arXiv abs link.

    URL format: https://arxiv.org/abs/2401.12345
    PDF URL: https://arxiv.org/pdf/2401.12345.pdf
    """
    arxiv_id = _extract_arxiv_id(url)
    if not arxiv_id:
        return None
    pdf_url = f"{_ARXIV_PDF_BASE}/{arxiv_id}.pdf"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                pdf_url,
                timeout=aiohttp.ClientTimeout(total=_FT_TIMEOUT),
            ) as resp:
                if resp.status != 200:
                    _append_diag(diagnostics, "arXiv", f"PDF fetch HTTP {resp.status}")
                    return None
                body = await resp.read()
        if not body or len(body) < 500:
            _append_diag(diagnostics, "arXiv", "PDF too small or empty")
            return None
        # Parse PDF to text for consistency with other tiers
        try:
            import io

            import fitz  # PyMuPDF
            import pymupdf4llm

            doc = fitz.open(stream=io.BytesIO(body), filetype="pdf")
            md_text = pymupdf4llm.to_markdown(doc)
            doc.close()
            text = md_text[: _SD_MIN_CHARS * 2]  # ~1K chars min for meaningful content
            if len(text.strip()) >= _SD_MIN_CHARS:
                return FullTextResult(text=text, source="arxiv_pdf", pdf_bytes=body)
        except Exception:
            pass
        # Fallback: return PDF bytes only (caller can parse)
        return FullTextResult(text="", source="arxiv_pdf", pdf_bytes=body)
    except Exception as exc:
        _append_diag(diagnostics, "arXiv", str(exc))
        logger.debug("arXiv fetch error for url=%s: %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# Tier 2b: bioRxiv/medRxiv PDF (DOIs 10.1101/...)
# ---------------------------------------------------------------------------


def _is_biorxiv_medrxiv_doi(doi: str | None) -> bool:
    """True if DOI is from bioRxiv or medRxiv (both use 10.1101 prefix)."""
    if not doi:
        return False
    s = doi.strip().lower().split("doi.org/")[-1] if "doi.org/" in doi else doi.strip().lower()
    return s.startswith("10.1101/")


async def _fetch_biorxiv_medrxiv(
    doi: str,
    diagnostics: list[str] | None = None,
) -> FullTextResult | None:
    """Fetch PDF from bioRxiv or medRxiv when DOI starts with 10.1101/.

    Try biorxiv first, then medrxiv. Try v1, v2, v3 for revisions if v1 404s.
    """
    if not _is_biorxiv_medrxiv_doi(doi):
        return None
    bare = _normalize_doi(doi)
    for base in (_BIORXIV_PDF_BASE, _MEDRXIV_PDF_BASE):
        for ver in ("v1", "v2", "v3"):
            pdf_url = f"{base}/{bare}{ver}.full.pdf"
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        pdf_url,
                        timeout=aiohttp.ClientTimeout(total=_FT_TIMEOUT),
                    ) as resp:
                        if resp.status != 200:
                            continue
                        body = await resp.read()
                if not body or len(body) < 500:
                    continue
                try:
                    import io

                    import fitz  # PyMuPDF
                    import pymupdf4llm

                    doc = fitz.open(stream=io.BytesIO(body), filetype="pdf")
                    md_text = pymupdf4llm.to_markdown(doc)
                    doc.close()
                    text = md_text[: _SD_MIN_CHARS * 2]
                    if len(text.strip()) >= _SD_MIN_CHARS:
                        return FullTextResult(
                            text=text,
                            source="biorxiv_medrxiv_pdf",
                            pdf_bytes=body,
                        )
                except Exception:
                    pass
                return FullTextResult(text="", source="biorxiv_medrxiv_pdf", pdf_bytes=body)
            except Exception:
                continue
    _append_diag(diagnostics, "biorxiv_medrxiv", "PDF not found (tried both servers, v1-v3)")
    return None


# ---------------------------------------------------------------------------
# Tier 2c: OpenAlex Content (paid $0.01/file; ~60M OA works)
# ---------------------------------------------------------------------------


async def _fetch_openalex_content(
    doi: str,
    diagnostics: list[str] | None = None,
) -> FullTextResult | None:
    """Fetch PDF from OpenAlex Content API (cached PDFs for OA works).

    Resolves DOI to work via the OpenAlex works API, then:
    1. Tries the content_urls.pdf field (OpenAlex CDN -- requires OPENALEX_API_KEY).
    2. Falls back to open_access.oa_url (direct publisher OA PDF, no key needed).
    Requires OPENALEX_API_KEY to be set for the CDN path.
    """
    api_key = os.environ.get("OPENALEX_API_KEY", "").strip()
    if not api_key:
        _append_diag(diagnostics, "OpenAlex", "OPENALEX_API_KEY not set")
        return None
    bare = _normalize_doi(doi)
    if not bare:
        return None
    try:
        # Correct URL format: works/https://doi.org/{doi}  (not works/DOI:{doi})
        work_url = f"{_OPENALEX_WORKS_URL}/https://doi.org/{quote(bare)}"
        async with aiohttp.ClientSession() as session:
            async with session.get(
                work_url,
                params={
                    "mailto": os.environ.get("PUBMED_EMAIL", "unknown@example.com"),
                    "api_key": api_key,
                },
                timeout=aiohttp.ClientTimeout(total=_FT_TIMEOUT),
            ) as resp:
                if resp.status != 200:
                    _append_diag(diagnostics, "OpenAlex", f"works API HTTP {resp.status}")
                    return None
                data = await resp.json(content_type=None)

        # Build ordered list of PDF URLs to try.
        # 1. OpenAlex CDN (content_urls.pdf) -- authoritative cached copy.
        # 2. open_access.oa_url -- direct OA PDF from publisher/repo.
        pdf_candidates: list[tuple[str, dict[str, str]]] = []
        content_urls = data.get("content_urls") or {}
        cdn_pdf = content_urls.get("pdf") if isinstance(content_urls, dict) else None
        if cdn_pdf and cdn_pdf.startswith("http"):
            pdf_candidates.append((cdn_pdf, {"api_key": api_key}))
        oa_url = (data.get("open_access") or {}).get("oa_url") or ""
        if oa_url and oa_url.startswith("http") and oa_url not in (cdn_pdf or ""):
            pdf_candidates.append((oa_url, {}))

        if not pdf_candidates:
            _append_diag(diagnostics, "OpenAlex", "no content_urls.pdf or oa_url")
            return None

        for pdf_url, extra_params in pdf_candidates:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        pdf_url,
                        params=extra_params if extra_params else None,
                        headers={
                            "User-Agent": (
                                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                            ),
                            "Accept": "application/pdf,*/*",
                        },
                        timeout=aiohttp.ClientTimeout(total=_FT_TIMEOUT),
                        allow_redirects=True,
                    ) as resp:
                        if resp.status != 200:
                            _append_diag(diagnostics, "OpenAlex", f"PDF HTTP {resp.status} for {pdf_url[:50]}")
                            continue
                        body = await resp.read()
                if not body or len(body) < 500:
                    continue
                try:
                    import io

                    import fitz  # PyMuPDF
                    import pymupdf4llm

                    doc = fitz.open(stream=io.BytesIO(body), filetype="pdf")
                    md_text = pymupdf4llm.to_markdown(doc)
                    doc.close()
                    text = md_text[: _SD_MIN_CHARS * 2]
                    if len(text.strip()) >= _SD_MIN_CHARS:
                        logger.info("OpenAlex Content: PDF fetched from %s", pdf_url[:70])
                        return FullTextResult(text=text, source="openalex_content", pdf_bytes=body)
                except Exception:
                    pass
                return FullTextResult(text="", source="openalex_content", pdf_bytes=body)
            except Exception as _exc:
                _append_diag(diagnostics, "OpenAlex", f"fetch error: {_exc!s:.60}")
                continue
        return None
    except Exception as exc:
        _append_diag(diagnostics, "OpenAlex", str(exc))
        logger.debug("OpenAlex Content fetch error for doi=%s: %s", doi, exc)
        return None


# ---------------------------------------------------------------------------
# Tier 4: PubMed Central full text
# ---------------------------------------------------------------------------


async def _fetch_pmc(doi: str, pmid: str | None = None, diagnostics: list[str] | None = None) -> FullTextResult | None:
    """Fetch full text from PubMed Central via NCBI E-utilities.

    Strategy:
      1. Resolve DOI/PMID -> PMCID via esearch.
      2. Try PDF first: GET https://pmc.ncbi.nlm.nih.gov/articles/PMC{pmcid}/pdf/
         Returns FullTextResult with pdf_bytes + parsed text when available.
      3. Fallback: fetch XML via efetch and strip tags (text-only, no pdf_bytes).
    Returns None when: no PMC record, parse error, or network error.
    """
    if not doi and not pmid:
        return None
    pmcid: str | None = None
    _pmc_pdf_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/pdf,*/*",
    }
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
                    _append_diag(diagnostics, "PMC", f"esearch HTTP {resp.status}")
                    return None
                data = await resp.json(content_type=None)
            ids = data.get("esearchresult", {}).get("idlist", [])
            if not ids:
                _append_diag(diagnostics, "PMC", "no PMCID for DOI")
                return None
            pmcid = ids[0]

            # Try PDF first -- available for most NIH-funded and author-manuscript deposits.
            pdf_url = f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{pmcid}/pdf/"
            try:
                async with session.get(
                    pdf_url,
                    headers=_pmc_pdf_headers,
                    timeout=aiohttp.ClientTimeout(total=_FT_TIMEOUT),
                    allow_redirects=True,
                ) as presp:
                    if presp.status == 200:
                        pbody = await presp.read()
                        if pbody[:4] == b"%PDF":
                            text = ""
                            try:
                                import io

                                import fitz  # PyMuPDF
                                import pymupdf4llm

                                doc = fitz.open(stream=io.BytesIO(pbody), filetype="pdf")
                                text = pymupdf4llm.to_markdown(doc)[:_LP_MAX_CHARS]
                                doc.close()
                            except Exception:
                                pass
                            logger.info("PMC: PDF retrieved for PMCID=%s", pmcid)
                            return FullTextResult(text=text, pdf_bytes=pbody, source="pmc_pdf")
            except Exception as pdf_exc:
                logger.debug("PMC PDF attempt failed for PMCID=%s: %s", pmcid, pdf_exc)

            # Fallback: fetch full text XML (text-only, no pdf_bytes)
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
                    _append_diag(diagnostics, "PMC", f"efetch HTTP {fresp.status}")
                    return None
                xml_bytes = await fresp.read()

        xml_text = xml_bytes.decode("utf-8", errors="replace")
        # Strip XML tags -- good enough for LLM consumption
        plain = re.sub(r"<[^>]+>", " ", xml_text)
        plain = re.sub(r"\s{2,}", " ", plain).strip()
        if len(plain) >= _SD_MIN_CHARS:
            return FullTextResult(text=plain, source="pmc")
        _append_diag(diagnostics, "PMC", "parsed text < 500 chars")
        return None
    except Exception as exc:
        _append_diag(diagnostics, "PMC", str(exc))
        logger.debug("PMC fetch error for doi=%s pmid=%s: %s", doi, pmid, exc)
        return None


# ---------------------------------------------------------------------------
# Tier 5: Crossref link discovery (fallback; many links paywalled)
# ---------------------------------------------------------------------------


async def _fetch_crossref_links(
    doi: str,
    diagnostics: list[str] | None = None,
) -> FullTextResult | None:
    """Try PDF URLs from Crossref works API link array.

    Prefer content-type: application/pdf and intended-application: text-mining.
    Many links are paywalled; worth trying as last-resort fallback.
    """
    if not doi:
        return None
    bare = _normalize_doi(doi)
    if not bare:
        return None
    try:
        url = f"{_CROSSREF_WORKS_URL}/{quote(bare)}"
        email = os.environ.get("CROSSREF_EMAIL") or os.environ.get("PUBMED_EMAIL") or "unknown@example.com"
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                params={"mailto": email},
                timeout=aiohttp.ClientTimeout(total=_FT_TIMEOUT),
            ) as resp:
                if resp.status != 200:
                    _append_diag(diagnostics, "Crossref", f"works API HTTP {resp.status}")
                    return None
                data = await resp.json(content_type=None)
        message = data.get("message", {})
        links = message.get("link", [])
        pdf_urls: list[tuple[str, int]] = []  # (url, priority: 0=pdf+text-mining, 1=pdf only)
        for link in links:
            ct = (link.get("content-type") or "").lower()
            app = (link.get("intended-application") or "").lower()
            u = link.get("URL", "").strip()
            if not u or "application/pdf" not in ct:
                continue
            priority = 0 if "text-mining" in app else 1
            pdf_urls.append((u, priority))
        pdf_urls.sort(key=lambda x: x[1])
        for pdf_url, _ in pdf_urls:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        pdf_url,
                        timeout=aiohttp.ClientTimeout(total=_FT_TIMEOUT),
                    ) as resp:
                        if resp.status != 200:
                            continue
                        body = await resp.read()
                if not body or len(body) < 500:
                    continue
                try:
                    import io

                    import fitz  # PyMuPDF
                    import pymupdf4llm

                    doc = fitz.open(stream=io.BytesIO(body), filetype="pdf")
                    md_text = pymupdf4llm.to_markdown(doc)
                    doc.close()
                    text = md_text[: _SD_MIN_CHARS * 2]
                    if len(text.strip()) >= _SD_MIN_CHARS:
                        return FullTextResult(text=text, source="crossref_link", pdf_bytes=body)
                except Exception:
                    pass
                return FullTextResult(text="", source="crossref_link", pdf_bytes=body)
            except Exception:
                continue
        _append_diag(diagnostics, "Crossref", "no PDF link or all fetches failed")
        return None
    except Exception as exc:
        _append_diag(diagnostics, "Crossref", str(exc))
        logger.debug("Crossref links fetch error for doi=%s: %s", doi, exc)
        return None


# ---------------------------------------------------------------------------
# Tier 0 helper: direct PDF fetch for known-pattern OA publisher URLs
# ---------------------------------------------------------------------------


async def _fetch_url_direct(
    pdf_url: str,
    diagnostics: list[str] | None = None,
) -> FullTextResult | None:
    """Fetch a URL that is expected to serve a PDF directly.

    Used for publisher-pattern URLs (MDPI /pdf, Frontiers /pdf, etc.) where we
    already know the exact PDF endpoint without any HTML parsing.  Returns None
    when the response is not a PDF or the fetch fails.
    """
    pdf_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/pdf,*/*",
    }
    try:
        async with aiohttp.ClientSession(connector=tcp_connector_with_certifi()) as session:
            async with session.get(
                pdf_url,
                headers=pdf_headers,
                timeout=aiohttp.ClientTimeout(total=_FT_TIMEOUT),
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    _append_diag(diagnostics, "PublisherDirect", f"HTTP {resp.status} for {pdf_url[:60]}")
                    return None
                pct = resp.headers.get("Content-Type", "").lower()
                body = await resp.read()
        if not body or len(body) < 500:
            _append_diag(diagnostics, "PublisherDirect", "response too short")
            return None
        if "application/pdf" not in pct and body[:4] != b"%PDF":
            _append_diag(diagnostics, "PublisherDirect", f"not a PDF (ct={pct[:40]})")
            return None
        text = ""
        try:
            import io as _io

            import fitz
            import pymupdf4llm

            doc = fitz.open(stream=_io.BytesIO(body), filetype="pdf")
            text = pymupdf4llm.to_markdown(doc)
            doc.close()
        except Exception:
            pass
        logger.info("PublisherDirect: PDF fetched from %s", pdf_url[:80])
        return FullTextResult(
            text=text[:_LP_MAX_CHARS] if text else "",
            source="publisher_direct_pdf",
            pdf_bytes=body,
        )
    except Exception as exc:
        _append_diag(diagnostics, "PublisherDirect", str(exc)[:80])
        logger.debug("PublisherDirect fetch error for %s: %s", pdf_url[:60], exc)
        return None


# ---------------------------------------------------------------------------
# Tier 6: Landing-page HTML resolver
# ---------------------------------------------------------------------------

_PDF_HREF_RE = re.compile(
    r"(/pdf|\.pdf(?:[?#]|$)|/download|article/download|article/view/[^\"'#]+/pdf)",
    re.IGNORECASE,
)

_JSONLD_SCRIPT_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)

_LP_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class _PDFLinkParser(HTMLParser):
    """Minimal HTML parser to extract PDF link candidates from scholarly landing pages.

    Checks:
    - <meta name="citation_pdf_url" content="...">
    - <link rel="alternate" type="application/pdf" href="...">
    - <a href="..."> matching .pdf / /pdf / /download / OJS-style patterns
    """

    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.candidates: list[str] = []
        self._seen: set[str] = set()

    def _add(self, href: str | None) -> None:
        if not href:
            return
        resolved = urljoin(self.base_url, href.strip())
        if resolved.startswith("http") and resolved not in self._seen:
            self._seen.add(resolved)
            self.candidates.append(resolved)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        d = dict(attrs)
        if tag == "meta":
            name = (d.get("name") or "").lower()
            if name == "citation_pdf_url":
                self._add(d.get("content"))
        elif tag == "link":
            rel = (d.get("rel") or "").lower()
            type_ = (d.get("type") or "").lower()
            if "alternate" in rel and "application/pdf" in type_:
                self._add(d.get("href"))
        elif tag == "a":
            href = d.get("href") or ""
            if _is_pdf_like_href(href):
                self._add(href)


def _is_pdf_like_href(href: str) -> bool:
    """Return True if an anchor href looks like a direct or near-direct PDF link."""
    if not href or href.startswith("#") or href.startswith("javascript"):
        return False
    return bool(_PDF_HREF_RE.search(href))


def _extract_jsonld_pdf_urls(html_text: str, base_url: str) -> list[str]:
    """Extract PDF content URLs from JSON-LD / schema.org script blocks."""
    results: list[str] = []
    for match in _JSONLD_SCRIPT_RE.finditer(html_text):
        try:
            data = json.loads(match.group(1))
            items: list[object] = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                for field in ("contentUrl", "url"):
                    v = item.get(field, "")
                    if isinstance(v, str) and "pdf" in v.lower():
                        resolved = urljoin(base_url, v)
                        if resolved.startswith("http"):
                            results.append(resolved)
                for enc in item.get("encoding", []):
                    if not isinstance(enc, dict):
                        continue
                    ct = (enc.get("encodingFormat") or "").lower()
                    v = enc.get("contentUrl") or enc.get("url") or ""
                    if "pdf" in ct or ("pdf" in v.lower()):
                        resolved = urljoin(base_url, v)
                        if resolved.startswith("http"):
                            results.append(resolved)
        except Exception:
            continue
    return results


def _publisher_direct_pdf_url(url: str) -> str | None:
    """Return a direct PDF URL for known OA publisher URL patterns, or None.

    This is applied to the *post-redirect* final_url (e.g. after doi.org resolves
    to the actual publisher domain), so detection is reliable even when paper.url
    is a doi.org link.  Only covers publishers with stable, predictable PDF URL
    conventions -- all are confirmed open-access.

    Patterns:
      MDPI:            mdpi.com/{j}/{v}/{i}/{n}         -> .../pdf
      Frontiers:       frontiersin.org/articles/{doi}/full  -> .../pdf
                       frontiersin.org/articles/{doi}        -> .../pdf
      BioMed Central:  *.biomedcentral.com/articles/{doi}   -> .../pdf
      SpringerOpen:    *.springeropen.com/articles/{doi}     -> .../pdf
      JMIR:            jmir.org/...                          -> .../PDF
      PLoS:            journals.plos.org/...?id={doi}        -> add type=printable
      PeerJ:           peerj.com/articles/{id}               -> .../pdf
    """
    if not url or not url.startswith("http"):
        return None
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/")

    # MDPI: https://www.mdpi.com/{journal-id}/{vol}/{iss}/{article-num}
    if "mdpi.com" in host and not path.endswith("/pdf"):
        return urlunparse(parsed._replace(path=path + "/pdf", query="", fragment=""))

    # Frontiers: https://www.frontiersin.org/articles/{doi}/full  OR  .../articles/{doi}
    if "frontiersin.org" in host:
        if path.endswith("/full"):
            return urlunparse(parsed._replace(path=path[:-5] + "/pdf", query="", fragment=""))
        if "/articles/" in path and not path.endswith("/pdf"):
            return urlunparse(parsed._replace(path=path + "/pdf", query="", fragment=""))

    # BioMed Central and SpringerOpen: https://xxx.biomedcentral.com/articles/{doi}
    if ("biomedcentral.com" in host or "springeropen.com" in host) and "/articles/" in path:
        if not path.endswith("/pdf"):
            return urlunparse(parsed._replace(path=path + "/pdf", query="", fragment=""))

    # JMIR: https://www.jmir.org/{year}/{n}/e{id}  ->  .../PDF
    if "jmir.org" in host and not path.endswith("/PDF"):
        return urlunparse(parsed._replace(path=path + "/PDF", query="", fragment=""))

    # PLoS: https://journals.plos.org/plosone/article?id={doi}  ->  add type=printable
    if "journals.plos.org" in host and "type=printable" not in parsed.query:
        params = dict(parse_qsl(parsed.query))
        params["type"] = "printable"
        return urlunparse(parsed._replace(query=urlencode(params), fragment=""))

    # PeerJ: https://peerj.com/articles/{id}
    if "peerj.com" in host and "/articles/" in path and not path.endswith(".pdf"):
        return urlunparse(parsed._replace(path=path + ".pdf", query="", fragment=""))

    return None


async def _resolve_landing_page(
    url: str,
    diagnostics: list[str] | None = None,
) -> FullTextResult | None:
    """Fetch an article landing page and extract the public PDF or text.

    Checks scholarly HTML metadata signals:
    - <meta name="citation_pdf_url"> (HighWire/OJS standard)
    - <link rel="alternate" type="application/pdf">
    - JSON-LD schema.org contentUrl / encoding
    - Common download anchors (.pdf, /pdf, /download, OJS article/download)

    Returns None when no accessible PDF or long-text is found (e.g. paywalled).
    Never returns raw publisher boilerplate HTML as article text.
    """
    if not url or not url.startswith("http"):
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=_LP_BROWSER_HEADERS,
                timeout=aiohttp.ClientTimeout(total=_FT_TIMEOUT),
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    _append_diag(diagnostics, "LandingPage", f"HTTP {resp.status}")
                    return None
                content_type = resp.headers.get("Content-Type", "").lower()
                body = await resp.read()
                final_url = str(resp.url)

        # The landing URL itself served a PDF directly (check content-type and magic bytes).
        if "application/pdf" in content_type or body[:4] == b"%PDF":
            try:
                import io

                import fitz  # PyMuPDF
                import pymupdf4llm

                doc = fitz.open(stream=io.BytesIO(body), filetype="pdf")
                text = pymupdf4llm.to_markdown(doc)
                doc.close()
                if len(text.strip()) >= _SD_MIN_CHARS:
                    return FullTextResult(text=text[:_LP_MAX_CHARS], source="landing_page_pdf", pdf_bytes=body)
            except Exception:
                pass
            return FullTextResult(text="", source="landing_page_pdf", pdf_bytes=body)

        if "text/html" not in content_type and "html" not in content_type:
            _append_diag(diagnostics, "LandingPage", f"non-HTML content-type: {content_type}")
            return None

        html_text = body.decode("utf-8", errors="replace")

        # Publisher-specific direct PDF URL: prepend before HTML parsing so it
        # is attempted first.  Operates on final_url (post-redirect) so MDPI /
        # Frontiers are detected even when the original URL was a doi.org link.
        pub_pdf = _publisher_direct_pdf_url(final_url)
        candidates: list[str] = [pub_pdf] if pub_pdf else []

        # Extract PDF candidates from HTML metadata and download anchors.
        parser = _PDFLinkParser(final_url)
        parser.feed(html_text)
        for c in parser.candidates:
            if c not in candidates:
                candidates.append(c)

        # Also scan JSON-LD blocks for schema.org contentUrl.
        for c in _extract_jsonld_pdf_urls(html_text, final_url):
            if c not in candidates:
                candidates.append(c)

        if not candidates:
            _append_diag(diagnostics, "LandingPage", "no PDF signals in HTML")
            return None

        pdf_headers = {
            "User-Agent": _LP_BROWSER_HEADERS["User-Agent"],
            "Accept": "application/pdf,*/*",
        }
        async with aiohttp.ClientSession() as session:
            for pdf_url in candidates[:5]:  # cap attempts at 5 per page
                try:
                    async with session.get(
                        pdf_url,
                        headers=pdf_headers,
                        timeout=aiohttp.ClientTimeout(total=_FT_TIMEOUT),
                        allow_redirects=True,
                    ) as presp:
                        if presp.status != 200:
                            continue
                        pct = presp.headers.get("Content-Type", "").lower()
                        pbody = await presp.read()
                    if not pbody or len(pbody) < 500:
                        continue
                    _is_pdf_response = (
                        "application/pdf" in pct or pdf_url.lower().endswith(".pdf") or pbody[:4] == b"%PDF"
                    )
                    if _is_pdf_response:
                        text = ""
                        try:
                            import io

                            import fitz  # PyMuPDF
                            import pymupdf4llm

                            doc = fitz.open(stream=io.BytesIO(pbody), filetype="pdf")
                            text = pymupdf4llm.to_markdown(doc)
                            doc.close()
                        except Exception:
                            pass
                        logger.info(
                            "LandingPage: PDF resolved at %s for page %s",
                            pdf_url[:80],
                            url[:60],
                        )
                        return FullTextResult(
                            text=text[:_LP_MAX_CHARS] if text else "",
                            source="landing_page_pdf",
                            pdf_bytes=pbody,
                        )
                    # Plain-text / article-HTML response.
                    decoded = pbody.decode("utf-8", errors="replace")
                    if len(decoded.strip()) >= _SD_MIN_CHARS:
                        logger.info(
                            "LandingPage: text resolved at %s for page %s",
                            pdf_url[:80],
                            url[:60],
                        )
                        return FullTextResult(
                            text=decoded[:_LP_MAX_CHARS],
                            source="landing_page_text",
                        )
                except Exception:
                    continue

        _append_diag(diagnostics, "LandingPage", "all candidates failed")
        return None
    except Exception as exc:
        _append_diag(diagnostics, "LandingPage", str(exc))
        logger.debug("LandingPage resolver error for url=%s: %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# Public: tiered full-text retrieval
# ---------------------------------------------------------------------------


async def fetch_full_text(
    doi: str | None = None,
    url: str | None = None,
    pmid: str | None = None,
    scopus_api_key: str | None = None,
    scopus_insttoken: str | None = None,
    use_sciencedirect: bool = True,
    use_unpaywall: bool = True,
    use_pmc: bool = True,
    use_core: bool = True,
    use_europepmc: bool = True,
    use_semanticscholar: bool = True,
    use_arxiv_pdf: bool = True,
    use_biorxiv_medrxiv: bool = True,
    use_openalex_content: bool = False,
    use_crossref_links: bool = True,
    use_landing_page: bool = True,
    diagnostics: list[str] | None = None,
) -> FullTextResult:
    """Retrieve full text using a tiered resolver.

    Priority:
      1. Unpaywall -- OA PDFs/text, no auth, ~50% of recent papers
      2. CORE -- institutional repos (~43M hosted), requires CORE_API_KEY
      3. ScienceDirect -- Elsevier DOIs only (10.1016, etc.); skip non-Elsevier
      4. PubMed Central -- NIH-funded OA XML
      Fallback: abstract

    Args:
        doi: Paper DOI (preferred identifier for all tiers).
        url: Paper URL (used as DOI source if doi missing and url is DOI-like).
        pmid: PubMed ID (fallback for PMC lookup when DOI is absent).
        scopus_api_key: Elsevier API key. Falls back to SCOPUS_API_KEY env var.
        scopus_insttoken: Institutional token for ScienceDirect PDF. Falls back to
            SCOPUS_INSTTOKEN env var. Contact Elsevier support to request one.
        use_sciencedirect: Enable tier 2 (ScienceDirect, Elsevier DOIs only).
        use_unpaywall: Enable tier 1 (Unpaywall).
        use_pmc: Enable tier 3 (PMC).

    Returns:
        FullTextResult with text (and optionally pdf_bytes for Unpaywall/Elsevier PDFs).
    """
    key = scopus_api_key or os.environ.get("SCOPUS_API_KEY", "")
    insttoken = (scopus_insttoken or os.environ.get("SCOPUS_INSTTOKEN", "")).strip() or None
    effective_doi = doi or ""

    # Tier 0: Publisher-direct PDF for known OA publisher URL patterns.
    # Applies to MDPI, Frontiers, BioMedCentral, SpringerOpen, JMIR, PLoS, PeerJ.
    # Skips all API round-trips for papers whose landing URL maps to a direct PDF endpoint.
    if url:
        direct_pdf_url = _publisher_direct_pdf_url(url)
        if direct_pdf_url:
            result = await _fetch_url_direct(direct_pdf_url, diagnostics=diagnostics)
            if result:
                logger.info(
                    "fetch_full_text: tier 0 PublisherDirect success for url=%s source=%s",
                    url[:60],
                    result.source,
                )
                return result

    # Tier 1: Unpaywall (OA first, no API key, no quota)
    if use_unpaywall and effective_doi:
        result = await _fetch_unpaywall(effective_doi, diagnostics=diagnostics)
        if result:
            logger.info(
                "fetch_full_text: tier 1 Unpaywall success for doi=%s source=%s",
                effective_doi,
                result.source,
            )
            return result

    # Tier 1b: arXiv PDF (for papers from arXiv connector; url must be arxiv.org/abs/...)
    if use_arxiv_pdf and url:
        result = await _fetch_arxiv(url, diagnostics=diagnostics)
        if result:
            logger.info(
                "fetch_full_text: tier 1b arXiv success for url=%s source=%s",
                url[:50],
                result.source,
            )
            return result

    # Tier 2a: Semantic Scholar (openAccessPdf, optional API key)
    if use_semanticscholar and effective_doi:
        result = await _fetch_semanticscholar(effective_doi, diagnostics=diagnostics)
        if result:
            logger.info(
                "fetch_full_text: tier 2a Semantic Scholar success for doi=%s source=%s",
                effective_doi,
                result.source,
            )
            return result

    # Tier 2b: bioRxiv/medRxiv (DOIs 10.1101/...; life sciences preprints)
    if use_biorxiv_medrxiv and effective_doi:
        result = await _fetch_biorxiv_medrxiv(effective_doi, diagnostics=diagnostics)
        if result:
            logger.info(
                "fetch_full_text: tier 2b bioRxiv/medRxiv success for doi=%s source=%s",
                effective_doi,
                result.source,
            )
            return result

    # Tier 2: CORE (institutional repos; helps "no OA location" papers)
    core_key = os.environ.get("CORE_API_KEY", "").strip()
    if use_core and core_key and effective_doi:
        result = await _fetch_core(effective_doi, core_key, diagnostics=diagnostics)
        if result:
            logger.info(
                "fetch_full_text: tier 2 CORE success for doi=%s source=%s",
                effective_doi,
                result.source,
            )
            return result

    # Tier 2c: OpenAlex Content (paid $0.01/file; ~60M OA works; opt-in)
    if use_openalex_content and effective_doi:
        result = await _fetch_openalex_content(effective_doi, diagnostics=diagnostics)
        if result:
            logger.info(
                "fetch_full_text: tier 2c OpenAlex Content success for doi=%s source=%s",
                effective_doi,
                result.source,
            )
            return result

    # Tier 2d: Europe PMC (OA subset, no auth)
    if use_europepmc and (effective_doi or pmid):
        result = await _fetch_europepmc(effective_doi, pmid, diagnostics=diagnostics)
        if result:
            logger.info(
                "fetch_full_text: tier Europe PMC success for doi=%s source=%s",
                effective_doi,
                result.source,
            )
            return result

    # Tier 3: ScienceDirect (Elsevier DOIs only; skip non-Elsevier to save quota)
    if use_sciencedirect and effective_doi and key:
        if not _is_elsevier_doi(effective_doi):
            _append_diag(diagnostics, "ScienceDirect", "skipped (non-Elsevier DOI)")
        else:
            result = await _fetch_sciencedirect(effective_doi, key, insttoken, diagnostics=diagnostics)
            if result:
                logger.info(
                    "fetch_full_text: tier 2 ScienceDirect success for doi=%s",
                    effective_doi,
                )
                return result

    # Tier 4: PMC
    if use_pmc and (effective_doi or pmid):
        result = await _fetch_pmc(effective_doi, pmid, diagnostics=diagnostics)
        if result:
            logger.info(
                "fetch_full_text: tier 4 PMC success for doi=%s (%d chars)",
                effective_doi,
                len(result.text),
            )
            return result

    # Tier 5: Crossref link discovery (fallback; many paywalled)
    if use_crossref_links and effective_doi:
        result = await _fetch_crossref_links(effective_doi, diagnostics=diagnostics)
        if result:
            logger.info(
                "fetch_full_text: tier 5 Crossref link success for doi=%s source=%s",
                effective_doi,
                result.source,
            )
            return result

    # Tier 6: Landing-page HTML resolver -- public scholarly pages that expose
    # PDFs via citation_pdf_url meta, link[type=application/pdf], JSON-LD, or
    # common download anchors (OJS article/download, etc.).
    if use_landing_page and (url or effective_doi):
        lp_url = url if url else f"https://doi.org/{quote(effective_doi)}"
        result = await _resolve_landing_page(lp_url, diagnostics=diagnostics)
        if result:
            logger.info(
                "fetch_full_text: tier 6 LandingPage success for url=%s source=%s",
                lp_url[:60],
                result.source,
            )
            return result

    logger.debug(
        "fetch_full_text: all tiers missed for doi=%s -- using abstract fallback",
        effective_doi,
    )
    return FullTextResult(text="", source="abstract")


_TABLE_EXTRACTION_PROMPT = """\
You are a systematic review data extractor specializing in extracting quantitative results from study tables.

Examine ALL tables in this document and extract structured outcome data.
For each table row that reports a quantitative result, output one JSON object with:
  - name: outcome measure name (exact from paper, e.g. "anxiety score reduction", "quality of life improvement")
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


def _parse_table_json(raw: str) -> list[dict[str, str]]:
    """Parse JSON array from LLM output, stripping markdown fences if present."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    data = json.loads(text)
    if isinstance(data, list):
        return [
            {k: str(v) for k, v in item.items() if isinstance(v, (str, int, float))}
            for item in data
            if isinstance(item, dict)
        ]
    return []


async def extract_tables_from_pdf(
    pdf_bytes: bytes | None,
    model_name: str | None = None,
    api_key: str | None = None,
) -> list[OutcomeRecord]:
    """Extract quantitative outcome tables from PDF bytes via PydanticAI multimodal.

    Uses PydanticAI BinaryContent to pass raw PDF bytes to Gemini vision
    natively (no deprecated google-generativeai SDK, no run_in_executor).

    Args:
        pdf_bytes: Raw PDF bytes. If None, returns empty list.
        model_name: Gemini model to use for vision extraction (without provider prefix).
        api_key: Unused; kept for backward compat. PydanticAI reads GEMINI_API_KEY.

    Returns:
        List of OutcomeRecord objects with keys: name, description, effect_size,
        se, n, p_value, ci_lower, ci_upper.
    """
    if not pdf_bytes:
        return []

    if model_name is None:
        model_name = _get_model_from_settings()

    from pydantic_ai import Agent
    from pydantic_ai.messages import BinaryContent
    from pydantic_ai.settings import ModelSettings

    full_model = model_name if ":" in model_name else f"google-gla:{model_name}"

    try:
        agent: Agent[None, str] = Agent(full_model, output_type=str)
        pdf_part = BinaryContent(data=pdf_bytes, media_type="application/pdf")
        result = await agent.run(
            [pdf_part, _TABLE_EXTRACTION_PROMPT],
            model_settings=ModelSettings(temperature=0.1),
        )
        raw_dicts = _parse_table_json(result.output)
        return [OutcomeRecord(**{k: v for k, v in d.items() if k in OutcomeRecord.model_fields}) for d in raw_dicts]
    except json.JSONDecodeError as exc:
        logger.warning("Table extraction: JSON parse error: %s", exc)
    except Exception as exc:
        logger.warning("Table extraction: vision API error: %s", exc)

    return []


def merge_outcomes(
    text_outcomes: list[OutcomeRecord],
    vision_outcomes: list[OutcomeRecord],
) -> tuple[list[OutcomeRecord], str]:
    """Merge text-extracted and vision-extracted outcomes, deduplicating by name.

    Returns (merged_outcomes, extraction_source) where extraction_source is one
    of 'text', 'pdf_vision', or 'hybrid'.
    """
    if not vision_outcomes:
        return text_outcomes, "text"
    if not text_outcomes:
        return vision_outcomes, "pdf_vision"

    # Merge: vision outcomes take precedence for numeric fields when both exist
    name_to_outcome: dict[str, OutcomeRecord] = {}
    for o in text_outcomes:
        name = o.name.lower().strip()
        if name:
            name_to_outcome[name] = o.model_copy()

    for o in vision_outcomes:
        name = o.name.lower().strip()
        if not name:
            continue
        if name in name_to_outcome:
            existing = name_to_outcome[name]
            # Vision takes precedence for numeric fields when non-empty
            numeric_fields = ("effect_size", "se", "ci_lower", "ci_upper", "p_value", "n")
            updates = {
                f: getattr(o, f) for f in numeric_fields if getattr(o, f) and getattr(o, f) not in ("", "not reported")
            }
            if updates:
                name_to_outcome[name] = existing.model_copy(update=updates)
        else:
            name_to_outcome[name] = o.model_copy()

    return list(name_to_outcome.values()), "hybrid"
