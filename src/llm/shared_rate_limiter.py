"""Shared RateLimiter instances keyed by primary LLM credential."""

from __future__ import annotations

import hashlib
from collections.abc import Callable

from src.config.env_context import get_env
from src.llm.rate_limiter import RateLimiter
from src.models import SettingsConfig

_limiters: dict[str, RateLimiter] = {}


def _credential_key() -> str:
    """Hash of GEMINI_API_KEY so providers sharing a key share one limiter."""
    raw = get_env("GEMINI_API_KEY") or ""
    return hashlib.sha256(raw.encode()).hexdigest()


def get_shared_rate_limiter(
    settings: SettingsConfig,
    on_waiting: Callable[[str, int, int, float], None] | None = None,
    on_resolved: Callable[[str, float], None] | None = None,
) -> RateLimiter:
    """Return a process-wide RateLimiter for the current primary LLM credential."""
    key = _credential_key()
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
