# Web + Frontend Inventory

Scope: `src/web/**`, `frontend/src/**`, `docs/API.md`, `docs/UI.md`. Generated for rearchitecture planning.

## 1. REST / SSE / streaming endpoints

**Mount (not in Section 10.1):** `GET /runs/*` — static files from `runs/` (`app.py`).

**SPA:** `GET /{full_path:path}` — serves `frontend/dist` or `index.html` (`app.py`, `include_in_schema=False`).

**Legacy (code only, `include_in_schema=False`):**

| Method | Path | Router | Purpose | DB / storage |
|--------|------|--------|---------|----------------|
| GET | `/api/runs` | `history.py` | In-memory active runs for tests/legacy clients | None ( `_lifecycle_coordinator` ) |
| GET | `/api/results/{run_id}` | `artifacts.py` | Alias of artifacts | `run_summary.json` on disk |

All other public `/api/*` routes match `docs/API.md` §10.1 (parity gate: `tests/integration/test_api_endpoint_parity_gate.py`).

### `system.py` (`APIRouter` prefix `/api`)

| Method | Path | Purpose | DB / tables |
|--------|------|---------|-------------|
| GET | `/api/health` | Liveness | None |

### `config.py` (prefix `/api/config`)

| Method | Path | Purpose | DB / tables |
|--------|------|---------|-------------|
| GET | `/api/config/review` | Default `config/review.yaml` | Filesystem |
| GET | `/api/config/env-keys` | Server env key values (setup prefill) | `os.environ` |
| GET | `/api/config/env-keys/required` | Required LLM env keys from settings | `config/settings.yaml` |
| GET | `/api/config/env-keys/status` | Masked provider readiness | `os.environ` + settings |

### `run_lifecycle.py`

| Method | Path | Purpose | DB / tables |
|--------|------|---------|-------------|
| POST | `/api/run` | Start pipeline from YAML + keys | Creates run dir, `runtime.db`, registry; in-memory `_RunRecord` |
| POST | `/api/run-with-masterlist` | Start from master CSV | Same + temp CSV |
| POST | `/api/run-with-supplementary-csv` | Connectors + supplementary CSV | Same |
| GET | `/api/stream/{run_id}` | **SSE** run events | In-memory event buffer; flush → `event_log` |
| GET | `/api/stream/workflow/{workflow_id}` | **SSE** when only workflow id known | Registry + active run lookup |
| POST | `/api/cancel/{run_id}` | Cancel in-flight run | In-memory cancellation |
| GET | `/api/download` | Artifact download (`path` under `runs/`) | Filesystem |
| POST | `/api/config/generate/stream` | **NDJSON/SSE-style** config generation | LLM in-process (`config_generator.py`); optional env override |

### `history.py`

| Method | Path | Purpose | DB / tables |
|--------|------|---------|-------------|
| GET | `/api/history` | Registry list (`view=rail`, `stats=`) | `workflows_registry.db` → `workflows_registry`; optional per-run `runtime.db` aggregates (`papers`, `cost_records`, …) |
| PATCH | `/api/notes/{workflow_id}` | Save sidebar note | `workflows_registry.notes` |
| GET | `/api/notes/stream` | **SSE** note updates | In-memory `NotesBroadcaster` |
| GET | `/api/history/{workflow_id}/config` | Saved `review.yaml` | Filesystem in run dir |
| GET | `/api/history/active-run` | Active run for workflow | In-memory coordinator |
| POST | `/api/history/resume` | Resume workflow | Registry + `runtime.db` / coordinator |
| DELETE | `/api/history/{workflow_id}` | Delete run + registry row | Registry + filesystem |
| POST | `/api/history/{workflow_id}/archive` | Soft archive | `workflows_registry` |
| POST | `/api/history/{workflow_id}/restore` | Unarchive | `workflows_registry` |
| POST | `/api/history/{workflow_id}/complete-hide` | Completed bucket | `workflows_registry` |
| POST | `/api/history/{workflow_id}/complete-restore` | Restore from completed | `workflows_registry` |
| POST | `/api/history/attach` | Hydrate historical `_RunRecord` | `event_log` replay via coordinator |

### `workflow_draft.py` + `workflow_draft.py` (service)

| Method | Path | Purpose | DB / tables |
|--------|------|---------|-------------|
| POST | `/api/workflow/reserve` | Allocate `wf-*`, run dir, draft status | `workflows`, `workflows_registry` |
| PUT | `/api/workflow/{workflow_id}/config-draft` | Persist generated YAML | Filesystem + registry status |

### `database_explorer.py`

| Method | Path | Purpose | DB / tables |
|--------|------|---------|-------------|
| GET | `/api/db/{run_id}/papers-facets` | Filter facet values | `papers`, `dual_screening_results` |
| GET | `/api/db/{run_id}/papers-suggest` | Autocomplete | `papers` |
| GET | `/api/db/{run_id}/papers-all` | Paginated paper grid | `papers`, joins to screening/extraction/RoB |
| GET | `/api/db/{run_id}/tables` | Vision-extracted tables | `extraction_records`, `papers` |
| GET | `/api/db/{run_id}/rag-diagnostics` | RAG retrieval diagnostics | `rag_retrieval_diagnostics` |

### `costs.py`

| Method | Path | Purpose | DB / tables |
|--------|------|---------|-------------|
| GET | `/api/db/{run_id}/costs` | Per-record costs | `cost_records`, `decision_log` (screening diagnostics) |
| GET | `/api/db/{run_id}/cost-dashboard` | Dashboard payload | `cost_records`, `decision_log` |
| GET | `/api/db/{run_id}/costs/aggregates` | Bucketed aggregates | `cost_records` |
| GET | `/api/db/{run_id}/costs/export` | CSV stream | `cost_records` |
| GET | `/api/history/costs/aggregates` | Global aggregates | `workflows_registry` + each linked `runtime.db` `cost_records` |
| GET | `/api/history/costs/export` | Global CSV | Same |

### `validation.py`

| Method | Path | Purpose | DB / tables |
|--------|------|---------|-------------|
| GET | `/api/workflow/{workflow_id}/validation/summary` | Latest validation run | `validation_runs`, `validation_checks` |
| GET | `/api/workflow/{workflow_id}/validation/checks` | Check rows | `validation_checks` |
| GET | `/api/workflow/{workflow_id}/manuscript-audit/summary` | Audit history | `manuscript_audit_runs` |
| GET | `/api/workflow/{workflow_id}/manuscript-audit/findings` | Findings | `manuscript_audit_findings` |
| GET | `/api/run/{run_id}/manuscript-audit` | Consolidated audit + `run_summary.json` contract fields | Audit tables + filesystem |

### `artifacts.py`

| Method | Path | Purpose | DB / tables |
|--------|------|---------|-------------|
| GET | `/api/run/{run_id}/artifacts` | `run_summary.json` | Filesystem |
| GET | `/api/run/{run_id}/manuscript` | MD/TeX from assembly or file | `manuscript_assemblies` or run dir files |
| GET | `/api/run/{run_id}/papers-reference` | Included papers + file flags | `papers`, `study_cohort_membership`, filesystem PDFs |
| GET | `/api/run/{run_id}/papers/{paper_id}/file` | Stream PDF/TXT | Filesystem |
| GET | `/api/run/{run_id}/studies-files.zip` | ZIP of study files | DB cohort + filesystem |
| POST | `/api/run/{run_id}/fetch-pdfs` | **Stream** retroactive PDF fetch | `papers` + full-text pipeline (heavy) |
| GET | `/api/run/{run_id}/events` | SSE buffer snapshot | In-memory / `event_log` |
| GET | `/api/workflow/{workflow_id}/events` | Historical events | `event_log` |
| POST | `/api/run/{run_id}/export` | IEEE package (`package_submission`) | Filesystem + export pipeline (heavy) |
| GET | `/api/run/{run_id}/readiness` | Readiness scorecard | Multiple tables via `compute_readiness_scorecard`, audit |
| GET | `/api/run/{run_id}/diagnostics` | Control plane + screening/extraction diagnostics | `workflow_steps`, `recovery_policies`, `writing_manifests`, `decision_log`, `dual_screening_results`, `screening_decisions`, `gate_results`, audit |
| GET | `/api/run/{run_id}/submission.zip` | Download package | Filesystem |
| GET | `/api/run/{run_id}/manuscript.docx` | DOCX | Filesystem |
| GET | `/api/run/{run_id}/prospero-form.docx` / `.md` | PROSPERO forms | Filesystem |

### `screening_review.py`

| Method | Path | Purpose | DB / tables |
|--------|------|---------|-------------|
| GET | `/api/run/{run_id}/screening-summary` | HITL screening summary | `papers`, `screening_decisions` |
| POST | `/api/run/{run_id}/approve-screening` | Approve + resume | `screening_decisions` updates + coordinator |

### `prospero_gate.py`

| Method | Path | Purpose | DB / tables |
|--------|------|---------|-------------|
| POST | `/api/run/{run_id}/submit-prospero` | Registration + optional resume | `workflows`, registry, YAML on disk |
| POST | `/api/run/{run_id}/regenerate-prospero` | Regenerate PROSPERO docs | Filesystem + `ProtocolGenerator` |

### `advanced.py`

| Method | Path | Purpose | DB / tables |
|--------|------|---------|-------------|
| GET | `/api/run/{run_id}/knowledge-graph` | Graph JSON | `papers`, `extraction_records`, `graph_communities`, `paper_relationships`, `research_gaps` |
| GET | `/api/run/{run_id}/prisma-checklist` | PRISMA validator | Filesystem manuscripts (CPU) |
| GET | `/api/run/{run_id}/prisma-diagram.png` | PNG | Filesystem |
| GET | `/api/run/{run_id}/prisma-flow.zip` | PRISMA CSV ZIP | Filesystem + DB export helpers |
| GET | `/api/run/{run_id}/grade-sof` | GRADE SoF | `grade_assessments` / related via `build_sof_table` |
| POST | `/api/run/{run_id}/living-refresh` | Incremental re-run | New run via coordinator (heavy) |
| GET | `/api/logs/stream` | **SSE** tail `app.jsonl` or PM2 logs | Filesystem / PM2 |

**Resolver pattern:** Most `{run_id}` routes use `run_resolver.resolve_runtime_db` → path from `workflows_registry.db` or run dir convention.

---

## 2. Frontend architecture

### Views (`frontend/src/views/`)

| View | Role | Primary APIs |
|------|------|----------------|
| `SetupView` | New review funnel | `config/*`, `workflow/reserve`, `config-draft`, `config/generate/stream`, `run*` |
| `RunView` | Tab shell | Delegates to child views |
| `ConfigView` | YAML editor | `fetchRunConfig`, artifacts sync |
| `ActivityView` | Timeline + logs | SSE `/api/stream/{runId}`, `fetchRunEvents` / workflow events |
| `DatabaseView` | Papers + outcomes | `papers-all`, `papers-facets`, `papers-suggest`, `tables` |
| `CostView` | Costs + validation sidebar | `cost-dashboard`, `costs`, aggregates, `validation/summary` |
| `ResultsView` | Deliverables | `fetchArtifacts`, `downloadUrl`, `triggerExport`, PRISMA URLs, `fetchGradeSof`, `fetchKnowledgeGraph`, direct `/api/run/.../manuscript.docx` |
| `ScreeningReviewView` | HITL gate | `screening-summary`, `approve-screening` |
| `ReferencesView` | Included papers | `papers-reference`, paper file URLs |

`App.tsx`: shell (sidebar, health dot, setup vs run), lazy-loads `SetupView`; URL sync via `parseRunUrl` (`/run/{workflowId}/{tab}`).

### Key components

- **Chrome / nav:** `Sidebar.tsx`, `RunChrome.tsx`, `RunNavCard`, history sections, `SettingsDialog`, `GlobalCostOpsDialog`
- **Setup:** `QuestionStage`, `ReviewTypeDecisionStage`, `ConfigReviewStage`, `CsvDropZone`, `ProsperoGatePanel`, API key sections
- **Activity:** `PhaseTimeline`, `ActivityLogPanel`, `LogStream` (renders `ReviewEvent[]`, not `/api/logs/stream`)
- **Database:** `PapersTable`, filters, `OutcomesTable`
- **Results:** `ManuscriptViewer`, `ArtifactFileList`, `PrismaSection`, `GradeSummarySection`, `EvidenceNetworkSection`, `ProsperoSection`
- **UI primitives:** `frontend/src/components/ui/*`

### Hooks (selected)

| Hook | Responsibility | APIs |
|------|----------------|------|
| `useRunSession` / `useRunSessionValue` | Central run UI state | Many via action hooks |
| `useSSEStream` / `useLiveRunStream` | Live SSE | `/api/stream/{runId}` |
| `useHistoricalEvents` | Historical replay | `events` endpoints |
| `useHistory` / `useSidebarRuns` | Sidebar registry | `/api/history?view=rail` |
| `useDraftConfigFlow` | Setup generation | draft + stream + start |
| `useDbPapers` / `useDbFilters` | Data tab | `papers-*`, `tables` |
| `useDbCosts` / `useCostStats` | Cost tab | `cost-*`, validation |
| `useReferences` / `useFilePreview` | References + previews | `papers-reference`, `/api/download` |
| `useBackendHealth` | API up | `/api/health` |
| `useNoteAutosave` | Notes | `PATCH notes`, `notes/stream` |
| `workflowActiveRunWatcher` | Gate reconnect | `history/active-run`, `stream/workflow` |
| `runSession/*` | Lifecycle, gates, artifacts, URL | runs, history, prospero, screening |

### API client (`frontend/src/lib/api/`)

Barrel: `lib/api.ts` → modules `client`, `config`, `runs`, `history`, `events`, `workflowDraft`, `artifacts`, `db`, `costs`, `validation`, `screening`, `notes`, `runLifecycle`, `urls`, `storage`, `types`.

`apiFetch` centralizes JSON GET/POST with `API_BASE = "/api"`. Some flows use raw `fetch` (multipart run start, streaming config/PDF fetch).

### State management

1. **React Context** — `RunSessionProvider` splits state/actions (`runSessionContext.ts`, `runSessionTypes.ts`).
2. **TanStack Query** — server state (history rail, DB papers/costs, references, config default, file preview); `queryClient` in `lib/queryClient.ts`.
3. **localStorage** — `StoredApiKeys`, `StoredLiveRun` (`storage.ts`).
4. **In-memory SSE** — `useSSEStream` + `@microsoft/fetch-event-source` for run stream; `EventSource` for notes + workflow stream.
5. **Theme** — `themeStore` + `ThemeContext`.

No Redux/Zustand for run domain.

---

## 3. Drift

### Docs vs code (Section 10.1)

- **Automated parity:** PASS for all `include_in_schema=True` `/api/*` routes (`scripts/lib/check_api_docs.py` scans `app.py` + `routers/`).
- **Undocumented but implemented:** `GET /api/runs`, `GET /api/results/{run_id}` (explicitly excluded from schema; used in `tests/integration/test_api_endpoints.py`).

### Documented endpoints with no frontend consumer

Useful for CLI/operators or future UI:

- `GET /api/logs/stream`
- `GET /api/run/{run_id}/readiness`
- `GET /api/run/{run_id}/diagnostics` (partial overlap: cost dashboard embeds screening diagnostics from `costs` router, not full diagnostics payload)
- `GET /api/run/{run_id}/manuscript-audit`, workflow manuscript-audit routes
- `GET /api/db/{run_id}/rag-diagnostics`
- `GET /api/run/{run_id}/prisma-checklist` (UI uses diagram/zip artifacts instead)
- `POST /api/run/{run_id}/living-refresh`
- `GET /api/run/{run_id}/manuscript?fmt=` (UI reads manuscript via artifact paths + `/api/download`, not assembly API)

### Frontend calls vs backend

No invalid paths found in `frontend/src` — all `/api/*` usage maps to existing routes. Direct anchor/href downloads: `manuscript.docx`, PRISMA PNG/ZIP, submission ZIP, prospero forms, `download?path=`.

### Type / contract drift (`frontend/src/lib/api/types.ts` vs `src/web/shared.py`)

| Area | Issue |
|------|--------|
| `RunRequest` | Backend has `parent_db_path`; frontend type omits it (living refresh is API-only today). |
| `RunRequest` | Backend treats `fireworks_api_key` as optional `str \| None`; frontend `RunRequest` in types does not list `fireworks_api_key` (passed via `buildRunRequest` / storage separately). |
| `StoredApiKeys` / env-keys | Backend `get_env_keys` includes `deepseek`; frontend `StoredApiKeys` has no `deepseek` field. |
| `HistoryRailEntry` | Aligns with backend `HistoryRailEntry` model in `history.py`. |
| `HistoryEntry` | Frontend includes `updated_at`; backend `HistoryEntry` model matches. |
| Validation / audit | Frontend `ValidationSummary` in `validation.ts` is hand-written; not tied to Pydantic models in `src/models/`. |
| `fetchPdfsForRun` | Docs say JSON `{attempted,succeeded,failed}`; implementation consumes **streaming** NDJSON (matches router). |

---

## 4. Robustness

### Large files (>800 lines)

| Path | Lines | Note |
|------|------:|------|
| `src/web/config_generator.py` | 1735 | LLM config generation; invoked from run lifecycle stream |
| `src/web/routers/artifacts.py` | 1078 | Export, readiness, diagnostics, PDF fetch |
| `src/web/state.py` | 691 | Active runs, broadcasters, eviction |

Frontend max ~589 lines (`EvidenceNetworkViz.tsx`); nothing >800 in `frontend/src`.

### Error handling gaps

- Many routers wrap broad `except Exception` → HTTP 500 with stringified error (`validation.py`, parts of `artifacts.py`).
- `get_run_manuscript` swallows assembly errors and falls back to file (`artifacts.py`).
- Frontend: mixed patterns — `apiFetch` throws `APIResponseError`; some hooks swallow errors (e.g. `fetchActiveRun` returns `null` on non-404 failures).
- `AppErrorBoundary` at root; tab views use `ViewBoundary` in places.

### Blocking / heavy work in async handlers

| Location | Issue |
|----------|--------|
| `artifacts.py` `get_run_artifacts`, `get_run_manuscript` | Sync `read_text` on event loop |
| `artifacts.py` `get_paper_file` | Sync `open().read()` inside async generator |
| `artifacts.py` `download_study_files_zip` / submission zip | Sync `zipfile` on loop |
| `advanced.py` `get_prisma_checklist` | Sync file reads + CPU validation |
| `config.py` `get_review_config` | Sync filesystem read |
| `validation.py` `get_run_manuscript_audit` | Sync `run_summary.json` read |
| `prospero_gate.py` | Sync YAML rewrite + `ProtocolGenerator` on request thread |
| `artifacts.py` `trigger_export` | `package_submission` async but heavy in-process |
| `artifacts.py` `fetch_pdfs_for_run` | Long-running PDF retrieval streamed but ties up worker |
| `run_lifecycle.py` `generate_config_stream` | Full LLM generation in API process |
| `advanced.py` `living_refresh` | Spawns full workflow task from API |

No widespread `time.sleep` in routers; coordinator uses `asyncio`.

---

## 5. Test coverage

### Backend web layer

| Test | Coverage |
|------|----------|
| `tests/integration/test_api_endpoints.py` | Broad HTTP contract (~72 tests): health, history, costs, papers, export, SSE, config stream, screening, PRISMA, attach, etc. |
| `tests/integration/test_api_endpoint_parity_gate.py` | Docs §10.1 ↔ FastAPI decorators |
| `tests/integration/test_validation_api.py`, `test_validation_include_checks.py` | Validation routes |
| `tests/unit/test_web_app_import.py` | Import smoke |
| `tests/unit/test_web_diagnostics_utils.py` | Diagnostics helpers |
| `tests/unit/test_web_tool_progress.py` | Tool progress utilities |
| `tests/unit/test_spec_endpoint_parity.py` | Parser unit tests for parity script |
| `tests/unit/test_frontend_phase_order_parity.py` | `PHASE_ORDER` vs backend |

Gaps: no dedicated router unit tests per file; SSE streams lightly asserted; `config_generator.py` tested indirectly via integration stream tests.

### Frontend

25 Vitest files under `frontend/src/**/*.test.{ts,tsx}` — helpers (`logLine`, `phaseProgress`, `runSessionUrl`), hooks (`useHistory`, `useDbCosts`, `useSidebarRuns`, …), components (`PapersTable`, `LogStream`, setup stages). **No** Playwright/e2e in repo. No component tests for `App.tsx` or full `RunView` integration.

Run: `pnpm test` (frontend), `uv run pytest tests/integration/test_api_endpoints.py` (API).

---

## 6. `docs/UI.md` alignment

- Documented tabs (`config`, `activity`, `database`, `cost`, `results`, `review-screening`) match `RunView.tsx`.
- API client path `frontend/src/lib/api/` and SSE hook names match code.
- Results categories (`lib/resultsCategories.ts`) match UI behavior.
- Redesign tracker phases partially shipped (Results categories done; workspace/ops pending).

---

## Summary matrix: endpoint → frontend

| Consumer | Endpoints |
|----------|-----------|
| **UI client modules** | All §10.1 except logs, readiness, diagnostics, rag-diagnostics, prisma-checklist, living-refresh, manuscript GET API, manuscript-audit family |
| **Browser direct URL** | PRISMA PNG, PRISMA ZIP, submission ZIP, manuscript.docx, prospero forms, paper files |
| **Tests / legacy only** | `/api/runs`, `/api/results/{run_id}` |
