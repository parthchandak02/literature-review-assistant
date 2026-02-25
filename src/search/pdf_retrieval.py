"""PDF retrieval helpers for full-text screening."""

from __future__ import annotations

import io
import logging
import os
from collections.abc import Sequence
from urllib.parse import quote

import aiohttp
from pydantic import BaseModel

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
    success: bool = False
    error: str | None = None


class FullTextCoverageSummary(BaseModel):
    attempted: int
    succeeded: int
    failed: int
    success_rate: float
    failed_paper_ids: list[str]


class PDFRetriever:
    def __init__(self, timeout_seconds: int = 20):
        self.timeout_seconds = timeout_seconds

    async def retrieve(self, paper: CandidatePaper) -> PDFRetrievalResult:
        candidate_urls = await self._candidate_urls(paper)
        if not candidate_urls:
            return PDFRetrievalResult(
                paper_id=paper.paper_id,
                success=False,
                error="No paper URL or DOI resolver result available.",
            )
        for url in candidate_urls:
            try:
                timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
                async with aiohttp.ClientSession(
                    timeout=timeout, connector=tcp_connector_with_certifi()
                ) as session:
                    async with session.get(url) as response:
                        if response.status != 200:
                            continue
                        content_type = response.headers.get("Content-Type", "").lower()
                        body = await response.read()
                if "application/pdf" in content_type:
                    parsed_text = _parse_pdf_bytes(body)
                    return PDFRetrievalResult(
                        paper_id=paper.paper_id,
                        resolved_url=url,
                        full_text=parsed_text,
                        success=True,
                    )
                text = body[:_PDF_MAX_CHARS].decode("utf-8", errors="ignore")
                if text.strip():
                    return PDFRetrievalResult(
                        paper_id=paper.paper_id,
                        resolved_url=url,
                        full_text=text,
                        success=True,
                    )
            except Exception:
                continue
        return PDFRetrievalResult(
            paper_id=paper.paper_id,
            resolved_url=candidate_urls[0],
            success=False,
            error="Unable to resolve downloadable full text.",
        )

    async def retrieve_batch(
        self, papers: Sequence[CandidatePaper]
    ) -> tuple[dict[str, PDFRetrievalResult], FullTextCoverageSummary]:
        results: dict[str, PDFRetrievalResult] = {}
        failed_ids: list[str] = []
        for paper in papers:
            outcome = await self.retrieve(paper)
            results[paper.paper_id] = outcome
            if not outcome.success:
                failed_ids.append(paper.paper_id)
        attempted = len(papers)
        succeeded = attempted - len(failed_ids)
        failed = len(failed_ids)
        success_rate = float(succeeded) / float(attempted) if attempted else 0.0
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

    async def _resolve_unpaywall(self, doi: str) -> str | None:
        email = os.getenv("CROSSREF_EMAIL") or os.getenv("PUBMED_EMAIL") or "unknown@example.com"
        url = f"https://api.unpaywall.org/v2/{quote(doi)}"
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
        url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{quote(doi)}"
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
