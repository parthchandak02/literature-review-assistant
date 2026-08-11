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
| API docs match routes | `uv run python scripts/check.py api` |
| Replay workflow | `uv run python scripts/check.py replay-workflow` |
| Backend | `uv run pytest tests/unit -q` + targeted integration |
| Frontend | `cd frontend && pnpm test && pnpm typecheck` |
| Full local checks | `make check-local` (alias: `make local-ci`) |

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
| P3 | Delete `workflow.py` pass-through wrappers; finish `End[WorkflowRunResult]` typing |
| P4 | `ProsperoGatePanel` component tests |
| P4 | Graph resume parametrized tests for `phase_1_prospero_gate` |
| P4 | Replay script phase-name lock |
| Investigate | `test_resume_workflow_smoke.py` hang (skipped in release-check) |

## Publication readiness (audit 2026-08-10)

**Verdict: not ready to tag a release until Sprint 1 blockers below are done.** Backend publication pass is largely solid; frontend HITL unpark (reconnect after approve) and fresh-clone CI parity were gaps found in the 2026-08-10 deep audit.

### Sprint 1 blockers (in progress)

| ID | Task | Owner | Status |
|----|------|-------|--------|
| S1-1 | Screening approve reconnect (`handleApproveScreeningAndResume` mirrors PROSPERO) | frontend | in progress |
| S1-2 | Replay fixture DBs committable (`!tests/fixtures/replay/*.db`) | oss | in progress |
| S1-3 | GitHub tests match `scripts/check.sh local` | oss | in progress |
| S1-4 | Migration 23 `json_valid` guard + extraction enum fallback | backend | in progress |

**Sprint 1 exit:** `make check-local` green on a fresh clone; manual QA: approve screening after 20s delay shows live Activity events without sidebar workaround.

### Completed in publication pass (2026-08-10)

- Park detection for `awaiting_review` (`detectAwaitingReview`, unified park in `useRunSessionSync`)
- Writing setup reloads canonical `included_primary` cohort
- `primary_study_status` migration 23 backfill + explorer column reads
- `advanced.py` uses `resolve_runtime_db`; coordinator read paths in history/artifacts
- CLI HITL no silent auto-approve on timeout
- MIT `LICENSE`, README (DeepSeek default, clone URL, tabs), GitHub Actions CI (initial)
- Prospero/draft + HITL approve integration tests in `check-local`
- `approve-screening` registry lookup via `find_by_workflow_id` (parity with PROSPERO gate)
- Replay fixtures regenerated for schema migration 23
- Resume smoke hang quarantined with skip + timeout guard

### Sprint 2 (after blockers)

| Priority | Task |
|----------|------|
| P1 | `resolve_registry_entry()` helper; collapse resolver aliases |
| P1 | HTTP integration test for `wf-*` resolution without active run |
| P1 | Unskip or replace `test_resume_workflow_smoke.py` |
| P2 | Screening + Prospero component tests |
| P2 | `human_review_checkpoint` Activity log label |

### Remaining polish (non-blocking)

- God-module splits when touched
- Export citation `complete_validated`
- Broad API `response_model` typing

## Reliability refactor sequence

1. Contract convergence (phases, typed ends)
2. Orchestration hardening (`RUN_GRAPH`, resume routing)
3. Persistence rewind guarantees (`rollback_phase_data`)
4. API/UI parity (`docs/API.md`, phase constants)
5. Replay and regression gates before ship
