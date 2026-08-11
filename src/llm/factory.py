"""Factory helpers for standardized PydanticAI clients."""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic_ai import (
    AgentRunResultEvent,
    BinaryImage,
    ImageGenerationTool,
    NativeOutput,
    StructuredDict,
    WebFetchTool,
    WebSearchTool,
)
from pydantic_ai.embeddings import Embedder
from pydantic_ai.messages import BaseToolCallPart, BinaryContent, BuiltinToolCallEvent
from pydantic_ai.settings import ModelSettings

from src.llm.provider import AgentRuntimeConfig
from src.llm.pydantic_client import (
    _BASE_DELAY,
    _MAX_DELAY,
    _MAX_RETRIES,
    PydanticAIClient,
    _is_retryable,
    _parse_retry_after,
    _run_with_retry,
)
from src.llm.registry import build_agent, normalize_agent_model_prefix, rate_tier_for_model
from src.models import SettingsConfig

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 120.0
_chat_clients: dict[float, PydanticAIClient] = {}
_embedder_cache: dict[tuple[str, int], Embedder] = {}
_image_clients: dict[float, PydanticAIImageClient] = {}


def resolve_agent(settings: SettingsConfig, key: str) -> AgentRuntimeConfig:
    agent = settings.agents[key]
    return AgentRuntimeConfig(
        model=agent.model,
        temperature=agent.temperature,
        tier=rate_tier_for_model(agent.model),
    )


def get_chat_client(timeout_seconds: float | None = None) -> PydanticAIClient:
    timeout = float(timeout_seconds or _DEFAULT_TIMEOUT_SECONDS)
    client = _chat_clients.get(timeout)
    if client is None:
        client = PydanticAIClient(timeout_seconds=timeout)
        _chat_clients[timeout] = client
    return client


def _normalize_embed_model(model: str) -> str:
    """Map settings.yaml ``google:`` aliases to PydanticAI's ``google-gla:`` embedder prefix."""
    return normalize_agent_model_prefix(model)


def get_embedder(model: str, dim: int) -> Embedder:
    normalized = _normalize_embed_model(model)
    key = (normalized, dim)
    embedder = _embedder_cache.get(key)
    if embedder is None:
        embedder = Embedder(normalized, settings={"dimensions": dim})
        _embedder_cache[key] = embedder
    return embedder


class PydanticAIImageClient:
    """Unified image generation client using PydanticAI built-in tools."""

    def __init__(self, timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS) -> None:
        self._timeout_seconds = timeout_seconds

    async def generate(
        self,
        *,
        model: str,
        prompt: str,
        aspect_ratio: str,
        size: str,
        reference_image_paths: list[str] | None = None,
    ) -> tuple[bytes, dict[str, int]]:
        tool = ImageGenerationTool(aspect_ratio=aspect_ratio, size=size)
        agent = build_agent(  # type: ignore[type-var]
            model,
            builtin_tools=[tool],
            output_type=BinaryImage,
        )
        parts: list[Any] = [prompt]
        for image_path in reference_image_paths or []:
            p = Path(image_path)
            if not p.exists():
                continue
            suffix = p.suffix.lower()
            media_type = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
                ".gif": "image/gif",
            }.get(suffix)
            if media_type is None:
                continue
            parts.append(BinaryContent(data=p.read_bytes(), media_type=media_type))
        result = await _run_with_retry(
            agent,
            parts,
            model_settings=ModelSettings(timeout=self._timeout_seconds),
        )
        usage = result.usage()
        payload = result.output
        return payload.data, {
            "tokens_in": usage.input_tokens or 0,
            "tokens_out": usage.output_tokens or 0,
            "cache_write_tokens": usage.cache_write_tokens or 0,
            "cache_read_tokens": usage.cache_read_tokens or 0,
        }


def get_image_client(timeout_seconds: float | None = None) -> PydanticAIImageClient:
    timeout = float(timeout_seconds or _DEFAULT_TIMEOUT_SECONDS)
    client = _image_clients.get(timeout)
    if client is None:
        client = PydanticAIImageClient(timeout_seconds=timeout)
        _image_clients[timeout] = client
    return client


def web_tool_progress_message(part: BaseToolCallPart) -> str | None:
    """Map a built-in web tool call to a short user-facing progress line."""
    tool = (part.tool_name or "").lower()
    args = part.args_as_dict()
    if "web_search" in tool:
        for key in ("query", "search_query", "q", "search_queries"):
            val = args.get(key)
            if isinstance(val, str) and val.strip():
                query = val.strip()
                suffix = "…" if len(query) > 100 else ""
                return f"Searching: {query[:100]}{suffix}"
            if isinstance(val, list) and val:
                first = str(val[0]).strip()
                if first:
                    suffix = "…" if len(first) > 100 else ""
                    return f"Searching: {first[:100]}{suffix}"
        return "Running Google web search..."
    if "web_fetch" in tool or tool.endswith("_fetch"):
        url = args.get("url") or args.get("uri")
        if isinstance(url, str) and url.strip():
            host = urlparse(url.strip()).netloc
            return f"Reading {host or url.strip()[:60]}"
        return "Fetching source pages..."
    return None


async def _run_text_with_web_tools_stream(
    agent: Any,
    prompt: str,
    *,
    model_settings: ModelSettings,
    on_progress: Callable[[str], None],
) -> str:
    on_progress("Planning search queries from your question...")
    final_output: str | None = None
    async for event in agent.run_stream_events(prompt, model_settings=model_settings):
        if isinstance(event, BuiltinToolCallEvent):
            message = web_tool_progress_message(event.part)
            if message:
                on_progress(message)
        elif isinstance(event, AgentRunResultEvent):
            final_output = str(event.result.output)
    if final_output is None:
        raise RuntimeError("Web research completed without output")
    return final_output


async def run_text_with_web_tools(
    *,
    model: str,
    prompt: str,
    temperature: float = 0.3,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    on_progress: Callable[[str], None] | None = None,
) -> str:
    """Run a text completion with WebSearch/WebFetch built-ins."""
    agent = build_agent(
        model,
        output_type=str,
        builtin_tools=[WebSearchTool(), WebFetchTool()],
    )
    model_settings = ModelSettings(temperature=temperature, timeout=timeout_seconds)
    if on_progress is None:
        result = await _run_with_retry(agent, prompt, model_settings=model_settings)
        return result.output

    for attempt in range(_MAX_RETRIES):
        try:
            return await _run_text_with_web_tools_stream(
                agent,
                prompt,
                model_settings=model_settings,
                on_progress=on_progress,
            )
        except Exception as exc:
            if not _is_retryable(exc) or attempt == _MAX_RETRIES - 1:
                raise
            retry_after = _parse_retry_after(exc)
            exponential_delay = min(_BASE_DELAY * (2**attempt) + random.uniform(0, 1), _MAX_DELAY)
            delay = max(exponential_delay, retry_after)
            logger.warning(
                "Web research transient error (attempt %d/%d), retrying in %.1fs: %s",
                attempt + 1,
                _MAX_RETRIES,
                delay,
                exc,
            )
            on_progress("Web search interrupted, retrying...")
            await asyncio.sleep(delay)
    raise RuntimeError("unreachable")  # pragma: no cover


async def run_native_structured_json(
    *,
    model: str,
    prompt: str,
    schema: dict[str, Any],
    temperature: float = 0.3,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """Run a schema-constrained completion and return JSON string output."""
    output_type = NativeOutput(StructuredDict(schema))
    agent = build_agent(model, output_type=output_type)  # type: ignore[type-var]
    result = await _run_with_retry(
        agent,
        prompt,
        model_settings=ModelSettings(temperature=temperature, timeout=timeout_seconds),
    )
    if isinstance(result.output, dict):
        import json

        return json.dumps(result.output)
    return str(result.output)
