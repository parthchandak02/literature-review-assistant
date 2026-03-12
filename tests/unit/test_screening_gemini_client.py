from __future__ import annotations

import pytest

from src.llm.pydantic_client import PydanticAIClient
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
