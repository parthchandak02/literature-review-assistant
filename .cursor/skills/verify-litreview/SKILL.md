---
name: verify-litreview
description: pstack-style verification CLI for literature-review-assistant. Run before claiming Phase 1 scoping work complete. Closes the agent loop via composable commands with JSON output.
---

# verify-litreview

Agent verification lever for this repo (adapted from pstack). Use instead of improvising curl/pytest sequences.

## When to use

- After editing `src/models/config.py`, `src/models/methodology_profile.py`, `src/web/config_generator.py`
- After editing setup wizard (`frontend/src/components/setup/*`)
- Before commit when scoping vs systematic config routing changed

## Commands

From repo root:

```bash
# Dev stack health
uv run python .cursor/skills/verify-litreview/control_litreview.py doctor --json

# Methodology profile from YAML
uv run python .cursor/skills/verify-litreview/control_litreview.py profile-resolve \
  --config tests/fixtures/scoping/review_scoping_smoke.yaml --json

# Phase 1 acceptance (scoping foundation)
uv run python .cursor/skills/verify-litreview/control_litreview.py phase1-gate --json

# SR regression — use --quick during iteration, full before commit
uv run python .cursor/skills/verify-litreview/control_litreview.py sr-regression --json
uv run python .cursor/skills/verify-litreview/control_litreview.py sr-regression --quick --json
```

Equivalent canonical gate:

```bash
uv run python scripts/check.py config-methodology
```

## Required loop after backend `src/` changes

```bash
./scripts/ops_pm2.sh restart --backend-only
uv run python .cursor/skills/verify-litreview/control_litreview.py phase1-gate --json
uv run python .cursor/skills/verify-litreview/control_litreview.py sr-regression --json
```

## Feature map

See `references/features/README.md` for setup wizard and config generation navigation.

## Phase boundaries

- **Phase 1 (current):** config + wizard only. Do not start scoping pipeline runs until Phase 2+.
- Scoping `replay-workflow` profile: Phase 2+ (requires `runtime_scoping.db` fixture).

## Do not

- Patch artifacts under `runs/` to pass checks
- Skip `sr-regression` when changing `ReviewConfig` or config generator
- Build browser/CDP automation for Phase 1 (Vitest + API tests suffice)
