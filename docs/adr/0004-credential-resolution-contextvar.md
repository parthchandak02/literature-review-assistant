# ADR-0004: Credential resolution via ContextVar (Option B)

## Status

Accepted

## Context

Concurrent web runs supply per-request API keys through `RunRequest` fields. Phase 0.3A introduced `src/config/env_context.py` with a `ContextVar` override map and monkeypatched `os.getenv` / `os.environ.get` so legacy call sites transparently saw task-local keys.

Monkeypatching `os` is fragile: third-party libraries cache references to the original functions, import order affects behavior, and debugging env reads becomes non-obvious. The override surface should be explicit and localized.

## Decision

**Option B: ContextVar as the single override source of truth.**

1. **Keep** `get_env()`, `resolve_env_overrides()`, `env_override_context()`, and `async_env_override_context()` in `src/config/env_context.py`.
2. **Remove** `_install_os_hooks()` and all `os.getenv` / `os.environ.get` monkeypatches.
3. **LLM agents** (`src/llm/`): pass `api_key` explicitly at PydanticAI `Agent` construction, resolved via `get_env()` inside the workflow task (handled in a separate normalization pass).
4. **Other modules** that need per-run credentials should call `get_env()` or accept an explicit `api_key` parameter; they must not rely on patched `os` reads.

Process-level defaults remain in `os.environ` (e.g. `.env` loaded at startup). `get_env()` continues to fall back to `os.environ` when no task override is set.

## Consequences

- Concurrent run isolation is preserved through `contextvars`, not `os.environ` mutation.
- Call sites using raw `os.getenv` / `os.environ.get` only see process env, not per-run overrides, until migrated to `get_env()` or explicit parameters.
- LLM credential wiring is centralized in `src/llm/` rather than implicit global hooks.
- Tests assert `get_env()` behavior and concurrent isolation; they no longer assert patched `os` behavior.
