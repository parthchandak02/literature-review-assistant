"""Central provider registry for model prefixes and runtime policies."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
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
