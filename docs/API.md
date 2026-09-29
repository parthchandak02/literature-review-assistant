# API

## Canonical sources

- **Routes:** `src/web/routers/*.py` (mounted in `src/web/app.py`, which also serves `/runs/*` and `frontend/dist`)
- **Frontend client:** `frontend/src/lib/api.ts`
- **DB resolve:** `resolve_runtime_db()` in `src/web/run_resolver.py` (accepts active `run_id` or `wf-*`)

## Domains

- Run lifecycle: `/api/run*`, `/api/stream/{run_id}`, `/api/cancel/{run_id}`
- History/registry: `/api/history*`, `/api/notes*`
- DB explorer and costs: `/api/db/{run_id}/*`, `/api/history/costs/*`
- Streams: `/api/logs/stream`, `/api/notes/stream`
- Artifacts/exports: `/api/run/{run_id}/*`
- Validation/audit: `/api/workflow/{workflow_id}/validation/*`, manuscript-audit routes
- Draft: `POST /api/workflow/reserve`, `PUT /api/workflow/{workflow_id}/config-draft`
- PROSPERO: `POST /api/run/{run_id}/submit-prospero`

## Gotchas

- `/api/config/generate/stream` is POST, not GET.
- `/api/run` is JSON; CSV uploads use multipart endpoints.
- `/api/history/active-run` requires `workflow_id` query param.
- SSE run events: `/api/stream/{run_id}` or `/api/stream/workflow/{workflow_id}` after gate resume. Streams stop when the client disconnects.

## Security and path rules

Guards live in `src/web/path_guard.py`.

- **Run roots:** `run_root` must resolve under `./runs` or an entry in `LITREVIEW_RUNS_ROOTS` (`os.pathsep`-separated); otherwise 400. Applies to `POST /api/run`, `/api/run-with-masterlist`, `/api/run-with-supplementary-csv`, and `DELETE /api/history/{workflow_id}` (which also rejects run dirs outside `run_root`).
- **Attach:** `POST /api/history/attach` `db_path` must be under a known run root (configured roots, candidate `runs/` dirs, registry-derived roots); otherwise 400.
- **Downloads:** `/api/download` checks `Path.is_relative_to` against allowed roots; returns 403 for paths outside them and for database (`.db`, `.sqlite`) and dotenv files (incl. WAL/SHM/journal), 404 if not a file.
- **Static `/runs/*`:** served by a handler (not `StaticFiles`) that returns 404 for database/env files and paths outside `runs/`.
- **Env keys:** `GET /api/config/env-keys` returns blank strings for every secret; only `pubmedEmail` and `crossrefEmail` carry server values. Blank run keys fall back to server env. Use `/env-keys/status` for configured/required state.
- **Run slots:** the concurrency slot is acquired before the in-memory run record is registered, so a 429 leaves no orphan record (no stray 409 on retry).

## Endpoint parity

Enforced by `scripts/check.py api` against Section 10.1 below. Update this table when adding routes.

### 10. API Contract

### 10.1 REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/run | Start new review from JSON config payload (`RunRequest`); returns `{run_id, topic}` |
| POST | /api/run-with-masterlist | Start review from master-list CSV upload (multipart form) |
| POST | /api/run-with-supplementary-csv | Start review with connector search plus supplementary CSV upload (multipart form) |
| GET | /api/stream/{run_id} | SSE stream of ReviewEvent JSON; heartbeat every 15s; ends with done/error/cancelled |
| GET | /api/stream/workflow/{workflow_id} | SSE stream keyed by workflow_id (reconnect after gate resume without run_id) |
| POST | /api/cancel/{run_id} | Cancel active run; sets cancellation event |
| GET | /api/download | Download artifact file (query param `path`; restricted to allowed run roots; 403 for db/env files) |
| GET | /api/config/review | Default review.yaml content (pre-fills Setup form) |
| POST | /api/config/generate/stream | SSE-streamed config generation (`research_question`, `gemini_api_key`, optional `generation_profile=standard|health_sdg`) |
| GET | /api/config/env-keys | Setup key map; secrets always blank, only PubMed/Crossref emails pre-filled from server env |
| GET | /api/config/env-keys/required | Required LLM provider UI keys for the active settings profile |
| GET | /api/config/env-keys/status | Masked env-key presence map for Setup diagnostics |
| GET | /api/health | Health check; polled every 6s by useBackendHealth hook |
| GET | /api/history | Past runs from workflows_registry.db; optional `view=rail` (slim sidebar rows) and `stats=false` (skip runtime.db stats). Rows carry `lane_override` (`in_progress`, `completed` or null) |
| GET | /api/history/active-run | Whether a run for the given workflow_id is currently active (requires `workflow_id` query param) |
| GET | /api/history/costs/aggregates | Global cost aggregates across registry-linked runtime.db files |
| GET | /api/history/costs/export | Global cost CSV export across registry-linked runtime.db files |
| GET | /api/history/{workflow_id}/config | Original review.yaml written at run completion |
| POST | /api/history/attach | Attach historical run for DB explorer; loads event_log from DB |
| POST | /api/history/resume | Resume a historical run; body includes workflow_id, optionally from_phase |
| POST | /api/history/{workflow_id}/archive | Soft-archive a workflow row; preserves run data and artifacts |
| POST | /api/history/{workflow_id}/restore | Restore an archived workflow row to the active list |
| POST | /api/history/{workflow_id}/complete-hide | Move a non-running workflow into the manual Completed bucket |
| POST | /api/history/{workflow_id}/complete-restore | Restore a workflow from the Completed bucket to In Progress |
| POST | /api/history/{workflow_id}/lane | Set the sidebar lane pin: body `{lane: "in_progress" \| "completed" \| null}`; `completed` also sets `is_completed_hidden` and is refused while running |
| DELETE | /api/history/{workflow_id} | Delete registry entry, the run directory and sibling `run_*` dirs in the workflow's own `wf-NNNN-*` folder, then empty parents up to `run_root`; symlinks and dirs of other registry rows are kept |
| GET | /api/db/{run_id}/papers-all | Paginated papers with doi + url fields. Optional `sort` (title, year, source, ta_decision, ft_decision, primary_status, confidence; 400 otherwise) and `dir` (asc, desc). Filters: `title`, `author`, `search` (substring); repeatable `ta_decision`, `ft_decision`, `primary_status`, `source`, `country` (substring by default, exact with `match=exact`, `__none__` matches missing values); `year_min`/`year_max` range; legacy `year`. `include=facets` co-fetches facet values and counts. `ta_decision` is `removed_by_automation` for records an automated step removed before any reviewer decision (PRISMA "removed by automation tools"), so `exclude` means reviewer-excluded; `duplicate` for stored records dedup removed before screening (only when their count equals PRISMA `duplicates_removed`) and `superseded` for a connector's first-search records a low-recall retry replaced; each row also has `automation_step` (`metadata_filter`, `rule_prefilter`, `keyword_ranking`, `batch_preranker`, `unclassified`, or null) |
| GET | /api/db/{run_id}/papers-facets | Distinct facet values (sources, decisions) for filter UI, plus `counts` per value for ta_decision, ft_decision, primary_status, year, source, country. Accepts the papers-all filters; each facet's counts ignore that facet's own filter. ta_decision includes the derived `removed_by_automation`, `duplicate` and `superseded` values |
| GET | /api/db/{run_id}/papers-export | Download the whole filtered set (`format=csv` or `ris`), same filter, `sort` and `dir` params as papers-all |
| GET | /api/db/{run_id}/papers/{paper_id} | One paper's full record: metadata, abstract, per-stage screening decisions with reasons, `automation_step` (null unless removed by automation), `unscreened_origin` (`duplicate`, `superseded` or null), extraction and quality summary |
| GET | /api/db/{run_id}/papers-suggest | Autocomplete suggestions for paper search |
| GET | /api/db/{run_id}/costs | Cost records grouped by model and phase (includes embedding phase) |
| GET | /api/db/{run_id}/costs/aggregates | Time-bucket and dimension cost aggregates (day/week/month/workflow/phase/model) |
| GET | /api/db/{run_id}/costs/export | CSV export for reconciliation (day/week/month buckets) |
| GET | /api/db/{run_id}/cost-dashboard | Consolidated per-run cost dashboard payload (model/phase breakdown) |
| GET | /api/db/{run_id}/tables | Numeric extracted outcome rows grouped by paper (`total_rows`, `total_papers`, `filtered`, `papers`). Accepts the papers-all filters to restrict outcomes to matching papers; optional `offset`/`limit` (1-500) paginate by outcome row. No params returns every row, as before |
| GET | /api/db/{run_id}/rag-diagnostics | Per-section RAG retrieval diagnostics |
| GET | /api/run/{run_id}/artifacts | Full run_summary.json for any run (live or historical) |
| GET | /api/run/{run_id}/manuscript | Download manuscript content (`fmt=md` or `fmt=tex`) |
| GET | /api/run/{run_id}/events | Replay buffer snapshot (all buffered SSE events for live run) |
| GET | /api/workflow/{workflow_id}/events | Events from event_log table by workflow ID (historical) |
| GET | /api/workflow/{workflow_id}/validation/summary | Latest workflow replay validation run summary; optional `include=checks` embeds check rows |
| GET | /api/workflow/{workflow_id}/validation/checks | Detailed checks for a validation run (latest by default) |
| GET | /api/workflow/{workflow_id}/manuscript-audit/summary | Latest + history manuscript audit run summaries |
| GET | /api/workflow/{workflow_id}/manuscript-audit/findings | Manuscript audit findings for latest or explicit audit_run_id |
| POST | /api/workflow/reserve | Reserve early workflow draft (`topic`, optional `run_root`); returns `{workflow_id, db_path, run_dir}` |
| PUT | /api/workflow/{workflow_id}/config-draft | Save review YAML config draft (`review_yaml`, optional `run_root`); returns `{workflow_id, status: config_ready}` |
| PATCH | /api/notes/{workflow_id} | Update run notes |
| GET | /api/notes/stream | SSE stream for notes updates |
| GET | /api/run/{run_id}/papers-reference | Included papers list with PDF/TXT file availability flags |
| GET | /api/run/{run_id}/papers/{paper_id}/file | Stream PDF or TXT file for a specific included paper |
| POST | /api/run/{run_id}/fetch-pdfs | Retroactive full-text fetch for completed runs; returns `{attempted, succeeded, failed}` |
| GET | /api/run/{run_id}/screening-summary | Human-in-the-loop screening summary: one row per screened paper with its final decision (`final_decision`, `stage`, `exclusion_reason`, `decided_by`, `automation_step`: PRISMA automation step when an automated step removed it before any reviewer decision, else null) plus `thresholds` |
| POST | /api/run/{run_id}/approve-screening | Approve screening (idempotent overrides) and unblock HumanReviewCheckpointNode |
| GET | /api/run/{run_id}/knowledge-graph | Force-directed knowledge graph nodes and edges for EvidenceNetworkViz |
| GET | /api/run/{run_id}/prisma-checklist | PRISMA 2020 compliance checklist (item-by-item pass/fail/partial) |
| GET | /api/run/{run_id}/prisma-diagram.png | Download latest PRISMA flow diagram PNG (`Cache-Control: no-store`) |
| GET | /api/run/{run_id}/prisma-counts | Live PRISMA counts from `runtime.db` (`live`), the `prisma_counts.json` sidecar the figure was drawn from (`sidecar`, null for older runs), and `figure_stale` (null without a sidecar) |
| GET | /api/run/{run_id}/prisma-flow.zip | Download PRISMA flow data ZIP (summary, per-paper records, search identification CSVs) |
| GET | /api/run/{run_id}/grade-sof | GRADE Summary of Findings table for the review |
| POST | /api/run/{run_id}/living-refresh | Start incremental re-run from last_search_date for living reviews |
| POST | /api/run/{run_id}/export | Package IEEE LaTeX submission; calls package_submission() |
| GET | /api/run/{run_id}/submission.zip | Download the submission ZIP package |
| GET | /api/run/{run_id}/studies-files.zip | Download bundled per-study full-text files (PDF/TXT) for included studies |
| GET | /api/run/{run_id}/manuscript.docx | Download the Word DOCX manuscript |
| GET | /api/run/{run_id}/prospero-form.docx | Download generated PROSPERO registration form (DOCX) |
| GET | /api/run/{run_id}/prospero-form.md | Download generated PROSPERO registration form (Markdown) |
| POST | /api/run/{run_id}/submit-prospero | Record PROSPERO registration (`registration_number`, `registration_date`) and resume workflow |
| POST | /api/run/{run_id}/regenerate-prospero | Regenerate PROSPERO draft documents from the current run config |
| GET | /api/run/{run_id}/manuscript-audit | Consolidated manuscript-audit payload resolved from run/workflow identifier |
| GET | /api/run/{run_id}/readiness | Readiness scorecard for export and operational review (finalize, PRISMA, contracts, fallbacks, PDF) |
| GET | /api/run/{run_id}/diagnostics | Step journal summary, recovery/fallback counts, writing manifests for run diagnostics |
| GET | /api/logs/stream | SSE tail of per-run `app.jsonl` (via `run_id` or `workflow_id`) or PM2 logs fallback |

### 10.1.1 Endpoint parity checklist

`scripts/check.py api` compares `/api/*` routes with `include_in_schema=True` in `src/web/app.py` and `src/web/routers/*.py`.
