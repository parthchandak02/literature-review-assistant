from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from src.config.loader import get_required_env_keys
from src.models import SettingsConfig
from src.orchestration.context import RunContext
from src.orchestration.state import ReviewState


def now_utc() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def hash_config(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def evaluate_rag_health(
    *,
    empty_sections: int,
    error_sections: int,
    max_empty_sections: int,
) -> tuple[bool, str]:
    failures = max(0, int(empty_sections)) + max(0, int(error_sections))
    limit = max(0, int(max_empty_sections))
    breached = failures > limit
    message = (
        "RAG health threshold "
        + ("violated" if breached else "ok")
        + f": empty+error sections={failures}, max_empty_sections={limit}"
    )
    return breached, message


def llm_available(settings: ReviewState | None = None, settings_cfg: SettingsConfig | None = None) -> bool:
    cfg: SettingsConfig | None = settings_cfg
    if cfg is None and settings is not None and hasattr(settings, "settings"):
        cfg = settings.settings
    if cfg is None:
        from src.config.env_context import get_env

        return any(
            bool(get_env(key))
            for key in (
                "GEMINI_API_KEY",
                "DEEPSEEK_API_KEY",
                "OPENROUTER_API_KEY",
                "OPENAI_API_KEY",
                "ANTHROPIC_API_KEY",
            )
        )

    from src.config.env_context import get_env

    for env_key in get_required_env_keys(cfg):
        if get_env(env_key):
            return True
    return False


def rc(state: ReviewState) -> RunContext | None:
    return state.run_context


def rc_print(run_context: RunContext | None, message: object) -> None:
    if run_context is None:
        return
    if hasattr(run_context, "console"):
        try:
            run_context.console.print(message)  # type: ignore[union-attr]
            return
        except Exception:
            pass
    if isinstance(message, str) and hasattr(run_context, "log_status"):
        try:
            run_context.log_status(message)  # type: ignore[union-attr]
        except Exception:
            pass
