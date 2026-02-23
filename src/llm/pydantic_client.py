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

import asyncio
import json
import logging
import random
from typing import Any

from pydantic_ai import Agent, NativeOutput, StructuredDict
from pydantic_ai.settings import ModelSettings

logger = logging.getLogger(__name__)

_GEMINI_PREFIXES = ("google-gla:", "google-vertex:")

# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------
_MAX_RETRIES = 5
_BASE_DELAY = 2.0   # seconds
_MAX_DELAY = 90.0   # seconds cap

# HTTP status codes that indicate a transient server-side problem.
_RETRYABLE_CODES = {"429", "502", "503", "504"}
# Substrings found in exception messages for retryable conditions.
_RETRYABLE_MSGS = {"unavailable", "resource_exhausted", "rate", "overloaded", "gateway", "quota"}


def _is_gemini(model: str) -> bool:
    return model.startswith(_GEMINI_PREFIXES)


def _is_retryable(exc: BaseException) -> bool:
    """Return True if *exc* represents a transient provider error worth retrying."""
    s = str(exc).lower()
    return any(c in s for c in _RETRYABLE_CODES) or any(m in s for m in _RETRYABLE_MSGS)


async def _run_with_retry(agent: Agent[Any, Any], prompt: str, *, model_settings: ModelSettings) -> Any:
    """Run *agent* with exponential-backoff retry on transient errors.

    Retries up to _MAX_RETRIES times on 429/502/503/504 and similar transient
    conditions. Non-retryable errors (auth failures, schema errors, etc.) are
    re-raised immediately on the first occurrence.
    """
    for attempt in range(_MAX_RETRIES):
        try:
            return await agent.run(prompt, model_settings=model_settings)
        except Exception as exc:
            if not _is_retryable(exc) or attempt == _MAX_RETRIES - 1:
                raise
            delay = min(_BASE_DELAY * (2 ** attempt) + random.uniform(0, 1), _MAX_DELAY)
            logger.warning(
                "LLM transient error (attempt %d/%d), retrying in %.1fs: %s",
                attempt + 1,
                _MAX_RETRIES,
                delay,
                exc,
            )
            await asyncio.sleep(delay)
    raise RuntimeError("unreachable")  # pragma: no cover


class PydanticAIClient:
    """Provider-agnostic LLM client backed by PydanticAI Agent.

    Satisfies the LLMBackend protocol. Switching the underlying model is a
    one-line change in config/settings.yaml -- no code changes required.

    Retry behavior: transient errors (503 UNAVAILABLE, 429 RESOURCE_EXHAUSTED,
    502/504 gateway errors) are retried up to _MAX_RETRIES times with exponential
    backoff and jitter. Non-retryable errors propagate immediately.
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
            result = await _run_with_retry(agent, prompt, model_settings=settings)
            output = result.output
            if isinstance(output, dict):
                return json.dumps(output)
            return str(output)
        else:
            text_agent: Agent[None, str] = Agent(model, output_type=str)
            text_result = await _run_with_retry(text_agent, prompt, model_settings=settings)
            return text_result.output

    async def complete_with_usage(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float,
        json_schema: dict | None = None,
    ) -> tuple[str, int, int, int, int]:
        """Run completion and return (text, input_tokens, output_tokens, cache_write, cache_read).

        All five values come directly from the provider's usage object so there
        are no word-count heuristics.  cache_write and cache_read are 0 when
        the provider does not report them (e.g. OpenAI, Groq).
        """
        settings = ModelSettings(temperature=temperature)

        if json_schema is not None:
            if _is_gemini(model):
                output_type = NativeOutput(StructuredDict(json_schema))
            else:
                output_type = StructuredDict(json_schema)
            agent = Agent(model, output_type=output_type)  # type: ignore[arg-type]
            result = await _run_with_retry(agent, prompt, model_settings=settings)
            usage = result.usage()
            text = json.dumps(result.output) if isinstance(result.output, dict) else str(result.output)
        else:
            text_agent: Agent[None, str] = Agent(model, output_type=str)
            result_str = await _run_with_retry(text_agent, prompt, model_settings=settings)
            usage = result_str.usage()
            text = result_str.output

        return (
            text,
            usage.input_tokens,
            usage.output_tokens,
            usage.cache_write_tokens or 0,
            usage.cache_read_tokens or 0,
        )
