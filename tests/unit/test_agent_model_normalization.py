"""Agent model prefix normalization and settings.yaml google: resolution."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic_ai.models.google import GoogleModel

from src.llm.registry import build_agent, infer_agent_model, normalize_agent_model_prefix

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SETTINGS_PATH = _REPO_ROOT / "config" / "settings.yaml"


def _google_models_from_settings() -> list[str]:
    raw = yaml.safe_load(_SETTINGS_PATH.read_text(encoding="utf-8"))
    models: list[str] = []
    for agent_cfg in raw.get("agents", {}).values():
        model = str(agent_cfg.get("model", "")).strip()
        if model.startswith("google:"):
            models.append(model)
    assert models, "expected at least one google: agent in config/settings.yaml"
    return models


def test_normalize_agent_model_prefix_maps_google_alias() -> None:
    assert normalize_agent_model_prefix("google:gemini-2.5-flash") == "google-gla:gemini-2.5-flash"
    assert normalize_agent_model_prefix("google-gla:gemini-2.5-flash") == "google-gla:gemini-2.5-flash"
    assert normalize_agent_model_prefix("deepseek:deepseek-v4-flash") == "deepseek:deepseek-v4-flash"


@pytest.fixture
def stub_gemini_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")


@pytest.mark.parametrize("model", _google_models_from_settings())
def test_settings_google_models_resolve(model: str, stub_gemini_api_key: None) -> None:
    resolved = infer_agent_model(model)
    assert isinstance(resolved, GoogleModel)
    assert normalize_agent_model_prefix(model).startswith("google-gla:")


@pytest.mark.parametrize("model", _google_models_from_settings())
def test_build_agent_accepts_settings_google_models(model: str, stub_gemini_api_key: None) -> None:
    agent = build_agent(model, output_type=str)
    assert agent is not None
