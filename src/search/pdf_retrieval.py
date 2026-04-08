"""PDF retrieval helpers for full-text screening."""

from __future__ import annotations

import asyncio
import io
import logging
import os
from collections.abc import Callable, Sequence
from urllib.parse import quote

import aiohttp
from pydantic import BaseModel, Field

from src.models import CandidatePaper
from src.utils.ssl_context import tcp_connector_with_certifi

logger = logging.getLogger(__name__)

# Maximum characters to keep from parsed PDF text before passing to the extractor.
# Gemini 2.5 Pro supports 1M tokens; 32K chars is well within budget and
# covers most academic papers (8-15 pages ~ 24K-45K chars).
_PDF_MAX_CHARS = 32_000


def _parse_pdf_bytes(body: bytes) -> str:
    """Parse raw PDF bytes into clean markdown text using PyMuPDF.

    Falls back to latin-1 decode if PyMuPDF is unavailable or parsing fails.
    Returns up to _PDF_MAX_CHARS of markdown text.
    """
    try:
        import fitz  # PyMuPDF
        import pymupdf4llm

        doc = fitz.open(stream=io.BytesIO(body), filetype="pdf")
        md_text: str = pymupdf4llm.to_markdown(doc)
        doc.close()
        return md_text[:_PDF_MAX_CHARS]
    except Exception as exc:
        logger.debug("PyMuPDF parsing failed (%s); falling back to latin-1 decode.", exc)
        return body[:_PDF_MAX_CHARS].decode("latin-1", errors="ignore")


class PDFRetrievalResult(BaseModel):
    paper_id: str
    resolved_url: str | None = None
    full_text: str = ""
    pdf_bytes: bytes | None = None
    source: str = "abstract"
    reason_code: str | None = None
    diagnostics: list[str] = Field(default_factory=list)
    success: bool = False
    error: str | None = None


class FullTextCoverageSummary(BaseModel):
    attempted: int
    succeeded: int
    failed: int
    success_rate: float
    failed_paper_ids: list[str]


class PDFRetriever:
    def __init__(self, timeout_seconds: int = 20, extraction_config: object | None = None):
        self.timeout_seconds = timeout_seconds
        self._ext_cfg = extraction_config

    @staticmethod
    def _infer_reason_code(source: str, diagnostics: list[str], error: str | None) -> str:
        if source and source != "abstract":
            return "oa_recovered"
        d = " | ".join(diagnostics).lower()
        e = (error or "").lower()
        if "per-paper timeout" in e:
            return "timeout"
        if "http 403" in d or "status 403" in d:
            return "publisher_403"
        if "http 401" in d or "status 401" in d:
            return "publisher_401"
        if "http 429" in d or "status 429" in d:
            return "rate_limited"
        if "doiresolve" in d and "no url-matched doi" in d:
            return "doi_unresolved"
        if "no pdf signals in html" in d:
            return "no_pdf_signal"
        if "no paper url or doi resolver result available" in e:
            return "no_identifier"
        return "no_oa_path"

    async def retrieve(self, paper: CandidatePaper) -> PDFRetrievalResult:
        # Primary: use unified fetch_full_text (Unpaywall, Semantic Scholar, CORE,
        # Europe PMC, ScienceDirect, PMC, arXiv, landing-page resolver) for papers
        # with a DOI or URL.
        if paper.doi or paper.url:
            try:
                from src.extraction.table_extraction import fetch_full_text

                _diag: list[str] = []
                _ext = self._ext_cfg
                _use_openalex = bool(os.getenv("OPENALEX_API_KEY", "").strip())
                _tier_kwargs: dict[str, bool] = {
                    "use_openalex_content": _use_openalex,
                }
                if _ext is not None:
                    _tier_kwargs.update({
                        "use_sciencedirect": getattr(_ext, "sciencedirect_full_text", True),
                        "use_unpaywall": getattr(_ext, "unpaywall_full_text", True),
                        "use_pmc": getattr(_ext, "pmc_full_text", True),
                        "use_core": getattr(_ext, "core_full_text", True),
                        "use_europepmc": getattr(_ext, "europepmc_full_text", True),
                        "use_semanticscholar": getattr(_ext, "semanticscholar_full_text", True),
                        "use_arxiv_pdf": getattr(_ext, "arxiv_full_text", True),
                        "use_biorxiv_medrxiv": getattr(_ext, "biorxiv_medrxiv_full_text", True),
                        "use_crossref_links": getattr(_ext, "crossref_links_full_text", True),
                    })
                    if getattr(_ext, "openalex_content_full_text", False) and _use_openalex:
                        _tier_kwargs["use_openalex_content"] = True
                ft_result = await fetch_full_text(
                    doi=paper.doi,
                    url=paper.url,
                    pmid=getattr(paper, "pmid", None),
                    diagnostics=_diag,
                    **_tier_kwargs,
                )
                if ft_result and ft_result.source != "abstract":
                    if ft_result.text and len(ft_result.text) >= 500:
                        return PDFRetrievalResult(
                            paper_id=paper.paper_id,
                            resolved_url=paper.url,
                            full_text=ft_result.text[:_PDF_MAX_CHARS],
                            pdf_bytes=ft_result.pdf_bytes
                            if ft_result.pdf_bytes and len(ft_result.pdf_bytes) > 1000
                            else None,
                            source=ft_result.source,
                            reason_code=self._infer_reason_code(ft_result.source, _diag, None),
                            diagnostics=_diag,
                            success=True,
                        )
                    if ft_result.pdf_bytes and len(ft_result.pdf_bytes) > 1000:
                        parsed = await asyncio.to_thread(_parse_pdf_bytes, ft_result.pdf_bytes)
                        return PDFRetrievalResult(
                            paper_id=paper.paper_id,
                            resolved_url=paper.url,
                            full_text=parsed,
                            pdf_bytes=ft_result.pdf_bytes,
                            source=ft_result.source,
                            reason_code=self._infer_reason_code(ft_result.source, _diag, None),
                            diagnostics=_diag,
                            success=True,
                        )
                if _diag:
                    _err = "; ".join(_diag[-4:])
                    return PDFRetrievalResult(
                        paper_id=paper.paper_id,
                        resolved_url=paper.url,
                        source=ft_result.source if ft_result else "abstract",
                        reason_code=self._infer_reason_code("abstract", _diag, _err),
                        diagnostics=_diag,
                        success=False,
                        error=_err,
                    )
            except Exception as exc:
                logger.warning("PDFRetriever: fetch_full_text failed for %s: %s", paper.paper_id, exc)

        # Fallback: legacy URL-based retrieval (paper.url, Unpaywall, Semantic Scholar)
        candidate_urls = await self._candidate_urls(paper)
        if not candidate_urls:
            return PDFRetrievalResult(
                paper_id=paper.paper_id,
                reason_code="no_identifier",
                success=False,
                error="No paper URL or DOI resolver result available.",
            )
        for url in candidate_urls:
            try:
                timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
                async with aiohttp.ClientSession(timeout=timeout, connector=tcp_connector_with_certifi()) as session:
                    async with session.get(url) as response:
                        if response.status != 200:
                            continue
                        content_type = response.headers.get("Content-Type", "").lower()
                        body = await response.read()
                if "application/pdf" in content_type:
                    parsed_text = await asyncio.to_thread(_parse_pdf_bytes, body)
                    return PDFRetrievalResult(
                        paper_id=paper.paper_id,
                        resolved_url=url,
                        full_text=parsed_text,
                        pdf_bytes=body,
                        source="url_direct_pdf",
                        reason_code="oa_recovered",
                        success=True,
                    )
                # For HTML responses use the landing-page resolver to find the
                # real PDF link.  Do NOT accept raw publisher HTML as article text
                # -- it is typically boilerplate (paywall page, journal index, etc.)
                if "text/html" in content_type or "html" in content_type:
                    from src.extraction.table_extraction import _resolve_landing_page

                    lp = await _resolve_landing_page(url)
                    if lp:
                        full_text = lp.text
                        lp_pdf = lp.pdf_bytes if lp.pdf_bytes and len(lp.pdf_bytes) > 1000 else None
                        if not full_text and lp_pdf:
                            full_text = await asyncio.to_thread(_parse_pdf_bytes, lp_pdf)
                        if full_text and len(full_text.strip()) >= 500:
                            return PDFRetrievalResult(
                                paper_id=paper.paper_id,
                                resolved_url=url,
                                full_text=full_text[:_PDF_MAX_CHARS],
                                pdf_bytes=lp_pdf,
                                source=lp.source if lp.source else "landing_page",
                                reason_code="oa_recovered",
                                success=True,
                            )
                    continue  # Skip -- raw HTML is not usable article text
                # Plain-text or XML response (not HTML, not PDF).
                decoded = body[:_PDF_MAX_CHARS].decode("utf-8", errors="ignore")
                if decoded.strip():
                    return PDFRetrievalResult(
                        paper_id=paper.paper_id,
                        resolved_url=url,
                        full_text=decoded,
                        source="url_direct_text",
                        reason_code="oa_recovered",
                        success=True,
                    )
            except Exception as exc:
                logger.warning("PDFRetriever: legacy URL retrieval failed for %s via %s: %s", paper.paper_id, url, exc)
                continue
        return PDFRetrievalResult(
            paper_id=paper.paper_id,
            resolved_url=candidate_urls[0],
            reason_code="no_oa_path",
            success=False,
            error="Unable to resolve downloadable full text.",
        )

    async def retrieve_batch(
        self,
        papers: Sequence[CandidatePaper],
        on_progress: Callable[[int, int], None] | None = None,
        concurrency: int = 8,
        per_paper_timeout: int = 45,
        on_result: Callable[[str, str, str, bool, str | None], None] | None = None,
    ) -> tuple[dict[str, PDFRetrievalResult], FullTextCoverageSummary]:
        """Retrieve full text for a batch of papers with bounded concurrency.

        Args:
            per_paper_timeout: Maximum wall-clock seconds for one paper across all tiers.
                Papers that exhaust all retrieval tiers (or hit a slow host) are capped
                at this value instead of blocking the semaphore slot for 260+ seconds.
            on_result: Optional per-paper callback fired after retrieval resolves.
                Signature: (paper_id, title, source, success).
        """
        results: dict[str, PDFRetrievalResult] = {}
        failed_ids: list[str] = []
        done_count: list[int] = [0]
        total = len(papers)
        sem = asyncio.Semaphore(concurrency)

        async def _fetch_one(paper: CandidatePaper) -> None:
            async with sem:
                try:
                    outcome = await asyncio.wait_for(self.retrieve(paper), timeout=per_paper_timeout)
                except TimeoutError:
                    outcome = PDFRetrievalResult(
                        paper_id=paper.paper_id,
                        reason_code="timeout",
                        success=False,
                        error=f"per-paper timeout after {per_paper_timeout}s",
                    )
                except Exception as exc:
                    logger.warning("PDFRetriever: unhandled retrieval error for %s: %s", paper.paper_id, exc)
                    outcome = PDFRetrievalResult(
                        paper_id=paper.paper_id,
                        reason_code="unexpected_error",
                        success=False,
                        error=str(exc)[:400],
                    )
            # asyncio is single-threaded: dict/list mutations here are safe
            results[paper.paper_id] = outcome
            if not outcome.success:
                failed_ids.append(paper.paper_id)
            done_count[0] += 1
            if on_progress is not None:
                try:
                    on_progress(done_count[0], total)
                except Exception as exc:
                    logger.warning("PDFRetriever: on_progress callback failed: %s", exc)
            if on_result is not None:
                try:
                    on_result(paper.paper_id, paper.title, outcome.source, outcome.success, outcome.reason_code)
                except Exception as exc:
                    logger.warning("PDFRetriever: on_result callback failed for %s: %s", paper.paper_id, exc)

        await asyncio.gather(*[_fetch_one(p) for p in papers], return_exceptions=True)
        attempted = len(papers)
        succeeded = attempted - len(failed_ids)
        failed = len(failed_ids)
        success_rate = float(succeeded) / float(attempted) if attempted else 0.0

        # Per-source and per-reason breakdowns for diagnostic logging
        source_counts: dict[str, int] = {}
        reason_counts: dict[str, int] = {}
        for r in results.values():
            src = r.source or "unknown"
            source_counts[src] = source_counts.get(src, 0) + 1
            rc = r.reason_code or "unknown"
            reason_counts[rc] = reason_counts.get(rc, 0) + 1
        logger.info(
            "PDF retrieval batch: %d/%d succeeded (%.0f%%) | sources=%s | reasons=%s",
            succeeded,
            attempted,
            success_rate * 100,
            source_counts,
            reason_counts,
        )

        summary = FullTextCoverageSummary(
            attempted=attempted,
            succeeded=succeeded,
            failed=failed,
            success_rate=success_rate,
            failed_paper_ids=failed_ids,
        )
        return results, summary

    async def _candidate_urls(self, paper: CandidatePaper) -> list[str]:
        urls: list[str] = []
        if paper.url:
            urls.append(paper.url)
        if paper.doi:
            unpaywall = await self._resolve_unpaywall(paper.doi)
            if unpaywall:
                urls.append(unpaywall)
            s2 = await self._resolve_semantic_scholar_pdf(paper.doi)
            if s2:
                urls.append(s2)
        # de-duplicate and keep insertion order
        seen: set[str] = set()
        unique: list[str] = []
        for url in urls:
            normalized = url.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique.append(normalized)
        return unique

    @staticmethod
    def _bare_doi(doi: str) -> str:
        """Strip https://doi.org/ prefix to get the bare DOI for API queries."""
        if "doi.org/" in doi.lower():
            doi = doi.split("doi.org/")[-1]
        return doi.strip()

    async def _resolve_unpaywall(self, doi: str) -> str | None:
        email = os.getenv("CROSSREF_EMAIL") or os.getenv("PUBMED_EMAIL") or "unknown@example.com"
        bare = self._bare_doi(doi)
        if not bare:
            return None
        url = f"https://api.unpaywall.org/v2/{quote(bare)}"
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
                connector=tcp_connector_with_certifi(),
            ) as session:
                async with session.get(url, params={"email": email}) as response:
                    if response.status != 200:
                        return None
                    payload = await response.json()
            best = payload.get("best_oa_location") or {}
            return best.get("url_for_pdf") or best.get("url")
        except Exception:
            return None

    async def _resolve_semantic_scholar_pdf(self, doi: str) -> str | None:
        s2_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
        headers: dict[str, str] = {}
        if s2_key:
            headers["x-api-key"] = s2_key
        bare = self._bare_doi(doi)
        if not bare:
            return None
        url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{quote(bare)}"
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
                headers=headers,
                connector=tcp_connector_with_certifi(),
            ) as session:
                async with session.get(url, params={"fields": "openAccessPdf,url"}) as response:
                    if response.status != 200:
                        return None
                    payload = await response.json()
            oa = payload.get("openAccessPdf") or {}
            return oa.get("url") or payload.get("url")
        except Exception:
            return None
