# Architecture Audit Report

**Date:** 2026-08-10  
**Scope:** End-to-end codebase (backend orchestration, web control plane, persistence, frontend, domain pipeline, tests/docs parity)  
**Mode:** Reporting only. No code changes in this pass.  
**Method:** Architecture skill (friction, seams, depth, deletion test) + Ponytail lens (YAGNI, delete pass-throughs, simplest correct structure)

Six parallel readonly domain reviews informed this document. Use it as the input for a phased remediation plan.

---

## Executive summary

The system has a **sound architectural skeleton**: PydanticAI graph workflow, typed models at most write paths, canonical cohort via `study_cohort_membership`, frontend phase constants aligned with `phase_catalog.py`, and a clear composition root in `src/web/app.py`.

The main problems are **mid-migration seams** and **contract drift**, not missing architecture:

1. **Docs and CI are behind code.** `PIPELINE.md` omits `phase_1_prospero_gate` and incorrectly says `phase_7_audit` was removed. Endpoint parity fails on 5 live routes (PROSPERO submit, workflow draft, PRISMA downloads). `make local-ci` is red until docs catch up.
2. **One concrete integrity bug.** `try_claim_for_resume` binds 4 resumable statuses into an `IN (?, ?, ?)` clause. Resume from `awaiting_prospero` can fail at SQL bind time.
3. **Untyped boundaries at graph end and API edges.** `run_end_type=dict`, loose `End[dict]` payloads, and some router responses violate the typed-contract invariant where it matters most (orchestration exit, export citation resolver).
4. **Duplicate ownership patterns.** Live-run identity on the frontend (4 near-copies), lifecycle mutations on the backend (coordinator vs raw `_active_runs` writes), and dual DB resolve paths (`wf-*` documented but not consistently implemented).
5. **God-modules with good Interfaces.** `retrieval.py`, `markdown_refs.py`, `contracts.py`, `context_builder.py`, `screening_runner.py`, and `artifacts.py` are deep but hard to change safely. Ponytail says: split internally for locality, not new public Interfaces.
6. **Pass-through layers fail the deletion test.** `workflow.py` helper wrappers, `orchestration_facade.py`, unused `FullTextResolver`, `domain_repositories.py` one-liners, and `RunRegistry` add hops without behavior.

**Overall integrity:** High at the data/cohort core; medium at control-plane and UI sync seams; docs/parity lag is the highest operational risk today.

---

## Severity rollup

| Severity | Count (themes) | Examples |
|----------|----------------|----------|
| **Critical** | 1 | Resume claim SQL placeholder mismatch (`workflow_registry.py`) |
| **High** | 8 | Doc/phase drift; endpoint parity red; Prospero vs HITL pause inconsistency; untyped graph end; dual DB resolve; frontend status model split; `primary_study_status` column vs JSON reads; lifecycle bypassing coordinator |
| **Medium** | 12+ | `workflow.py` pass-through hub; god-modules; `artifacts.py` catch-all; incomplete coordinator extraction; phase progress duplication; export LLM citation path |
| **Low** | 6+ | Dual loggers; stale `phase N/7` label; `RunView` type re-exports; replay script phase label drift |

---

## P0: Fix before next feature work

These are correctness or CI-blocking issues, not style.

| ID | Domain | Issue | Location | Direction |
|----|--------|-------|----------|-----------|
| P0-1 | Persistence | `IN (?, ?, ?)` with 4 `_RESUMABLE_REGISTRY_STATUSES` values | `src/db/workflow_registry.py` ~L164-173 | Dynamic placeholders; test claim for each status including `awaiting_prospero` |
| P0-2 | Docs/CI | 5 undocumented live endpoints | `API_ENDPOINTS.md` Section 10.1 | Add routes; re-run `scripts/check_spec_endpoint_parity.py` until green |
| P0-3 | Docs | `PIPELINE.md` omits Prospero gate; denies `phase_7_audit` | `.cursor/docs/PIPELINE.md` | Align mermaid + checkpoint list with `phase_catalog.py` |
| P0-4 | Tests | No HTTP integration for submit-prospero or workflow draft | `tests/integration/` | Parked active + cold resume + invalid CRD; reserve + config-draft round-trip |
| P0-5 | Persistence | Included-study fallback reads `primary_study_status` from JSON, not column | `src/db/repos/screening.py`, `stats.py` | Read column; align defaults with `PrimaryStudyStatus` enum |

---

## Cross-cutting themes

### Theme A: Single source of truth for phases

**Canonical code:** `src/orchestration/phase_catalog.py`

| Consumer | Status |
|----------|--------|
| `resume.py` | Re-exports catalog (OK) |
| `workflow.py` `RUN_GRAPH` | Aligned for checkpointed phases |
| Frontend `PHASE_ORDER` / `RESUME_PHASE_ORDER` | Aligned with `UI_TIMELINE_PHASE_ORDER` / `USER_RESUMABLE_PHASE_ORDER` |
| `PIPELINE.md` | **Drifted** (no Prospero; audit "removed") |
| `IMPLEMENTATION_STATUS.md` | **Drifted** (says erase `phase_7_audit` assumptions) |
| CLI `phase N/7` label | **Stale** magic number |

**Exception to document explicitly:** `human_review_checkpoint` is a graph node outside `PHASE_ORDER`, status-driven via registry `awaiting_review`.

### Theme B: External-wait gates (Prospero + HITL)

| Gate | Web behavior | CLI behavior |
|------|--------------|--------------|
| Prospero | Park via `End`, registry `awaiting_prospero` | Infinite poll loop |
| HITL | Poll in task (holds worker) | Poll with `max_wait` |

**Direction:** One primitive: set registry status → `End(paused)` on web → `ResumeStartNode` routes by status. CLI may poll or exit; same contract.

### Theme C: Typed boundaries where behavior leaves the process

| Boundary | Today | Target |
|----------|-------|--------|
| Graph end / CLI / web facade | `dict`, `End[dict]` | Discriminated `WorkflowRunResult` Pydantic model |
| Synthesis artifact write | `synthesis_payload: dict` | Small `SynthesisArtifact` model |
| Export citation LLM resolver | Free-text JSON + `json.loads` | `complete_validated` + typed map model |
| API submit-prospero response | Loose dict | Response model (reserve path already partially typed) |

### Theme D: Ponytail deletion candidates (fail deletion test)

| Delete / merge | Files | Rationale |
|----------------|-------|-----------|
| Workflow helper wrappers | `workflow.py` L133-354 | Zero-behavior pass-throughs; tests should import `helpers/*` |
| `orchestration_facade.py` | `src/web/orchestration_facade.py` | Rename-only wrapper around `run_workflow` |
| `RunRegistry` + `app.state.run_registry` | `src/web/state.py` | Same dict as coordinator; barely used |
| `FullTextResolver` / `FullTextResolveRequest` | `src/fulltext/__init__.py` | Zero call sites |
| `domain_repositories` Paper/Screening/Cost wrappers | `src/db/domain_repositories.py` | One-liner pass-throughs |
| `PHASE_LABEL_MAP` duplicate | `frontend/src/lib/constants.ts` | Abbreviate from `PHASE_LABELS` |
| Private re-exports in extraction | `src/extraction/table_extraction.py` | Freezes fulltext internals for test patching |

**Do not delete (real depth):** `phase_catalog.py`, `WritingGroundingData`, `SearchConnector`, `IncludedSetResolver`, `helpers/prospero_validation.py`, tiered `fetch_full_text` race.

### Theme E: God-modules (keep Interface, split Implementation locally)

| Module | ~LOC | Ponytail rule |
|--------|------|---------------|
| `src/fulltext/retrieval.py` | 1846 | Internal tier splits only; public `fetch_full_text` stays |
| `src/export/markdown_refs.py` | 2103 | Split by artifact concern behind `assemble_submission_manuscript` |
| `src/manuscript/contracts.py` | 1349 | Group detectors by family; one `run_manuscript_contracts` entry |
| `src/writing/context_builder.py` | 1780 | Split DB assembly vs formatting; keep `WritingGroundingData` |
| `src/orchestration/runners/screening_runner.py` | 1218 | Extract pure functions; one orchestrator runner |
| `src/web/routers/artifacts.py` | 1078 | Extract PDF fetch + diagnostics helpers first |
| `src/web/config_generator.py` | 1625 | Move domain logic out of `src/web/` when touched |

---

## Domain reports

### 1. Backend orchestration

**Agents:** [Orchestration review](542ab692-1b07-49a8-901f-e9056a91a120)

**Healthy:** Real `RUN_GRAPH` + `ReviewState`; Prospero gate structurally sound; `phase_catalog` tests exist; typed models inside many runners/gates.

**Friction candidates:**

| # | Candidate | Severity | Direction |
|---|-----------|----------|-----------|
| O-C1 | `workflow.py` compatibility mega-hub | Medium | Graph + entrypoints only; migrate tests off `_foo` wrappers |
| O-C2 | Inconsistent node/runner layout + circular imports via `workflow` barrel | Medium | Nodes import siblings directly; finish Embedding/KG extraction |
| O-C3 | Phase catalog vs docs vs `/7` CLI label | High | Docs SSOT = `phase_catalog.py`; fix mermaid + label |
| O-C4 | Prospero vs HITL pause semantics | High | Unify external-wait gate pattern |
| O-C5 | Untyped `End`/run results | High | `WorkflowRunResult` discriminated union |
| O-C6 | `RunContext` / `_emit` duck typing | Medium | `RunEventSink` Protocol; ban `_emit` outside `context.py` |
| O-C7 | Triple workflow registration (start/prospero/search) | Medium | Start owns identity; later phases only checkpoint |
| O-C8 | God-runners (screening, extraction, writing) | Medium | Pure extractions only; no new wrapper layers |
| O-C10 | `resume.py` kappa payload parsing as raw dict | Low-Med | Typed `PhaseDoneScreeningSummary` |

**Top 5 orchestration fixes (future plan):**
1. Typed `WorkflowRunResult` as `run_end_type`
2. Unify Prospero + HITL external-wait gates
3. Make `phase_catalog.py` documented SSOT; fix PIPELINE mermaid
4. Collapse `workflow.py` compatibility layer
5. `RunEventSink` Protocol; remove `_emit` probing

---

### 2. Web API / control plane

**Agents:** [Web control plane review](4d4dbea7-f110-464c-93e2-7b99317e7599)

**Healthy:** `app.py` composition root; reconciler logic is real; workflow draft router is thin; frontend API modules mostly match path prefixes.

**Friction candidates:**

| # | Candidate | Severity | Direction |
|---|-----------|----------|-----------|
| W-C1 | Incomplete lifecycle extraction (`state.py` vs coordinator) | Medium | One Module: active runs + resolve + claim/resume + reconcile |
| W-C2 | Dual DB resolve paths (`_get_db_path` vs workflow-capable) | High | Single `resolve_runtime_db(identifier)`; fix `API_CONTRACT.md` |
| W-C3 | `artifacts.py` god router | Medium | Extract PDF fetch + diagnostics; split only if still painful |
| W-C4 | Pass-throughs: facade, ControlPlaneService, RunRegistry | Medium | Delete facade + RunRegistry; keep snapshot helper if useful |
| W-C5 | Lifecycle mutations split across routers | High | All start/resume through coordinator; gates call one lifecycle method |
| W-C6 | Hollow parity gate + doc drift | High | Integration test on real `run_parity_check`; document 5 routes |
| W-C7 | `config_generator.py` in web package | Medium | Move to `src/protocol/` or `src/config/` when touched |

**Endpoint ownership confusion (summary):**

| Concern | Router(s) | Note |
|---------|-----------|------|
| Start/stream/cancel | `run_lifecycle` | Clear |
| Resume/attach | `history` | OK if shared coordinator Implementation |
| Living refresh | `advanced` | **Bypasses coordinator** |
| Screening gate | `screening_review` | Status flip only |
| PROSPERO | `prospero_gate` + `artifacts` (forms) | Split ownership |
| Draft reserve | `workflow_draft` | Missing from ARCHITECTURE list |

**Top 5 web fixes:**
1. Unify DB resolve across all `run_id` routes
2. Finish coordinator ownership (ban raw `_active_runs` writes)
3. Restore real parity CI
4. Delete facade + RunRegistry pass-throughs
5. Carve `artifacts` hotspots (PDF, diagnostics)

---

### 3. Persistence and typed contracts

**Agents:** [Persistence review](97da5186-251e-4e23-9e87-8219eeb0f585)

**Healthy:** FK-safe upserts; cohort membership canonical; schema contract validation in `database.py`; most write paths use Pydantic.

**Friction candidates:**

| # | Candidate | Severity | Direction |
|---|-----------|----------|-----------|
| D-C1 | Dual schema ownership (`schema.sql` + migrations) | Medium | One owner policy; expand contract validation |
| D-C2 | `WorkflowRepository` `__getattr__` facade | Medium | Explicit delegation or direct sub-repo access |
| D-C3 | `domain_repositories.py` pass-throughs | Low | Delete unused wrappers |
| D-C4 | `WritingRepo` bloat (parsing + SQL) | Medium | Move parsing to manuscript module when touched |
| D-C5 | Registry vs history router duplication | Medium | Complete `RegistryEntry`; one migration path |
| D-C6 | `TABLE_OWNERSHIP` unused at runtime | Low | Delete or wire into `RunStatsResolver` only |
| D-C7 | `primary_study_status` column vs JSON | High | Read column in fallbacks |
| D-C8 | Untyped export/stats tuples and dicts | Medium | Pydantic at repo→API seam |
| D-C9 | Resume claim SQL binding | **Critical** | Fix placeholders + tests |

**Data integrity risks:**

- Resume claim failure on `awaiting_prospero`
- Included count miscount when cohort empty and JSON default differs from column
- Silent migration `except: pass`
- `repair_foreign_key_integrity` stub papers inflating counts
- Dual manuscript truth (`section_drafts` + `manuscript_*`)

**Top 5 persistence fixes:**
1. Fix `try_claim_for_resume` SQL (P0-1)
2. Column-based `primary_study_status` reads (P0-5)
3. Collapse registry list/migrations into `workflow_registry`
4. Schema single-source policy + expanded contract checks
5. Delete pass-through repos; type citation export when touched

---

### 4. Frontend

**Agents:** [Frontend review](541e23c1-acb6-42da-ab55-b32b1596c78d)

**Healthy:** Matches `UI_ARCHITECTURE.md` top-level Modules; `lib/api` barrel; phase lists aligned with backend catalog; `useSSEStream` complexity is earned.

**Friction candidates:**

| # | Candidate | Severity | Direction |
|---|-----------|----------|-----------|
| F-C1 | Live-run identity copied in 4 places | **P0** | One `connectLiveRun` + `clearLiveRunUi` helper |
| F-C2 | Draft + PROSPERO state in `App.tsx` | P1 | Move into session actions/state |
| F-C3 | Fragmented status model (`awaiting_review` → `streaming`) | **P0** | Canonical `RunStatus` including gate statuses |
| F-C4 | Duplicated `buildPhaseStates` | P1 | Single builder in `phaseProgress.ts` |
| F-C5 | Monolithic session context (SSE re-renders sidebar) | P2 | Split stream vs selection context |
| F-C6 | `RunView` re-exports session types | Low | Import from `runSessionTypes` only |
| F-C7 | Phase label / parity enforcement | Med | One label map; optional generated fixture from Python |
| F-C8 | View bloat (Database, Activity, Cost) | Med | Extract only on second consumer or blocker |
| F-C9 | Dual draft identity (`"draft"` vs reserved `wf-*`) | Med | Prefer reserved drafts only |

**Contract drift (frontend ↔ backend):**

| Risk | Severity |
|------|----------|
| `awaiting_review` collapsed to `streaming` in sidebar | High |
| Dual PROSPERO status owners (App + sync + RunView) | High |
| `fulltext_pdf_retrieval` UI vs `phase_3b_fulltext` checkpoint | Medium (OK if replay maps) |
| Hardcoded `RESUME_PHASE_ORDER` in tests vs Python | Medium |
| Draft URL `/run/draft/config` vs sync bounce to `/` | Medium |

**Top 5 frontend fixes:**
1. `connectLiveRun` unification (F-C1)
2. Canonical status model (F-C3)
3. Move draft/PROSPERO into session (F-C2)
4. Single `buildPhaseStates` (F-C4)
5. Split stream context (F-C5)

**Non-candidates (do not refactor):** `lib/api/*` split, `RunSessionProvider` pass-through, `useSSEStream`.

---

### 5. Domain pipeline (search, fulltext, writing, manuscript, export, llm, protocol)

**Agents:** [Pipeline domain review](c4ae5592-9897-4938-abe3-203105e0f7dd)

**Healthy seams:** `SearchConnector`, `WritingGroundingData`, `complete_validated` in section writing/outlines/audit, tiered full-text race, deterministic `ProtocolGenerator`.

**Subdomain highlights:**

| Area | Keep | Simplify / fix |
|------|------|----------------|
| Search | `strategy.py` coordinator | Unify HTTP retry via `HttpSearchConnectorBase`; one DOI normalizer |
| Fulltext | `fetch_full_text` Interface + race | Delete `FullTextResolver`; split `retrieval.py` internally |
| Writing | Grounding + evidence assembler | Finish `complete_validated` on JSON paths; shrink orchestration barrel |
| Manuscript | `reviewer.py` validated audit | Split `contracts.py` detectors by family |
| Export | Mechanical citation layers first | `complete_validated` for LLM resolver; split `markdown_refs.py` |
| LLM | `complete_validated` as structured default | Narrow `run_native_structured_json`; honest `LLMBackend` Protocol |
| Protocol | Deterministic PROSPERO assembly | Optional internal split only |

**System integrity risks:**

1. Stats/PRISMA arithmetic if grounding bypassed
2. Silent citation loss in export LLM fallback
3. Full-text false success (short HTML as text)
4. Dual retrieval (`search/pdf_retrieval` vs `fulltext`)
5. Phrase blocklists vs structural heuristics (project policy conflict)
6. Cohort bypass (screening include vs `included_primary`)

**Top 5 pipeline fixes:**
1. `complete_validated` for export citation resolver (P0 trust boundary)
2. One retrieval orchestration path; delete unused facade
3. Internal splits for `markdown_refs`, `contracts`, `retrieval` (one at a time)
4. Unify DOI normalize + summary sanitize; structural heuristics over phrase lists
5. Shrink `writing.orchestration` barrel exports

---

### 6. Tests, docs parity, CI

**Agents:** [Tests and drift review](7b559263-e1a9-4552-bef5-b644ebdb420a)

**Verified live:** `uv run python scripts/check_spec_endpoint_parity.py` fails on 5 routes (2026-08-10).

**Doc-code drift matrix:**

| Doc | Drift |
|-----|-------|
| `PIPELINE.md` | No Prospero; audit "removed" |
| `IMPLEMENTATION_STATUS.md` | Contradicts audit in code |
| `API_ENDPOINTS.md` | Missing 5 routes |
| `ARCHITECTURE.md` | Missing `prospero_gate`, `workflow_draft` routers |
| `API_CONTRACT.md` | Missing draft/PROSPERO domains; `wf-*` resolve overstated |
| `UI_ARCHITECTURE.md` | Understates App draft ownership; draft URL vs sync |
| `validate_workflow_replay.py` | Non-canonical phase label strings |

**Test gaps (priority):**

| Gap | Priority |
|-----|----------|
| `POST .../submit-prospero` integration | P0 |
| Workflow reserve + config-draft HTTP | P0 |
| Resume → ProsperoGate graph path | P1 |
| `ProsperoGatePanel` + session hooks | P1 |
| Replay PROSPERO artifact checks | P2 |

**Ponytail test balance:** Heavy unit coverage on export typography/helpers; undertested control-plane HTTP and draft→gate→search E2E seam.

**Healthy seams to keep:** `test_phase_catalog.py`, `test_frontend_phase_order_parity.py`, `test_graph_transitions.py` (extend for Prospero).

---

## Recommended remediation phases (plan input)

Use this ordering when moving from report to implementation. Each phase should end with green parity/tests for its scope.

### Phase 0: Unblock CI and correctness (1-2 days)

- P0-1 resume claim SQL fix + tests
- P0-2 + P0-3 doc updates (API_ENDPOINTS, PIPELINE, ARCHITECTURE router list)
- P0-5 `primary_study_status` column reads
- P0-4 minimal HTTP integration tests for prospero + draft

### Phase 1: Contract convergence (3-5 days)

- `WorkflowRunResult` typed graph end
- Unified external-wait gate (Prospero + HITL)
- Frontend `connectLiveRun` + canonical status model
- Single DB resolve helper across routers

### Phase 2: Lifecycle and coordinator (3-5 days)

- Ban raw `_active_runs` writes outside coordinator
- Route living-refresh, screening, prospero resume through coordinator
- Delete `orchestration_facade`, `RunRegistry`
- Slim `workflow.py` wrappers; point tests at helpers

### Phase 3: Locality without new seams (ongoing, one module per PR)

- Pick one god-module per sprint: `artifacts` hotspots → `markdown_refs` → `contracts` → `retrieval`
- Export citation `complete_validated`
- Registry typing consolidation
- Move `config_generator` out of web when next touched

### Phase 4: Test hardening

- Graph resume parametrized for `phase_1_prospero_gate`
- Frontend Prospero panel tests
- Replay script phase-name lock + optional PROSPERO artifact check
- Unit suite invokes live parity check (or CI always runs integration gate)

---

## Grill queue (pick one to pressure-test before coding)

When ready to plan implementation, grill these in order:

1. **O-C4 + O-C5** — External-wait gate + `WorkflowRunResult` (touches orchestration, web, frontend)
2. **W-C2 + F-C1 + F-C3** — Resolve + live identity + status (touches most user-visible bugs)
3. **D-C9 + D-C7** — Integrity pair (small diff, high trust)
4. **W-C1** — Lifecycle Interface boundary (larger refactor; do after P0)

Load `.cursor/skills/grill/SKILL.md` before large refactors on any candidate.

---

## Subagent index

| Domain | Agent ID | Focus |
|--------|----------|-------|
| Orchestration | `542ab692-1b07-49a8-901f-e9056a91a120` | Graph, resume, Prospero, typed ends |
| Web API | `4d4dbea7-f110-464c-93e2-7b99317e7599` | Lifecycle, resolve, artifacts, parity |
| Persistence | `97da5186-251e-4e23-9e87-8219eeb0f585` | Registry, repos, integrity bugs |
| Frontend | `541e23c1-acb6-42da-ab55-b32b1596c78d` | Session, status, phase UI |
| Pipeline | `c4ae5592-9897-4938-abe3-203105e0f7dd` | Search through export, LLM contracts |
| Tests/docs | `7b559263-e1a9-4552-bef5-b644ebdb420a` | Drift, CI, coverage gaps |

---

## Notes

- **Matt Pocock skills:** No project-specific Matt Pocock skill was found in this repo. TypeScript quality was reviewed via architecture + UI_ARCHITECTURE contracts and frontend domain review. If you have an external TS patterns skill to attach, re-run frontend grill with it.
- **This document is the audit artifact.** Update it when a remediation phase completes; do not treat it as a substitute for `ARCHITECTURE.md` or `PIPELINE.md` (those should be corrected to match code during Phase 0).
