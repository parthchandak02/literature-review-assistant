# API Endpoints Parity Table

This file is the endpoint parity anchor for `scripts/check_spec_endpoint_parity.py`.

When API routes change in `src/web/app.py`, update this table in the same change.

## 10. API Contract

### 10.1 REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/run | Start new review from JSON config payload (`RunRequest`); returns `{run_id, topic}` |
| POST | /api/run-with-masterlist | Start review from master-list CSV upload (multipart form) |
| POST | /api/run-with-supplementary-csv | Start review with connector search plus supplementary CSV upload (multipart form) |
| GET | /api/stream/{run_id} | SSE stream of ReviewEvent JSON; heartbeat every 15s; ends with done/error/cancelled |
| POST | /api/cancel/{run_id} | Cancel active run; sets cancellation event |
| GET | /api/download | Download artifact file (query param `path`; restricted to runs/) |
| GET | /api/config/review | Default review.yaml content (pre-fills Setup form) |
| POST | /api/config/generate/stream | SSE-streamed version of config generation |
| GET | /api/config/env-keys | API keys already set in server .env; used to pre-fill Setup form |
| GET | /api/health | Health check; polled every 6s by useBackendHealth hook |
| GET | /api/history | Past runs from workflows_registry.db |
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
| DELETE | /api/history/{workflow_id} | Delete run directory + registry entry from disk |
| GET | /api/db/{run_id}/papers-all | All papers with doi + url fields for clickable links |
| GET | /api/db/{run_id}/papers-facets | Distinct facet values (sources, decisions) for filter UI |
| GET | /api/db/{run_id}/papers-suggest | Autocomplete suggestions for paper search |
| GET | /api/db/{run_id}/costs | Cost records grouped by model and phase (includes embedding phase) |
| GET | /api/db/{run_id}/costs/aggregates | Time-bucket and dimension cost aggregates (day/week/month/workflow/phase/model) |
| GET | /api/db/{run_id}/costs/export | CSV export for reconciliation (day/week/month buckets) |
| GET | /api/db/{run_id}/tables | Vision-extracted table rows from papers |
| GET | /api/db/{run_id}/rag-diagnostics | Per-section RAG retrieval diagnostics |
| GET | /api/run/{run_id}/artifacts | Full run_summary.json for any run (live or historical) |
| GET | /api/run/{run_id}/manuscript | Download manuscript content (`fmt=md` or `fmt=tex`) |
| GET | /api/run/{run_id}/events | Replay buffer snapshot (all buffered SSE events for live run) |
| GET | /api/workflow/{workflow_id}/events | Events from event_log table by workflow ID (historical) |
| GET | /api/workflow/{workflow_id}/validation/summary | Latest workflow replay validation run summary |
| GET | /api/workflow/{workflow_id}/validation/checks | Detailed checks for a validation run (latest by default) |
| GET | /api/workflow/{workflow_id}/manuscript-audit/summary | Latest + history manuscript audit run summaries |
| GET | /api/workflow/{workflow_id}/manuscript-audit/findings | Manuscript audit findings for latest or explicit audit_run_id |
| PATCH | /api/notes/{workflow_id} | Update run notes |
| GET | /api/notes/stream | SSE stream for notes updates |
| GET | /api/run/{run_id}/papers-reference | Included papers list with PDF/TXT file availability flags |
| GET | /api/run/{run_id}/papers/{paper_id}/file | Stream PDF or TXT file for a specific included paper |
| POST | /api/run/{run_id}/fetch-pdfs | Retroactive full-text fetch for completed runs; returns `{attempted, succeeded, failed}` |
| GET | /api/run/{run_id}/screening-summary | Human-in-the-loop screening summary (counts, sample decisions) |
| POST | /api/run/{run_id}/approve-screening | Approve screening and unblock HumanReviewCheckpointNode |
| GET | /api/run/{run_id}/knowledge-graph | Force-directed knowledge graph nodes and edges for EvidenceNetworkViz |
| GET | /api/run/{run_id}/prisma-checklist | PRISMA 2020 compliance checklist (item-by-item pass/fail/partial) |
| GET | /api/run/{run_id}/grade-sof | GRADE Summary of Findings table for the review |
| POST | /api/run/{run_id}/living-refresh | Start incremental re-run from last_search_date for living reviews |
| POST | /api/run/{run_id}/export | Package IEEE LaTeX submission; calls package_submission() |
| GET | /api/run/{run_id}/submission.zip | Download the submission ZIP package |
| GET | /api/run/{run_id}/studies-files.zip | Download bundled per-study full-text files (PDF/TXT) for included studies |
| GET | /api/run/{run_id}/manuscript.docx | Download the Word DOCX manuscript |
| GET | /api/run/{run_id}/prospero-form.docx | Download generated PROSPERO registration form (DOCX) |
| GET | /api/run/{run_id}/prospero-form.md | Download generated PROSPERO registration form (Markdown) |
| GET | /api/run/{run_id}/manuscript-audit | Consolidated manuscript-audit payload resolved from run/workflow identifier |
| GET | /api/run/{run_id}/readiness | Readiness scorecard for export and operational review (finalize, PRISMA, contracts, fallbacks, PDF) |
| GET | /api/run/{run_id}/diagnostics | Step journal summary, recovery/fallback counts, writing manifests for run diagnostics |
| GET | /api/logs/stream | SSE tail of per-run PM2 log file; filtered by run_id query param |

### 10.1.1 Endpoint Parity Checklist

Endpoint parity is enforced by `scripts/check_spec_endpoint_parity.py` against `src/web/app.py`.
