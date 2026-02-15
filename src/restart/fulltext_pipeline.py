"""Full-text retrieval pipeline with GROBID-first structuring fallback chain."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

from ..utils.pdf_retriever import PDFRetriever


@dataclass(frozen=True)
class FullTextResult:
    """Result payload from full-text retrieval and parsing."""

    text: str
    parser_used: str
    source_url: str | None = None


@dataclass
class FullTextRetrievalPipeline:
    """Retrieves PDFs from Open URLs and parses using GROBID then fallback extractors."""

    grobid_url: str | None = None
    timeout_seconds: int = 45
    pdf_retriever: PDFRetriever = field(default_factory=PDFRetriever)
    session: requests.Session = field(default_factory=requests.Session)

    def fetch_and_parse(self, paper: Any, max_length: int = 50000) -> FullTextResult | None:
        pdf_url = getattr(paper, "url", None) or paper.get("url")
        if not pdf_url:
            text = self.pdf_retriever.retrieve_full_text(paper, max_length=max_length)
            if not text:
                return None
            return FullTextResult(text=text, parser_used="pdf_retriever_fallback")

        try:
            pdf_bytes = self._download_pdf(pdf_url)
        except Exception:
            text = self.pdf_retriever.retrieve_full_text(paper, max_length=max_length)
            if not text:
                return None
            return FullTextResult(text=text, parser_used="pdf_retriever_fallback", source_url=pdf_url)

        if self.grobid_url:
            grobid_text = self._parse_with_grobid(pdf_bytes)
            if grobid_text:
                return FullTextResult(
                    text=grobid_text[:max_length],
                    parser_used="grobid",
                    source_url=pdf_url,
                )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as handle:
            path = Path(handle.name)
            handle.write(pdf_bytes)

        try:
            fallback_text = self.pdf_retriever._extract_text_from_pdf(str(path))
        finally:
            path.unlink(missing_ok=True)

        if not fallback_text:
            return None

        return FullTextResult(
            text=fallback_text[:max_length],
            parser_used="pdf_retriever_extract",
            source_url=pdf_url,
        )

    def _download_pdf(self, url: str) -> bytes:
        response = self.session.get(url, timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.content

    def _parse_with_grobid(self, pdf_bytes: bytes) -> str | None:
        endpoint = self.grobid_url.rstrip("/") + "/api/processFulltextDocument"
        files = {"input": ("paper.pdf", pdf_bytes, "application/pdf")}
        response = self.session.post(endpoint, files=files, timeout=self.timeout_seconds)
        if response.status_code >= 400:
            return None
        xml = response.text
        if not xml.strip():
            return None
        return self._strip_tei(xml)

    @staticmethod
    def _strip_tei(tei_xml: str) -> str:
        # Lightweight XML tag removal to keep dependency surface small.
        output: list[str] = []
        inside = False
        for char in tei_xml:
            if char == "<":
                inside = True
                continue
            if char == ">":
                inside = False
                continue
            if not inside:
                output.append(char)
        return "".join(output).strip()
