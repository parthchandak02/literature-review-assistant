# Context

Canonical routing and glossary for agents. User-facing setup: root `README.md`. Agent entry: root `AGENTS.md`.

If docs conflict with code, trust `src/` and `frontend/src/`. If docs conflict with `.cursor/rules/core/`, trust the rule, then verify in code.

## Doc map

| Doc | Use when |
|-----|----------|
| `ARCHITECTURE.md` | Runtime planes, pipeline, persistence, LLM/costs, invariants |
| `API.md` | HTTP/SSE contracts; endpoint parity table (Section 10.1) |
| `UI.md` | Frontend structure, design rules, regression checklist |
| `TASKS.md` | Verification gates, open work, commit checklist |
| `SCRIPTS.md` | Script entrypoints, intent routing, naming conventions |
| `adr/` | Architecture decision records |

## Lifecycle routing

| Stage | Read |
|-------|------|
| Think | `ARCHITECTURE.md` |
| Plan | `ARCHITECTURE.md#pipeline`, `TASKS.md` |
| Build | Domain skill in `.cursor/skills/**/SKILL.md` + relevant doc above |
| Review | `API.md`, `ARCHITECTURE.md#persistence`, `UI.md` |
| Frontend UI redesign | `UI.md` before changing run navigation or views |
| Test | Parity and replay checks in `TASKS.md`; script routing in `SCRIPTS.md` |
| Ship | `.cursor/skills/commit/SKILL.md` |

## Glossary

- **Build phases (1-8):** Planning labels. Not interchangeable with runtime checkpoint keys.
- **Runtime checkpoints:** Keys in `src/orchestration/phase_catalog.py` (`PHASE_ORDER`).
- **User-resumable phase:** `USER_RESUMABLE_PHASE_ORDER` (excludes internal `phase_7_audit`). See ADR-0001.
- **Included primary cohort:** `study_cohort_membership` where `synthesis_eligibility='included_primary'`.
- **Cost truth:** `cost_records`.
- **Humanization:** Phase 6 post-write readability pass; facts and citations preserved.
- **HumanizerFlag:** Finding from `src/writing/humanizer_checks.py` (`high` / `medium` / `low`).
- **phase_catalog:** Canonical phase metadata (`src/orchestration/phase_catalog.py`).
- **env_context:** Per-task API key overrides via `contextvars` (`src/config/env_context.py`). ADR-0004.
- **LifecycleCoordinator:** Run start/stream/cancel/attach (`src/web/lifecycle_coordinator.py`).
- **RunSession:** Frontend selection contract (`RunSessionProvider`, `useRunSession*`, `runSession.ts`).
- **WorkflowRunResult:** Typed graph end (`src/models/workflow.py`).
- **resolve_runtime_db:** Canonical DB path resolver (`src/web/run_resolver.py`).

## ADRs

`docs/adr/000N-slug.md` - sequential decision records.
