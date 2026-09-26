"""Shared RateLimiter instances keyed by the provider credentials in use."""

from __future__ import annotations

import hashlib
from collections.abc import Callable

from src.config.env_context import get_env
from src.llm.rate_limiter import RateLimiter
from src.llm.registry import env_key_for_model
from src.models import SettingsConfig

_limiters: dict[str, RateLimiter] = {}


def _credential_key(settings: SettingsConfig) -> str:
    """Hash of the provider credentials used by configured agents.

    Runs sharing the same provider keys share one limiter; a missing key hashes as
    empty so keyless runs still share a single limiter per provider set.
    """
    env_keys = sorted({k for k in (env_key_for_model(a.model) for a in settings.agents.values()) if k})
    material = "|".join(f"{env_key}={get_env(env_key) or ''}" for env_key in env_keys)
    return hashlib.sha256(material.encode()).hexdigest()


def get_shared_rate_limiter(
    settings: SettingsConfig,
    on_waiting: Callable[[str, int, int, float], None] | None = None,
    on_resolved: Callable[[str, float], None] | None = None,
) -> RateLimiter:
    """Return a process-wide RateLimiter for the current primary LLM credential."""
    key = _credential_key(settings)
    if key not in _limiters:
        llm_cfg = settings.llm
        _limiters[key] = RateLimiter(
            flash_rpm=llm_cfg.flash_rpm,
            flash_lite_rpm=llm_cfg.flash_lite_rpm,
            pro_rpm=llm_cfg.pro_rpm,
            on_waiting=on_waiting,
            on_resolved=on_resolved,
        )
    return _limiters[key]


def clear_shared_rate_limiters() -> None:
    """Clear cached limiters (unit tests only)."""
    _limiters.clear()
