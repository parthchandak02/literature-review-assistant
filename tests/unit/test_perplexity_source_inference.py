"""Unit tests for Perplexity URL-to-source inference for PRISMA attribution."""

from __future__ import annotations

import pytest

from src.models.enums import SourceCategory
from src.search.perplexity_search import (
    PERPLEXITY_WEB,
    _infer_source_from_url,
)


@pytest.mark.parametrize(
    "url,expected_db,expected_cat",
    [
        # PubMed / PMC / NCBI
        ("https://pmc.ncbi.nlm.nih.gov/articles/PMC12058729/", "pubmed", SourceCategory.DATABASE),
        ("https://pubmed.ncbi.nlm.nih.gov/12345678/", "pubmed", SourceCategory.DATABASE),
        ("https://www.ncbi.nlm.nih.gov/pmc/articles/PMC123/", "pubmed", SourceCategory.DATABASE),
        # arXiv
        ("https://arxiv.org/abs/2401.12345", "arxiv", SourceCategory.DATABASE),
        ("https://arxiv.org/html/2506.18941v1", "arxiv", SourceCategory.DATABASE),
        # IEEE
        ("https://ieeexplore.ieee.org/document/12345678", "ieee_xplore", SourceCategory.DATABASE),
        ("https://www.ieee.org/publications/", "ieee_xplore", SourceCategory.DATABASE),
        # Semantic Scholar
        ("https://www.semanticscholar.org/paper/abc123", "semantic_scholar", SourceCategory.DATABASE),
        # OpenAlex
        ("https://openalex.org/W12345678", "openalex", SourceCategory.DATABASE),
        # Crossref / DOI
        ("https://doi.org/10.1234/xyz", "crossref", SourceCategory.DATABASE),
        ("https://dx.doi.org/10.5678/abc", "crossref", SourceCategory.DATABASE),
        # Publishers (Crossref-indexed)
        ("https://www.frontiersin.org/journals/ai/articles/10.3389/", "crossref", SourceCategory.DATABASE),
        ("https://link.springer.com/article/10.1007/s12345", "crossref", SourceCategory.DATABASE),
        ("https://www.nature.com/articles/s41586-024-12345", "crossref", SourceCategory.DATABASE),
        ("https://www.sciencedirect.com/science/article/pii/S12345678", "crossref", SourceCategory.DATABASE),
        ("https://dl.acm.org/doi/10.1145/1234567", "crossref", SourceCategory.DATABASE),
        ("https://iacis.org/iis/2025/4_iis_2025_233-247.pdf", "crossref", SourceCategory.DATABASE),
        ("https://srcpublishers.com/index.php/article/view/123", "crossref", SourceCategory.DATABASE),
        ("https://dialoguessr.com/index.php/2/article/view/1047", "crossref", SourceCategory.DATABASE),
        # Grey lit / web (perplexity_web)
        ("https://bura.brunel.ac.uk/bitstream/2438/31061/1/FullText.pdf", PERPLEXITY_WEB, SourceCategory.OTHER_SOURCE),
        ("https://nhsjs.com/2025/some-article/", PERPLEXITY_WEB, SourceCategory.OTHER_SOURCE),
        ("https://appinventiv.com/blog/conversational-ai-in-education/", PERPLEXITY_WEB, SourceCategory.OTHER_SOURCE),
        ("https://insighto.ai/blog/post", PERPLEXITY_WEB, SourceCategory.OTHER_SOURCE),
        ("https://www.mimicminds.com/post/article", PERPLEXITY_WEB, SourceCategory.OTHER_SOURCE),
        ("https://binarybrain.pages.dev/blog/post", PERPLEXITY_WEB, SourceCategory.OTHER_SOURCE),
        ("https://pakedx.com/blog/article", PERPLEXITY_WEB, SourceCategory.OTHER_SOURCE),
        ("https://theasu.ca/blog/article", PERPLEXITY_WEB, SourceCategory.OTHER_SOURCE),
        # Edge cases
        (None, PERPLEXITY_WEB, SourceCategory.OTHER_SOURCE),
        ("", PERPLEXITY_WEB, SourceCategory.OTHER_SOURCE),
        ("   ", PERPLEXITY_WEB, SourceCategory.OTHER_SOURCE),
    ],
)
def test_infer_source_from_url(url: str | None, expected_db: str, expected_cat: SourceCategory) -> None:
    """Verify URL-to-source inference for PRISMA attribution."""
    db, cat = _infer_source_from_url(url)
    assert db == expected_db, f"Expected database {expected_db!r}, got {db!r} for {url!r}"
    assert cat == expected_cat, f"Expected category {expected_cat}, got {cat} for {url!r}"
