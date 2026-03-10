"""Resolve fallback models from settings.yaml only.

This module intentionally does NOT hardcode concrete model IDs.
If settings cannot be loaded, callers get a clear runtime error so model
selection remains centralized in config/settings.yaml.
"""

from __future__ import annotations


def get_fallback_model(tier: str = "flash") -> str:
    """Return model string for the requested tier from settings.yaml.

    Raises:
        RuntimeError: when settings cannot be loaded or required model key is missing.
    """
    _tier_to_agent: dict[str, str] = {
        "lite": "screening_reviewer_a",
        "flash": "writing",
        "pro": "quality_assessment",
    }
    agent_key = _tier_to_agent.get(tier, "writing")
    try:
        from src.config.loader import load_configs

        _, s = load_configs(settings_path="config/settings.yaml")
    except Exception as exc:
        raise RuntimeError("Unable to load model fallback from config/settings.yaml") from exc

    agent_cfg = s.agents.get(agent_key)
    if agent_cfg and agent_cfg.model:
        return agent_cfg.model
    raise RuntimeError(f"Missing agent model for fallback tier '{tier}' in config/settings.yaml")
