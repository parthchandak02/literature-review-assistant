"""Screening LLM client backed by PydanticAI -- satisfies ScreeningLLMClient protocol."""

from __future__ import annotations

from typing import TypeVar

from src.llm.factory import get_chat_client
from src.models import BatchScreeningResponsePayload, ScreeningResponsePayload

_T = TypeVar("_T", ScreeningResponsePayload, BatchScreeningResponsePayload)


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
        schema = ScreeningResponsePayload.model_json_schema()
        client = get_chat_client()
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
        schema = ScreeningResponsePayload.model_json_schema()
        client = get_chat_client()
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
        client = get_chat_client()
        return await client.complete_with_usage(
            prompt,
            model=model,
            temperature=temperature,
            json_schema=object_schema,
        )

    async def complete_validated_with_usage(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
        response_model: type[_T],
        json_schema: dict | None = None,
    ) -> tuple[_T, int, int, int, int]:
        """Return schema-validated payload with provider usage."""
        _ = agent_name
        client = get_chat_client()
        parsed, tok_in, tok_out, cache_write, cache_read, _retries = await client.complete_validated(
            prompt,
            model=model,
            temperature=temperature,
            response_model=response_model,
            json_schema=json_schema,
        )
        return parsed, tok_in, tok_out, cache_write, cache_read

    async def complete_screening_response_with_usage(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
    ) -> tuple[ScreeningResponsePayload, int, int, int, int]:
        """Return typed single-paper screening decision payload."""
        return await self.complete_validated_with_usage(
            prompt,
            agent_name=agent_name,
            model=model,
            temperature=temperature,
            response_model=ScreeningResponsePayload,
        )

    async def complete_batch_screening_with_usage(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
        item_schema: dict[str, object],
    ) -> tuple[BatchScreeningResponsePayload, int, int, int, int]:
        """Return typed batch screening payload."""
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
        return await self.complete_validated_with_usage(
            prompt,
            agent_name=agent_name,
            model=model,
            temperature=temperature,
            response_model=BatchScreeningResponsePayload,
            json_schema=object_schema,
        )


__all__ = ["PydanticAIScreeningClient"]
