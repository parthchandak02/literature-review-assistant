"""Unit tests for thread-pool PDF parsing helpers."""

from __future__ import annotations

import asyncio

import pytest

from src.search.pdf_parse import (
    configure_pdf_parse_pool,
    is_binary_garbage,
    parse_pdf_bytes,
    parse_pdf_bytes_async,
    validated_full_text,
)


def test_parse_pdf_bytes_rejects_tiny_payload() -> None:
    assert parse_pdf_bytes(b"") == ""
    assert parse_pdf_bytes(b"x" * 50) == ""


def test_parse_pdf_bytes_latin1_fallback_on_invalid_pdf() -> None:
    body = b"plain text payload " * 20
    text = parse_pdf_bytes(body, max_chars=500)
    assert text
    assert "plain text payload" in text


def test_is_binary_garbage_rejects_pdf_header() -> None:
    assert is_binary_garbage("%PDF-1.4 binary") is True
    assert is_binary_garbage("Normal academic prose with sufficient printable content.") is False


def test_validated_full_text_rejects_garbage() -> None:
    assert validated_full_text("%PDF-1.4\x00\x01") == ""
    prose = "Coverage increased from 61% to 84% across 240 participants. " * 5
    assert validated_full_text(prose) == prose


def test_parse_pdf_bytes_max_chars_truncation() -> None:
    body = b"readable prose " * 200
    text = parse_pdf_bytes(body, max_chars=100)
    assert len(text) <= 100


def test_parse_pdf_bytes_valid_minimal_pdf() -> None:
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Sample academic paper text for unit testing. " * 30)
    pdf_bytes = doc.tobytes()
    doc.close()
    assert len(pdf_bytes) >= 100
    text = parse_pdf_bytes(pdf_bytes, max_chars=8000)
    assert "Sample academic paper text" in text


@pytest.mark.asyncio
async def test_parse_pdf_bytes_async_uses_thread_pool() -> None:
    configure_pdf_parse_pool(max_workers=2)
    body = b"async readable payload " * 30
    text = await parse_pdf_bytes_async(body, max_chars=500)
    assert "async readable payload" in text


@pytest.mark.asyncio
async def test_parse_pdf_bytes_async_does_not_block_event_loop() -> None:
    configure_pdf_parse_pool(max_workers=2)
    body = b"concurrent payload " * 40

    async def _tick() -> int:
        await asyncio.sleep(0)
        return 1

    results = await asyncio.gather(
        parse_pdf_bytes_async(body, max_chars=400),
        _tick(),
        _tick(),
    )
    assert "concurrent payload" in results[0]
