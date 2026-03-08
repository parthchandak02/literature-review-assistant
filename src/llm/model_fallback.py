"""Centralized fallback model resolver.

When config load fails (e.g. missing key in settings.yaml), modules that need
a model string call get_fallback_model() instead of hardcoding stale model names.
The last-resort constants below match the current tiers in settings.yaml and will
be kept in sync manually -- they are the ONLY place model names may be hardcoded.

Tier mapping:
  lite  -- highest throughput (flash-lite): screening, table extraction, search
  flash -- balanced (flash): extraction, quality, writing, humanizer
  pro   -- highest quality (pro): currently unused in production config
"""

from __future__ import annotations

_TIER_LAST_RESORT: dict[str, str] = {
    "lite": "google-gla:gemini-3.1-flash-lite-preview",
    "flash": "google-gla:gemini-3-flash-preview",
    "pro": "google-gla:gemini-3-flash-preview",  # pro mapped to flash; pro quota is scarce
}


def get_fallback_model(tier: str = "flash") -> str:
    """Return a fallback model string for the given tier.

    First attempts to read the setting from config/settings.yaml so the
    fallback stays in sync with the operator's config. Falls back to the
    last-resort constant only when config load itself fails.

    Args:
        tier: "lite", "flash", or "pro"

    Returns:
        A fully-qualified model string e.g. "google-gla:gemini-3-flash-preview".
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
        agent_cfg = s.agents.get(agent_key)
        if agent_cfg and agent_cfg.model:
            return agent_cfg.model
    except Exception:
        pass
    return _TIER_LAST_RESORT.get(tier, _TIER_LAST_RESORT["flash"])
