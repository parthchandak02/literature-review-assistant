---
name: setup-pre-commit
description: Sets up commit-time quality checks for this polyglot repo using Python pre-commit as the default, with optional frontend checks. Use when adding or repairing pre-commit hooks, formatting gates, lint/type/test checks, or commit hygiene automation.
disable-model-invocation: true
---

# Setup Pre-Commit

Default to Python `pre-commit` workflow for this repository.  
Use frontend hooks only when JS/TS files are present and relevant.

## What to set up

- `.pre-commit-config.yaml` with core formatting/lint hooks
- local hooks for project checks (for example `uv run ruff check`, targeted tests, optional frontend checks)
- git hook installation via `pre-commit install`
- minimal developer note describing how to run hooks locally

## Steps

### 1) Detect repository shape

Check for:

- Python project markers (`pyproject.toml`, `uv.lock`)
- frontend markers (`frontend/package.json`, `pnpm-lock.yaml`)

### 2) Install tooling

Prefer `uv`:

```bash
uv add --dev pre-commit
```

If dependency management policy requires non-edit installs:

```bash
uv tool install pre-commit
```

### 3) Author `.pre-commit-config.yaml`

Start with fast, deterministic checks:

- whitespace/end-of-file fixers
- YAML/TOML validation
- Python formatter/linter hooks (repo-standard tools)

Then add local hooks for project-specific checks as needed.

### 4) Add optional frontend checks

If frontend is active, add a local hook invoking:

- `pnpm -C frontend lint`
- `pnpm -C frontend typecheck`

Keep frontend hooks scoped and skip when frontend is untouched or absent.

### 5) Install and verify

Run:

```bash
uv run pre-commit install
uv run pre-commit run --all-files
```

If hooks fail, fix root cause, rerun, and confirm clean pass.

## Fallback path

Only if user explicitly asks for Husky/lint-staged, provide that path.  
Otherwise prefer Python `pre-commit` for this repo.

## Scope boundary

This skill configures hooks. It does not own commit sequencing, staging policy, or push confirmation rules.  
For commit/push safety workflow, use `general-rules`.

## Guardrails

- Do not add slow checks by default when fast equivalents exist.
- Do not modify unrelated project scripts unless required.
- Explain any skipped checks and why they were omitted.
