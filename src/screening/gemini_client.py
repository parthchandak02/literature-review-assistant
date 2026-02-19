"""Screening LLM client backed by PydanticAI -- satisfies ScreeningLLMClient protocol.

GeminiScreeningClient is retained as an alias for backward compatibility with any
code that imports it by name (primarily workflow.py and __init__.py).
"""

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


# Backward-compatibility alias -- workflow.py and __init__.py import this name.
GeminiScreeningClient = PydanticAIScreeningClient

__all__ = ["PydanticAIScreeningClient", "GeminiScreeningClient"]
