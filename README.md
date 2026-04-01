# Research Article Writer

An open-source tool that automates systematic literature reviews end-to-end -- from a research question to an IEEE-submission-ready manuscript.

It runs a full PRISMA 2020-compliant pipeline: searches academic databases (defaults from `config/review.yaml`; additional databases can be enabled per review), dual-reviews papers that pass prefiltering with independent AI reviewers, extracts data, assesses risk of bias (RoB 2, ROBINS-I, GRADE), synthesizes evidence (meta-analysis or narrative), and writes the manuscript with citation lineage enforced throughout.

**Use it via browser (web UI) or terminal (CLI).**

---

## What It Produces

After a run completes, the run directory (`runs/YYYY-MM-DD/wf-NNNN-<topic-slug>/run_<time>/`) contains:

- `doc_manuscript.md` -- the full manuscript in markdown
- `doc_manuscript.tex` -- IEEE LaTeX version (generated automatically, no export step needed)
- `references.bib` -- all citations (generated automatically)
- `fig_*.png` / `fig_*.svg` -- all figures (PRISMA flow, RoB traffic-light, forest plot, funnel plot, timeline, geographic, concept diagrams)

Clicking **Export** in the browser (or running `uv run python -m src.main export`) assembles a `submission/` folder:

- `manuscript.tex` (+ `manuscript.pdf` when local LaTeX/pdflatex compilation succeeds) -- IEEE-formatted manuscript with bundled figures
- `manuscript.docx` -- Word format with figures and formatted tables (for sharing / human review)
- `references.bib` -- all citations
- `figures/` -- PRISMA flow diagram, RoB traffic-light, forest plot, funnel plot, publication timeline, geographic distribution
- `supplementary/` -- search strategies appendix, screening decisions CSV, extracted data CSV, PRISMA checklist (`prisma_checklist.html`, `prisma_checklist.md`, `prisma_checklist.csv`)

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.11+ | [python.org](https://www.python.org/downloads/) or `brew install python` |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js | 20.19+ or 22.12+ | [nodejs.org](https://nodejs.org/) or `brew install node` |
| pnpm | latest | `npm install -g pnpm` or `brew install pnpm` |

---

## Quick Start (Web UI)

The web UI is the easiest way to get started. No local config editing is required at launch -- you provide the research question and API keys in the browser.

**1. Clone the repo**

```bash
git clone https://github.com/parthchandak/literature-review-assistant
cd literature-review-assistant
```

**2. Install Python dependencies**

```bash
# Install uv (if you don't have it)
curl -LsSf https://astral.sh/uv/install.sh | sh

uv sync
```

**3. Install frontend dependencies and build**

```bash
cd frontend
pnpm install
pnpm build
cd ..
```

**4. Start the server**

```bash
uv run uvicorn src.web.app:app --port 8001
```

**5. Open your browser**

Go to `http://localhost:8001`. Click "+" in the sidebar to start a new review.

The setup page uses one question-first flow:

- Enter your research question in plain English and click "Generate Review Config". The AI generates PICO, keywords, criteria, and scope.
- Optionally attach a supplementary CSV (Scopus export format: Title, Authors, Year, Source title, DOI, Abstract). If provided, CSV records are merged with connector results before deduplication and screening.
- Review or edit YAML, confirm API keys, then launch the run.

A secondary "Paste YAML directly" link is also available for pasting a raw config from a previous run or external source.

Your Gemini API key is required and is pre-filled from localStorage on return visits. All keys are saved locally in your browser and never sent anywhere except your local backend.

The sidebar shows all your runs (live and historical) with status colors (emerald = completed, violet = running, red = error, amber = cancelled) and a stats strip (papers found, papers included, artifacts, cost). Selecting a run opens its dashboard with 6 base tabs: Config (research question + review.yaml), Activity (phase timeline + event log), Data, Cost, Results, and References (included papers list with PDF/TXT download). A conditional Review Screening tab appears only when the run pauses for human-in-the-loop screening approval (`awaiting_review`). To resume from a specific phase, use the Activity phase timeline (tap once to arm, tap again to confirm) or use the sidebar Resume button for default auto-resume. Runs can be archived from the active list, restored from the Archived section, and permanently deleted from archived-item overflow actions.

**Tip -- reuse a past config:** Click "+" to open the form, then use the "Load from past run" dropdown to pre-populate the form from any previous run's config. Useful for iterating on the same research question with different parameters.

---

## Quick Start (CLI)

Prefer the terminal? Use this path.

**1. Clone and install**

```bash
git clone https://github.com/parthchandak/literature-review-assistant
cd literature-review-assistant
uv sync
```

**2. Set up API keys**

Copy the template and fill in your keys:

```bash
cp .env.example .env
```

Edit `.env`:

```bash
GEMINI_API_KEY=your-key-here              # Required -- get free at ai.google.dev
OPENALEX_API_KEY=your-key-here            # Required if openalex is enabled (default review template includes openalex)
PUBMED_EMAIL=your-email@example.com       # Strongly recommended for PubMed
PUBMED_API_KEY=your-key-here              # Optional -- faster PubMed rate limits
IEEE_API_KEY=your-key-here                # Optional -- IEEE Xplore access
PERPLEXITY_SEARCH_API_KEY=your-key-here   # Optional -- auxiliary discovery
SEMANTIC_SCHOLAR_API_KEY=your-key-here    # Optional -- higher rate limits
CROSSREF_EMAIL=your-email@example.com     # Optional -- polite crawling for Crossref
SCOPUS_API_KEY=your-key-here              # Optional -- Scopus connector
WOS_API_KEY=your-key-here                 # Optional -- Web of Science connector
EMBASE_API_KEY=your-key-here              # Optional -- Embase connector
CORE_API_KEY=your-key-here                # Optional -- CORE full-text retrieval
```

**3. Configure your review**

Edit `config/review.yaml` with your research question:

```yaml
research_question: "How does X affect Y in population Z?"
review_type: "systematic"

pico:
  population: "..."
  intervention: "..."
  comparison: "..."
  outcome: "..."

keywords:
  - "keyword one"
  - "keyword two"

date_range_start: 2015
date_range_end: 2026
```

**4. Run**

```bash
uv run python -m src.main run --config config/review.yaml
```

The pipeline takes 20-60 minutes depending on how many papers are found. It prints progress as it goes.

**5. Export**

```bash
uv run python -m src.main export --workflow-id <id shown at end of run>
```

Your `submission/` folder is ready.

---

## API Keys

| Key | Where to Get | Required? |
|-----|-------------|-----------|
| `GEMINI_API_KEY` | [ai.google.dev](https://ai.google.dev) | Yes |
| `OPENALEX_API_KEY` | [openalex.org](https://openalex.org/sign-up) | Conditionally required (required for the default template unless `openalex` is removed from `target_databases`) |
| `PUBMED_EMAIL` | Any email address | Recommended (PubMed identification/rate policy) |
| `PUBMED_API_KEY` | [ncbi.nlm.nih.gov/account](https://www.ncbi.nlm.nih.gov/account/settings/) | No (higher rate limits) |
| `IEEE_API_KEY` | [developer.ieee.org](https://developer.ieee.org) | No |
| `PERPLEXITY_SEARCH_API_KEY` | [docs.perplexity.ai](https://docs.perplexity.ai) | No |
| `SEMANTIC_SCHOLAR_API_KEY` | [api.semanticscholar.org](https://api.semanticscholar.org) | No (higher rate limits) |
| `CROSSREF_EMAIL` | Any email address | No (polite Crossref crawling) |
| `CORE_API_KEY` | [core.ac.uk/api-keys/register](https://core.ac.uk/api-keys/register) | No (full-text from institutional repos) |
| `SCOPUS_API_KEY` | Elsevier API (institutional) | No (enables Scopus connector and improves Elsevier full-text enrichment paths) |
| `WOS_API_KEY` | [Clarivate developer portal](https://developer.clarivate.com) | No (Web of Science Starter API, 300 req/day free) |
| `EMBASE_API_KEY` | Elsevier institutional (apisupport@elsevier.com) | No (Embase connector) |

The free Gemini tier (Flash-Lite / Flash / Pro) is sufficient for most reviews. A full run typically costs under $5.

Web UI note: the browser setup form supports the most common connector keys. Some optional connectors (for example Embase and CORE retrieval) currently read credentials from the backend environment (`.env`) rather than per-run browser payload fields.

**Cost control tip:** Screening is usually the biggest cost driver. In default batch mode (`reviewer_batch_size: 10`), one dual-reviewer call can process multiple papers; in per-paper mode (`reviewer_batch_size: 0`), it calls the LLM once per paper. To cap costs on exploratory runs, set `max_llm_screen` in `config/settings.yaml`:

```yaml
screening:
  max_llm_screen: 200  # BM25-rank all candidates; send top 200 to LLM; exclude the rest
```

When `max_llm_screen` is set, all candidate papers are BM25-ranked by relevance to your research question. The top N go to LLM dual-review; the remainder are auto-excluded. These pre-filter exclusions are recorded as "Automation tools" in the PRISMA 2020 flow diagram and disclosed in the Methods section automatically.

Remove the line (or set it to `null`) to send all candidate papers through LLM screening.

---

## CLI Reference

```bash
# Start a new review
uv run python -m src.main run --config config/review.yaml

# Run with verbose output (shows each LLM call)
uv run python -m src.main run --config config/review.yaml --verbose
uv run python -m src.main run --config config/review.yaml --debug
uv run python -m src.main run --config config/review.yaml --offline
uv run python -m src.main run --config config/review.yaml --fresh
uv run python -m src.main run --config config/review.yaml --run-root runs/

# Resume after a crash or Ctrl+C (auto-detects first incomplete phase)
uv run python -m src.main resume --topic "your research question"
uv run python -m src.main resume --workflow-id wf-0007
uv run python -m src.main resume --workflow-id wf-0007 --no-api

# Resume from a specific phase (prior phases must have checkpoints)
uv run python -m src.main resume --workflow-id wf-0007 --from-phase phase_3_screening

# Export submission package
uv run python -m src.main export --workflow-id wf-0007

# Validate IEEE compliance and PRISMA checklist
uv run python -m src.main validate --workflow-id wf-0007

# Check run status and artifact paths
uv run python -m src.main status --workflow-id wf-0007

# Regenerate PROSPERO form from an existing workflow
uv run python -m src.main prospero --workflow-id wf-0007
```

**Tip:** Press Ctrl+C once during screening to proceed with already-screened papers. Press Ctrl+C twice to abort. Re-running with the same topic automatically prompts you to resume.

---

## Configuration

Two config files control behavior:

**`config/review.yaml`** -- change this for every new review:
- `research_question`, `pico`, `keywords`, `domain`
- `inclusion_criteria`, `exclusion_criteria`
- `date_range_start`, `date_range_end`
- `target_databases` (defaults come from `config/review.yaml`; add/remove connectors per review)
- `search_overrides` (per-database query overrides; AI config generation may populate a subset based on routing confidence and selected mode; omit a key to use the auto-generated fallback)
- `living_review: false` -- set to `true` + set `last_search_date` to re-run only from that date forward

**`config/settings.yaml`** -- change this rarely:
- LLM model assignments (which Gemini tier handles screening vs. writing)
- `agents.screening_reviewer_b.model` -- second reviewer model for cross-model validation
- Screening thresholds (include/exclude confidence cutoffs)
- `max_llm_screen` -- hard cap on LLM screening volume (cost control)
- `human_in_the_loop.enabled` -- pause after screening for manual review of AI decisions
- `gates.manuscript_contract_mode` -- contract enforcement (`observe` / `soft` / `strict`, default is `strict`)
- Quality gate thresholds
- Search depth (records per database)

Full documentation of every config field is in `spec.md` Section 4.

---

## How It Works

The pipeline runs as an 8-phase PydanticAI graph (with two enhancement sub-phases). Each phase writes results to SQLite immediately so a crash can resume from the first incomplete checkpoint.

```text
Phase 1: Foundation/startup (load config, initialize DB, set run artifacts and workflow state)
Phase 2: Search + deduplication + protocol generation
Phase 3: Screening (prefilters + optional batch prerank + dual-review + optional HITL gate)
Phase 4: Extraction + quality assessment (RoB/CASP/MMAT/GRADE routing)
Phase 4b: Embedding sub-phase (RAG chunking + vector persistence)
Phase 5: Synthesis (meta-analysis or narrative + sensitivity)
Phase 5b: Knowledge-graph sub-phase (communities + gap signals)
Phase 6: Writing via structured section IR (schema-constrained output -> completeness gates -> deterministic render) + manuscript assembly (`doc_manuscript.md`) + PRISMA/timeline/geographic figures
Finalize: final artifacts (`doc_manuscript.tex`, `references.bib`, `run_summary.json`)
Export (on demand): submission packaging (`submission/`, zip, docx/pdf when dependencies are available)
```

Every factual claim in the manuscript is traced back to a citation via the citation ledger. The LLM is given only the real extracted data -- it cannot hallucinate statistics.

---

## API Endpoints (Quick Reference)

Grouped endpoints most users use:

- Run lifecycle: `POST /api/run`, `POST /api/run-with-masterlist`, `POST /api/run-with-supplementary-csv`, `GET /api/stream/{run_id}`, `POST /api/cancel/{run_id}`
- History/resume: `GET /api/history`, `GET /api/history/active-run`, `GET /api/history/{workflow_id}/config`, `POST /api/history/attach`, `POST /api/history/resume`, `POST /api/history/{workflow_id}/archive`, `POST /api/history/{workflow_id}/restore`, `DELETE /api/history/{workflow_id}`
- Results/export: `GET /api/run/{run_id}/artifacts`, `GET /api/run/{run_id}/manuscript`, `POST /api/run/{run_id}/export`, `GET /api/run/{run_id}/submission.zip`, `GET /api/run/{run_id}/manuscript.docx`, `GET /api/run/{run_id}/prospero-form.docx`
- References/full text: `GET /api/run/{run_id}/papers-reference`, `GET /api/run/{run_id}/papers/{paper_id}/file`, `POST /api/run/{run_id}/fetch-pdfs`
- Human review/living review: `GET /api/run/{run_id}/screening-summary`, `POST /api/run/{run_id}/approve-screening`, `POST /api/run/{run_id}/living-refresh`
- Data explorer: `GET /api/db/{run_id}/papers-all`, `/screening`, `/costs`, `/tables`, `/rag-diagnostics`
- Validation: `GET /api/workflow/{workflow_id}/validation/summary`, `GET /api/workflow/{workflow_id}/validation/checks`
- Notes and logs: `PATCH /api/notes/{workflow_id}`, `GET /api/notes/stream`, `GET /api/logs/stream`

---

## Development

**Dev servers:**

The primary dev workflow uses [PM2](https://pm2.keymetrics.io/). Install it once:

```bash
npm install -g pm2
```

Then start both the FastAPI backend (port 8001) and Vite frontend (port 5173, HMR) with:

```bash
pm2 start ecosystem.config.js
```

Open `http://localhost:5173` (Vite dev UI, HMR) or `http://localhost:8001` (API direct). The `litreview-ui` PM2 process runs Vite on port 5173 and proxies `/api` to the backend on port 8001 automatically.

Useful PM2 commands:

```bash
pm2 logs                      # tail logs from all processes
pm2 logs litreview-api        # tail backend logs only
pm2 logs litreview-tunnel     # tail cloudflared tunnel logs
pm2 restart litreview-api     # restart backend (e.g. after adding a dependency)
pm2 restart litreview-ui      # restart frontend dev server
pm2 stop all                  # stop all processes
pm2 delete all                # remove all processes from PM2 registry
pm2 status                    # show process status table
```

**IMPORTANT -- restart after code changes:** Python loads modules into memory at startup. If you modify any `src/` file while the server is running, the running process continues using the old code. Always run `pm2 restart litreview-api` (or restart the uvicorn process) after making backend changes before starting a new review run. Failure to restart means your run will use the pre-change code even though the files on disk are updated. The `--reload` flag handles this automatically in the plain-terminal dev workflow above, but PM2 does not hot-reload by default.

**Production deploys -- rebuild the frontend:** When running in production (FastAPI serves `frontend/dist/` as static files on port 8001), a `pnpm build` is required after every frontend code change. The Vite dev server (port 5173) picks up changes automatically, but the production URL always serves the last built `dist/`. After rebuilding, restart the API process so it serves the new assets:

```bash
cd frontend && pnpm build && cd ..
pm2 restart litreview-api
```

**Alternative -- Overmind (requires tmux):**

```bash
brew install overmind   # macOS
overmind start          # reads Procfile.dev
```

**Alternative -- plain terminals:**

```bash
# Terminal 1
uv run uvicorn src.web.app:app --reload --port 8001

# Terminal 2
cd frontend && pnpm dev
```

**Run tests:**

```bash
uv run pytest tests/unit -q
uv run pytest tests/integration -q
# real-workflow replay validation (recommended before/after pipeline edits)
uv run python scripts/validate_workflow_replay.py --workflow-id wf-XXXX --profile quick
```

Real-workflow-first policy:
- For end-to-end and pipeline validation, use existing workflow IDs and their `runtime.db` records.
- Do not rely only on synthetic dummy fixtures for pipeline behavior checks.
- Replay validation writes append-only evidence to `validation_runs` and `validation_checks` in the same workflow DB.
- Quick workflow picker example:
  - `sqlite3 runs/workflows_registry.db "SELECT workflow_id, status, updated_at FROM workflows_registry ORDER BY updated_at DESC LIMIT 5;"`

**Lint and fix:**

```bash
uv run ruff check . --fix && uv run ruff format .
cd frontend && pnpm fix && pnpm typecheck
```

**Project layout:**

| Directory | What's in it |
|-----------|-------------|
| `src/models/` | Pydantic data contracts (every phase boundary) |
| `src/db/` | SQLite schema, typed repositories, workflow registry |
| `src/orchestration/` | PydanticAI Graph nodes, quality gates, resume logic |
| `src/search/` | Database connectors + deduplication + search strategy |
| `src/screening/` | Batch LLM pre-ranker, dual reviewer, Cohen's kappa, keyword pre-filter |
| `src/extraction/` | Study design classifier, data extractor |
| `src/quality/` | RoB 2, ROBINS-I, CASP, MMAT, GRADE |
| `src/synthesis/` | Feasibility checker, meta-analysis, narrative synthesis |
| `src/rag/` | RAG pipeline: chunker, embedder (PydanticAI), hybrid BM25+dense retriever (RRF), HyDE query expansion, Gemini listwise reranker |
| `src/knowledge_graph/` | Builder, community (Louvain), gap detector |
| `src/writing/` | Section writer, humanizer, deterministic guardrails, grounding |
| `src/citation/` | Citation ledger -- claim-to-evidence-to-BibTeX lineage |
| `src/export/` | IEEE LaTeX exporter, Word DOCX exporter, BibTeX builder, PRISMA validator |
| `src/visualization/` | Forest plot, funnel plot, RoB figure, timeline, geographic |
| `src/prisma/` | PRISMA 2020 flow diagram generator |
| `src/protocol/` | PROSPERO-format protocol generator |
| `src/web/` | FastAPI backend for the browser UI |
| `src/llm/` | Gemini client, PydanticAI agent factory, rate limiter |
| `src/config/` | Config loader (review.yaml + settings.yaml) |
| `src/utils/` | SSL context, structured logging, shared path helpers |
| `frontend/` | React + TypeScript web UI |

**Full architecture spec:** `spec.md`

**Utility scripts:**

| Script | Purpose |
|--------|---------|
| `scripts/validate_workflow_replay.py` | Runs quick/standard/deep replay validation directly on an existing workflow `runtime.db` and persists phase-level check results to `validation_runs` and `validation_checks`. |
| `scripts/finalize_manuscript.py` | Thin regeneration utility for `doc_manuscript.md`: re-assembles all sections (Declarations, GRADE tables, Study Characteristics Table, Search appendix, Figures, References) from an existing run's runtime.db. Strips unresolved citekeys and injects IMRaD headings for historical runs. Usage: `uv run python scripts/finalize_manuscript.py --run-dir runs/YYYY-MM-DD/wf-NNNN-<topic-slug>/run_<time>` |
| `scripts/migrate_to_runs.py` | One-time migration to move legacy run artifacts into the current `runs/YYYY-MM-DD/wf-NNNN-<topic-slug>/run_<time>/` directory structure. |
| `scripts/re_extract.py` | Targeted re-extraction for studies with low-quality data (placeholder outcomes, missing authors). Usage: `uv run python scripts/re_extract.py --run-dir runs/YYYY-MM-DD/wf-NNNN-<topic-slug>/run_<time>` |
| `scripts/benchmark.py` | Validate tool outputs against a gold-standard corpus: measures screening recall, extraction field accuracy, and RoB Cohen's kappa vs. published review. Usage: `uv run python scripts/benchmark.py --run-dir runs/YYYY-MM-DD/wf-NNNN-<topic-slug>/run_<time> --gold gold.json` |
| `scripts/test_fulltext_retrieval.py` | Test full-text retrieval for included papers from a workflow. Reports coverage across retrieval tiers/sources (publisher-direct, citation meta PDF, Unpaywall, arXiv, Semantic Scholar, CORE, Europe PMC, ScienceDirect, PMC, Crossref, landing-page fallback). Usage: `uv run python scripts/test_fulltext_retrieval.py --workflow-id wf-xxx` or `--run-dir runs/<path>` |
| `scripts/validate_scopus_key.py` | Validate SCOPUS_API_KEY against Elsevier API. Usage: `uv run python scripts/validate_scopus_key.py` |
| `scripts/show_run_info.py` | Print run metadata (status, included papers, cost) for a workflow ID without opening the browser. Usage: `uv run python scripts/show_run_info.py --workflow-id wf-xxx` |
| `scripts/build_benchmark.py` | Build or update the gold-standard benchmark from reference/ PDFs using the PDF vision LLM. Extracts structured quality dimensions and computes derived thresholds. Usage: `uv run python scripts/build_benchmark.py` or `--fetch-web` to pull additional published SRs. |
| `scripts/test_humanizer_pipeline.py` | Stage-wise validator for humanizer integrity. Runs deterministic guardrails (and optional LLM humanizer pass) and verifies citation blocks and numeric tokens are unchanged. Usage: `uv run python scripts/test_humanizer_pipeline.py --input-file sample.txt [--citation-catalog-file catalog.txt] [--run-llm]` |
| `scripts/test_search_connectors.py` | Live smoke-test for all configured search connectors. Loads API keys from .env and config from review.yaml, runs a real query per connector, and reports record counts and errors. Usage: `uv run python scripts/test_search_connectors.py` |
| `scripts/inject_missing_citations.py` | Post-hoc CLI: reads a completed run's section drafts, identifies uncited citekeys, patches the Results section with a design-grouped coverage paragraph, and regenerates the manuscript. Accepts `--workflow-id`. Uses LLM batch resolver as fallback for unmatched keys. Usage: `uv run python scripts/inject_missing_citations.py --workflow-id wf-xxx` |
| `scripts/test_openalex_quality.py` | Diagnostic: checks OpenAlex filter quality for a query (journal vs. preprint ratio, core vs. broad coverage). Usage: `uv run python scripts/test_openalex_quality.py` |
| `scripts/backfill_primary_study_status.py` | Backfills primary-study status in runtime DBs for historical runs. |
| `scripts/compare_primary_filter_delta.py` | Compares before/after impact of primary-study filtering changes. |
| `scripts/analyze_past_run_logs.py` | Summarizes historical run logs to find recurrent failures or bottlenecks. |
| `scripts/benchmark_config_generator.py` | Benchmarks AI config generation quality/consistency over prompt sets. |
| `scripts/benchmark_model_routing_promptfoo.py` | Promptfoo-style benchmark for model-routing decisions and prompt behavior. |

---

## Troubleshooting

**SSL errors (`CERTIFICATE_VERIFY_FAILED`):**
- macOS: run `Install Certificates.command` from your Python.app folder
- Corporate proxy: set `SSL_CERT_FILE` to your org CA bundle
- Dev only (insecure): `RESEARCH_AGENT_SSL_SKIP_VERIFY=1`

**Rate limit errors:** The tool respects Gemini free-tier limits automatically. If you hit them, wait a minute and resume.

**"No papers found":** Check `OPENALEX_API_KEY`, verify `target_databases` in `config/review.yaml`, and inspect `doc_search_strategies_appendix.md` for over-restrictive query overrides. Also check connector warnings in Activity logs (for example quota failures or low-recall warnings).

**PubMed returns far fewer papers than a previous run:** Check `doc_search_strategies_appendix.md` in the run directory to see the exact query used. Exact-phrase requirements in the `search_overrides.pubmed` AND group kill recall -- `"mindfulness-based stress reduction"[Title/Abstract]` (multi-word phrase) may return far fewer records than `"mindfulness"[Title/Abstract]` (single word). Use single-word or short root-form terms in the second AND group of the PubMed override. Also avoid MeSH terms that are too narrow or too broad for your specific topic -- verify coverage by checking PubMed directly.

---

## License

MIT
