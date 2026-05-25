"""Factory helpers for standardized PydanticAI clients."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic_ai import (
    Agent,
    BinaryImage,
    ImageGenerationTool,
    NativeOutput,
    StructuredDict,
    WebFetchTool,
    WebSearchTool,
)
from pydantic_ai.embeddings import Embedder
from pydantic_ai.messages import BinaryContent
from pydantic_ai.settings import ModelSettings

from src.llm.provider import AgentRuntimeConfig
from src.llm.pydantic_client import PydanticAIClient, _run_with_retry
from src.llm.registry import rate_tier_for_model
from src.models import SettingsConfig

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
    import os

    if model.startswith("google:"):
        if "GOOGLE_API_KEY" not in os.environ and "GEMINI_API_KEY" in os.environ:
            os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]
        return "google-gla:" + model[7:]
    return model


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
        agent: Agent[Any, BinaryImage] = Agent(  # type: ignore[type-var]
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


async def run_text_with_web_tools(
    *,
    model: str,
    prompt: str,
    temperature: float = 0.3,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """Run a text completion with WebSearch/WebFetch built-ins."""
    agent: Agent[None, str] = Agent(
        model,
        output_type=str,
        builtin_tools=[WebSearchTool(), WebFetchTool()],
    )
    result = await _run_with_retry(
        agent,
        prompt,
        model_settings=ModelSettings(temperature=temperature, timeout=timeout_seconds),
    )
    return result.output


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
    agent: Agent[Any, Any] = Agent(model, output_type=output_type)  # type: ignore[type-var]
    result = await _run_with_retry(
        agent,
        prompt,
        model_settings=ModelSettings(temperature=temperature, timeout=timeout_seconds),
    )
    if isinstance(result.output, dict):
        import json

        return json.dumps(result.output)
    return str(result.output)
