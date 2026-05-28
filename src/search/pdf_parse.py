"""Thread-safe PDF parsing helpers for full-text retrieval."""

from __future__ import annotations

import asyncio
import io
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import partial

logger = logging.getLogger(__name__)

# Default cap aligned with pdf_retrieval extractor budget.
DEFAULT_PDF_MAX_CHARS = 32_000

_parse_executor: ThreadPoolExecutor | None = None
_parse_pool_size = 4


def configure_pdf_parse_pool(max_workers: int = 4) -> None:
    """Configure bounded thread pool for PDF parsing (call once at startup)."""
    global _parse_executor, _parse_pool_size
    _parse_pool_size = max(1, int(max_workers))
    if _parse_executor is not None:
        _parse_executor.shutdown(wait=False, cancel_futures=True)
    _parse_executor = ThreadPoolExecutor(
        max_workers=_parse_pool_size,
        thread_name_prefix="pdf-parse",
    )


def _get_parse_executor() -> ThreadPoolExecutor:
    global _parse_executor
    if _parse_executor is None:
        configure_pdf_parse_pool(_parse_pool_size)
    assert _parse_executor is not None
    return _parse_executor


def is_binary_garbage(text: str) -> bool:
    """Return True when decoded text still looks like raw binary content."""
    sample = str(text or "")[:4000]
    if not sample:
        return True
    stripped = sample.lstrip()
    if stripped.startswith("%PDF"):
        return True
    non_printable = 0
    total = 0
    for ch in sample:
        total += 1
        code = ord(ch)
        if ch in "\n\r\t\f":
            continue
        if 32 <= code <= 126:
            continue
        non_printable += 1
    if total == 0:
        return True
    return (non_printable / total) > 0.15


def validated_full_text(text: str, *, max_chars: int = DEFAULT_PDF_MAX_CHARS) -> str:
    """Reject empty, binary, or garbage decoded PDF text."""
    cleaned = str(text or "")[:max_chars]
    if not cleaned.strip():
        return ""
    if is_binary_garbage(cleaned):
        return ""
    return cleaned


def parse_pdf_bytes(body: bytes, *, max_chars: int = DEFAULT_PDF_MAX_CHARS) -> str:
    """Parse raw PDF bytes into markdown text (sync — run via thread pool only)."""
    if not body or len(body) < 100:
        return ""
    try:
        import fitz  # PyMuPDF
        import pymupdf4llm

        doc = fitz.open(stream=io.BytesIO(body), filetype="pdf")
        try:
            md_text: str = pymupdf4llm.to_markdown(doc)
        finally:
            doc.close()
        return validated_full_text(md_text[:max_chars], max_chars=max_chars)
    except Exception as exc:
        logger.debug("PyMuPDF parsing failed (%s); falling back to latin-1 decode.", exc)
        decoded = body[:max_chars].decode("latin-1", errors="ignore")
        return validated_full_text(decoded, max_chars=max_chars)


async def parse_pdf_bytes_async(body: bytes, *, max_chars: int = DEFAULT_PDF_MAX_CHARS) -> str:
    """Offload PDF parsing to bounded thread pool so the event loop stays responsive."""
    loop = asyncio.get_running_loop()
    executor = _get_parse_executor()
    fn = partial(parse_pdf_bytes, body, max_chars=max_chars)
    return await loop.run_in_executor(executor, fn)
