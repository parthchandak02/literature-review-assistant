from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.extraction.table_extraction import extract_tables_from_pdf


class _StubPayloadItem:
    def __init__(self, payload: dict[str, str]) -> None:
        self._payload = payload

    def model_dump(self) -> dict[str, str]:
        return dict(self._payload)


class _StubPayloadEnvelope:
    def __init__(self, items: list[dict[str, str]]) -> None:
        self.outcomes = [_StubPayloadItem(item) for item in items]


@pytest.mark.asyncio
async def test_extract_tables_from_pdf_uses_validated_multimodal_client() -> None:
    stub_response = _StubPayloadEnvelope(
        [
            {
                "name": "Exam score",
                "description": "Primary outcome",
                "effect_size": "0.42",
                "se": "0.10",
                "n": "120",
            }
        ]
    )

    with patch(
        "src.extraction.table_extraction.PydanticAIClient.complete_validated_parts",
        new=AsyncMock(return_value=(stub_response, 10, 5, 0, 0, 0)),
    ) as mocked:
        results = await extract_tables_from_pdf(b"%PDF-1.4 fake bytes", model_name="google-gla:gemini-2.5-flash-lite")

    assert mocked.await_count == 1
    assert len(results) == 1
    assert results[0].name == "Exam score"
    assert results[0].effect_size == "0.42"
