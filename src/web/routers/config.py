"""Configuration and environment-key API routes."""

from __future__ import annotations

import os
import pathlib

from fastapi import APIRouter

from src.config.loader import get_required_env_keys as _get_required_env_keys
from src.config.loader import load_configs as _load_configs

router = APIRouter(prefix="/api/config", tags=["config"])

_UI_KEY_TO_ENV: dict[str, str] = {
    "gemini": "GEMINI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "cohere": "CO_API_KEY",
    "openalex": "OPENALEX_API_KEY",
    "ieee": "IEEE_API_KEY",
    "pubmedEmail": "PUBMED_EMAIL",
    "pubmedApiKey": "PUBMED_API_KEY",
    "perplexity": "PERPLEXITY_SEARCH_API_KEY",
    "semanticScholar": "SEMANTIC_SCHOLAR_API_KEY",
    "crossrefEmail": "CROSSREF_EMAIL",
    "wos": "WOS_API_KEY",
    "scopus": "SCOPUS_API_KEY",
}


def _mask_secret(value: str) -> str:
    trimmed = (value or "").strip()
    if not trimmed or trimmed.lower() in {"undefined", "your-deepseek-api-key", "your-gemini-api-key"}:
        return ""
    if len(trimmed) <= 8:
        return "••••"
    return f"{trimmed[:4]}…{trimmed[-4:]}"


@router.get("/review")
async def get_review_config() -> dict[str, str]:
    try:
        content = pathlib.Path("config/review.yaml").read_text()
    except Exception:
        content = ""
    return {"content": content}


@router.get("/env-keys")
async def get_env_keys() -> dict[str, str]:
    return {
        "gemini": os.environ.get("GEMINI_API_KEY", ""),
        "deepseek": os.environ.get("DEEPSEEK_API_KEY", ""),
        "openrouter": os.environ.get("OPENROUTER_API_KEY", ""),
        "openai": os.environ.get("OPENAI_API_KEY", ""),
        "anthropic": os.environ.get("ANTHROPIC_API_KEY", ""),
        "groq": os.environ.get("GROQ_API_KEY", ""),
        "mistral": os.environ.get("MISTRAL_API_KEY", ""),
        "cohere": os.environ.get("CO_API_KEY", ""),
        "openalex": os.environ.get("OPENALEX_API_KEY", ""),
        "ieee": os.environ.get("IEEE_API_KEY", ""),
        "pubmedEmail": os.environ.get("PUBMED_EMAIL", "") or os.environ.get("NCBI_EMAIL", ""),
        "pubmedApiKey": os.environ.get("PUBMED_API_KEY", ""),
        "perplexity": os.environ.get("PERPLEXITY_SEARCH_API_KEY", ""),
        "semanticScholar": os.environ.get("SEMANTIC_SCHOLAR_API_KEY", ""),
        "crossrefEmail": os.environ.get("CROSSREF_EMAIL", ""),
        "wos": os.environ.get("WOS_API_KEY", ""),
        "scopus": os.environ.get("SCOPUS_API_KEY", ""),
    }


@router.get("/env-keys/required")
async def get_required_env_keys() -> dict[str, list[str]]:
    cfg = _load_configs(settings_path="config/settings.yaml")[1]
    env_keys = _get_required_env_keys(cfg)
    env_to_ui_key = {v: k for k, v in _UI_KEY_TO_ENV.items()}
    ui_keys = [env_to_ui_key[key] for key in env_keys if key in env_to_ui_key]
    return {"env_keys": env_keys, "ui_keys": ui_keys}


@router.get("/env-keys/status")
async def get_env_keys_status() -> dict[str, object]:
    """Return which credentials are configured on the server (.env), without exposing secrets."""
    cfg = _load_configs(settings_path="config/settings.yaml")[1]
    required_env = _get_required_env_keys(cfg)
    env_to_ui_key = {v: k for k, v in _UI_KEY_TO_ENV.items()}
    required_ui = [env_to_ui_key[key] for key in required_env if key in env_to_ui_key]

    providers: dict[str, dict[str, object]] = {}
    for ui_key, env_name in _UI_KEY_TO_ENV.items():
        raw = os.environ.get(env_name, "")
        if env_name == "PUBMED_EMAIL" and not raw:
            raw = os.environ.get("NCBI_EMAIL", "")
        masked = _mask_secret(raw)
        providers[ui_key] = {
            "configured": bool(masked),
            "masked": masked,
            "source": "env" if masked else None,
            "required": ui_key in required_ui,
        }

    return {
        "required_ui_keys": required_ui,
        "providers": providers,
        "server_ready": all(providers.get(k, {}).get("configured") for k in required_ui),
    }
