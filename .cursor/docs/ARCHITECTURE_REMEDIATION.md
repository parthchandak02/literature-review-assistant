# Architecture Remediation Tracker

**Started:** 2026-08-10  
**Completed:** 2026-08-10 (Phases 0-2)  
**Source:** `.cursor/docs/ARCHITECTURE_AUDIT.md`  
**Goal:** End-to-end fixes across P0 through Phase 2.

## Status legend

- [x] Done
- [-] Deferred (with reason)

---

## Phase 0: Unblock CI and correctness

| ID | Task | Status | Notes |
|----|------|--------|-------|
| P0-1 | Fix `try_claim_for_resume` SQL placeholders + unit tests | [x] | Dynamic `IN` placeholders; 11 registry tests |
| P0-2 | Add 5 missing routes to `API_ENDPOINTS.md` Section 10.1 | [x] | 66 endpoints parity green |
| P0-3 | Fix `PIPELINE.md` (Prospero gate, audit phase) | [x] | Mermaid + `awaiting_prospero` gate |
| P0-3b | Fix `ARCHITECTURE.md` router list + `IMPLEMENTATION_STATUS.md` | [x] | `prospero_gate`, `workflow_draft`, `phase_catalog.py` SSOT |
| P0-4 | HTTP integration tests: submit-prospero + workflow draft | [x] | `tests/integration/test_prospero_and_draft_api.py` (3 tests) |
| P0-5 | Read `primary_study_status` column in screening/stats fallbacks | [x] | Column-based filter; `test_run_stats.py` updated |
| P0-V | Parity script green + targeted pytest | [x] | `make local-ci` passed |

---

## Phase 1: Contract convergence

| ID | Task | Status | Notes |
|----|------|--------|-------|
| P1-1 | `WorkflowRunResult` typed graph end | [x] | `WorkflowRunStatus` + `WorkflowRunResult` in `src/models/workflow.py` |
| P1-2 | Unify external-wait gates (Prospero + HITL park pattern) | [x] | HITL web parks via `End(awaiting_review)`; CLI poll unchanged |
| P1-3 | Frontend `connectLiveRun` + canonical status model | [x] | `runSession.ts`; `awaiting_review` first-class in `RunStatus` |
| P1-4 | Single DB resolve helper across routers | [x] | `resolve_runtime_db` in `run_resolver.py` |
| P1-V | Backend + frontend tests green | [x] | 43 frontend tests; backend unit+integration green |

---

## Phase 2: Lifecycle cleanup

| ID | Task | Status | Notes |
|----|------|--------|-------|
| P2-1 | Route lifecycle mutations through coordinator | [x] | `living_refresh`, screening resume via coordinator |
| P2-2 | Delete `orchestration_facade.py` + `RunRegistry` | [x] | Direct `run_workflow`/`run_workflow_resume` imports |
| P2-3 | Slim `workflow.py` pass-through wrappers | [x] | 3 wrappers removed; tests import helpers |
| P2-V | `make local-ci` | [x] | Passed 2026-08-10 |

---

## Phase 3-4: Deferred (future sprints)

| ID | Task | Status | Reason |
|----|------|--------|--------|
| P3-1 | Split god-modules (`markdown_refs`, `contracts`, `retrieval`) | [-] | One module per PR when touched |
| P3-2 | Export citation `complete_validated` | [-] | Trust boundary; schedule with export work |
| P3-3 | Move `config_generator` out of `src/web/` | [-] | Large move; defer until next config feature |
| P4-1 | Graph resume tests for `phase_1_prospero_gate` | [-] | Partial coverage via prospero unit + integration |
| P4-2 | Frontend `ProsperoGatePanel` component tests | [-] | Defer to UI test sprint |
| P4-3 | Replay script phase-name lock | [-] | Low urgency; replay passes |

---

## Key code changes (by area)

### Backend persistence
- `src/db/workflow_registry.py` - dynamic SQL placeholders; `awaiting_review` resumable
- `src/db/repos/screening.py`, `src/db/stats.py` - column-based `primary_study_status`

### Backend orchestration
- `src/models/workflow.py` - `WorkflowRunResult`, `WorkflowRunStatus`
- `src/orchestration/workflow.py` - typed `run_end_type`; 3 pass-through wrappers removed
- `src/orchestration/runners/hitl_runner.py` - web park pattern
- Multiple nodes/runners - `End(WorkflowRunResult.*)` wrappers

### Web control plane
- `src/web/run_resolver.py` - `resolve_runtime_db`
- `src/web/routers/prospero_gate.py` - registry lookup fix, YAML json mode
- `src/web/routers/screening_review.py`, `costs.py`, `database_explorer.py` - unified resolve
- `src/web/routers/advanced.py` - coordinator for living-refresh
- **Deleted:** `src/web/orchestration_facade.py`
- **Removed:** `RunRegistry`, `app.state.run_registry`

### Frontend
- `frontend/src/lib/runSession.ts` - `connectLiveRun`, `clearLiveRunUi`
- `frontend/src/lib/constants.ts` - `awaiting_review` canonical status
- `frontend/src/hooks/useRunSession*.ts`, `useLiveRunStream.ts` - unified connect
- `frontend/src/App.tsx` - removed parallel status remapping

### Tests added
- `tests/unit/test_workflow_registry.py` - claim per status
- `tests/integration/test_prospero_and_draft_api.py` - 3 HTTP tests
- `tests/unit/test_run_resolver.py` - resolve delegation

### Docs updated
- `.cursor/docs/API_ENDPOINTS.md`, `PIPELINE.md`, `ARCHITECTURE.md`, `IMPLEMENTATION_STATUS.md`

---

## Verification gates (2026-08-10)

| Gate | Result |
|------|--------|
| `scripts/check_spec_endpoint_parity.py` | PASS (66 endpoints) |
| `make local-ci` | PASS |
| `pnpm test` (frontend) | 43 passed |
| `tsc --noEmit` (frontend) | PASS |
| `pm2 restart litreview-api` | Done |

---

## Session log

| Time | Agent / action | Result |
|------|----------------|--------|
| 2026-08-10 | Tracker created | — |
| 2026-08-10 | P0 backend (b5b15a01) | SQL fix + primary_study_status; 32 tests |
| 2026-08-10 | P0 docs (a69d5d5f) | Parity green; PIPELINE/ARCHITECTURE fixed |
| 2026-08-10 | P0 integration (49fd4e05) | 3 HTTP tests + prospero_gate fixes |
| 2026-08-10 | P1 orchestration (6ff963c9) | WorkflowRunResult + HITL park; 17 tests |
| 2026-08-10 | P1 frontend (41c8e1f4) | connectLiveRun + status model; 43 tests |
| 2026-08-10 | P1 resolve (9cbe65ea) | resolve_runtime_db; 16 unit tests |
| 2026-08-10 | P2 lifecycle (5f91e761) | Facade deleted; coordinator; 46 tests |
| 2026-08-10 | Parent verification | `make local-ci` PASS |

---

## Known follow-ups

1. `test_resume_workflow_smoke.py` hangs (>5 min) - pre-existing; investigate separately
2. `test_studies_files_zip_no_files_returns_404` error message mismatch - pre-existing unrelated
3. Phase 3 god-module splits - schedule one per PR when editing those files
4. `awaiting_review` now resumable in registry - verify HITL approve + resume E2E in browser
