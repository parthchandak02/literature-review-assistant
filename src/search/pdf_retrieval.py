"""PDF retrieval helpers for full-text screening."""

from __future__ import annotations

from pydantic import BaseModel

import os
from urllib.parse import quote
from collections.abc import Sequence

import aiohttp

from src.models import CandidatePaper


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
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url) as response:
                        if response.status != 200:
                            continue
                        content_type = response.headers.get("Content-Type", "").lower()
                        body = await response.read()
                if "application/pdf" in content_type:
                    return PDFRetrievalResult(
                        paper_id=paper.paper_id,
                        resolved_url=url,
                        full_text=body[:8000].decode("latin-1", errors="ignore"),
                        success=True,
                    )
                text = body[:8000].decode("utf-8", errors="ignore")
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
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
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
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15), headers=headers) as session:
                async with session.get(url, params={"fields": "openAccessPdf,url"}) as response:
                    if response.status != 200:
                        return None
                    payload = await response.json()
            oa = payload.get("openAccessPdf") or {}
            return oa.get("url") or payload.get("url")
        except Exception:
            return None
