"""Unit tests for Enhancement #7: Multi-Modal Table Extraction.

Covers:
- fetch_full_text() tier chain and fallback behaviour (offline mocks)
- merge_outcomes() conflict resolution and extraction_source labels
- chunk_table_outcomes() output shape and content
- enrich_scopus_abstracts() (offline mock)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.extraction.table_extraction import (
    FullTextResult,
    fetch_full_text,
    merge_outcomes,
)
from src.rag.chunker import chunk_table_outcomes

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ft(text: str = "", source: str = "abstract", pdf_bytes: bytes | None = None) -> FullTextResult:
    return FullTextResult(text=text, source=source, pdf_bytes=pdf_bytes)


# ---------------------------------------------------------------------------
# fetch_full_text: tier routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_full_text_uses_unpaywall_first_then_sciencedirect(monkeypatch):
    """Tier 1 (Unpaywall) miss -> Tier 2 (ScienceDirect) hit for Elsevier DOI."""
    sd_result = _ft(text="A" * 600, source="sciencedirect")

    monkeypatch.setenv("SCOPUS_API_KEY", "test-key")
    with (
        patch(
            "src.extraction.table_extraction._fetch_unpaywall",
            new=AsyncMock(return_value=None),
        ) as mock_uw,
        patch(
            "src.extraction.table_extraction._fetch_sciencedirect",
            new=AsyncMock(return_value=sd_result),
        ) as mock_sd,
        patch(
            "src.extraction.table_extraction._fetch_pmc",
            new=AsyncMock(return_value=None),
        ) as mock_pmc,
    ):
        result = await fetch_full_text(doi="10.1016/j.test.2024.01.001")

    assert result.source == "sciencedirect"
    assert len(result.text) == 600
    mock_uw.assert_called_once()
    mock_sd.assert_called_once()
    mock_pmc.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_full_text_falls_to_unpaywall_when_sd_misses(monkeypatch):
    """Tier 1 miss -> Tier 2 hit."""
    uw_result = _ft(text="B" * 800, source="unpaywall_text")

    monkeypatch.setenv("SCOPUS_API_KEY", "test-key")
    with (
        patch(
            "src.extraction.table_extraction._fetch_sciencedirect",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "src.extraction.table_extraction._fetch_unpaywall",
            new=AsyncMock(return_value=uw_result),
        ) as mock_uw,
        patch(
            "src.extraction.table_extraction._fetch_pmc",
            new=AsyncMock(return_value=None),
        ) as mock_pmc,
    ):
        result = await fetch_full_text(doi="10.1000/test")

    assert result.source == "unpaywall_text"
    mock_uw.assert_called_once()
    mock_pmc.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_full_text_falls_to_pmc_when_unpaywall_misses(monkeypatch):
    """Tiers 1+2 miss -> Tier 3 hit."""
    pmc_result = _ft(text="C" * 1000, source="pmc")

    monkeypatch.setenv("SCOPUS_API_KEY", "test-key")
    with (
        patch("src.extraction.table_extraction._fetch_sciencedirect", new=AsyncMock(return_value=None)),
        patch("src.extraction.table_extraction._fetch_unpaywall", new=AsyncMock(return_value=None)),
        patch("src.extraction.table_extraction._fetch_pmc", new=AsyncMock(return_value=pmc_result)) as mock_pmc,
    ):
        result = await fetch_full_text(doi="10.1000/test")

    assert result.source == "pmc"
    mock_pmc.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_full_text_returns_abstract_fallback_when_all_tiers_miss(monkeypatch):
    """All 3 tiers miss -> fallback FullTextResult with empty text and source='abstract'."""
    monkeypatch.setenv("SCOPUS_API_KEY", "test-key")
    with (
        patch("src.extraction.table_extraction._fetch_sciencedirect", new=AsyncMock(return_value=None)),
        patch("src.extraction.table_extraction._fetch_unpaywall", new=AsyncMock(return_value=None)),
        patch("src.extraction.table_extraction._fetch_pmc", new=AsyncMock(return_value=None)),
    ):
        result = await fetch_full_text(doi="10.1000/test")

    assert result.source == "abstract"
    assert result.text == ""
    assert result.pdf_bytes is None


@pytest.mark.asyncio
async def test_fetch_full_text_skips_sd_when_no_api_key(monkeypatch):
    """ScienceDirect tier skipped when SCOPUS_API_KEY is absent."""
    monkeypatch.delenv("SCOPUS_API_KEY", raising=False)
    uw_result = _ft(text="D" * 600, source="unpaywall_text")

    with (
        patch("src.extraction.table_extraction._fetch_sciencedirect", new=AsyncMock(return_value=None)) as mock_sd,
        patch("src.extraction.table_extraction._fetch_unpaywall", new=AsyncMock(return_value=uw_result)),
        patch("src.extraction.table_extraction._fetch_pmc", new=AsyncMock(return_value=None)),
    ):
        result = await fetch_full_text(doi="10.1000/test")

    assert result.source == "unpaywall_text"
    # _fetch_sciencedirect is still called, but internally it returns None with no key
    # The tier is skipped at the orchestration level when key is empty
    assert mock_sd.call_count == 0


@pytest.mark.asyncio
async def test_fetch_full_text_disable_tiers_via_flags(monkeypatch):
    """When use_unpaywall=False and use_pmc=False, skip tiers 2+3 even with misses."""
    monkeypatch.setenv("SCOPUS_API_KEY", "test-key")
    with (
        patch("src.extraction.table_extraction._fetch_sciencedirect", new=AsyncMock(return_value=None)),
        patch("src.extraction.table_extraction._fetch_unpaywall", new=AsyncMock()) as mock_uw,
        patch("src.extraction.table_extraction._fetch_pmc", new=AsyncMock()) as mock_pmc,
    ):
        result = await fetch_full_text(doi="10.1000/test", use_unpaywall=False, use_pmc=False)

    assert result.source == "abstract"
    mock_uw.assert_not_called()
    mock_pmc.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_full_text_returns_pdf_bytes_from_unpaywall(monkeypatch):
    """Unpaywall PDF result populates pdf_bytes, not text."""
    pdf_bytes = b"%PDF-1.4 fake content"
    uw_result = _ft(text="", source="unpaywall_pdf", pdf_bytes=pdf_bytes)

    monkeypatch.setenv("SCOPUS_API_KEY", "test-key")
    with (
        patch("src.extraction.table_extraction._fetch_sciencedirect", new=AsyncMock(return_value=None)),
        patch("src.extraction.table_extraction._fetch_unpaywall", new=AsyncMock(return_value=uw_result)),
        patch("src.extraction.table_extraction._fetch_pmc", new=AsyncMock(return_value=None)),
    ):
        result = await fetch_full_text(doi="10.1000/test")

    assert result.source == "unpaywall_pdf"
    assert result.pdf_bytes == pdf_bytes
    assert result.text == ""


# ---------------------------------------------------------------------------
# merge_outcomes: conflict resolution
# ---------------------------------------------------------------------------


def test_merge_outcomes_returns_text_only_when_no_vision():
    text_outcomes = [{"name": "HbA1c", "effect_size": "SMD=0.4"}]
    merged, source = merge_outcomes(text_outcomes, [])
    assert source == "text"
    assert merged == text_outcomes


def test_merge_outcomes_returns_vision_only_when_no_text():
    vision_outcomes = [{"name": "LDL", "effect_size": "MD=-0.8", "p_value": "0.03"}]
    merged, source = merge_outcomes([], vision_outcomes)
    assert source == "pdf_vision"
    assert merged == vision_outcomes


def test_merge_outcomes_vision_overrides_numeric_fields():
    text_out = [{"name": "mortality", "effect_size": "OR=1.2", "p_value": "0.1"}]
    vision_out = [{"name": "Mortality", "effect_size": "OR=1.5 (95% CI 1.1-2.0)", "p_value": "0.01"}]
    merged, source = merge_outcomes(text_out, vision_out)
    assert source == "hybrid"
    assert len(merged) == 1
    assert merged[0]["effect_size"] == "OR=1.5 (95% CI 1.1-2.0)"
    assert merged[0]["p_value"] == "0.01"


def test_merge_outcomes_adds_new_vision_outcome_not_in_text():
    text_out = [{"name": "hba1c", "effect_size": "SMD=0.4"}]
    vision_out = [{"name": "ldl", "effect_size": "MD=-0.8"}]
    merged, source = merge_outcomes(text_out, vision_out)
    assert source == "hybrid"
    assert len(merged) == 2


def test_merge_outcomes_does_not_overwrite_with_empty_vision_values():
    text_out = [{"name": "bp", "effect_size": "MD=-5", "p_value": "0.001"}]
    vision_out = [{"name": "BP", "effect_size": ""}]  # empty -- should not overwrite
    merged, source = merge_outcomes(text_out, vision_out)
    assert merged[0]["effect_size"] == "MD=-5"
    assert merged[0]["p_value"] == "0.001"


def test_merge_outcomes_case_insensitive_name_matching():
    text_out = [{"name": "30-Day Mortality", "effect_size": "RR=0.9"}]
    vision_out = [{"name": "30-day mortality", "p_value": "<0.05"}]
    merged, _ = merge_outcomes(text_out, vision_out)
    assert len(merged) == 1
    assert merged[0]["p_value"] == "<0.05"
    assert merged[0]["effect_size"] == "RR=0.9"


# ---------------------------------------------------------------------------
# chunk_table_outcomes: output shape
# ---------------------------------------------------------------------------


def test_chunk_table_outcomes_produces_one_chunk_per_named_row():
    outcomes = [
        {"name": "HbA1c", "effect_size": "SMD=0.4", "p_value": "0.02"},
        {"name": "Weight", "effect_size": "MD=-2kg", "ci_lower": "-3", "ci_upper": "-1"},
    ]
    chunks = chunk_table_outcomes("paper-001", outcomes)
    assert len(chunks) == 2


def test_chunk_table_outcomes_skips_rows_with_no_name():
    outcomes = [
        {"effect_size": "SMD=0.4"},  # no name
        {"name": "HbA1c", "effect_size": "SMD=0.4"},
    ]
    chunks = chunk_table_outcomes("paper-002", outcomes)
    assert len(chunks) == 1
    assert chunks[0].paper_id == "paper-002"


def test_chunk_table_outcomes_chunk_ids_are_unique():
    outcomes = [{"name": f"outcome_{i}", "effect_size": f"MD={i}"} for i in range(5)]
    chunks = chunk_table_outcomes("paper-003", outcomes)
    chunk_ids = [c.chunk_id for c in chunks]
    assert len(chunk_ids) == len(set(chunk_ids))


def test_chunk_table_outcomes_content_includes_effect_size():
    outcomes = [{"name": "LDL", "effect_size": "OR=2.1 (95% CI 1.3-3.4)", "p_value": "0.001"}]
    chunks = chunk_table_outcomes("paper-004", outcomes)
    assert len(chunks) == 1
    content = chunks[0].content
    assert "LDL" in content
    assert "OR=2.1" in content
    assert "0.001" in content


def test_chunk_table_outcomes_includes_ci_when_both_bounds_present():
    outcomes = [{"name": "BP", "ci_lower": "1.2", "ci_upper": "3.4"}]
    chunks = chunk_table_outcomes("paper-005", outcomes)
    assert "95% CI" in chunks[0].content
    assert "1.2" in chunks[0].content
    assert "3.4" in chunks[0].content


def test_chunk_table_outcomes_start_index_offset():
    outcomes = [{"name": "HbA1c", "effect_size": "SMD=0.5"}]
    chunks = chunk_table_outcomes("paper-006", outcomes, start_index=10)
    assert chunks[0].chunk_index == 10
    assert chunks[0].chunk_id == "paper-006_table_10"


def test_chunk_table_outcomes_empty_outcomes_returns_empty():
    assert chunk_table_outcomes("paper-007", []) == []


# ---------------------------------------------------------------------------
# enrich_scopus_abstracts: offline mock
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enrich_scopus_abstracts_skips_papers_with_no_doi():
    from src.models.papers import CandidatePaper

    papers = [
        CandidatePaper(
            paper_id="p1",
            title="Paper 1",
            authors=["Author A"],
            source_database="scopus",
            doi=None,  # no DOI -- should be skipped
        )
    ]
    from src.search.scopus import enrich_scopus_abstracts

    count = await enrich_scopus_abstracts(papers, api_key="test")
    assert count == 0
    assert papers[0].abstract is None


@pytest.mark.asyncio
async def test_enrich_scopus_abstracts_skips_papers_already_with_abstract():
    from src.models.papers import CandidatePaper

    papers = [
        CandidatePaper(
            paper_id="p2",
            title="Paper 2",
            authors=["Author B"],
            source_database="scopus",
            doi="10.1000/test",
            abstract="Already has abstract",
        )
    ]
    from src.search.scopus import enrich_scopus_abstracts

    count = await enrich_scopus_abstracts(papers, api_key="test")
    assert count == 0


@pytest.mark.asyncio
async def test_enrich_scopus_abstracts_skips_non_scopus_papers():
    from src.models.papers import CandidatePaper

    papers = [
        CandidatePaper(
            paper_id="p3",
            title="Paper 3",
            authors=["Author C"],
            source_database="openalex",  # not scopus
            doi="10.1000/test",
        )
    ]
    from src.search.scopus import enrich_scopus_abstracts

    count = await enrich_scopus_abstracts(papers, api_key="test")
    assert count == 0
