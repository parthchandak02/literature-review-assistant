"""Central provider registry for model prefixes and runtime policies."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic_ai import Agent

if TYPE_CHECKING:
    from pydantic_ai.models import Model
    from pydantic_ai.providers import Provider

    from src.models import SettingsConfig

# PydanticAI model prefix -> required auth env var.
PREFIX_TO_ENV: dict[str, str] = {
    "google:": "GEMINI_API_KEY",
    "google-cloud:": "GEMINI_API_KEY",
    # Deprecated aliases retained for backward compatibility.
    "google-gla:": "GEMINI_API_KEY",
    "google-vertex:": "GEMINI_API_KEY",
    "anthropic:": "ANTHROPIC_API_KEY",
    "openai:": "OPENAI_API_KEY",
    "openai-responses:": "OPENAI_API_KEY",
    "groq:": "GROQ_API_KEY",
    "mistral:": "MISTRAL_API_KEY",
    "cohere:": "CO_API_KEY",
    "deepseek:": "DEEPSEEK_API_KEY",
    "openrouter:": "OPENROUTER_API_KEY",
}

# PydanticAI model prefix -> genai-prices provider id.
PREFIX_TO_PROVIDER_ID: dict[str, str] = {
    "google:": "google",
    "google-cloud:": "google",
    "google-gla:": "google",
    "google-vertex:": "google",
    "anthropic:": "anthropic",
    "openai:": "openai",
    "openai-responses:": "openai",
    "groq:": "groq",
    "mistral:": "mistral",
    "cohere:": "cohere",
    "deepseek:": "deepseek",
    # OpenRouter is an OpenAI-compatible gateway for many providers.
    "openrouter:": "openai",
}


def normalize_agent_model_prefix(model: str) -> str:
    """Map settings.yaml ``google:`` aliases to PydanticAI's ``google-gla:`` agent prefix."""
    if model.startswith("google:"):
        return "google-gla:" + model[7:]
    return model


def _api_key_for_model(model: str) -> str | None:
    from src.config.env_context import get_env

    env_key = env_key_for_model(model)
    if env_key is None:
        return None
    return get_env(env_key)


def _provider_with_api_key(provider_name: str, api_key: str | None) -> Provider[Any]:
    """Construct a pydantic-ai provider with explicit api_key from get_env()."""
    if provider_name in ("google-vertex", "google-gla"):
        from pydantic_ai.providers.google import GoogleProvider

        return GoogleProvider(api_key=api_key, vertexai=provider_name == "google-vertex")
    if provider_name in ("openai", "openai-responses", "openai-chat"):
        from pydantic_ai.providers.openai import OpenAIProvider

        return OpenAIProvider(api_key=api_key)
    if provider_name == "anthropic":
        from pydantic_ai.providers.anthropic import AnthropicProvider

        return AnthropicProvider(api_key=api_key)
    if provider_name == "groq":
        from pydantic_ai.providers.groq import GroqProvider

        return GroqProvider(api_key=api_key)
    if provider_name == "mistral":
        from pydantic_ai.providers.mistral import MistralProvider

        return MistralProvider(api_key=api_key)
    if provider_name == "cohere":
        from pydantic_ai.providers.cohere import CohereProvider

        return CohereProvider(api_key=api_key)
    if provider_name == "deepseek":
        from pydantic_ai.providers.deepseek import DeepSeekProvider

        return DeepSeekProvider(api_key=api_key)
    if provider_name == "openrouter":
        from pydantic_ai.providers.openrouter import OpenRouterProvider

        return OpenRouterProvider(api_key=api_key)

    from pydantic_ai.providers import infer_provider

    return infer_provider(provider_name)


def infer_agent_model(model: str) -> Model:
    """Resolve a configured model string to a PydanticAI Model with explicit auth."""
    from pydantic_ai.models import infer_model

    normalized = normalize_agent_model_prefix(model)
    api_key = _api_key_for_model(model)

    def provider_factory(provider_name: str) -> Provider[Any]:
        return _provider_with_api_key(provider_name, api_key)

    return infer_model(normalized, provider_factory=provider_factory)


def build_agent(model: str, **kwargs: Any) -> Agent[Any, Any]:
    """Construct an Agent with normalized model prefix and explicit provider auth."""
    return Agent(infer_agent_model(model), **kwargs)


def parse_model_ref(model: str) -> tuple[str, str | None]:
    """Split '<provider-prefix><model-ref>' -> ('<model-ref>', '<provider_id>')."""
    for prefix, provider_id in PREFIX_TO_PROVIDER_ID.items():
        if model.startswith(prefix):
            return model[len(prefix) :], provider_id
    return model, None


def env_key_for_model(model: str) -> str | None:
    """Return required env key for a model string, if recognized."""
    for prefix, env_key in PREFIX_TO_ENV.items():
        if model.startswith(prefix):
            return env_key
    return None


def required_env_keys_from_settings(settings: SettingsConfig) -> list[str]:
    """Collect env keys implied by all configured model references."""
    required: set[str] = set()

    for agent_cfg in settings.agents.values():
        env_key = env_key_for_model(agent_cfg.model)
        if env_key:
            required.add(env_key)

    for model in (
        settings.rag.embed_model,
        settings.rag.hyde_model,
        settings.rag.reranker_model,
        settings.extraction.pdf_vision_model,
    ):
        if model:
            env_key = env_key_for_model(model)
            if env_key:
                required.add(env_key)

    if not required:
        required.add("DEEPSEEK_API_KEY")
    return sorted(required)


_GOOGLE_PREFIXES = tuple(k for k in PREFIX_TO_ENV if k.startswith("google"))


def supports_native_image_generation(model: str) -> bool:
    """Return True when *model* can drive PydanticAI ImageGenerationTool."""
    if not model.startswith(_GOOGLE_PREFIXES):
        return False
    lowered = model.lower()
    # Explicit image-preview / imagen refs; other Google chat models cannot emit BinaryImage.
    return "image" in lowered or "imagen" in lowered


def rate_tier_for_model(model: str) -> str:
    """Map model strings to rate-limit tiers (flash-lite / flash / pro)."""
    lowered = model.lower()
    if any(token in lowered for token in ("flash-lite", "lite", "mini")):
        return "flash-lite"
    if "deepseek-v4-pro" in lowered or ("-pro" in lowered and "deepseek" in lowered):
        return "pro"
    if any(token in lowered for token in ("flash", "haiku", "sonnet", "deepseek-v4-flash")):
        return "flash"
    return "pro"
