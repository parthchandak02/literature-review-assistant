"""Fallback model resolution must stay centralized in settings.yaml."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.llm import model_fallback


def _settings_with_agents(**models: str) -> SimpleNamespace:
    agents = {key: SimpleNamespace(model=value) for key, value in models.items()}
    return SimpleNamespace(agents=agents)


@pytest.mark.parametrize(
    ("tier", "agent_key"),
    [
        ("lite", "screening_reviewer_a"),
        ("flash", "writing"),
        ("pro", "quality_assessment"),
        ("unknown", "writing"),
    ],
)
def test_get_fallback_model_maps_tier_to_settings_agent(
    monkeypatch: pytest.MonkeyPatch,
    tier: str,
    agent_key: str,
) -> None:
    settings = _settings_with_agents(
        screening_reviewer_a="provider:lite-model",
        writing="provider:flash-model",
        quality_assessment="provider:pro-model",
    )
    monkeypatch.setattr(
        "src.config.loader.load_configs",
        lambda settings_path="config/settings.yaml": (None, settings),
    )
    expected = settings.agents[agent_key].model
    assert model_fallback.get_fallback_model(tier) == expected


def test_get_fallback_model_defaults_flash_tier(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings_with_agents(writing="provider:default-flash")
    monkeypatch.setattr(
        "src.config.loader.load_configs",
        lambda settings_path="config/settings.yaml": (None, settings),
    )
    assert model_fallback.get_fallback_model() == "provider:default-flash"


def test_get_fallback_model_raises_when_settings_cannot_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(settings_path: str = "config/settings.yaml") -> tuple[None, None]:
        raise OSError("missing settings")

    monkeypatch.setattr("src.config.loader.load_configs", _boom)
    with pytest.raises(RuntimeError, match="Unable to load model fallback"):
        model_fallback.get_fallback_model("flash")


def test_get_fallback_model_raises_when_agent_model_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings_with_agents(writing="")
    settings.agents["writing"] = SimpleNamespace(model="")
    monkeypatch.setattr(
        "src.config.loader.load_configs",
        lambda settings_path="config/settings.yaml": (None, settings),
    )
    with pytest.raises(RuntimeError, match="Missing agent model for fallback tier 'flash'"):
        model_fallback.get_fallback_model("flash")


def test_get_fallback_model_raises_when_agent_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(agents={})
    monkeypatch.setattr(
        "src.config.loader.load_configs",
        lambda settings_path="config/settings.yaml": (None, settings),
    )
    with pytest.raises(RuntimeError, match="Missing agent model for fallback tier 'lite'"):
        model_fallback.get_fallback_model("lite")
