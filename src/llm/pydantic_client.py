"""PydanticAI-backed LLM client implementing LLMBackend protocol.

Supports all providers that PydanticAI supports (Gemini, Anthropic, OpenAI, Groq,
Mistral, Cohere, etc.). Provider is inferred from the model string prefix already
used in config/settings.yaml (e.g. "google-gla:", "anthropic:", "openai:").

Structured output strategy per provider:
- Gemini (google-gla:, google-vertex:): NativeOutput -- uses responseSchema
  at the API level, equivalent to the previous responseJsonSchema behavior.
- All other providers: default ToolOutput -- uses tool calling to enforce schema.

This module is the single replacement for the four raw aiohttp Gemini clients
that previously existed in the codebase.
"""

from __future__ import annotations

import json
import logging

from pydantic_ai import Agent, NativeOutput, StructuredDict
from pydantic_ai.settings import ModelSettings

logger = logging.getLogger(__name__)

_GEMINI_PREFIXES = ("google-gla:", "google-vertex:")


def _is_gemini(model: str) -> bool:
    return model.startswith(_GEMINI_PREFIXES)


class PydanticAIClient:
    """Provider-agnostic LLM client backed by PydanticAI Agent.

    Satisfies the LLMBackend protocol. Switching the underlying model is a
    one-line change in config/settings.yaml -- no code changes required.

    Retry behavior: PydanticAI uses the provider SDK's built-in retry logic.
    For Gemini, the google-genai SDK retries on 429/503 automatically.
    """

    async def complete(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float,
        json_schema: dict | None = None,
    ) -> str:
        """Run a single LLM completion and return the response as a string.

        If json_schema is provided, the response is a JSON string conforming to
        that schema. Callers should use model_validate_json() on the result.
        If no schema is provided, the response is plain text.
        """
        settings = ModelSettings(temperature=temperature)

        if json_schema is not None:
            if _is_gemini(model):
                # NativeOutput uses Gemini's native responseSchema enforcement,
                # preserving the previous responseJsonSchema behavior exactly.
                output_type = NativeOutput(StructuredDict(json_schema))
            else:
                # Other providers: ToolOutput (default) enforces schema via tool call.
                output_type = StructuredDict(json_schema)
            agent: Agent = Agent(model, output_type=output_type)  # type: ignore[arg-type]
            result = await agent.run(prompt, model_settings=settings)
            output = result.output
            if isinstance(output, dict):
                return json.dumps(output)
            return str(output)
        else:
            text_agent: Agent[None, str] = Agent(model, output_type=str)
            text_result = await text_agent.run(prompt, model_settings=settings)
            return text_result.output

    async def complete_with_usage(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float,
        json_schema: dict | None = None,
    ) -> tuple[str, int, int]:
        """Run completion and return (response_text, input_tokens, output_tokens).

        Use this variant in callers that need accurate token counts for cost
        logging -- avoids word-count heuristics.
        """
        settings = ModelSettings(temperature=temperature)

        if json_schema is not None:
            if _is_gemini(model):
                output_type = NativeOutput(StructuredDict(json_schema))
            else:
                output_type = StructuredDict(json_schema)
            agent = Agent(model, output_type=output_type)  # type: ignore[arg-type]
            result = await agent.run(prompt, model_settings=settings)
            usage = result.usage()
            text = json.dumps(result.output) if isinstance(result.output, dict) else str(result.output)
        else:
            text_agent: Agent[None, str] = Agent(model, output_type=str)
            result_str = await text_agent.run(prompt, model_settings=settings)
            usage = result_str.usage()
            text = result_str.output

        return text, usage.input_tokens, usage.output_tokens
