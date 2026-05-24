from __future__ import annotations

from src.llm.registry import env_key_for_model, parse_model_ref, rate_tier_for_model, required_env_keys_from_settings
from src.models import SettingsConfig


def _settings_with_models(agent_model: str, *, embed_model: str = "google:gemini-embedding-001") -> SettingsConfig:
    return SettingsConfig.model_validate(
        {
            "agents": {
                "writing": {"model": agent_model, "temperature": 0.1},
            },
            "rag": {
                "embed_model": embed_model,
                "embed_dim": 768,
                "use_hyde": False,
                "rerank": False,
            },
            "extraction": {
                "use_pdf_vision": False,
                "pdf_vision_model": "",
            },
        }
    )


def test_parse_model_ref_handles_openrouter() -> None:
    model_ref, provider_id = parse_model_ref("openrouter:deepseek/deepseek-v4-flash")
    assert model_ref == "deepseek/deepseek-v4-flash"
    assert provider_id == "openai"


def test_required_env_keys_from_settings_includes_agent_and_embed_models() -> None:
    settings = _settings_with_models("deepseek:deepseek-v4-flash", embed_model="openai:text-embedding-3-small")
    keys = required_env_keys_from_settings(settings)
    assert "DEEPSEEK_API_KEY" in keys
    assert "OPENAI_API_KEY" in keys


def test_rate_tier_for_model_maps_flash_lite_and_flash() -> None:
    assert rate_tier_for_model("google:gemini-2.5-flash-lite") == "flash-lite"
    assert rate_tier_for_model("deepseek:deepseek-v4-flash") == "flash"
    assert rate_tier_for_model("openai:gpt-5") == "pro"


def test_env_key_for_model_unknown_prefix() -> None:
    assert env_key_for_model("unknown:model") is None
