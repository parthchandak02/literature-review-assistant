# Architecture Remediation Tracker

**Started:** 2026-08-10  
**Source:** `.cursor/docs/ARCHITECTURE_AUDIT.md`  
**Goal:** End-to-end fixes across P0 through Phase 2; track progress here.

## Status legend

- [ ] Not started
- [~] In progress
- [x] Done
- [-] Deferred (with reason)

---

## Phase 0: Unblock CI and correctness

| ID | Task | Status | Notes |
|----|------|--------|-------|
| P0-1 | Fix `try_claim_for_resume` SQL placeholders + unit tests | [ ] | |
| P0-2 | Add 5 missing routes to `API_ENDPOINTS.md` Section 10.1 | [x] | |
| P0-3 | Fix `PIPELINE.md` (Prospero gate, audit phase) | [x] | |
| P0-3b | Fix `ARCHITECTURE.md` router list + `IMPLEMENTATION_STATUS.md` audit wording | [x] | |
| P0-4 | HTTP integration tests: submit-prospero + workflow draft | [x] | `tests/integration/test_prospero_and_draft_api.py` |
| P0-5 | Read `primary_study_status` column in screening/stats fallbacks | [ ] | |
| P0-V | Parity script green + targeted pytest | [ ] | |

---

## Phase 1: Contract convergence

| ID | Task | Status | Notes |
|----|------|--------|-------|
| P1-1 | `WorkflowRunResult` typed graph end | [x] | `WorkflowRunStatus` + `WorkflowRunResult` in `src/models/workflow.py`; `run_end_type=WorkflowRunResult` |
| P1-2 | Unify external-wait gates (Prospero + HITL park pattern) | [x] | HITL web mode parks via `End(awaiting_review)`; CLI keeps poll loop |
| P1-3 | Frontend `connectLiveRun` + canonical status model | [x] | `connectLiveRun`/`clearLiveRunUi` in runSession.ts; `awaiting_review` in RunStatus |
| P1-4 | Single DB resolve helper across routers | [x] | `resolve_runtime_db` in `run_resolver.py`; screening_review, prospero_gate, costs, database_explorer |
| P1-V | Backend + frontend tests green | [ ] | |

---

## Phase 2: Lifecycle cleanup

| ID | Task | Status | Notes |
|----|------|--------|-------|
| P2-1 | Route lifecycle mutations through coordinator | [x] | living-refresh + screening resume via coordinator |
| P2-2 | Delete `orchestration_facade.py` + `RunRegistry` | [x] | Direct `run_workflow`/`run_workflow_resume` imports |
| P2-3 | Slim `workflow.py` pass-through wrappers | [x] | Removed 3 wrappers; tests import helpers directly |
| P2-V | `make local-ci` or `make release-check` | [~] | Targeted pytest run below |

---

## Session log

| Time | Agent / action | Result |
|------|----------------|--------|
| 2026-08-10 | Tracker created | — |
| 2026-08-10 | P2 lifecycle cleanup | Facade deleted; coordinator owns living-refresh + screening resume |
