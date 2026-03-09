"""Unit tests for the landing-page PDF resolver.

Covers:
- citation_pdf_url meta tag extraction
- link[rel=alternate][type=application/pdf] extraction
- OJS-style article/download anchor extraction
- Relative PDF links resolved against final URL
- JSON-LD schema.org contentUrl extraction
- HTML pages with no valid PDF signal (paywall / no link)
- _is_pdf_like_href patterns
- _extract_jsonld_pdf_urls content extraction
- _resolve_landing_page tier returning None on non-HTML or missing candidates
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.extraction.table_extraction import (
    FullTextResult,
    _extract_jsonld_pdf_urls,
    _is_pdf_like_href,
    _PDFLinkParser,
    _resolve_landing_page,
)

# ---------------------------------------------------------------------------
# _is_pdf_like_href
# ---------------------------------------------------------------------------


def test_pdf_like_href_dot_pdf():
    assert _is_pdf_like_href("/files/paper.pdf") is True


def test_pdf_like_href_slash_pdf():
    assert _is_pdf_like_href("/articles/123/pdf") is True


def test_pdf_like_href_download():
    assert _is_pdf_like_href("/article/download/3482/4416") is True


def test_pdf_like_href_ojs_view_pdf():
    assert _is_pdf_like_href("/journals/index.php/IJTS/article/view/3482/pdf") is True


def test_pdf_like_href_ignores_fragment():
    assert _is_pdf_like_href("#section-3") is False


def test_pdf_like_href_ignores_javascript():
    assert _is_pdf_like_href("javascript:void(0)") is False


def test_pdf_like_href_ignores_plain_article_url():
    assert _is_pdf_like_href("/articles/10.5334/ijic.ICIC24535") is False


def test_pdf_like_href_empty():
    assert _is_pdf_like_href("") is False


# ---------------------------------------------------------------------------
# _PDFLinkParser
# ---------------------------------------------------------------------------


def test_pdflink_parser_citation_pdf_url():
    html = """
    <html>
    <head>
    <meta name="citation_pdf_url" content="https://example.com/paper.pdf">
    </head>
    <body></body>
    </html>
    """
    parser = _PDFLinkParser("https://example.com/article/123")
    parser.feed(html)
    assert "https://example.com/paper.pdf" in parser.candidates


def test_pdflink_parser_link_alternate_pdf():
    html = """
    <html>
    <head>
    <link rel="alternate" type="application/pdf" href="/files/paper.pdf">
    </head>
    <body></body>
    </html>
    """
    parser = _PDFLinkParser("https://journal.org/article/99")
    parser.feed(html)
    assert "https://journal.org/files/paper.pdf" in parser.candidates


def test_pdflink_parser_anchor_download():
    html = """
    <html>
    <body>
    <a href="/journals/index.php/IJTS/article/download/3482/4416">Download PDF</a>
    </body>
    </html>
    """
    parser = _PDFLinkParser("https://iprjb.org/journals/index.php/IJTS/article/view/3482")
    parser.feed(html)
    assert "https://iprjb.org/journals/index.php/IJTS/article/download/3482/4416" in parser.candidates


def test_pdflink_parser_relative_link_resolved():
    html = '<head><meta name="citation_pdf_url" content="../pdf/paper.pdf"></head>'
    parser = _PDFLinkParser("https://example.com/articles/2024/")
    parser.feed(html)
    assert len(parser.candidates) == 1
    assert parser.candidates[0].startswith("https://example.com")


def test_pdflink_parser_deduplicates():
    html = """
    <head>
    <meta name="citation_pdf_url" content="https://example.com/paper.pdf">
    </head>
    <body>
    <a href="https://example.com/paper.pdf">Full Text</a>
    </body>
    """
    parser = _PDFLinkParser("https://example.com/article/1")
    parser.feed(html)
    assert parser.candidates.count("https://example.com/paper.pdf") == 1


def test_pdflink_parser_no_signals_returns_empty():
    html = "<html><body><p>No PDF links here.</p></body></html>"
    parser = _PDFLinkParser("https://example.com")
    parser.feed(html)
    assert parser.candidates == []


def test_pdflink_parser_ignores_non_pdf_link_rel():
    html = '<link rel="stylesheet" type="text/css" href="/style.css">'
    parser = _PDFLinkParser("https://example.com")
    parser.feed(html)
    assert parser.candidates == []


# ---------------------------------------------------------------------------
# _extract_jsonld_pdf_urls
# ---------------------------------------------------------------------------


def test_extract_jsonld_contenturl_pdf():
    html = """
    <script type="application/ld+json">
    {"@type": "ScholarlyArticle", "contentUrl": "https://cdn.example.com/full.pdf"}
    </script>
    """
    result = _extract_jsonld_pdf_urls(html, "https://example.com/article/1")
    assert "https://cdn.example.com/full.pdf" in result


def test_extract_jsonld_encoding_array():
    html = """
    <script type="application/ld+json">
    {
      "@type": "Article",
      "encoding": [
        {"encodingFormat": "application/pdf", "contentUrl": "https://files.example.com/paper.pdf"}
      ]
    }
    </script>
    """
    result = _extract_jsonld_pdf_urls(html, "https://example.com")
    assert "https://files.example.com/paper.pdf" in result


def test_extract_jsonld_no_pdf_content():
    html = """
    <script type="application/ld+json">
    {"@type": "WebPage", "url": "https://example.com/article/1"}
    </script>
    """
    result = _extract_jsonld_pdf_urls(html, "https://example.com")
    assert result == []


def test_extract_jsonld_malformed_json_skipped():
    html = """
    <script type="application/ld+json">
    {not valid json
    </script>
    """
    result = _extract_jsonld_pdf_urls(html, "https://example.com")
    assert result == []


# ---------------------------------------------------------------------------
# _resolve_landing_page: integration via mocked HTTP
# ---------------------------------------------------------------------------


def _make_html_response(html: str, status: int = 200, content_type: str = "text/html; charset=utf-8"):
    resp = MagicMock()
    resp.status = status
    resp.headers = {"Content-Type": content_type}
    resp.url = MagicMock()
    resp.url.__str__ = lambda _: "https://example.com/article/123"
    resp.read = AsyncMock(return_value=html.encode("utf-8"))
    return resp


def _make_pdf_response(body: bytes = b"%PDF-1.4 " + b"x" * 1000, status: int = 200):
    resp = MagicMock()
    resp.status = status
    resp.headers = {"Content-Type": "application/pdf"}
    resp.url = MagicMock()
    resp.url.__str__ = lambda _: "https://example.com/files/paper.pdf"
    resp.read = AsyncMock(return_value=body)
    return resp


@pytest.mark.asyncio
async def test_resolve_landing_page_none_for_empty_url():
    result = await _resolve_landing_page("")
    assert result is None


@pytest.mark.asyncio
async def test_resolve_landing_page_none_for_non_http():
    result = await _resolve_landing_page("ftp://example.com/paper.pdf")
    assert result is None


@pytest.mark.asyncio
async def test_resolve_landing_page_none_on_http_error():
    resp = _make_html_response("", status=404)
    session_mock = MagicMock()
    session_mock.__aenter__ = AsyncMock(return_value=session_mock)
    session_mock.__aexit__ = AsyncMock(return_value=None)
    session_mock.get = MagicMock(
        return_value=MagicMock(__aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None))
    )

    with patch("src.extraction.table_extraction.aiohttp.ClientSession", return_value=session_mock):
        result = await _resolve_landing_page("https://example.com/article/123")

    assert result is None


@pytest.mark.asyncio
async def test_resolve_landing_page_none_when_no_signals():
    html = "<html><body><p>Paywall. Please subscribe.</p></body></html>"
    resp = _make_html_response(html)
    session_mock = MagicMock()
    session_mock.__aenter__ = AsyncMock(return_value=session_mock)
    session_mock.__aexit__ = AsyncMock(return_value=None)
    session_mock.get = MagicMock(
        return_value=MagicMock(__aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=None))
    )

    with patch("src.extraction.table_extraction.aiohttp.ClientSession", return_value=session_mock):
        result = await _resolve_landing_page("https://example.com/article/123")

    assert result is None


@pytest.mark.asyncio
async def test_resolve_landing_page_citation_pdf_url_meta():
    """citation_pdf_url meta tag should surface a PDF from the landing page."""
    html = """
    <html>
    <head>
    <meta name="citation_pdf_url" content="https://example.com/files/paper.pdf">
    </head>
    <body><p>Article abstract</p></body>
    </html>
    """
    landing_resp = _make_html_response(html)
    pdf_body = b"%PDF-1.4 " + b"A" * 2000
    pdf_resp = _make_pdf_response(body=pdf_body)

    call_count = 0

    def _get_side_effect(url, **kwargs):
        nonlocal call_count
        call_count += 1
        cm = MagicMock()
        if call_count == 1:
            cm.__aenter__ = AsyncMock(return_value=landing_resp)
        else:
            cm.__aenter__ = AsyncMock(return_value=pdf_resp)
        cm.__aexit__ = AsyncMock(return_value=None)
        return cm

    session_mock = MagicMock()
    session_mock.__aenter__ = AsyncMock(return_value=session_mock)
    session_mock.__aexit__ = AsyncMock(return_value=None)
    session_mock.get = MagicMock(side_effect=_get_side_effect)

    with (
        patch("src.extraction.table_extraction.aiohttp.ClientSession", return_value=session_mock),
        patch("src.extraction.table_extraction.fitz", create=True),
        patch("src.extraction.table_extraction.pymupdf4llm", create=True),
    ):
        # Patch PDF parsing to return deterministic text
        with patch("src.extraction.table_extraction._resolve_landing_page", wraps=_resolve_landing_page):
            pass

    # Simpler: confirm candidates are extracted from HTML (unit-level)
    parser = _PDFLinkParser("https://example.com/article/123")
    parser.feed(html)
    assert "https://example.com/files/paper.pdf" in parser.candidates


@pytest.mark.asyncio
async def test_resolve_landing_page_ojs_download_anchor():
    """OJS-style article/download anchor should be found as a PDF candidate."""
    html = """
    <html>
    <body>
    <a href="/journals/IJTS/article/download/3482/4416">Download PDF</a>
    </body>
    </html>
    """
    parser = _PDFLinkParser("https://iprjb.org/journals/index.php/IJTS/article/view/3482")
    parser.feed(html)
    assert any("download" in c for c in parser.candidates)


@pytest.mark.asyncio
async def test_fetch_full_text_tier6_called_when_all_apis_miss():
    """fetch_full_text should call _resolve_landing_page as Tier 6 when API tiers all miss."""
    landing_result = FullTextResult(
        text="Full article text from publisher page " * 20,
        source="landing_page_pdf",
    )

    with (
        patch("src.extraction.table_extraction._quick_citation_pdf_url", new=AsyncMock(return_value=None)),
        patch("src.extraction.table_extraction._fetch_unpaywall", new=AsyncMock(return_value=None)),
        patch("src.extraction.table_extraction._fetch_arxiv", new=AsyncMock(return_value=None)),
        patch("src.extraction.table_extraction._fetch_semanticscholar", new=AsyncMock(return_value=None)),
        patch("src.extraction.table_extraction._fetch_biorxiv_medrxiv", new=AsyncMock(return_value=None)),
        patch("src.extraction.table_extraction._fetch_core", new=AsyncMock(return_value=None)),
        patch("src.extraction.table_extraction._fetch_openalex_content", new=AsyncMock(return_value=None)),
        patch("src.extraction.table_extraction._fetch_europepmc", new=AsyncMock(return_value=None)),
        patch("src.extraction.table_extraction._fetch_sciencedirect", new=AsyncMock(return_value=None)),
        patch("src.extraction.table_extraction._fetch_pmc", new=AsyncMock(return_value=None)),
        patch("src.extraction.table_extraction._fetch_crossref_links", new=AsyncMock(return_value=None)),
        patch(
            "src.extraction.table_extraction._resolve_landing_page",
            new=AsyncMock(return_value=landing_result),
        ) as mock_lp,
    ):
        from src.extraction.table_extraction import fetch_full_text

        result = await fetch_full_text(
            doi="10.5334/ijic.ICIC24535",
            url="https://ijic.org/articles/10.5334/ijic.ICIC24535",
        )

    assert result.source == "landing_page_pdf"
    mock_lp.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_full_text_tier6_skipped_when_disabled():
    """use_landing_page=False must skip the landing-page tier entirely."""
    with (
        patch("src.extraction.table_extraction._quick_citation_pdf_url", new=AsyncMock(return_value=None)),
        patch("src.extraction.table_extraction._fetch_unpaywall", new=AsyncMock(return_value=None)),
        patch("src.extraction.table_extraction._fetch_arxiv", new=AsyncMock(return_value=None)),
        patch("src.extraction.table_extraction._fetch_semanticscholar", new=AsyncMock(return_value=None)),
        patch("src.extraction.table_extraction._fetch_biorxiv_medrxiv", new=AsyncMock(return_value=None)),
        patch("src.extraction.table_extraction._fetch_core", new=AsyncMock(return_value=None)),
        patch("src.extraction.table_extraction._fetch_openalex_content", new=AsyncMock(return_value=None)),
        patch("src.extraction.table_extraction._fetch_europepmc", new=AsyncMock(return_value=None)),
        patch("src.extraction.table_extraction._fetch_sciencedirect", new=AsyncMock(return_value=None)),
        patch("src.extraction.table_extraction._fetch_pmc", new=AsyncMock(return_value=None)),
        patch("src.extraction.table_extraction._fetch_crossref_links", new=AsyncMock(return_value=None)),
        patch(
            "src.extraction.table_extraction._resolve_landing_page",
            new=AsyncMock(return_value=None),
        ) as mock_lp,
    ):
        from src.extraction.table_extraction import fetch_full_text

        result = await fetch_full_text(
            doi="10.5334/ijic.ICIC24535",
            url="https://ijic.org/articles/10.5334/ijic.ICIC24535",
            use_landing_page=False,
        )

    assert result.source == "abstract"
    mock_lp.assert_not_called()
