from __future__ import annotations

import pytest

from src.llm.pydantic_client import PydanticAIClient
from src.models import BatchScreeningResponsePayload
from src.screening.gemini_client import PydanticAIScreeningClient


@pytest.mark.asyncio
async def test_batch_schema_wrap_preserves_defs_for_ref_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def _fake_complete_with_usage(
        self: PydanticAIClient,
        prompt: str,
        *,
        model: str,
        temperature: float,
        json_schema: dict | None = None,
    ) -> tuple[str, int, int, int, int]:
        _ = (self, prompt, model, temperature)
        captured["schema"] = json_schema or {}
        return ("{}", 1, 1, 0, 0)

    monkeypatch.setattr(PydanticAIClient, "complete_with_usage", _fake_complete_with_usage)

    item_schema = {
        "type": "object",
        "properties": {
            "decision": {"$ref": "#/$defs/ScreeningDecisionType"},
        },
        "required": ["decision"],
        "$defs": {
            "ScreeningDecisionType": {
                "type": "string",
                "enum": ["include", "exclude", "uncertain"],
            }
        },
    }

    client = PydanticAIScreeningClient()
    await client.complete_json_array_with_usage(
        "prompt",
        agent_name="screening_reviewer_a",
        model="google-gla:gemini-2.5-flash-lite",
        temperature=0.1,
        item_schema=item_schema,
    )

    schema = captured["schema"]
    assert isinstance(schema, dict)
    assert schema.get("type") == "object"
    assert "decisions" in schema.get("properties", {})
    assert "ScreeningDecisionType" in schema.get("$defs", {})


@pytest.mark.asyncio
async def test_complete_batch_screening_with_usage_uses_validated_path(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def _fake_complete_validated(
        self: PydanticAIClient,
        prompt: str,
        *,
        model: str,
        temperature: float,
        response_model,
        json_schema: dict | None = None,
        max_validation_retries: int = 2,
    ):
        _ = (self, prompt, model, temperature, max_validation_retries)
        captured["response_model"] = response_model
        captured["schema"] = json_schema or {}
        payload = BatchScreeningResponsePayload(decisions=[])
        return payload, 3, 4, 0, 0, 0

    monkeypatch.setattr(PydanticAIClient, "complete_validated", _fake_complete_validated)

    client = PydanticAIScreeningClient()
    payload, tok_in, tok_out, cache_write, cache_read = await client.complete_batch_screening_with_usage(
        "prompt",
        agent_name="screening_reviewer_a",
        model="google-gla:gemini-2.5-flash-lite",
        temperature=0.1,
        item_schema={
            "type": "object",
            "properties": {"paper_id": {"type": "string"}, "decision": {"type": "string"}},
            "required": ["paper_id", "decision"],
            "additionalProperties": False,
        },
    )

    assert isinstance(payload, BatchScreeningResponsePayload)
    assert tok_in == 3
    assert tok_out == 4
    assert cache_write == 0
    assert cache_read == 0
    assert captured.get("response_model") is BatchScreeningResponsePayload
