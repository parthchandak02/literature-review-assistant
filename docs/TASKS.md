# Tasks

Verification gates, commit checklist, and open work.

## Before you commit (high-level changes)

If you change architecture, phases, public API, persistence/schema, or `docs/`:

1. Run **Docs-to-code parity** below
2. Run **Verification gates**
3. Follow `.cursor/skills/commit/SKILL.md`

Narrow bugfixes can rely on tests and hooks only.

## Docs-to-code parity

1. Doc paths resolve to existing files under `docs/`
2. Endpoint table matches `src/web/app.py` (`docs/API.md` Section 10.1)
3. Phase order matches `src/orchestration/phase_catalog.py`
4. Frontend `RESUME_PHASE_ORDER` matches `USER_RESUMABLE_PHASE_ORDER`
5. Schema claims match `src/db/schema.sql`
6. `.cursor/rules/` and skills do not contradict `docs/`

**Drift policy:** Update `docs/` first, then rules/skills, then `AGENTS.md` / `README.md`.

## Verification gates

| Gate | Command |
|------|---------|
| Endpoint parity | `uv run python scripts/check_spec_endpoint_parity.py` |
| Replay | `uv run python scripts/validate_workflow_replay.py` |
| Backend | `uv run pytest tests/unit -q` + targeted integration |
| Frontend | `cd frontend && pnpm test && pnpm typecheck` |
| Full local CI | `make local-ci` |

### Frontend UI gate

When changing run navigation, tabs, or `views/*`:

1. `pnpm test && pnpm typecheck`
2. Complete checklist in `docs/UI.md#regression-checklist`
3. Update `docs/UI.md` if tab or Results contracts change

## Runtime status

Top-level checkpoints in `phase_catalog.py` are implemented in `workflow.py` `RUN_GRAPH`.

Recent remediation (2026-08-10, Phases 0-2) completed:

- Resume claim SQL fix; `primary_study_status` column reads
- Endpoint parity green (66 routes)
- `WorkflowRunResult` typed graph end
- Unified HITL/Prospero web park pattern
- `connectLiveRun` + canonical `awaiting_review` status
- `resolve_runtime_db` across routers
- Coordinator ownership; deleted `orchestration_facade` and `RunRegistry`

## Open work (backlog)

| Priority | Task |
|----------|------|
| P3 | Split god-modules one per PR when touched (`markdown_refs`, `contracts`, `retrieval`) |
| P3 | Export citation `complete_validated` |
| P3 | Move `config_generator` out of `src/web/` |
| P4 | `ProsperoGatePanel` component tests |
| P4 | Graph resume parametrized tests for `phase_1_prospero_gate` |
| P4 | Replay script phase-name lock |
| Investigate | `test_resume_workflow_smoke.py` hang (pre-existing) |

## Reliability refactor sequence

1. Contract convergence (phases, typed ends)
2. Orchestration hardening (`RUN_GRAPH`, resume routing)
3. Persistence rewind guarantees (`rollback_phase_data`)
4. API/UI parity (`docs/API.md`, phase constants)
5. Replay and regression gates before ship
