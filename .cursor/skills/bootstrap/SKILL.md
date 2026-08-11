---
name: bootstrap
description: Session bootstrap and orientation for this repo. Use when starting work, invoking /bootstrap, or needing lifecycle routing before edits.
disable-model-invocation: true
---

# Bootstrap

Canonical session startup for literature-review-assistant. Load this skill at the start of planning or implementation work.

## Sequence

1. Read `AGENTS.md` and `docs/CONTEXT.md`.
2. Read only task-routed docs from `docs/CONTEXT.md`.
3. Review recent git context (`git log`, `git status`) before edits.
4. Build a quick zoom-out map: lifecycle stage, entrypoints, typed boundaries, blast radius.
5. Run task-appropriate checks before claiming completion.
6. For script/ops commands: read `docs/SCRIPTS.md` or run `./scripts/help.sh`.

When docs conflict with code, trust code and active rules, then note drift for follow-up.

## Optional accelerators

- Broad codebase orientation: Repomix (`pack_codebase`) or `git ls-files` + `rg`.
- Build-phase implementation: switch to `build-phase` immediately after routing.

## Mandatory exceptions

- Never patch `runs/` artifacts to fix behavior.
- If docs conflict with code, trust code and active rules, then report drift.

## Related skills

- `build-phase` - phase router and implementation contract
- `general-rules` - cross-cutting engineering defaults (uv, ruff, diagnose/TDD)
- `research` - external source-backed guidance when needed
