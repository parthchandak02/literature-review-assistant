"""PydanticAI-backed LLM client implementing LLMBackend protocol.

Supports all providers that PydanticAI supports (Gemini, Anthropic, OpenAI, Groq,
Mistral, Cohere, etc.). Provider is inferred from the model string prefix already
used in config/settings.yaml (e.g. "google:", "anthropic:", "openai:").

Structured output strategy per provider:
- Gemini (google:, google-cloud:): NativeOutput -- uses responseSchema
  at the API level, equivalent to the previous responseJsonSchema behavior.
- DeepSeek (deepseek:) and Fireworks-hosted DeepSeek (fireworks:...deepseek...):
  StructuredDict with thinking disabled via extra_body,
  because V4 models default to thinking mode and reject tool_choice=required.
- All other providers: default ToolOutput -- uses tool calling to enforce schema.

This module is the single replacement for the four raw aiohttp Gemini clients
that previously existed in the codebase.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import json
import logging
import random
import re
import time
from collections.abc import Iterator
from typing import Any, TypeVar

from pydantic import BaseModel
from pydantic_ai import Agent, NativeOutput, StructuredDict
from pydantic_ai.settings import ModelSettings

from src.llm.registry import build_agent

logger = logging.getLogger(__name__)

_T = TypeVar("_T", bound=BaseModel)

_GEMINI_PREFIXES = (
    "google:",
    "google-cloud:",
    # Deprecated aliases retained for backward compatibility.
    "google-gla:",
    "google-vertex:",
)

_DEEPSEEK_PREFIX = "deepseek:"
# DeepSeek V4 enables thinking by default; tool_choice=required (StructuredDict) fails unless disabled.
# https://api-docs.deepseek.com/guides/thinking_mode
_DEEPSEEK_DISABLE_THINKING_EXTRA_BODY: dict[str, object] = {"thinking": {"type": "disabled"}}

# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------
_MAX_RETRIES = 5
_BASE_DELAY = 2.0  # seconds
_MAX_DELAY = 90.0  # seconds cap
# One logical LLM call (including every nested retry layer) may not spend more
# than this many transient retries or this much wall-clock time retrying.
_MAX_TOTAL_TRANSIENT_RETRIES = _MAX_RETRIES
_RETRY_DEADLINE_SECONDS = 300.0

# HTTP status codes that indicate a transient server-side problem.
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
# Status code embedded in a message: "status_code: 503", "Error code: 429", "HTTP 502".
_STATUS_IN_MSG = re.compile(r"(?i:status[_ ]?code|error code|http(?:/[\d.]+)?)\W{0,3}(\d{3})\b")
# Google-style "<code> <STATUS_NAME>", e.g. "503 UNAVAILABLE" (case-sensitive on purpose).
_STATUS_NAME_IN_MSG = re.compile(r"\b(\d{3}) [A-Z][A-Z_]{3,}\b")
# Whole-phrase transient markers; word boundaries keep "moderate"/"generate" out.
_TRANSIENT_PHRASES = re.compile(
    r"\b(?:rate[ _-]?limit(?:ed|s)?|too many requests|resource[ _]exhausted|overloaded|"
    r"service unavailable|temporarily unavailable|bad gateway|gateway timeout|timed out)\b",
    re.IGNORECASE,
)


def _transient_exception_types() -> tuple[type[BaseException], ...]:
    types: list[type[BaseException]] = [TimeoutError, asyncio.TimeoutError, ConnectionError]
    try:
        import httpx

        types += [httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError]
    except ImportError:  # pragma: no cover
        pass
    try:
        import aiohttp

        types += [aiohttp.ClientConnectionError, aiohttp.ServerTimeoutError]
    except ImportError:  # pragma: no cover
        pass
    try:
        import openai

        types += [openai.APIConnectionError, openai.APITimeoutError]
    except ImportError:  # pragma: no cover
        pass
    return tuple(types)


_TRANSIENT_EXCEPTION_TYPES = _transient_exception_types()


class _RetryBudget:
    __slots__ = ("deadline", "retries_left")

    def __init__(self, *, deadline_seconds: float, max_retries: int) -> None:
        self.deadline = time.monotonic() + deadline_seconds
        self.retries_left = max_retries


_retry_budget_var: contextvars.ContextVar[_RetryBudget | None] = contextvars.ContextVar(
    "llm_retry_budget", default=None
)


@contextlib.contextmanager
def retry_budget(
    *,
    deadline_seconds: float = _RETRY_DEADLINE_SECONDS,
    max_retries: int = _MAX_TOTAL_TRANSIENT_RETRIES,
) -> Iterator[_RetryBudget]:
    """Share one transient-retry budget across all nested ``_run_with_retry`` calls.

    The outermost scope wins, so validation-retry loops (or callers wrapping a
    fallback chain) cap the total transient retries instead of multiplying them.
    """
    existing = _retry_budget_var.get()
    if existing is not None:
        yield existing
        return
    budget = _RetryBudget(deadline_seconds=deadline_seconds, max_retries=max_retries)
    token = _retry_budget_var.set(budget)
    try:
        yield budget
    finally:
        _retry_budget_var.reset(token)


def _is_gemini(model: str) -> bool:
    return model.startswith(_GEMINI_PREFIXES)


def _needs_thinking_disabled(model: str) -> bool:
    lowered = model.lower()
    return model.startswith(_DEEPSEEK_PREFIX) or (
        model.startswith("fireworks:") and "deepseek" in lowered
    )


def _model_settings(
    *,
    temperature: float,
    timeout: float,
    model: str,
    structured: bool,
) -> ModelSettings:
    """Build per-request ModelSettings, applying provider-specific structured-output fixes."""
    settings: ModelSettings = ModelSettings(temperature=temperature, timeout=timeout)
    if structured and _needs_thinking_disabled(model):
        settings["extra_body"] = _DEEPSEEK_DISABLE_THINKING_EXTRA_BODY
    return settings


def _exception_chain(exc: BaseException) -> list[BaseException]:
    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and current not in chain and len(chain) < 8:
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain


def _status_code_of(exc: BaseException) -> int | None:
    """Return the HTTP status carried by the exception (attribute first, then message)."""
    for obj in _exception_chain(exc):
        for candidate in (
            getattr(obj, "status_code", None),
            getattr(obj, "status", None),
            getattr(obj, "code", None),
            getattr(getattr(obj, "response", None), "status_code", None),
        ):
            if isinstance(candidate, int) and 100 <= candidate <= 599:
                return candidate
    message = str(exc)
    for pattern in (_STATUS_IN_MSG, _STATUS_NAME_IN_MSG):
        match = pattern.search(message)
        if match:
            code = int(match.group(1))
            if 100 <= code <= 599:
                return code
    return None


def _is_retryable(exc: BaseException) -> bool:
    """Return True if *exc* represents a transient provider error worth retrying.

    Classification order: transport exception types (timeouts, connection
    errors) -> HTTP status (429/500/502/503/504 retry, any other status does
    not) -> whole-phrase transient markers in the message.
    """
    if any(isinstance(obj, _TRANSIENT_EXCEPTION_TYPES) for obj in _exception_chain(exc)):
        return True
    status = _status_code_of(exc)
    if status is not None:
        return status in _RETRYABLE_STATUS_CODES
    return bool(_TRANSIENT_PHRASES.search(str(exc)))


def _parse_retry_after(exc: BaseException) -> float:
    """Extract the Retry-After value (seconds) from a 429 exception, if present.

    Gemini 429 responses may include a Retry-After header. PydanticAI surfaces
    this value in the exception message or as an attribute on the underlying
    response. Returns 0.0 when not found so callers can safely use max().
    """
    exc_str = str(exc)
    # Try common patterns: "retry-after: 30", "Retry-After=30", "retry_after=30"
    patterns = [
        r"retry[-_]after[:\s=]+(\d+(?:\.\d+)?)",
        r'"retry-after":\s*"?(\d+(?:\.\d+)?)"?',
    ]
    for pattern in patterns:
        m = re.search(pattern, exc_str, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
    # Check for retry_after attribute on the exception or its cause
    for obj in (exc, getattr(exc, "__cause__", None), getattr(exc, "__context__", None)):
        if obj is not None and hasattr(obj, "retry_after"):
            try:
                return float(obj.retry_after)
            except (TypeError, ValueError):
                pass
        if obj is not None and hasattr(obj, "headers"):
            try:
                return float(obj.headers.get("retry-after", 0))
            except (TypeError, ValueError):
                pass
    return 0.0


async def _run_with_retry(agent: Agent[Any, Any], prompt: str, *, model_settings: ModelSettings) -> Any:
    """Run *agent* with exponential-backoff retry on transient errors.

    Retries transient conditions (see ``_is_retryable``). Non-retryable errors
    (auth failures, schema errors, etc.) are re-raised immediately.

    Retries draw from the ambient ``retry_budget`` (created here if none is
    active), so nested callers share one cap on retry count and wall-clock
    deadline. A Retry-After that would overrun the deadline fails fast.
    """
    with retry_budget() as budget:
        attempt = 0
        while True:
            try:
                return await agent.run(prompt, model_settings=model_settings)
            except Exception as exc:
                if not _is_retryable(exc):
                    raise
                retry_after = _parse_retry_after(exc)
                exponential_delay = min(_BASE_DELAY * (2**attempt) + random.uniform(0, 1), _MAX_DELAY)
                delay = max(exponential_delay, retry_after)
                if budget.retries_left <= 0 or time.monotonic() + delay > budget.deadline:
                    logger.warning("LLM transient error; retry budget exhausted, giving up: %s", exc)
                    raise
                budget.retries_left -= 1
                attempt += 1
                logger.warning(
                    "LLM transient error (retry %d, %d left in budget), retrying in %.1fs%s: %s",
                    attempt,
                    budget.retries_left,
                    delay,
                    f" (Retry-After={retry_after:.0f}s)" if retry_after > 0 else "",
                    exc,
                )
                await asyncio.sleep(delay)


_DEFAULT_TIMEOUT_SECONDS = 120.0


class PydanticAIClient:
    """Provider-agnostic LLM client backed by PydanticAI Agent.

    Satisfies the LLMBackend protocol. Switching the underlying model is a
    one-line change in config/settings.yaml -- no code changes required.

    Retry behavior: transient errors (HTTP 429/500/502/503/504, timeouts,
    connection errors) are retried with exponential backoff and jitter, drawing
    from a shared per-call retry budget (count + deadline). Non-retryable errors
    propagate immediately.

    timeout_seconds: Per-request HTTP timeout passed to ModelSettings.timeout.
    Reads from config/settings.yaml llm.request_timeout_seconds at construction
    time when provided; falls back to _DEFAULT_TIMEOUT_SECONDS (120s).
    """

    def __init__(self, timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS) -> None:
        self._timeout_seconds = timeout_seconds

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
        settings = _model_settings(
            temperature=temperature,
            timeout=self._timeout_seconds,
            model=model,
            structured=json_schema is not None,
        )

        if json_schema is not None:
            if _is_gemini(model):
                # NativeOutput uses Gemini's native responseSchema enforcement,
                # preserving the previous responseJsonSchema behavior exactly.
                output_type = NativeOutput(StructuredDict(json_schema))
            else:
                # Other providers: ToolOutput (default) enforces schema via tool call.
                output_type = StructuredDict(json_schema)
            # output_retries=3: extraction/screening schemas are complex; LLM sometimes
            # returns malformed JSON. More retries reduce "Exceeded maximum retries" failures.
            agent: Agent = build_agent(model, output_type=output_type, retries=3, output_retries=3)  # type: ignore[arg-type]
            result = await _run_with_retry(agent, prompt, model_settings=settings)
            output = result.output
            if isinstance(output, dict):
                return json.dumps(output)
            return str(output)
        else:
            text_agent: Agent[None, str] = build_agent(model, output_type=str)
            text_result = await _run_with_retry(text_agent, prompt, model_settings=settings)
            return text_result.output

    async def complete_text(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float = 0.0,
    ) -> str:
        """Run plain-text completion with retry/backoff and return output text."""
        return await self.complete(
            prompt,
            model=model,
            temperature=temperature,
            json_schema=None,
        )

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
        settings = _model_settings(
            temperature=temperature,
            timeout=self._timeout_seconds,
            model=model,
            structured=json_schema is not None,
        )

        if json_schema is not None:
            if _is_gemini(model):
                output_type = NativeOutput(StructuredDict(json_schema))
            else:
                output_type = StructuredDict(json_schema)
            agent = build_agent(model, output_type=output_type, retries=3, output_retries=3)  # type: ignore[arg-type]
            result = await _run_with_retry(agent, prompt, model_settings=settings)
            usage = result.usage()
            text = json.dumps(result.output) if isinstance(result.output, dict) else str(result.output)
        else:
            text_agent: Agent[None, str] = build_agent(model, output_type=str)
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

    async def complete_validated(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float,
        response_model: type[_T],
        json_schema: dict | None = None,
        max_validation_retries: int = 2,
    ) -> tuple[_T, int, int, int, int, int]:
        """Run LLM completion with schema enforcement and caller-side validation retry.

        Returns (validated_model, total_input_tokens, total_output_tokens,
                 total_cache_write, total_cache_read, validation_retries_used).

        On Pydantic ValidationError or JSON decode failure after the provider
        returns, the LLM is re-prompted with the validation error details
        appended so the model can self-correct. This eliminates silent fallback
        to heuristic paths for recoverable schema mismatches.

        If *json_schema* is not provided it is derived from
        ``response_model.model_json_schema()``.

        After *max_validation_retries* attempts the last exception propagates
        so callers can still fall back to a heuristic if desired.

        All validation attempts share one transient-retry budget.
        """
        with retry_budget():
            return await self._complete_validated(
                prompt,
                model=model,
                temperature=temperature,
                response_model=response_model,
                json_schema=json_schema,
                max_validation_retries=max_validation_retries,
            )

    async def _complete_validated(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float,
        response_model: type[_T],
        json_schema: dict | None,
        max_validation_retries: int,
    ) -> tuple[_T, int, int, int, int, int]:
        effective_schema = json_schema or response_model.model_json_schema()
        total_in = total_out = total_cw = total_cr = 0
        current_prompt = prompt
        last_exc: Exception | None = None

        for attempt in range(1 + max_validation_retries):
            text, tok_in, tok_out, cw, cr = await self.complete_with_usage(
                current_prompt,
                model=model,
                temperature=temperature,
                json_schema=effective_schema,
            )
            total_in += tok_in
            total_out += tok_out
            total_cw += cw
            total_cr += cr

            try:
                validated = response_model.model_validate_json(text)
                return validated, total_in, total_out, total_cw, total_cr, attempt
            except Exception as exc:
                last_exc = exc
                if attempt < max_validation_retries:
                    error_detail = str(exc)[:800]
                    current_prompt = (
                        f"{prompt}\n\n"
                        f"YOUR PREVIOUS RESPONSE FAILED VALIDATION.\n"
                        f"Fix the following errors and return corrected JSON:\n"
                        f"{error_detail}"
                    )
                    logger.warning(
                        "Validation retry %d/%d for %s: %s",
                        attempt + 1,
                        max_validation_retries,
                        response_model.__name__,
                        str(exc)[:200],
                    )
                    continue
        assert last_exc is not None  # guaranteed by loop structure
        raise last_exc

    async def complete_validated_parts(
        self,
        prompt_parts: list[Any],
        *,
        model: str,
        temperature: float,
        response_model: type[_T],
        json_schema: dict | None = None,
        max_validation_retries: int = 2,
    ) -> tuple[_T, int, int, int, int, int]:
        """Run multimodal completion with schema validation and retry.

        Mirrors ``complete_validated()`` but accepts prompt parts such as
        BinaryContent instances plus text instructions for multimodal calls.
        """
        with retry_budget():
            return await self._complete_validated_parts(
                prompt_parts,
                model=model,
                temperature=temperature,
                response_model=response_model,
                json_schema=json_schema,
                max_validation_retries=max_validation_retries,
            )

    async def _complete_validated_parts(
        self,
        prompt_parts: list[Any],
        *,
        model: str,
        temperature: float,
        response_model: type[_T],
        json_schema: dict | None,
        max_validation_retries: int,
    ) -> tuple[_T, int, int, int, int, int]:
        effective_schema = json_schema or response_model.model_json_schema()
        total_in = total_out = total_cw = total_cr = 0
        current_parts = list(prompt_parts)
        last_exc: Exception | None = None
        settings = _model_settings(
            temperature=temperature,
            timeout=self._timeout_seconds,
            model=model,
            structured=True,
        )

        for attempt in range(1 + max_validation_retries):
            if _is_gemini(model):
                output_type = NativeOutput(StructuredDict(effective_schema))
            else:
                output_type = StructuredDict(effective_schema)
            agent: Agent = build_agent(model, output_type=output_type, retries=3, output_retries=3)  # type: ignore[arg-type]
            result = await _run_with_retry(agent, current_parts, model_settings=settings)
            usage = result.usage()
            total_in += usage.input_tokens
            total_out += usage.output_tokens
            total_cw += usage.cache_write_tokens or 0
            total_cr += usage.cache_read_tokens or 0
            text = json.dumps(result.output) if isinstance(result.output, (dict, list)) else str(result.output)

            try:
                validated = response_model.model_validate_json(text)
                return validated, total_in, total_out, total_cw, total_cr, attempt
            except Exception as exc:
                last_exc = exc
                if attempt < max_validation_retries:
                    error_detail = str(exc)[:800]
                    retry_msg = (
                        "YOUR PREVIOUS RESPONSE FAILED VALIDATION.\n"
                        "Fix the following errors and return corrected JSON only:\n"
                        f"{error_detail}"
                    )
                    current_parts = list(prompt_parts) + [retry_msg]
                    logger.warning(
                        "Validation retry %d/%d for %s multimodal response: %s",
                        attempt + 1,
                        max_validation_retries,
                        response_model.__name__,
                        str(exc)[:200],
                    )
                    continue
        assert last_exc is not None
        raise last_exc
