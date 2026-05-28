from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.models.papers import CandidatePaper
from src.search.pdf_retrieval import PDFRetrievalResult, PDFRetriever


def _paper() -> CandidatePaper:
    return CandidatePaper(
        paper_id="p-1",
        title="Test paper",
        authors=["A Author"],
        year=2024,
        source_database="test",
        doi="10.1000/test",
        url="https://example.org/article",
    )


@pytest.mark.asyncio
async def test_retrieve_maps_403_to_reason_code():
    retriever = PDFRetriever()

    async def _fake_fetch_full_text(**kwargs):  # type: ignore[no-untyped-def]
        diagnostics = kwargs.get("diagnostics")
        if isinstance(diagnostics, list):
            diagnostics.append("PublisherDirect: HTTP 403 for https://example.org/file.pdf")
        from src.extraction.table_extraction import FullTextResult

        return FullTextResult(text="", source="abstract")

    with patch("src.extraction.table_extraction.fetch_full_text", new=AsyncMock(side_effect=_fake_fetch_full_text)):
        result = await retriever.retrieve(_paper())

    assert result.success is False
    assert result.reason_code == "publisher_403"
    assert any("HTTP 403" in d for d in result.diagnostics)


@pytest.mark.asyncio
async def test_retrieve_batch_timeout_reason_code():
    retriever = PDFRetriever()
    with patch.object(retriever, "retrieve", new=AsyncMock(side_effect=TimeoutError())):
        results, summary = await retriever.retrieve_batch([_paper()], per_paper_timeout=1, concurrency=1)
    assert summary.failed == 1
    assert results["p-1"].reason_code == "timeout"


@pytest.mark.asyncio
async def test_retrieve_batch_normalizes_unexpected_exception():
    retriever = PDFRetriever()
    with patch.object(retriever, "retrieve", new=AsyncMock(side_effect=RuntimeError("boom"))):
        results, summary = await retriever.retrieve_batch([_paper()], per_paper_timeout=1, concurrency=1)
    assert summary.failed == 1
    assert results["p-1"].reason_code == "unexpected_error"
    assert "boom" in (results["p-1"].error or "")


def test_infer_reason_code_cookie_wall() -> None:
    reason = PDFRetriever._infer_reason_code(
        "abstract",
        diagnostics=["LandingPage: redirected to /action/cookieAbsent"],
        error=None,
    )
    assert reason == "cookie_wall"


def test_infer_reason_code_metadata_only_endpoint() -> None:
    reason = PDFRetriever._infer_reason_code(
        "abstract",
        diagnostics=["Resolver: metadata-only endpoint for https://api.elsevier.com/content/abstract/scopus_id/1"],
        error=None,
    )
    assert reason == "metadata_only_endpoint"


@pytest.mark.asyncio
async def test_retrieve_pdf_parse_failed_on_corrupt_pdf_bytes():
    retriever = PDFRetriever()

    async def _fake_fetch_full_text(**kwargs):  # type: ignore[no-untyped-def]
        from src.extraction.table_extraction import FullTextResult

        return FullTextResult(
            text="",
            source="unpaywall",
            pdf_bytes=b"%PDF-1.4\x00\x01 corrupt binary payload " * 80,
        )

    with patch("src.extraction.table_extraction.fetch_full_text", new=AsyncMock(side_effect=_fake_fetch_full_text)):
        result = await retriever.retrieve(_paper())

    assert result.success is False
    assert result.reason_code == "pdf_parse_failed"


@pytest.mark.asyncio
async def test_retrieve_parses_pdf_bytes_successfully():
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Recovered full text from PDF bytes. " * 40)
    pdf_bytes = doc.tobytes()
    doc.close()
    retriever = PDFRetriever()
    prose = "Recovered full text from PDF bytes. " * 40

    async def _fake_fetch_full_text(**kwargs):  # type: ignore[no-untyped-def]
        from src.extraction.table_extraction import FullTextResult

        return FullTextResult(text=prose, source="unpaywall", pdf_bytes=pdf_bytes)

    with patch("src.extraction.table_extraction.fetch_full_text", new=AsyncMock(side_effect=_fake_fetch_full_text)):
        result = await retriever.retrieve(_paper())

    assert result.success is True
    assert "Recovered full text" in result.full_text


@pytest.mark.asyncio
async def test_retrieve_batch_stall_watchdog_marks_pending_as_timeout():
    retriever = PDFRetriever()
    paper = _paper()
    monotonic_values = iter([0.0, 0.0, 120.0, 120.0])

    async def _never_complete(_paper: CandidatePaper) -> PDFRetrievalResult:
        await asyncio.sleep(3600)
        return PDFRetrievalResult(paper_id=_paper.paper_id, success=True)

    async def _wait_no_progress(pending, **kwargs):  # type: ignore[no-untyped-def]
        return set(), set(pending)

    with (
        patch.object(retriever, "retrieve", new=AsyncMock(side_effect=_never_complete)),
        patch("src.search.pdf_retrieval.asyncio.wait", side_effect=_wait_no_progress),
        patch("src.search.pdf_retrieval.time.monotonic", side_effect=lambda: next(monotonic_values)),
    ):
        results, summary = await retriever.retrieve_batch(
            [paper],
            per_paper_timeout=5,
            concurrency=1,
        )

    assert summary.failed == 1
    assert results[paper.paper_id].reason_code == "timeout"
    assert "stall watchdog" in (results[paper.paper_id].error or "")
