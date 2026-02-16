"""YAML and env loader with fail-fast validation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple

import yaml
from dotenv import load_dotenv

from src.models import ReviewConfig, SettingsConfig


REQUIRED_ENV_KEYS = ("GEMINI_API_KEY",)


def _read_yaml(path: str) -> dict:
    resolved = Path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"Missing config file: {path}")
    with resolved.open("r", encoding="utf-8") as file_obj:
        loaded = yaml.safe_load(file_obj) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected object at root of YAML file: {path}")
    return loaded


def load_configs(
    review_path: str = "config/review.yaml",
    settings_path: str = "config/settings.yaml",
) -> Tuple[ReviewConfig, SettingsConfig]:
    load_dotenv()
    review = ReviewConfig.model_validate(_read_yaml(review_path))
    settings = SettingsConfig.model_validate(_read_yaml(settings_path))
    return review, settings


def validate_secret_env() -> list[str]:
    load_dotenv()
    missing: list[str] = []
    for key in REQUIRED_ENV_KEYS:
        if not os.getenv(key):
            missing.append(key)
    return missing
