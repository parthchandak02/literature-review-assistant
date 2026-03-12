"""Screening LLM client backed by PydanticAI -- satisfies ScreeningLLMClient protocol."""

from __future__ import annotations

from src.llm.pydantic_client import PydanticAIClient
from src.screening.dual_screener import ScreeningResponse


class PydanticAIScreeningClient:
    """Screening client backed by PydanticAI Agent.

    Satisfies the ScreeningLLMClient Protocol defined in dual_screener.py.
    Uses NativeOutput for Gemini models (native responseSchema enforcement),
    ToolOutput for all other providers.
    """

    async def complete_json(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
    ) -> str:
        """Return a JSON string matching ScreeningResponse schema."""
        _ = agent_name
        schema = ScreeningResponse.model_json_schema()
        client = PydanticAIClient()
        return await client.complete(
            prompt,
            model=model,
            temperature=temperature,
            json_schema=schema,
        )

    async def complete_json_with_usage(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
    ) -> tuple[str, int, int, int, int]:
        """Return (json_str, input_tokens, output_tokens, cache_write, cache_read).

        Mirrors complete_json but returns real token counts from the provider
        so dual_screener.py can record accurate costs instead of heuristics.
        """
        _ = agent_name
        schema = ScreeningResponse.model_json_schema()
        client = PydanticAIClient()
        return await client.complete_with_usage(
            prompt,
            model=model,
            temperature=temperature,
            json_schema=schema,
        )

    async def complete_json_array_with_usage(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
        item_schema: dict[str, object],
    ) -> tuple[str, int, int, int, int]:
        """Return usage-aware JSON for batched screening decisions.

        Keep the top-level schema as an object because some providers reject
        top-level arrays for structured output validation.
        """
        _ = agent_name
        embedded_item_schema = dict(item_schema)
        shared_defs = embedded_item_schema.pop("$defs", None)
        embedded_item_schema.pop("$schema", None)
        object_schema: dict[str, object] = {
            "type": "object",
            "properties": {
                "decisions": {
                    "type": "array",
                    "items": embedded_item_schema,
                }
            },
            "required": ["decisions"],
            "additionalProperties": False,
        }
        if isinstance(shared_defs, dict) and shared_defs:
            object_schema["$defs"] = shared_defs
        client = PydanticAIClient()
        return await client.complete_with_usage(
            prompt,
            model=model,
            temperature=temperature,
            json_schema=object_schema,
        )


__all__ = ["PydanticAIScreeningClient"]
