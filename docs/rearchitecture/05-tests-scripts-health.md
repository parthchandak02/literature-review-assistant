# Tests, scripts, and CI health (audit)

**Date:** 2026-09-26  
**Scope:** `tests/**`, `scripts/**`, `Makefile`, `pyproject.toml`, `docs/SCRIPTS.md`, `docs/TASKS.md`, `ecosystem.config.js`, `.cursor/skills/verify-litreview`  
**Constraint:** Read-only audit; no source edits.

---

## 1. Test inventory

### 1.1 Layout and counts

| Area | Files | Pytest items (collect-only) | Role |
|------|-------|-----------------------------|------|
| `tests/unit/` | 140 `test_*.py` | 1,179 | Fast, mostly mocked LLM / in-memory SQLite |
| `tests/integration/` | 25 `test_*.py` | 162 | API, graph, pipeline slices, replay DB surfaces |
| `tests/fixtures/` | 9 assets | — | Replay DBs, scoping YAML, manuscript audit JSON, humanizer samples |
| `tests/` (root) | `conftest.py` | — | Session `load_dotenv(override=True)`, replay env fixtures |
| `tests/e2e/` | — | — | **Does not exist** (per `.cursor/rules/testing/tests.mdc`) |

**Replay-related paths:** `tests/fixtures/replay/` (`manifest.json`, `runtime.db`, `runtime_adversarial.db`, `doc_manuscript.md`); integration modules `test_workflow_replay_*.py`, `test_workflow_replay_execution.py`.

**Total backend collection:** 1,341 tests (`uv run pytest --collect-only`).

### 1.2 Coverage by `src/` top-level package (test files that import the package)

| Package | Unit test files | Integration test files |
|---------|-----------------|--------------------------|
| `models` | 70 | 13 |
| `db` | 31 | 17 |
| `web` | 21 | 7 |
| `orchestration` | 20 | 6 |
| `writing` | 19 | 1 |
| `search` | 17 | 1 |
| `llm` | 14 | 3 |
| `export` | 11 | 1 |
| `extraction` | 8 | 1 |
| `manuscript` | 8 | 1 |
| `quality` | 7 | 2 |
| `screening` | 7 | 3 |
| `config` | 5 | 3 |
| `synthesis` | 5 | 1 |
| `visualization` | 5 | 1 |
| `rag` | 4 | 0 |
| `protocol`, `citation`, `prisma`, `utils`, `main` | 2 each (unit) | sparse |
| `knowledge_graph`, `fulltext` | 1 each (unit) | 0 |

### 1.3 Integration modules (what they exercise)

| File | Focus |
|------|--------|
| `test_api_endpoint_parity_gate.py` | Fast gate: OpenAPI/route parity smoke |
| `test_api_endpoints.py` | Broad FastAPI contract tests (large) |
| `test_prospero_and_draft_api.py` | PROSPERO gate + workflow draft APIs |
| `test_golden_path_api.py` | POST start → terminal workflow state |
| `test_phase1_smoke.py` | Config loader + review YAML |
| `test_resume_workflow_smoke.py` | Resume facade with stubbed graph tail |
| `test_resume_rewind.py` | Phase rollback / checkpoint clearing |
| `test_lifecycle_restart.py` | Durability, SSE replay, stale resume |
| `test_app_shutdown.py` | Graceful shutdown (release gate) |
| `test_graph_transitions.py` | Graph routing |
| `test_run_command.py` | CLI `run` through real orchestrator path |
| `test_*_pipeline.py` | screening, extraction, quality, synthesis, writing, export |
| `test_dual_screening.py`, `test_batch_screening_pipeline.py` | Screening pipelines |
| `test_gate_strictness.py`, `test_validation_*.py` | Gates and validation API |
| `test_workflow_replay_*.py` | SQL/query replay against committed `runtime.db` |

### 1.4 `src/` modules with no direct test import match (52 / 231 non-`__init__` files)

Heuristic: no `src.<module>` string in any `test_*.py` and no `test_<basename>` filename match. Many are thin runners/nodes covered indirectly by integration tests; list is a **gap radar**, not proof of zero coverage.

| Package | Modules |
|---------|---------|
| `db` | `domain_repositories`, `repos.costs`, `repos.events`, `repos.workflow_state` |
| `export` | `markdown_utils` |
| `llm` | `base_client`, `model_fallback` |
| `orchestration` | `knowledge_graph_node`, `nodes.finalize`, `nodes.human_review`, `helpers.manuscript_gate`, `helpers.writing_manuscript`, runners (`audit_runner`, `extraction_runner`, `finalize_runner`, `screening_runner`, `search_runner`, `synthesis_runner`, `writing_runner`, `writing.post_assembly`, `writing.rag_retrieval`, `writing.section_loop`) |
| `quality` | `runner` |
| `rag` | `embedder`, `reranker` |
| `screening` | `criteria_refinement`, `heuristics`, `persistence` |
| `search` | `base`, `common`, `core`, `dblp`, `europepmc`, `semantic_scholar`, `source_quality` |
| `synthesis` | `constants` |
| `utils` | `ssl_context` |
| `visualization` | `evidence_network`, `rob_figure`, `timeline` |
| `web` | `lifecycle_coordinator`, `run_concurrency`, `routers.advanced`, `routers.run_lifecycle`, `routers.system` |
| `writing` | `abstract_utils`, `citation_catalog`, `date_windows`, `grounding_patches`, `instruction_constants`, `prompts.base`, `section_validation` |

### 1.5 Frontend tests

- **Runner:** Vitest (`frontend/package.json`: `pnpm test` → `vitest run`).
- **25** test files, **172** tests (all under `frontend/src/**`).
- Covers hooks, lib helpers, setup wizard (`ReviewTypeDecisionStage`), cost ops formatters, API client pieces—not full browser E2E.

---

## 2. Test run results (2026-09-26)

Environment: macOS, Python via `uv`, Node v20.19.2. `pnpm` via Corepack failed in this shell (`ERR_VM_DYNAMIC_IMPORT_CALLBACK_MISSING`); frontend checks used `frontend/node_modules/.bin` instead (same as `ecosystem.config.js` recommendation for PM2).

### 2.1 Full backend pytest

```bash
uv run pytest -q -x --timeout=300 2>&1 | tail -50   # stopped at first failure
uv run pytest -q --timeout=300 -r f                  # full run
```

| Metric | Value |
|--------|-------|
| **Passed** | 1,322 |
| **Failed** | 13 |
| **Skipped** | 6 |
| **Wall time** | ~175–183 s |

**Failures (13):**

1. `tests/integration/test_api_endpoints.py::test_studies_files_zip_no_files_returns_404` — 404 `detail` string mismatch  
2. `tests/integration/test_api_endpoints.py::test_generate_config_stream_includes_topic_routing_metadata`  
3. `tests/integration/test_api_endpoints.py::test_generate_config_stream_done_event_includes_quality_metrics`  
4. `tests/integration/test_api_endpoints.py::test_generate_config_stream_passes_health_sdg_profile`  
5. `tests/integration/test_golden_path_api.py::test_post_start_reaches_terminal_done_with_workflow_row`  
6. `tests/integration/test_phase1_smoke.py::test_config_loader_reads_review_yaml`  
7–10. `tests/integration/test_resume_rewind.py` (4 tests) — phase rollback / section draft clearing  
11. `tests/integration/test_run_command.py::test_run_executes_single_path_orchestrator`  
12. `tests/integration/test_workflow_replay_screening.py::test_real_workflow_screening_replay_surface`  
13. `tests/unit/test_attach_defer_backfill.py::test_attach_history_still_migrates_legacy_schema`

**Note:** `make check-local` runs **only** `tests/unit` plus a **subset** of integration tests; it does **not** run the full 1,341-item suite. Local gate can be green while full `pytest` fails.

### 2.2 Frontend

```bash
cd frontend && ./node_modules/.bin/tsc -b --noEmit   # exit 0
cd frontend && ./node_modules/.bin/vitest run      # 25 files, 172 passed, ~1.4s
```

### 2.3 `make check-local`

```bash
make check-local   # wall ~178 s, exit 0
```

| Step | Result |
|------|--------|
| `ruff check .` | pass |
| `pytest tests/unit` | **1,177 passed**, 2 skipped (~155 s) |
| `test_api_endpoint_parity_gate.py` | 1 passed |
| `test_prospero_and_draft_api.py` | 7 passed |
| `scripts/check.py api` | 69 endpoints match |
| `pnpm lint` / `typecheck` / `test` | pass (172 tests) |
| `replay-fixture` + `replay-workflow` (local profile, `wf-0088`) | 0 errors |

First background `make check-local` (parallel with full pytest) left a truncated log (~unit start only); rerun serially completed successfully.

### 2.4 `make check-release` (not executed)

Not run in this audit (~15 min budget used by `check-local` + full pytest). Per `scripts/check.sh release`: adds frontend **build**, more integration files, event-store durability, multi-profile replay (`default` + `adversarial`).

---

## 3. Scripts and Makefile

### 3.1 Makefile targets

| Target | Alias | Command | Gate? |
|--------|-------|---------|-------|
| `lint` | — | `uv run ruff check .` | optional |
| `test-unit` | — | `pytest tests/unit -q` | dev |
| `test-integration-smoke` | — | parity gate file only | dev |
| `check-api` | `parity` | `scripts/check.py api` | **local + release** |
| `check-replay-fixture` | — | `scripts/check.py replay-fixture` | **local + release** |
| `check-local` | `local-ci` | `scripts/check.sh local` | **primary pre-commit** |
| `check-release` | `release-check` | `scripts/check.sh release` | **pre-release** |
| `pm2-restart` | — | `ops_pm2.sh restart` | ops |
| `deploy-prod` | — | `ops_pm2.sh restart --prod-ui` | ops |
| `scripts-help` | — | `scripts/help.sh` | docs |

### 3.2 User-facing scripts (`docs/SCRIPTS.md`)

| Entrypoint | Purpose |
|------------|---------|
| `scripts/check.sh` | Orchestrates local vs release gates |
| `scripts/check.py` | `api`, `replay-fixture`, `replay-workflow`, `config-methodology` |
| `scripts/review.py` | `start`, `watch`, `info` — operator CLI |
| `scripts/repair.py` | `finalize`, `re-extract`, `inject-citations`, `regen-replay-fixture` |
| `scripts/ops_pm2.sh` | PM2: `litreview-api`, `litreview-ui`, `litreview-tunnel` |
| `scripts/hermes.sh` | Hermes operator maintenance |
| `scripts/help.sh` | Terminal index |

Implementation lives in `scripts/lib/` (not invoked directly per project rules).

### 3.3 `ecosystem.config.js`

- **`litreview-api`:** `uvicorn` on `:8001`, 45s kill timeout for graceful shutdown.  
- **`litreview-tunnel`:** Cloudflare tunnel.  
- **`litreview-ui`:** Vite dev on `:5173`, `autorestart: false` (dev-only; production serves `frontend/dist` via API).

### 3.4 `.cursor/skills/verify-litreview`

Agent CLI `control_litreview.py`:

| Command | What it runs |
|---------|----------------|
| `doctor` | PM2 jlist, `/api/health`, ruff on models/config_generator, frontend `tsc` |
| `profile-resolve` | Wraps `scripts/check.py config-methodology` |
| `phase1-gate` | Scoping unit tests + scoping fixture + wizard Vitest + `tsc` |
| `sr-regression` | `--quick`: small pytest subset; full: `make check-local` |

Documented in `docs/TASKS.md` as optional Phase 1 / scoping acceptance; not a substitute for `check-release`.

### 3.5 `pyproject.toml` test tooling

- **pytest:** `tests/`, `asyncio_mode=auto`, session-scoped event loop, `pytest-timeout` in dev deps.  
- **ruff:** E/F/I/UP; per-file ignores for scripts and orchestration import order.  
- **mypy / pyright:** not configured in `pyproject.toml`; backend typing is ruff-only for CI gates.

---

## 4. E2E and replay coverage

### 4.1 Is there a full-pipeline E2E with mocked LLM/search?

**No single test runs the entire `RUN_GRAPH` end-to-end with all externals mocked.**

Closest patterns:

| Pattern | Location | Behavior |
|---------|----------|----------|
| **Replay validation** | `scripts/lib/check_workflow_replay.py` via `check.py replay-workflow` | Read-only checks on committed `runtime.db` (phase row counts, manuscript contracts, etc.) |
| **Replay integration** | `test_workflow_replay_*.py` | Executes selected SQL/helpers against fixture DB (replay env vars or default fixture) |
| **CLI smoke** | `test_run_command.py` | Real `main run` with `unsupported_db` and warning gates—runs orchestrator, expects checkpoint phases in DB (slow, environment-sensitive) |
| **Resume smoke** | `test_resume_workflow_smoke.py` | Real resume path; **stubs graph tail** after gate (documented: embedding/RAG/synthesis too heavy) |
| **Pipeline integration** | `test_*_pipeline.py` | Phase-scoped with mocks/fixtures |

Replay fixtures are **snapshots of real completed runs**, not synthesized from mocked LLM transcripts.

### 4.2 How replay fixtures are built

1. Complete a real workflow run (produces `runs/.../runtime.db`).  
2. Regenerate fixture:  
   `uv run python scripts/repair.py regen-replay-fixture --workflow-id wf-XXXX`  
   (implementation: `scripts/lib/maint_replay_fixture.py`).  
3. Commit under `tests/fixtures/replay/` per `manifest.json` (`schema_version`, `profiles.default` / `profiles.adversarial`).  
4. Gates: `check.py replay-fixture` (schema) + `check.py replay-workflow` (validation profiles: `local`, `adversarial`, etc.).

`check-local` validates **default** profile only; `check-release` loops all manifest profiles (including adversarial `wf-0044` early-failure DB).

### 4.3 Battle-testing gaps

| Area | Current signal | Gap |
|------|----------------|-----|
| **Fault injection** | `runtime_adversarial.db` profile; some unit tests (malformed Scopus entry, contract malformed heading) | No systematic fault injection in graph runner (connector 500 storms, mid-phase SIGKILL, corrupt checkpoint JSON) |
| **Resume after crash** | `test_lifecycle_restart.py`, `test_resume_*`, `test_event_store_durability.py` (release) | No chaos test that kills API mid-LLM-call and asserts idempotent resume |
| **Rate-limit storms** | `test_shared_rate_limiter.py`, Scopus 429 sleep test | No multi-connector concurrent 429 integration test |
| **Malformed LLM output** | `complete_validated` / contract matrix unit tests; export manuscript contracts | Limited cross-phase tests that assert **fail-fast** (not advisory) when structured output breaks mid-pipeline |
| **Full graph E2E** | Partial | No mocked-LLM golden run asserting every phase transition in one test |
| **Frontend E2E** | Vitest only | No Playwright/CDP; `verify-litreview` explicitly defers browser automation for Phase 1 |

---

## 5. Lint and type status

```bash
uv run ruff check src tests   # All checks passed!
```

| Tool | Backend | Frontend |
|------|---------|----------|
| Ruff | gated in `check-local` / `check-release` | — |
| mypy | not in CI | — |
| pyright | not in CI | — |
| ESLint | — | `pnpm lint` in `check-local` |
| TypeScript | — | `tsc -b --noEmit` — **pass** |

---

## 6. Summary alignment with `docs/TASKS.md`

- Documented gates match Makefile (`check-local`, `check-api`, replay-workflow).  
- **Drift:** TASKS still mentions 66 routes; `check.py api` reported **69** endpoints (2026-09-26 run).  
- Open backlog items (component tests, replay phase-name lock, resume hang) remain relevant; full pytest failures cluster around **API config stream**, **resume rewind**, **replay screening surface**, and **legacy schema attach**.

---

## 7. Recommended follow-ups (report-only)

1. Decide whether full `pytest` (all integration) belongs in `check-local` or a nightly `check-full` target.  
2. Fix or quarantine the 13 failing tests before treating full-suite green as release criteria.  
3. Extend replay adversarial profile checks into pytest (not only `check-release` shell loop).  
4. Add targeted tests for `orchestration/runners/*` entrypoints listed in §1.4.  
5. Document Corepack/`pnpm` failure mode; standardize on `node_modules/.bin` in CI docs (already done for PM2 UI).
