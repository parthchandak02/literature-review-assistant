from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.models.papers import CandidatePaper
from src.search.pdf_retrieval import PDFRetriever


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
