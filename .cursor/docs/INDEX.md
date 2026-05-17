# Cursor Docs Index

This directory is the canonical AI-agent documentation surface for this repository.
Primary onboarding entrypoint is root `AGENTS.md`.

If any statement here conflicts with code, trust code in `src/` and `frontend/`.
If any statement here conflicts with `.cursor/rules/core/`, trust the rule and then verify code.

## Core Docs (read first)

- `ARCHITECTURE.md` - runtime boundaries, invariants, canonical source-of-truth paths
- `PIPELINE.md` - phase lifecycle, canonical process diagram, and checkpoint taxonomy map
- `IMPLEMENTATION_STATUS.md` - validation surfaces and parity checklist

## Deep Docs (read on demand)

- `API_CONTRACT.md` - API surfaces, endpoint ownership, SSE behavior
- `PERSISTENCE.md` - `runtime.db`, `workflows_registry.db`, and canonical table usage
- `UI_ARCHITECTURE.md` - frontend structure, view model, and API client boundaries
- `LLM_AND_COSTS.md` - model routing, rate limiting, and cost accounting contracts

## Lifecycle Routing

- Think: read `ARCHITECTURE.md` and `PIPELINE.md`
- Plan: read `PIPELINE.md` and `IMPLEMENTATION_STATUS.md`
- Build: read domain skill in `.cursor/skills/**/SKILL.md` plus relevant contract doc
- Review: read `API_CONTRACT.md`, `PERSISTENCE.md`, `UI_ARCHITECTURE.md`
- Test: run parity and replay checks documented in `IMPLEMENTATION_STATUS.md`
- Ship: follow `.cursor/skills/general-rules/SKILL.md` for canonical commit/push workflow; use `.cursor/commands/3-pre-commit-workflow.md` as a thin launcher.

## Compatibility Notes

- `AGENTS.md` is the onboarding entrypoint.
- `.cursor/docs/API_ENDPOINTS.md` is the endpoint parity anchor.
- `README.md` remains a user-facing entrypoint and should point back to this index for canonical contracts.
