"""PDF retrieval helpers for full-text screening."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Callable, Sequence
from urllib.parse import quote, urlparse

import aiohttp
from pydantic import BaseModel, Field

from src.models import CandidatePaper
from src.search.pdf_parse import (
    DEFAULT_PDF_MAX_CHARS,
    parse_pdf_bytes_async,
    validated_full_text,
)
from src.utils.ssl_context import tcp_connector_with_certifi

logger = logging.getLogger(__name__)

# Maximum characters to keep from parsed PDF text before passing to the extractor.
# Gemini 2.5 Pro supports 1M tokens; 32K chars is well within budget and
# covers most academic papers (8-15 pages ~ 24K-45K chars).
_PDF_MAX_CHARS = DEFAULT_PDF_MAX_CHARS


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
        if "cookieabsent" in d or "cookie wall" in d:
            return "cookie_wall"
        if "status 418" in d or "bot_blocked" in d or "likely_bot_blocked" in d:
            return "bot_blocked"
        if "metadata-only endpoint" in d:
            return "metadata_only_endpoint"
        if "paywall" in d:
            return "paywalled"
        if "no pdf signals in html" in d:
            return "pdf_link_missing"
        if "http 403" in d or "status 403" in d:
            return "publisher_403"
        if "http 401" in d or "status 401" in d:
            return "publisher_401"
        if "http 429" in d or "status 429" in d:
            return "rate_limited"
        if "doiresolve" in d and "no url-matched doi" in d:
            return "doi_unresolved"
        if "no paper url or doi resolver result available" in e:
            return "identifier_missing"
        if "metadata-only endpoint" in e:
            return "metadata_only_endpoint"
        if "no pdf signals in html" in d:
            return "no_pdf_signal"
        if "identifier_missing" in d:
            return "identifier_missing"
        return "no_oa_path"

    @staticmethod
    def _looks_metadata_only_endpoint(url: str, content_type: str, body: bytes) -> bool:
        host = urlparse(url).netloc.lower()
        content_type_lower = content_type.lower()
        if "api.elsevier.com" in host and "/content/abstract/" in url:
            return True
        if "xml" not in content_type_lower and "json" not in content_type_lower:
            return False
        sample = body[:1200].decode("utf-8", errors="ignore").lower()
        return "<abstract" in sample or "<dc:" in sample or '"abstract"' in sample

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
                    _tier_kwargs.update(
                        {
                            "use_sciencedirect": getattr(_ext, "sciencedirect_full_text", True),
                            "use_unpaywall": getattr(_ext, "unpaywall_full_text", True),
                            "use_pmc": getattr(_ext, "pmc_full_text", True),
                            "use_core": getattr(_ext, "core_full_text", True),
                            "use_europepmc": getattr(_ext, "europepmc_full_text", True),
                            "use_semanticscholar": getattr(_ext, "semanticscholar_full_text", True),
                            "use_arxiv_pdf": getattr(_ext, "arxiv_full_text", True),
                            "use_biorxiv_medrxiv": getattr(_ext, "biorxiv_medrxiv_full_text", True),
                            "use_crossref_links": getattr(_ext, "crossref_links_full_text", True),
                        }
                    )
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
                    validated_text = validated_full_text(ft_result.text, max_chars=_PDF_MAX_CHARS)
                    if validated_text and len(validated_text) >= 500:
                        return PDFRetrievalResult(
                            paper_id=paper.paper_id,
                            resolved_url=paper.url,
                            full_text=validated_text,
                            pdf_bytes=ft_result.pdf_bytes
                            if ft_result.pdf_bytes and len(ft_result.pdf_bytes) > 1000
                            else None,
                            source=ft_result.source,
                            reason_code=self._infer_reason_code(ft_result.source, _diag, None),
                            diagnostics=_diag,
                            success=True,
                        )
                    if ft_result.pdf_bytes and len(ft_result.pdf_bytes) > 1000:
                        parsed = await parse_pdf_bytes_async(ft_result.pdf_bytes, max_chars=_PDF_MAX_CHARS)
                        if not parsed:
                            return PDFRetrievalResult(
                                paper_id=paper.paper_id,
                                resolved_url=paper.url,
                                source=ft_result.source,
                                reason_code="pdf_parse_failed",
                                diagnostics=_diag,
                                success=False,
                                error="Decoded PDF content failed validation.",
                            )
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
        fallback_diagnostics: list[str] = []
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
                    parsed_text = await parse_pdf_bytes_async(body, max_chars=_PDF_MAX_CHARS)
                    if not parsed_text:
                        return PDFRetrievalResult(
                            paper_id=paper.paper_id,
                            resolved_url=url,
                            pdf_bytes=body,
                            source="url_direct_pdf",
                            reason_code="pdf_parse_failed",
                            success=False,
                            error="Decoded PDF content failed validation.",
                        )
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
                        full_text = validated_full_text(lp.text, max_chars=_PDF_MAX_CHARS)
                        lp_pdf = lp.pdf_bytes if lp.pdf_bytes and len(lp.pdf_bytes) > 1000 else None
                        if not full_text and lp_pdf:
                            full_text = await parse_pdf_bytes_async(lp_pdf, max_chars=_PDF_MAX_CHARS)
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
                    fallback_diagnostics.append(f"LandingPage: no PDF signals in HTML for {url[:80]}")
                    continue  # Skip -- raw HTML is not usable article text
                # Plain-text or XML response (not HTML, not PDF).
                if self._looks_metadata_only_endpoint(url, content_type, body):
                    fallback_diagnostics.append(f"Resolver: metadata-only endpoint for {url[:80]}")
                    continue
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
                fallback_diagnostics.append(f"LegacyFetch: {str(exc)[:120]}")
                continue
        final_error = "Unable to resolve downloadable full text."
        inferred_reason = self._infer_reason_code("abstract", fallback_diagnostics, final_error)
        return PDFRetrievalResult(
            paper_id=paper.paper_id,
            resolved_url=candidate_urls[0],
            reason_code=inferred_reason,
            diagnostics=fallback_diagnostics[-8:],
            success=False,
            error=final_error,
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
        # If no task completes for this long, assume one provider call wedged.
        stall_timeout_seconds = max(float(per_paper_timeout) + 20.0, 60.0)

        def _record_outcome(paper: CandidatePaper, outcome: PDFRetrievalResult) -> None:
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

        async def _fetch_one(paper: CandidatePaper) -> PDFRetrievalResult:
            async with sem:
                try:
                    return await asyncio.wait_for(self.retrieve(paper), timeout=per_paper_timeout)
                except TimeoutError:
                    return PDFRetrievalResult(
                        paper_id=paper.paper_id,
                        reason_code="timeout",
                        success=False,
                        error=f"per-paper timeout after {per_paper_timeout}s",
                    )
                except Exception as exc:
                    logger.warning("PDFRetriever: unhandled retrieval error for %s: %s", paper.paper_id, exc)
                    return PDFRetrievalResult(
                        paper_id=paper.paper_id,
                        reason_code="unexpected_error",
                        success=False,
                        error=str(exc)[:400],
                    )

        task_to_paper: dict[asyncio.Task[PDFRetrievalResult], CandidatePaper] = {
            asyncio.create_task(_fetch_one(paper)): paper for paper in papers
        }
        pending: set[asyncio.Task[PDFRetrievalResult]] = set(task_to_paper)
        last_completion_at = time.monotonic()

        try:
            while pending:
                done, pending = await asyncio.wait(
                    pending,
                    timeout=5.0,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not done:
                    if (time.monotonic() - last_completion_at) >= stall_timeout_seconds:
                        logger.error(
                            "PDFRetriever: stall watchdog triggered after %.1fs with %d pending tasks. "
                            "Marking pending papers as timeout and continuing.",
                            stall_timeout_seconds,
                            len(pending),
                        )
                        for task in list(pending):
                            paper = task_to_paper[task]
                            _record_outcome(
                                paper,
                                PDFRetrievalResult(
                                    paper_id=paper.paper_id,
                                    reason_code="timeout",
                                    success=False,
                                    error=f"stall watchdog timeout after {stall_timeout_seconds:.1f}s",
                                ),
                            )
                            task.cancel()
                        pending.clear()
                        break
                    continue

                last_completion_at = time.monotonic()
                for task in done:
                    paper = task_to_paper[task]
                    try:
                        outcome = task.result()
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        logger.warning("PDFRetriever: task result failed for %s: %s", paper.paper_id, exc)
                        outcome = PDFRetrievalResult(
                            paper_id=paper.paper_id,
                            reason_code="unexpected_error",
                            success=False,
                            error=str(exc)[:400],
                        )
                    _record_outcome(paper, outcome)
        except asyncio.CancelledError:
            logger.warning("PDFRetriever: retrieve_batch cancelled with %d pending tasks", len(pending))
            raise
        finally:
            if pending:
                for task in pending:
                    task.cancel()
                try:
                    await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=2.0)
                except TimeoutError:
                    logger.warning("PDFRetriever: pending tasks did not cancel within 2s after batch end")

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
