"""YAML and env loader with fail-fast validation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple

import yaml
from dotenv import load_dotenv

from src.models import ReviewConfig, SettingsConfig


# Map model string prefixes to the env var that must be set for that provider.
_PREFIX_TO_ENV: dict[str, str] = {
    "google-gla:": "GEMINI_API_KEY",
    "google-vertex:": "GEMINI_API_KEY",
    "anthropic:": "ANTHROPIC_API_KEY",
    "openai:": "OPENAI_API_KEY",
    "groq:": "GROQ_API_KEY",
    "mistral:": "MISTRAL_API_KEY",
    "cohere:": "CO_API_KEY",
}


def _read_yaml(path: str) -> dict:
    resolved = Path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"Missing config file: {path}")
    with resolved.open("r", encoding="utf-8") as file_obj:
        loaded = yaml.safe_load(file_obj) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected object at root of YAML file: {path}")
    return loaded


def get_required_env_keys(settings: SettingsConfig) -> list[str]:
    """Derive which API key env vars are required based on configured model prefixes.

    Returns a list of env var names that must be set. If all agents use
    google-gla: prefix (the default), only GEMINI_API_KEY is required.
    Switching any agent to anthropic: adds ANTHROPIC_API_KEY to the list.
    """
    required: set[str] = set()
    for agent_cfg in settings.agents.values():
        for prefix, env_key in _PREFIX_TO_ENV.items():
            if agent_cfg.model.startswith(prefix):
                required.add(env_key)
    # Fallback: if no prefix matched, require GEMINI_API_KEY (safe default).
    if not required:
        required.add("GEMINI_API_KEY")
    return sorted(required)


def load_configs(
    review_path: str = "config/review.yaml",
    settings_path: str = "config/settings.yaml",
) -> Tuple[ReviewConfig, SettingsConfig]:
    load_dotenv()
    review = ReviewConfig.model_validate(_read_yaml(review_path))
    settings = SettingsConfig.model_validate(_read_yaml(settings_path))
    return review, settings


def validate_secret_env(settings: SettingsConfig | None = None) -> list[str]:
    """Return list of missing required env var names.

    If settings is provided, derives required keys dynamically from model
    prefixes. Otherwise falls back to requiring GEMINI_API_KEY only.
    """
    load_dotenv()
    if settings is not None:
        required = get_required_env_keys(settings)
    else:
        required = ["GEMINI_API_KEY"]
    return [key for key in required if not os.getenv(key)]
