# AGENTS

Single onboarding entrypoint for any agentic dev tool.

If you read only one file, read this one first.

## Fast Start (under 2 minutes)

1. Read `docs/CONTEXT.md`
2. Read one task-specific contract doc from `docs/`
3. Read one relevant skill in `.cursor/skills/**/SKILL.md`
4. For session startup: `.cursor/skills/bootstrap/SKILL.md`
5. For cross-cutting defaults: `.cursor/skills/general-rules/SKILL.md`

## Non-Cursor Tools

If your tool does not auto-load `.cursor/rules/`, use explicit file reads:

1. `AGENTS.md`
2. `docs/CONTEXT.md`
3. One task doc under `docs/`
4. One relevant skill under `.cursor/skills/**/SKILL.md`

## Source of Truth Priority

1. Code in `src/` and `frontend/src/`
2. Always-on rules in `.cursor/rules/core/`
3. Canonical docs in `docs/`
4. Endpoint parity anchor (`docs/API.md#rest-endpoints` Section 10.1 only)

If sources conflict, follow this order and verify in code.

## Production hosting

Public URL: `https://litreview.parthchandak.info` (Cloudflare Tunnel → local `:8001`). Cloudflare Access email OTP at edge; tune Application session to 30d (`720h`) so devices re-auth monthly, not daily. See [docs/agents/dashboard-hosting.md](docs/agents/dashboard-hosting.md).

## Minimal Task Routing

- Architecture or behavior questions -> `docs/ARCHITECTURE.md`
- Pipeline/phase work -> `docs/ARCHITECTURE.md#pipeline`
- API work -> `docs/API.md`
- DB/runtime state work -> `docs/ARCHITECTURE.md#persistence`
- Frontend flow work -> `docs/UI.md`
- LLM/cost work -> `docs/ARCHITECTURE.md#llm-and-costs`
- LLM provider or API key changes -> `.cursor/skills/llm-provider/SKILL.md`
- Validation/readiness -> `docs/TASKS.md`
- Scripts / ops commands -> `docs/SCRIPTS.md` or `./scripts/help.sh`
- UX before/after screenshots -> [UX screenshot harness](#ux-screenshot-harness) below
- Offline per-run LLM cost breakdown -> [Run cost summary CLI](#run-cost-summary-cli) below
- Redraw a run's PRISMA figure from `runtime.db` -> [PRISMA regenerate CLI](#prisma-regenerate-cli) below
- Compare Jev vs LLM reviewer B on a finished run -> [Jev eval CLI](#jev-eval-cli) below
- Validate or rebuild workflow replay test fixtures -> [Workflow replay CLI](#workflow-replay-cli) below
- Repair an existing run's manuscript sections, failed extractions, or missing citations -> [Run repair CLI](#run-repair-cli) below
- Import a master-list or supplementary CSV into search -> [CSV search import](#csv-search-import) below
- Retrieve paper PDFs via OA tier racing, institutional session cookies, or a manual PDF folder -> [Full-text retrieval and manual PDF ingest](#full-text-retrieval-and-manual-pdf-ingest) below

## Run cost summary CLI

Offline operator tool for a single run's LLM spend. Reads `cost_records` from that run's `runtime.db`, prints per-model/phase rows, then a provider-family rollup. No network calls and no writes.

| Piece | Role |
|-------|------|
| Entrypoint | `scripts/review.py info` with `--costs` |
| Implementation | `scripts/lib/diag_costs.py` (`run_costs` / `summarize`); call only via the entrypoint |
| Data source | Canonical `cost_records` table in the resolved `runtime.db` |

How to run:

```bash
# By workflow id (resolves db_path from workflows_registry.db under runs/)
uv run python scripts/review.py info --workflow-id wf-XXXX --costs

# Or point at a run directory that contains runtime.db
uv run python scripts/review.py info --run-dir runs/<run_id> --costs
```

Optional: omit `--costs` for the usual Rich diagnostic tables only. For dashboard/API aggregates across many runs, use Settings → Costs (`CostsPanel`) or `GET /api/history/costs/aggregates` (see `docs/ARCHITECTURE.md#llm-and-costs`).

How to test: unit contract in `tests/unit/test_review_costs_docs.py` (docs + CLI flag shape). Manual check: run the commands above against any finished run and confirm model/phase rows and the "By provider family" section print. Full script index: `docs/SCRIPTS.md`.

## UX screenshot harness

Developer-only Playwright helpers for visual review of the local dashboard. They are not part of the review pipeline and are not wired into `make check-local`. Outputs go under `tmp/ux-shots/<label>/` (gitignored). Requires a running UI (API on `:8001` or the Vite proxy) and a local Playwright Chromium install (`pip install playwright && playwright install chromium`).

| Script | Purpose | Entrypoint |
|--------|---------|------------|
| `scripts/ux_screenshots.py` | Capture desktop (dark/light) and mobile shots of Setup, Activity, Results, Data, Config, and Cost | `python3 scripts/ux_screenshots.py <label> [--base http://localhost:8001]` |
| `scripts/ux_screening_preview.py` | Present a completed run as `awaiting_review` on the screening gate (rewrites history/attach GETs only; blocks other non-GET API writes) | `python3 scripts/ux_screening_preview.py <label> [--base URL] [--workflow wf-0001]` |

How to run:

```bash
# terminal 1: API serving the UI (or use Vite on :5173 and pass --base http://localhost:5173)
uv run uvicorn src.web.app:app --port 8001

# terminal 2: labeled before/after captures
python3 scripts/ux_screenshots.py before
python3 scripts/ux_screening_preview.py before-screening --workflow wf-0001
```

How to test: unit contract in `tests/unit/test_ux_screenshot_harness_docs.py` (docs + CLI shape). Manual check: open files under `tmp/ux-shots/<label>/` after a capture. Full script index: `docs/SCRIPTS.md`.

## PRISMA regenerate CLI

Offline repair tool that recomputes PRISMA 2020 flow counts from a run's `runtime.db`, redraws `fig_prisma_flow.png`, and writes `prisma_counts.json` beside it. No network calls and no LLM spend. Use when the figure or sidecar drifted from DB truth (for example after a screening repair) without re-running the whole pipeline.

| Piece | Role |
|-------|------|
| Entrypoint | `scripts/regenerate_prisma.py` (`--run`, optional `--dry-run`, `--run-root`) |
| Implementation | `src/prisma/regenerate.py` (`regenerate_prisma`, `format_counts_diff`, `stale_manuscript_warning`) |
| Data source | Live counts from the run `runtime.db`; compares against any existing `prisma_counts.json` sidecar |

How to run:

```bash
# Preview old (sidecar) vs new (DB) counts; write nothing
uv run python scripts/regenerate_prisma.py --run wf-XXXX --dry-run

# Or point at a run directory / runtime.db path
uv run python scripts/regenerate_prisma.py --run runs/<run_id>
uv run python scripts/regenerate_prisma.py --run runs/<run_id>/runtime.db
```

`--dry-run` prints the count diff only. A real run also refreshes `submission/figures/fig_prisma_flow.png` when that copy exists. If `doc_manuscript.md` still quotes the old numbers, the CLI prints a stale-manuscript warning on stderr (it does not rewrite prose).

How to test: unit contracts in `tests/unit/test_prisma_regenerate_docs.py` (docs + CLI shape) and `tests/unit/test_prisma_counts_automation.py` (regenerate behavior). Manual check: `--dry-run` on any finished run, confirm the printed old/new table, then omit `--dry-run` and open the rewritten figure. Full script index: `docs/SCRIPTS.md`.

## Jev eval CLI

Offline quality check that compares Jev screening decisions against LLM reviewer B and final title/abstract decisions from a finished run's `runtime.db`. Default mode is read-only (no network, no writes). Optional `--live-sample N` re-screens N papers through Jev and reviewer B; that path costs money and refuses to run without `--confirm-live`.

| Piece | Role |
|-------|------|
| Entrypoint | `scripts/check.py jev-eval` (`--db`, optional `--json`, `--live-sample`, `--confirm-live`, `--out`) |
| Implementation | `scripts/lib/check_jev_eval.py` (`evaluate_db`, `run_live_sample`, `build_parser`); call only via the entrypoint |
| Data source | Read-only tables `jev_decisions`, `screening_decisions`, `dual_screening_results`, `study_cohort_membership`, and `cost_records` |

How to run:

```bash
# Offline agreement / recall / kappa report for one runtime.db
uv run python scripts/check.py jev-eval --db runs/<run_id>/runtime.db

# Same report as JSON (stdout), optional write to a file
uv run python scripts/check.py jev-eval --db runs/<run_id>/runtime.db --json --out /tmp/jev-eval.json

# Live re-screen of N papers (external API calls; requires --confirm-live)
uv run python scripts/check.py jev-eval --db runs/<run_id>/runtime.db --live-sample N --confirm-live
```

How to test: unit contracts in `tests/unit/test_jev_eval.py` (metrics and offline report) and `tests/unit/test_jev_eval_docs.py` (docs + CLI shape). Manual check: run the offline command on any finished run and confirm agreement, recall, and kappa lines print. Full script index: `docs/SCRIPTS.md`.

## Workflow replay CLI

Offline validation and fixture refresh tools for workflow `runtime.db` files and `tests/fixtures/replay/`. No network calls and no LLM spend. Note that `replay-workflow` records `validation_runs` and `validation_checks` rows inside the target `runtime.db` (`scripts/check.sh` copies fixture DBs to a temp file before validating). After adding a migration in `src/db/database.py`, run `regen-replay-fixture` for both `default` and `adversarial` profiles so `check-local` and `check-release` stay aligned with the schema version.

| Piece | Role |
|-------|------|
| Entrypoint | `scripts/check.py replay-fixture`, `scripts/check.py replay-workflow`, `scripts/repair.py regen-replay-fixture` |
| Implementation | `scripts/lib/check_replay_fixture.py` (`check_fixture`), `scripts/lib/check_workflow_replay.py` (`_run_checks`), `scripts/lib/maint_replay_fixture.py` (`run_regen_replay_fixture`); call only via the entrypoints |
| Data source | `tests/fixtures/replay/manifest.json` and `runtime.db` / `runtime_adversarial.db`, or any run's `runtime.db` plus `doc_manuscript.md` |

How to run:

```bash
# Verify committed replay fixture DBs match current schema_version in src/db/database.py
uv run python scripts/check.py replay-fixture

# Validate a workflow runtime.db against replay checks (profiles: quick, standard, deep, local, adversarial)
uv run python scripts/check.py replay-workflow --workflow-id wf-XXXX --profile local --fail-on-error
uv run python scripts/check.py replay-workflow --workflow-id wf-XXXX --db-path /tmp/runtime.db --profile local --fail-on-error

# Rebuild tests/fixtures/replay after a DB schema migration (apply migrations + update manifest.json)
uv run python scripts/repair.py regen-replay-fixture --workflow-id wf-XXXX
uv run python scripts/repair.py regen-replay-fixture --profile adversarial
```

How to test: unit contract in `tests/unit/test_workflow_replay_docs.py` (docs + CLI shape). Manual check: run `uv run python scripts/check.py replay-fixture` and confirm `replay fixture OK` prints with the current `schema_version`. Full script index: `docs/SCRIPTS.md`.

## Run repair CLI

Post-run repair subcommands for fixing manuscript assembly, placeholder extraction rows, or missing included-study citations on an existing run directory without re-running the full pipeline. Note: these are authorized repair tools for historical or interrupted runs; for process or pipeline bugs, fix the code under `src/` rather than patching `runs/` by hand. `finalize` is offline and deterministic (no LLM spend). `re-extract` calls the extraction LLM for failed records (`is_extraction_failed`), and `inject-citations` patches `section_drafts` in `runtime.db`, rewrites `doc_manuscript.md`, `doc_manuscript.tex`, and `references.bib`, and may call the LLM fallback citation resolver when mechanical DOI/URL/title matching leaves unmatched references.

| Piece | Role |
|-------|------|
| Entrypoint | `scripts/repair.py finalize`, `scripts/repair.py re-extract`, `scripts/repair.py inject-citations` |
| Implementation | `scripts/lib/maint_finalize.py` (`run_finalize`), `scripts/lib/maint_re_extract.py` (`run_re_extract`), `scripts/lib/inject_citations.py` (`run_inject_citations`, `resolve_run_dir`); call only via the entrypoint |
| Data source | Run directory `runtime.db`, `doc_manuscript.md`, `review.yaml` / `config_snapshot.yaml`, and `doc_search_strategies_appendix.md` |

How to run:

```bash
# Offline: strip and re-assemble appended manuscript sections (Declarations, GRADE, tables, figures, references, appendix)
uv run python scripts/repair.py finalize --run-dir runs/<run_id>

# Paid LLM calls: re-run extraction for placeholder/failed records, then run finalize to refresh the manuscript
uv run python scripts/repair.py re-extract --run-dir runs/<run_id>
uv run python scripts/repair.py re-extract --run-dir runs/<run_id> --config config/review.yaml

# Patch uncited included-study citekeys into Results section_draft and regenerate .md, .tex, and references.bib
uv run python scripts/repair.py inject-citations --workflow-id wf-XXXX
uv run python scripts/repair.py inject-citations --run-dir runs/<run_id>
```

How to test: unit contract in `tests/unit/test_run_repair_docs.py` (docs + CLI shape). Manual check: run `uv run python scripts/repair.py --help` (or a subcommand `--help`) to verify flags, or run `finalize` on a scratch copy of a finished run directory and confirm `doc_manuscript.md` updates cleanly. Full script index: `docs/SCRIPTS.md`.

## CSV search import

Offline-capable ingestion workflow for importing externally exported search CSVs (Scopus, Embase, CINAHL, PubMed, or RIS-derived exports) into `phase_2_search` as typed `SearchResult` objects without altering downstream deduplication, screening, or PRISMA accounting. Two modes are supported: `masterlist_csv_path` replaces all live database connectors while keeping DB persistence, protocol generation, and checkpointing identical; `supplementary_csv_paths` merges additional CSV exports onto live connector results before deduplication. The parser sniffs encodings (`utf-8-sig`, `utf-8`, `cp1252`, `latin-1`) and delimiters (`,`, `;`, tab, `|`), normalizes DOIs, matches flexible column aliases (a recognizable Title column is required), and groups rows by inferred source database (`src/search/source_inference.py`).

| Piece | Role |
|-------|------|
| Importer | `src/search/csv_import.py` (`validate_csv_file`, `parse_masterlist_csv`, `parse_supplementary_csvs`) |
| Source inference | `src/search/source_inference.py` (`infer_csv_row_source`, `detect_csv_export_format`, `resolve_database_column`) |
| Pipeline runner | `src/orchestration/runners/search_runner.py` (branches on `masterlist_csv_path` or merges `supplementary_csv_paths`) |
| HTTP API | `POST /api/run-with-masterlist`, `POST /api/run-with-supplementary-csv` in `src/web/routers/run_lifecycle.py` |
| Config schema | `masterlist_csv_path`, `supplementary_csv_paths` on `ReviewConfig` in `src/models/config.py` |

How to run:

```bash
# Offline pre-flight validation of a CSV export (returns total rows and per-source counts)
uv run python -c "from src.search.csv_import import validate_csv_file; print(validate_csv_file('path/to/export.csv'))"

# CLI run: set masterlist_csv_path or supplementary_csv_paths in config/review.yaml
# (target_databases is still required by ReviewConfig validation even when masterlist_csv_path is set)
uv run python -m src.main run --config config/review.yaml
```

For web uploads, send multipart form data (`csv_file` and `review_yaml`, plus required API keys) to `POST /api/run-with-masterlist` or `POST /api/run-with-supplementary-csv`; the router stages the file under `runs/staging/<run_id>/`, validates it with `validate_csv_file`, injects the path into `review_yaml`, and launches the workflow.

How to test: run `uv run pytest tests/unit/test_csv_import.py tests/unit/test_source_inference.py tests/unit/test_csv_import_docs.py -q` for parser, source-inference, and docs contract checks, and `uv run pytest tests/integration/test_api_endpoints.py -k "masterlist or supplementary" -q` for the upload endpoints.

## Full-text retrieval and manual PDF ingest

Tiered full-text and PDF resolver (`src/fulltext/`, ADR-0002) used during `phase_3b_fulltext` screening (`PDFRetriever`) and `phase_4_extraction_quality` table extraction. `fetch_full_text` tries three priority groups before falling back to abstract text: Group A checks instant publisher-direct PDF URLs (MDPI, Frontiers, BMC, SpringerOpen, JMIR, PLoS, PeerJ, IEEE stamp); Group B races open-access sources in parallel (landing-page `citation_pdf_url` meta tag, Unpaywall, arXiv, Semantic Scholar `openAccessPdf`, bioRxiv/medRxiv, CORE with `CORE_API_KEY`, opt-in OpenAlex Content with `OPENALEX_API_KEY`, and Europe PMC) and cancels pending tasks on the first hit; Group C runs sequential authenticated or local fallbacks including ScienceDirect Article API (`SCOPUS_API_KEY` / `SCOPUS_INSTTOKEN`), institutional ScienceDirect PDF download via browser session cookies (`SCOPUS_SESSION_COOKIE_FILE` or `EMBASE_SESSION_COOKIE_FILE`), an operator manual PDF drop folder (`FULLTEXT_MANUAL_PDF_DIR` or `MANUAL_PDF_DIR`, matching recursive `*.pdf` filenames that contain the DOI with `/` or `_`/`-` after the `10.xxxx` prefix), PubMed Central, Crossref links, and full landing-page HTML resolution.

| Piece | Role |
|-------|------|
| Bounded context facade | `src/fulltext/__init__.py` (`FullTextResolver`, `FullTextResolveRequest`, `FullTextResult`, `fetch_full_text`, `resolve_landing_page`) |
| Tiered resolver | `src/fulltext/retrieval.py` (`fetch_full_text`, `resolve_landing_page`, `FullTextResult`) |
| Institutional session tier | `src/fulltext/institutional.py` (`fetch_sciencedirect_pdf_via_session`, `resolve_sciencedirect_pii`) and `src/search/scopus_session.py` (`load_scopus_session_cookie`) |
| Manual PDF drop folder | `src/fulltext/manual_ingest.py` (`manual_pdf_directory`, `find_manual_pdf_path`, `load_manual_pdf_bytes`, `reset_manual_index_cache`) |
| Pipeline and CLI callers | `src/search/pdf_retrieval.py` (`PDFRetriever`), `src/orchestration/runners/extraction_runner.py`, and `scripts/review.py info --fetch-pdfs` (`scripts/lib/review_show_info.py`) |

How to run:

```bash
# Offline: verify that a manually dropped PDF in FULLTEXT_MANUAL_PDF_DIR matches a DOI
FULLTEXT_MANUAL_PDF_DIR=/path/to/pdfs uv run python -c "from src.fulltext.manual_ingest import find_manual_pdf_path; print(find_manual_pdf_path('10.1016/j.jamda.2024.01.014'))"

# Live CLI check: attempt full-text retrieval for a run's included studies and save to runs/<run_id>/papers/
uv run python scripts/review.py info --workflow-id wf-XXXX --fetch-pdfs
uv run python scripts/review.py info --run-dir runs/<run_id> --fetch-pdfs
```

How to test: run `uv run pytest tests/unit/test_institutional_fulltext.py tests/unit/test_fulltext_doi_normalize.py tests/unit/test_pdf_retrieval.py tests/unit/test_landing_page_resolver.py tests/unit/test_fulltext_retrieval_docs.py -q`.

## Hard Constraints

- Never patch artifacts under `runs/` to fix process behavior.
- Use typed contracts from `src/models/` at phase boundaries.
- Keep model ids configured in `config/settings.yaml`.
- Preserve endpoint parity anchor in `docs/API.md#rest-endpoints` Section 10.1.
- New dependency versions must be at least 7 days old (`exclude-newer = "7 days"` in `pyproject.toml`, `minimumReleaseAge: 10080` in `frontend/pnpm-workspace.yaml`); for a security fix, pin an explicit version and exempt it via `[tool.uv.exclude-newer-package]` (or `--exclude-newer-package`) / `minimumReleaseAgeExclude`.

## Commit and Push

Use `.cursor/skills/commit/SKILL.md` (`/commit`).

If the change is **high level** (architecture, phases, API, persistence, frontend phase alignment, or `docs/`), run the **Before you commit** section in `docs/TASKS.md` first.

## Compatibility Notes

- `docs/API.md#rest-endpoints` is parity-only, not primary architecture guidance.
