"""Unit tests for institutional session and manual PDF ingest tiers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.fulltext.manual_ingest import (
    find_manual_pdf_path,
    load_manual_pdf_bytes,
    reset_manual_index_cache,
)
from src.fulltext.retrieval import fetch_full_text


@pytest.fixture
def manual_pdf_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    reset_manual_index_cache()
    monkeypatch.setenv("FULLTEXT_MANUAL_PDF_DIR", str(tmp_path))
    pdf = tmp_path / "10.1016_j.jamda.2024.01.014.pdf"
    pdf.write_bytes(b"%PDF-1.4\n" + b"0" * 120)
    return tmp_path


def test_manual_ingest_finds_pdf_by_doi_in_filename(manual_pdf_dir: Path) -> None:
    path = find_manual_pdf_path("10.1016/j.jamda.2024.01.014")
    assert path is not None
    assert path.name == "10.1016_j.jamda.2024.01.014.pdf"


def test_manual_ingest_loads_pdf_bytes(manual_pdf_dir: Path) -> None:
    body = load_manual_pdf_bytes("10.1016/j.jamda.2024.01.014")
    assert body is not None
    assert body.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_fetch_full_text_uses_manual_tier(monkeypatch: pytest.MonkeyPatch, manual_pdf_dir: Path) -> None:
    monkeypatch.delenv("SCOPUS_API_KEY", raising=False)
    monkeypatch.delenv("EMBASE_API_KEY", raising=False)

    async def _no_oa(**kwargs):  # type: ignore[no-untyped-def]
        return None

    with (
        patch("src.fulltext.retrieval._race_first_success", new=AsyncMock(return_value=None)),
        patch("src.fulltext.retrieval._fetch_sciencedirect", new=AsyncMock(return_value=None)),
        patch("src.fulltext.retrieval._fetch_pmc", new=AsyncMock(return_value=None)),
        patch("src.fulltext.retrieval._fetch_crossref_links", new=AsyncMock(return_value=None)),
        patch("src.fulltext.retrieval._resolve_landing_page", new=AsyncMock(return_value=None)),
        patch(
            "src.fulltext.institutional.fetch_sciencedirect_pdf_via_session",
            new=AsyncMock(return_value=None),
        ),
    ):
        result = await fetch_full_text(
            doi="10.1016/j.jamda.2024.01.014",
            use_sciencedirect=False,
            use_unpaywall=False,
            use_pmc=False,
            use_core=False,
            use_europepmc=False,
            use_semanticscholar=False,
            use_arxiv_pdf=False,
            use_biorxiv_medrxiv=False,
            use_crossref_links=False,
            use_landing_page=False,
            use_institutional_session=False,
        )

    assert result.source == "manual_pdf"
    assert result.pdf_bytes is not None
    assert result.pdf_bytes.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_fetch_full_text_uses_institutional_session_tier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCOPUS_API_KEY", "test-key")

    fake_pdf = b"%PDF-1.4\n" + b"0" * 120

    with (
        patch("src.fulltext.retrieval._race_first_success", new=AsyncMock(return_value=None)),
        patch("src.fulltext.retrieval._fetch_sciencedirect", new=AsyncMock(return_value=None)),
        patch(
            "src.fulltext.institutional.fetch_sciencedirect_pdf_via_session",
            new=AsyncMock(return_value=fake_pdf),
        ),
        patch("src.fulltext.retrieval._fetch_pmc", new=AsyncMock(return_value=None)),
        patch("src.fulltext.retrieval._fetch_crossref_links", new=AsyncMock(return_value=None)),
        patch("src.fulltext.retrieval._resolve_landing_page", new=AsyncMock(return_value=None)),
    ):
        result = await fetch_full_text(
            doi="10.1016/j.jamda.2024.01.014",
            use_unpaywall=False,
            use_pmc=False,
            use_core=False,
            use_europepmc=False,
            use_semanticscholar=False,
            use_arxiv_pdf=False,
            use_biorxiv_medrxiv=False,
            use_crossref_links=False,
            use_landing_page=False,
            use_manual_ingest=False,
        )

    assert result.source == "sciencedirect_session_pdf"
    assert result.pdf_bytes == fake_pdf
