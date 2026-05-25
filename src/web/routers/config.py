"""Configuration and environment-key API routes."""

from __future__ import annotations

import os
import pathlib

from fastapi import APIRouter

from src.config.loader import get_required_env_keys as _get_required_env_keys
from src.config.loader import load_configs as _load_configs

router = APIRouter(prefix="/api/config", tags=["config"])


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
    env_to_ui_key = {
        "GEMINI_API_KEY": "gemini",
        "DEEPSEEK_API_KEY": "deepseek",
        "OPENROUTER_API_KEY": "openrouter",
        "OPENAI_API_KEY": "openai",
        "ANTHROPIC_API_KEY": "anthropic",
        "GROQ_API_KEY": "groq",
        "MISTRAL_API_KEY": "mistral",
        "CO_API_KEY": "cohere",
    }
    ui_keys = [env_to_ui_key[key] for key in env_keys if key in env_to_ui_key]
    return {"env_keys": env_keys, "ui_keys": ui_keys}
