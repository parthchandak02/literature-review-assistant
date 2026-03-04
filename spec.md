# LitReview -- Unified System Specification

**Version:** 1.0
**Date:** March 2026
**Owner:** Parth Chandak
**Purpose:** Single living recipe for building and maintaining the LitReview systematic review automation system. Covers architecture, technology decisions, data flow, phase design, and operating procedures. This document is the sole source of truth -- read it before writing any code.

---

## 1. Product Purpose and Strategic Context

### 1.1 What It Is

LitReview is a local-first AI agent that automates systematic literature reviews from a research question to an IEEE-submission-ready manuscript package. It runs entirely on the researcher's machine. No cloud service, no multi-tenancy, no account required.

The system has two interfaces that are fully independent:
- A CLI (`uv run python -m src.main`) for headless pipeline execution
- A local web dashboard (FastAPI + React) for interactive runs, live log streaming, and DB exploration

Adding or removing the frontend does not affect the backend pipeline.

### 1.2 Why It Exists

The primary goal is to publish 3-4 systematic review papers per year in IEEE journals (IEEE Access, IEEE CG&A, IEEE Transactions on Human-Machine Systems) to support an EB-1A extraordinary ability visa petition. Speed to first publication is the number-one priority.

The tool must produce manuscripts that pass peer review without requiring the user to manually execute any systematic review methodology step.

---

## 2. System Architecture

The system has three runtime layers and two persistent databases.

```
[Browser (React/Vite :5173 dev | FastAPI :8000 prod)]
    |  HTTP POST /api/run
    |  GET  /api/stream/{run_id}  (SSE)
    |  GET  /api/db/{run_id}/...
    v
[FastAPI -- src/web/app.py -- port 8000]
    |  asyncio.create_task(run_workflow())
    |  WebRunContext emits JSON events to asyncio.Queue + replay buffer
    v
[PydanticAI Graph -- src/orchestration/workflow.py]
    |  aiosqlite reads/writes (paper-level persistence at every step)
    v
[runs/{date}/{topic}/run_*/runtime.db]   <-- per-run SQLite
[runs/workflows_registry.db]             <-- central resume registry
    |
    v
[runs/{date}/{topic}/run_*/]             <-- fig_, doc_, data_ artifacts (same dir)
```

### 2.1 Workflow Graph

The pipeline is a directed acyclic graph implemented with PydanticAI's stable `BaseNode` subclass API. Each node corresponds to one build phase and returns the next node or `End`.

```
StartNode / ResumeStartNode
    |
    v
SearchNode          (phase_2_search)
    |
    v
ScreeningNode       (phase_3_screening)
    |
    v
ExtractionQualityNode  (phase_4_extraction_quality)
    |
    v
SynthesisNode       (phase_5_synthesis)
    |
    v
WritingNode         (phase_6_writing)
    |
    v
FinalizeNode        (finalize -- no checkpoint; writes run_summary.json)
```

`ResumeStartNode` reads the `checkpoints` table and routes directly to the first incomplete phase, enabling paper-level resume without reprocessing completed work.

### 2.2 Directory Layout

```
research-article-writer/
|-- pyproject.toml                  # uv-managed; Python 3.11+
|-- spec.md                         # THIS FILE -- single source of truth (replaces docs/research-agent-v2-spec.md + docs/frontend-spec.md)
|-- Procfile.dev                    # Overmind: api + ui processes
|-- bin/dev                         # ./bin/dev starts both processes
|-- config/
|   |-- review.yaml                 # Per-review research config (change every review)
|   `-- settings.yaml               # System behavior config (change rarely)
|-- frontend/                       # React/Vite/TypeScript web UI
|   |-- vite.config.ts              # @ alias, /api proxy to :8000
|   `-- src/
|       |-- App.tsx                 # Root: sidebar + lazy view router
|       |-- lib/api.ts              # All typed fetch wrappers + SSE types
|       |-- hooks/                  # useSSEStream, useCostStats, useBackendHealth
|       |-- components/             # Sidebar, LogStream, ResultsPanel
|       `-- views/                  # SetupView, RunView, ActivityView, CostView, DatabaseView, ResultsView, HistoryView, ScreeningReviewView
|-- src/
|   |-- main.py                     # CLI entry point (run, resume, export, validate, status)
|   |-- models/                     # ALL Pydantic data contracts
|   |-- db/                         # SQLite schema, connection manager, repositories, registry
|   |-- orchestration/              # workflow.py, context.py, state.py, resume.py, gates.py
|   |-- search/                     # base.py (SearchConnector protocol), 7 connectors, dedup, strategy, pdf_retrieval
|   |-- screening/                  # dual_screener, keyword_filter, prompts.py, reliability, gemini_client
|   |-- extraction/                 # extractor, study_classifier
|   |-- quality/                    # rob2, robins_i, casp, grade, study_router
|   |-- synthesis/                  # feasibility, meta_analysis, effect_size, narrative
|   |-- rag/                        # chunker, embedder (PydanticAI), hybrid retriever (BM25+dense RRF), hyde (HyDE query expansion), reranker (Gemini listwise)
|   |-- writing/                    # section_writer, humanizer, style_extractor, naturalness_scorer, prompts/ (dir), context_builder, orchestration
|   |-- citation/                   # ledger (claim -> evidence -> citation)
|   |-- protocol/                   # PROSPERO-format protocol generator
|   |-- prisma/                     # PRISMA 2020 flow diagram
|   |-- visualization/              # forest_plot, funnel_plot, rob_figure, timeline, geographic
|   |-- export/                     # ieee_latex, bibtex_builder, submission_packager, prisma_checklist, ieee_validator
|   |-- llm/                        # provider, gemini_client (shim), pydantic_client, base_client, rate_limiter
|   |-- web/                        # FastAPI app (25 endpoints, SSE, static serving)
|   `-- utils/                      # structured_log, logging_paths (RunPaths + create_run_paths), ssl_context
|-- tests/
|   |-- unit/                       # 20 unit test files (86 passing)
|   `-- integration/                # 7 integration test files
`-- runs/                           # All per-run artifacts + central registry (gitignored)
```

---

## 3. Technology Stack and Decisions

| Layer | Technology | Version | Why This, Not Something Else |
|-------|-----------|---------|------------------------------|
| Language | Python | 3.11+ | Type hints, async/await, mature ecosystem |
| Package manager | uv | latest | Fast; single tool for venv + install + run |
| Orchestration | PydanticAI Graph (BaseNode API) | latest | Built by Pydantic team; typed state, model-agnostic; avoids LangChain ecosystem weight; native Pydantic integration |
| LLM provider | Google Gemini 3.x (3 tiers) | 3.x | 1M token context window; cost-tiered by task volume; free tier sufficient for a single review run |
| Persistence | SQLite via aiosqlite | latest | Single-user local tool; zero deployment; trivially portable; paper-level write durability |
| CLI output | rich | 13+ | Progress bars, tables, status panels |
| Search (primary) | OpenAlex REST API | direct aiohttp | 250M+ works; CC0 licensed; free API key; api_key in URL required since Feb 2026 |
| Search (supplemental) | PubMed Entrez, arXiv, IEEE Xplore, Semantic Scholar, Crossref | various | Recall expansion per domain |
| Search (auxiliary) | Perplexity Search API | latest | Discovery only; tagged OTHER_SOURCE; not primary evidence |
| Meta-analysis | statsmodels combine_effects() | 0.14+ | Deterministic; peer-validated; forest plot built in; avoids custom statistical implementation |
| Effect sizes | scipy.stats + statsmodels | latest | Deterministic; LLMs are NEVER used for statistics |
| Screening ranking | bm25s | 0.2+ | BM25 relevance ranking for LLM screening cap; pure Python, scipy-based; faster than rank-bm25 |
| Author parsing | nameparser | 1.1+ | Surname extraction for display_label; handles "Last, First" and "First Last" formats |
| Title filtering | wordfreq | 3.0+ | Zipf frequency lookup for domain-agnostic title word filtering in display_label |
| Backend API | FastAPI + uvicorn | 0.129+ / 0.40+ | Async; Pydantic-native; SSE via sse-starlette |
| Frontend | React + TypeScript | 19 / 5 | Strict typing; no `any` at API boundaries |
| Build tool | Vite + pnpm | 7 / 10 | Fast HMR in dev; chunk splitting in prod |
| UI components | shadcn/ui + Tailwind CSS | latest / 4 | Copy-owned Radix-based components; utility classes only; no CSS-in-JS |
| Charts | Recharts | latest | Cost bar charts in CostView |
| SSE client | @microsoft/fetch-event-source | latest | Robust SSE with abort controller support |
| Process manager | PM2 | latest | Primary: runs litreview-api + litreview-ui via ecosystem.config.js; Overmind (tmux) is available as alternative via Procfile.dev |

### 3.1 Absolute Rules

These rules apply to every line of code in this project. They are not suggestions.

1. **NO LLM-computed statistics.** Meta-analysis, effect sizes, and heterogeneity stats use scipy/statsmodels deterministic functions only.
2. **NO untyped dictionaries at phase boundaries.** Every function crossing a module boundary accepts and returns Pydantic models from `src/models/`. Internal helpers within a module may use dicts.
3. **ALL I/O is async.** aiosqlite for database, aiohttp for HTTP, asyncio.Semaphore for concurrency control.
4. **ALL LLM calls are logged** with model, tokens in, tokens out, cost USD, and latency ms to the `cost_records` table immediately after each call.
5. **Paper-level persistence.** Write each individual screening decision, extraction record, and quality assessment to SQLite immediately after processing. Never batch writes at phase end. Every processing loop checks for already-processed IDs before starting.
6. **Build in exact phase order.** Do not implement Phase N+1 code before Phase N is approved.
7. **Use `rich`** for all CLI output -- progress bars with completed/total count for long-running phases.
8. **Use exact checkpoint phase key strings** from Section 8.3. Mismatched strings cause silent resume failures.
9. **No Unicode characters** in any file. ASCII 32-126 only. Use YES/NO/PASS/FAIL instead of checkmarks, -> instead of arrows.
10. **Never commit** `.env`, `runs/**`, or other run-specific generated artifacts.

---

## 4. Configuration System

Three-layer configuration following the twelve-factor app principle. Secrets live in `.env`. Per-review research parameters live in `review.yaml`. System behavior parameters live in `settings.yaml`. Infrastructure constants (connector rate limits, API retry counts) live in Python code.

### 4.1 `.env` -- Secrets

Never committed to git. Loaded via python-dotenv at startup before any config access.

```
GEMINI_API_KEY=...              # Required
OPENALEX_API_KEY=...            # Required since Feb 2026 (free at openalex.org)
IEEE_API_KEY=...                # Optional; for IEEE Xplore connector
PUBMED_EMAIL=...                # Required for PubMed Entrez (Biopython)
PUBMED_API_KEY=...              # Optional; raises PubMed rate limit from 3 to 10 req/sec
PERPLEXITY_SEARCH_API_KEY=...   # Optional; for auxiliary discovery connector
SEMANTIC_SCHOLAR_API_KEY=...    # Optional; improves rate limits for Semantic Scholar
PORT=8001                       # Optional; backend port (default 8001 in dev, 8002 in prod)
UI_PORT=5173                    # Optional; Vite dev server port (dev only)
```

The web UI never stores API keys server-side. The user pastes keys into the Setup form; they are posted in the request body to the local FastAPI process. The browser caches them in `localStorage` under `litreview_api_keys` for convenience between sessions.

### 4.2 `config/review.yaml` -- Per-Review Config

Edit this file for each new review. All other files stay the same.

| Field | What It Controls |
|-------|-----------------|
| `research_question` | The driving question; becomes the workflow topic key in the registry |
| `review_type` | systematic / scoping / narrative |
| `pico.*` | population, intervention, comparison, outcome -- injected verbatim into screening prompts |
| `keywords` | Intervention keyword list -- used by the keyword pre-filter and BM25 ranker |
| `inclusion_criteria` | List of criteria strings -- passed to Reviewer A prompt |
| `exclusion_criteria` | List of criteria strings -- passed to Reviewer B prompt |
| `target_databases` | Which connectors to activate for this review |
| `date_range_start` / `date_range_end` | Year bounds applied by all connectors |
| `search_overrides` | Optional per-database Boolean query override; omit a key to use auto-generated |
| `protocol.*` | PROSPERO registration info (PRISMA 2020 requirement) |
| `funding.*` / `conflicts_of_interest` | Disclosure fields for manuscript |
| `domain` | Subject domain string injected into LLM prompts for context |
| `scope` | Scope description string injected into LLM prompts |
| `target_sections` | Optional list of section names to generate (defaults to all 6) |

### 4.3 `config/settings.yaml` -- System Behavior Config

Change rarely. Values are tuned from real runs.

| Section | Key Fields |
|---------|-----------|
| `llm.*` | `flash_rpm`, `flash_lite_rpm`, `pro_rpm` -- free-tier rate limits enforced by rate limiter |
| `agents.*` | Per-agent model string (e.g. `google-gla:gemini-2.5-flash-lite`) and temperature. Changing a model requires only a YAML edit. |
| `screening.*` | `stage1_include_threshold` (0.85), `stage1_exclude_threshold` (0.80), `screening_concurrency` (asyncio.Semaphore), `max_llm_screen` (optional BM25 cap), `skip_fulltext_if_no_pdf` |
| `dual_review.*` | `enabled`, `kappa_warning_threshold` (0.4) |
| `gates.*` | `profile` (strict / warning), `search_volume_minimum` (50), `screening_minimum` (5), `extraction_completeness_threshold` (0.80), `cost_budget_max` (USD) |
| `writing.*` | `style_extraction`, `humanization`, `humanization_iterations` (2), `naturalness_threshold` (0.75), `checkpoint_per_section`, `llm_timeout` (120s) |
| `risk_of_bias.*` | `rct_tool` (rob2), `non_randomized_tool` (robins_i), `qualitative_tool` (casp) |
| `meta_analysis.*` | `enabled`, `heterogeneity_threshold` (50 = I-squared cutoff for fixed vs random effects), `funnel_plot_minimum_studies` (10), effect measures |
| `ieee_export.*` | `template` (IEEEtran), `max_abstract_words` (250), `target_page_range` ([7, 10]) |
| `citation_lineage.*` | `block_export_on_unresolved` (true), `minimum_evidence_score` (0.5) |
| `search.*` | `max_results_per_db` (global default: 500), `per_database_limits` (per-connector overrides), `citation_chasing_enabled` (false -- PRISMA 2020 snowball forward citation chasing) |
| `extraction.*` | `core_full_text`, `europepmc_full_text`, `semanticscholar_full_text` (toggles for full-text tiers), `sciencedirect_full_text`, `unpaywall_full_text`, `pmc_full_text`, `use_pdf_vision`, `full_text_min_chars` |
| `rag.*` | `embed_model` (gemini-embedding-001), `embed_dim` (768 -- MRL dimension, changing requires re-embedding), `embed_batch_size` (20), `chunk_max_words` (400), `chunk_overlap_sentences` (2), `use_hyde` (true -- HyDE query expansion before dense embed), `hyde_model` (gemini-3.1-flash-lite-preview), `rerank` (true -- Gemini listwise reranking), `reranker_model` (gemini-3.1-flash-lite-preview) |

Both YAML files are validated into Pydantic models at startup via `src/config/loader.py`. Invalid config fails fast with a clear error message.

---

## 5. Data Contracts

All phase boundaries use Pydantic models from `src/models/`. The contract layer is the only mechanism that allows phases to be tested, replaced, or resumed in isolation.

### 5.1 Phase Boundary Model Map

| Crossing | Input | Output |
|---------|-------|--------|
| CLI / API -> workflow | `ReviewConfig` + `SettingsConfig` | `ReviewState` |
| Search -> Screening | `CandidatePaper` list (via `SearchResult`) | filtered `CandidatePaper` list |
| Screening -> Extraction | `CandidatePaper` list (included papers) | `DualScreeningResult` per paper |
| Extraction -> Quality | `CandidatePaper` + `ExtractionRecord` | `RoB2Assessment` / `RobinsIAssessment` / `GRADEOutcomeAssessment` |
| Quality -> Synthesis | `ExtractionRecord` list + assessments | `MetaAnalysisResult` list or `NarrativeSynthesis` |
| Synthesis -> Writing | synthesis results + `PRISMACounts` | `SectionDraft` per section |
| Writing -> Export | `SectionDraft` list + `CitationEntryRecord` list | IEEE LaTeX package |
| Any phase -> Gate | phase output values | `GateResult` |

### 5.2 Model Families (src/models/)

| File | Key Models |
|------|-----------|
| `papers.py` | `CandidatePaper`, `SearchResult`, `compute_display_label()` |
| `screening.py` | `ScreeningDecision` (single reviewer), `DualScreeningResult` (both + adjudication) |
| `extraction.py` | `ExtractionRecord` -- study design, participants, intervention, outcomes, effect sizes, source spans |
| `quality.py` | `RoB2Assessment` (5 domains), `RobinsIAssessment` (7 domains), `GRADEOutcomeAssessment` (8 factors) |
| `claims.py` | `ClaimRecord`, `EvidenceLinkRecord`, `CitationEntryRecord` -- 3-tier citation lineage chain |
| `writing.py` | `SectionDraft` -- versioned section with claim and citation ID lists |
| `workflow.py` | `GateResult`, `DecisionLogEntry` |
| `additional.py` | `InterRaterReliability`, `MetaAnalysisResult`, `PRISMACounts`, `ProtocolDocument`, `SummaryOfFindingsRow`, `CostRecord` |
| `config.py` | `ReviewConfig`, `SettingsConfig`, and all sub-configs |
| `enums.py` | All shared enums: `ReviewType`, `ScreeningDecisionType`, `ReviewerType`, `RiskOfBiasJudgment`, `RobinsIJudgment`, `GateStatus`, `ExclusionReason`, `GRADECertainty`, `StudyDesign`, `SourceCategory` |

### 5.3 Phase-Internal Models

These models cross internal function boundaries within a single module but do NOT cross module boundaries. They are defined in their home module, not in `src/models/`, to avoid circular imports.

| Model | Lives In |
|-------|---------|
| `SynthesisFeasibility`, `NarrativeSynthesis` | `src/synthesis/` |
| `StylePatterns`, `StudySummary`, `WritingGroundingData` | `src/writing/` |
| `AgentRuntimeConfig` | `src/llm/provider.py` |

### 5.4 display_label

`CandidatePaper.display_label` is computed once on first DB save via `compute_display_label()` in `src/models/papers.py` and stored in the `papers.display_label` column. All downstream code (RoB figure, BibTeX citekey generation, visualizations) reads this field. Never re-derive it with local heuristics. Priority chain: author surname + year -> first meaningful title word + year -> first 22 chars of title -> `Paper_{paper_id[:6]}`.

Implementation uses two libraries: `nameparser.HumanName(authors[0]).last` for author surname extraction (handles "Last, First" and "First Last" formats robustly), and `wordfreq.zipf_frequency(word, "en")` with a threshold of 3.5 to skip common filler words in title extraction -- replacing the previous ~60-entry hardcoded domain word list with a language-frequency-based filter that requires no topic-specific knowledge.

---

## 6. Pipeline Phases

Eight build phases in strict dependency order. Each phase writes a completion marker to the `checkpoints` table (except FinalizeNode, which uses `run_summary.json`). The canonical phase key strings are fixed -- any mismatch silently breaks resume.

```
Phase 1: Foundation        -> no checkpoint (workflow row serves as marker)
Phase 2: Search            -> checkpoint key: "phase_2_search"
Phase 3: Screening         -> checkpoint key: "phase_3_screening"
Phase 4: Extraction+Quality -> checkpoint key: "phase_4_extraction_quality"
Phase 5: Synthesis         -> checkpoint key: "phase_5_synthesis"
Phase 6: Writing           -> checkpoint key: "phase_6_writing"
Finalize                   -> writes run_summary.json + registry status = "completed"
```

### 6.1 Phase 1: Foundation

**What to build:** All Pydantic models in `src/models/`. SQLite database layer (`src/db/`): connection manager with WAL journal mode + NORMAL sync + FK enforcement + 40MB cache + temp in memory. Typed CRUD repositories for every table. Six quality gates. Decision log. Citation ledger. LLM provider with 3-tier model assignment, token-bucket rate limiter, and cost logging. Review config loader.

**Quality gates defined here:**

| Gate | Passes When |
|------|------------|
| `search_volume` | Total deduplicated records >= 50 |
| `screening_safeguard` | Papers passing full-text screening >= 5 |
| `extraction_completeness` | >= 80% fields filled AND < 35% papers with empty core fields |
| `citation_lineage` | Zero unresolved claims at export |
| `cost_budget` | Cumulative LLM cost < `settings.gates.cost_budget_max` |
| `resume_integrity` | All checkpoint data valid on resume |

### 6.2 Phase 2: Search

**What happens:** Connectors run concurrently via asyncio. Each builds a query from `ReviewConfig` (or uses `search_overrides`). Results map to `CandidatePaper` objects. Two-stage deduplication: exact DOI match, then fuzzy title match (thefuzz >= 90% similarity). Per-database counts are recorded for the PRISMA diagram. A PROSPERO-format protocol document is generated.

**Default connectors (active unless overridden by target_databases):**

| Connector | Protocol | Source Category |
|-----------|---------|----------------|
| Scopus | Elsevier Scopus Search API, TITLE-ABS-KEY field codes | DATABASE |
| Web of Science | Clarivate WoS Starter API, TS= prefix syntax | DATABASE |
| OpenAlex | Direct aiohttp REST, api_key in URL, relevance search | DATABASE |
| PubMed | Biopython Entrez, MeSH + field codes | DATABASE |
| Semantic Scholar | Academic Graph API, keyword search | DATABASE |

**Opt-in connectors (add to target_databases in review.yaml to enable):**

| Connector | Protocol | Source Category |
|-----------|---------|----------------|
| IEEE Xplore | Direct REST with API key | DATABASE |
| ClinicalTrials.gov | CT.gov v2 API, query.term | OTHER_SOURCE |
| arXiv | arxiv Python library | DATABASE |
| Crossref | Works API, polite email | DATABASE |
| Perplexity | Perplexity Search API, cap 20 | OTHER_SOURCE |
| Web of Science | Clarivate WoS Starter API (X-ApiKey header, 300 req/day free tier, 50 records/page) | DATABASE |

Perplexity and ClinicalTrials items tagged `SourceCategory.OTHER_SOURCE` count toward the PRISMA right-hand column (other sources). URL-based source inference (`_infer_source_from_url()`) attributes Perplexity-discovered papers to academic databases when they link to PubMed, arXiv, etc.

**Query generation:** `src/search/strategy.py` `build_database_query()` applies database-specific query syntax. Scopus uses TITLE-ABS-KEY field codes; WoS uses TS= prefix groups; PubMed uses MeSH + [Title/Abstract] field codes; OpenAlex and Semantic Scholar use a short relevance-search phrase (5-10 keywords) because their APIs are relevance-ranked, not boolean-filter. A `search_overrides` key in `review.yaml` takes precedence for any database. The AI config generator (`src/web/config_generator.py`) generates database-specific overrides for all six primary databases (including openalex) in a single two-stage Gemini pipeline.

**Gate:** `search_volume` -- fails if deduplicated records < 50.

**Outputs:** `CandidatePaper` list in `ReviewState`, per-database counts in `PRISMACounts`, `doc_search_strategies_appendix.md`, `doc_protocol.md`.

### 6.3 Phase 3: Screening

**What happens:** Papers pass through a two-stage funnel.

Stage 0 (pre-filter): The keyword filter auto-excludes papers with zero intervention keyword matches before any LLM call (`ExclusionReason.KEYWORD_FILTER`). If `max_llm_screen` is set, BM25 (bm25s library) ranks remaining candidates by topic relevance; papers below the cap receive `LOW_RELEVANCE_SCORE` exclusions written to the DB without LLM calls. This cuts LLM costs by up to 80%.

Stage 1 (title/abstract): Two independent AI reviewers process each paper concurrently via `asyncio.Semaphore`. Reviewer A uses an inclusion-emphasis prompt (temperature 0.1). Reviewer B uses an exclusion-emphasis prompt (temperature 0.3). Both use Gemini Flash-Lite. Agreement yields the final decision. Disagreement triggers Adjudicator (Gemini Pro) that sees both decisions.

Stage 2 (full-text): Papers passing Stage 1 get full text via a unified resolver (Unpaywall, Semantic Scholar, CORE, Europe PMC, ScienceDirect, PMC). Papers without retrievable full text are excluded with `NO_FULL_TEXT` when `skip_fulltext_if_no_pdf` is true. Full-text screening follows the same dual-reviewer pattern.

**Ctrl+C behavior:** First Ctrl+C sets proceed-with-partial flag; the screening loop exits after the current paper and saves a checkpoint with `status='partial'`. Second Ctrl+C raises `KeyboardInterrupt` (hard abort). The SIGINT handler is registered via `asyncio.add_signal_handler` (skipped on Windows where it is not supported).

**Inter-rater reliability:** Cohen's kappa computed via `sklearn.metrics.cohen_kappa_score`. A kappa below `kappa_warning_threshold` (0.4) triggers a warning. The target kappa for Definition of Done is >= 0.6.

**Confidence fast-path:** If both reviewers agree with confidence above the auto-include or auto-exclude threshold, adjudication is skipped. Papers with confidence between thresholds always go to adjudication.

**Gate:** `screening_safeguard` -- fails if fewer than 5 papers pass full-text screening.

**Outputs:** `DualScreeningResult` per paper, `InterRaterReliability`, `doc_disagreements_report.md`, `doc_fulltext_retrieval_coverage.md`.

### 6.4 Phase 4: Extraction and Quality Assessment

**What happens:** For each included paper, full text is fetched via a 6-tier resolver (Unpaywall, Semantic Scholar, CORE, Europe PMC, ScienceDirect, PMC) before extraction. The study design classifier (Gemini Pro, confidence threshold 0.70) routes the paper to the correct risk-of-bias tool. Classifiers with confidence < 0.70 fall back to `StudyDesign.NON_RANDOMIZED`. Every classification decision is written to the decision log with confidence, threshold, and rationale.

Structured extraction (Gemini Pro) populates `ExtractionRecord` fields including `outcomes[].effect_size` and `outcomes[].se` for downstream statistical pooling. Heuristic fallback activates on API error.

Risk-of-bias assessment runs async (Gemini Pro with typed JSON schema output):

| Study Type | Tool | Domains | Scale |
|-----------|------|---------|-------|
| RCT | RoB 2 | 5 Cochrane domains | Low / Some concerns / High |
| Non-randomized | ROBINS-I | 7 domains | Low / Moderate / Serious / Critical / No Information |
| Qualitative | CASP | Design-specific checklist | Pass / Fail / Can't tell |

RoB 2 overall judgment algorithm: all Low -> Low; any High -> High; otherwise -> Some Concerns. NEVER a single summary score.

GRADE certainty is assessed per outcome across 5 downgrading factors (risk of bias, inconsistency, indirectness, imprecision, publication bias) and 3 upgrading factors (large effect magnitude, dose-response gradient, residual confounding). Starting certainty: High for RCTs, Low for observational.

A risk-of-bias traffic-light figure (matplotlib) shows rows = studies, columns = domains, cells = colored by judgment. The figure reads `display_label` from the DB for study labels.

**Gate:** `extraction_completeness` -- fails if >= 35% of papers have empty core fields or < 80% of required fields filled.

**Outputs:** `ExtractionRecord` per paper, `RoB2Assessment` / `RobinsIAssessment` per paper, `GRADEOutcomeAssessment` per outcome, `fig_rob_traffic_light.png`.

### 6.5 Phase 5: Synthesis

**What happens:** A feasibility checker determines whether quantitative pooling is possible based on clinical and methodological similarity. Generic groupings (`primary_outcome`, `secondary_outcome`) are treated as NOT feasible even if the feasibility verdict is true.

If feasible:
- Effect sizes computed via statsmodels (`effectsize_smd` for continuous, `effectsize_2proportions` for dichotomous) and scipy -- never by LLM
- Results pooled via `statsmodels.stats.meta_analysis.combine_effects()`
- Fixed-effect model when I-squared < 50%; random-effects (DerSimonian-Laird) when I-squared >= 50%
- Forest plot generated per outcome using statsmodels `.plot_forest()`
- Funnel plot (matplotlib scatter: x = effect size, y = standard error inverted) generated when >= 10 studies

If not feasible: structured narrative synthesis produced with effect direction tables and per-study summary rows.

Synthesis results (`SynthesisFeasibility` + `NarrativeSynthesis`) are persisted to the `synthesis_results` table. The writing node loads these first and falls back to `data_narrative_synthesis.json` for older runs.

**Outputs:** `MetaAnalysisResult` per outcome (or `NarrativeSynthesis`), `fig_forest_plot.png`, `fig_funnel_plot.png`, `data_narrative_synthesis.json`.

### 6.6 Phase 6: Writing

**What happens:** Before writing begins, a style extractor (Gemini Pro) analyzes included papers (up to 50,000 chars per paper) to extract sentence openings, domain vocabulary, citation integration patterns, and transition phrases. These patterns are injected into every section prompt.

**RAG retrieval (runs before each section):** A three-stage pipeline surfaces the most relevant evidence chunks from embedded paper content. (1) HyDE (`src/rag/hyde.py`) generates a 100-200 word hypothetical excerpt of the section using Gemini Flash -- producing a richer dense query vector than the bare section name. (2) The hypothetical text is embedded for cosine retrieval; BM25 uses the original research question + section name without the hypothetical, to avoid hallucinated keyword drift. Reciprocal Rank Fusion combines both signals into a top-20 candidate set. (3) A Gemini Flash listwise reranker (`src/rag/reranker.py`) scores all 20 candidates in a single LLM call and returns the top-8 chunks, which are injected as `rag_context` into the writing prompt. The abstract skips HyDE (already synthesis-grounded). Any retrieval failure falls back silently -- the section is written without RAG context. RAG is controlled by `settings.yaml rag.*` (`use_hyde`, `rerank`, and their model keys).

A `WritingGroundingData` object is built from PRISMA counts, extraction records, and synthesis results. This block of factual data -- search metadata, PRISMA counts, study characteristics, synthesis direction, per-study summaries, and valid citekeys -- is injected verbatim into every writing prompt. The LLM is instructed to use these numbers exactly and never invent statistics.

A section writer (Gemini Pro) generates each of six manuscript sections. All section prompts enforce:
- Prohibited AI-tell phrases (e.g. "Of course", "As an expert", "Certainly")
- Citation catalog constraint: LLM may only use citekeys from the provided catalog; hallucinated citations are forbidden
- Style patterns from included papers
- Study-count-adapted language (singular vs plural)

After each section, a naturalness scorer (Gemini Pro, 3,000 chars input) rates the output 0-1. If below `naturalness_threshold` (0.75), the humanizer (Gemini Pro, 4,000 chars input) runs up to `humanization_iterations` refinement passes.

The citation ledger validates after each section: every in-text citekey must resolve to a `CitationEntryRecord`. Zero unresolved citations is required before export.

Each completed section is saved to the `section_drafts` table immediately. On resume after a crash, the writing node loads completed sections from the DB and skips them.

**Zero-papers guard:** When 0 papers are included (e.g. gates.profile=warning allows continuation past screening_safeguard), WritingNode produces a minimal manuscript without LLM calls via `_build_minimal_sections_for_zero_papers()`. No style extraction, HyDE, or section-writing LLM calls run.

**Gate:** `citation_lineage` -- blocks export if `block_export_on_unresolved` is true and any claim has an unresolved citation.

**Outputs:** `SectionDraft` per section (6 total), `doc_manuscript.md`.

### 6.7 Phase 7: PRISMA and Visualizations (Part of FinalizeNode)

**What happens:** PRISMA 2020 flow diagram rendered using the `prisma-flow-diagram` library (`plot_prisma2020_new`) with a matplotlib fallback on ImportError. Two-column structure: databases left, other sources right. Per-database counts in the identification box. Exclusion reasons categorized from `ExclusionReason` enum. Arithmetic validation runs (records in = records out at every stage).

Known v1 limitation: The "other sources" right-hand column is currently disabled in `render_prisma_diagram()` because all papers pass through a single unified screening pipeline. Restoring the two-column split requires a deduplication-aware PRISMA count builder that can separate already-screened other-source papers.

Publication timeline and geographic distribution figures are also generated here.

**Outputs:** `fig_prisma_flow.png`, `fig_publication_timeline.png`, `fig_geographic_distribution.png`.

### 6.8 Phase 8: Export (Part of FinalizeNode)

**What happens:** IEEE LaTeX exporter converts the manuscript to IEEEtran.cls format with numbered `\cite{citekey}` references, `booktabs` tables, and `\includegraphics` figures. BibTeX file generated from the citation ledger. A submission package is assembled:

```
submission/
|-- manuscript.tex
|-- manuscript.pdf
|-- manuscript.docx
|-- references.bib
|-- figures/
`-- supplementary/
    |-- search_strategies_appendix.pdf  (stub in v1)
    |-- prisma_checklist.pdf            (stub in v1)
    |-- extracted_data.csv
    `-- screening_decisions.csv
```

Validators run:
- IEEE validator: abstract 150-250 words, references 30-80, all `\cite{}` resolve in `.bib`, no placeholder text
- PRISMA checklist validator: 27 items, gate requires >= 24/27 reported

Registry status updated to "completed". `run_summary.json` written to log dir with all artifact paths.

**Outputs:** Full `submission/` directory, `run_summary.json`.

---

## 7. LLM Integration

### 7.1 Three-Tier Model Selection

| Tier | Model | Input / Output per 1M tokens | Agent Assignments |
|------|-------|------------------------------|-------------------|
| Bulk | gemini-3.1-flash-lite-preview | $0.25 / $1.50 | screening_reviewer_a, search, study_type_detection, abstract_generation, hyde generation, rag reranker |
| Fast | gemini-3-flash-preview | lower cost | screening_reviewer_b |
| Quality | gemini-3.1-pro-preview | $1.25 / $10.00 | screening_adjudicator, extraction, quality_assessment, writing, humanizer, style_extraction |

Reviewer A (gemini-3.1-flash-lite-preview) and Reviewer B (gemini-3-flash-preview) use different models intentionally -- this provides genuine cross-model validation rather than intra-model temperature variation. Flash-Lite-Preview is optimal for bulk classification at scale; gemini-3-flash-preview provides a different model perspective for Reviewer B without the cost of Pro. HyDE generation and listwise reranking also use flash-lite-preview for speed and cost efficiency.

Model assignments per agent are in `settings.yaml` under `agents.*`. Changing a model requires only a YAML edit -- no code changes.

### 7.2 Rate Limiting

A token-bucket rate limiter in `src/llm/rate_limiter.py` enforces free-tier Gemini limits:
- Flash-Lite: 15 RPM
- Flash: 10 RPM
- Pro: 5 RPM

`reserve_call_slot(agent_name)` blocks until a slot is available. A `rate_limit_wait` SSE event is emitted whenever the limiter pauses. These limits can be relaxed in `settings.yaml` for paid-tier keys (paid Flash: 2,000 RPM).

### 7.3 Cost Tracking

Every LLM call records a `CostRecord` to the `cost_records` table immediately after the call completes. The `cost_budget` gate queries the cumulative total at the end of each phase. The web UI `CostView` reads cost data from the `cost_records` table via `GET /api/db/{run_id}/costs` (DB polling every 5s for active runs), which is the complete and authoritative source across all phases. SSE `api_call` events are used as a last-resort fallback only if the DB has not yet responded. The `useCostStats` hook aggregates SSE events for the sidebar badge display only.

### 7.4 GeminiClient (Shared)

`src/llm/gemini_client.py` provides a shared `GeminiClient` with:
- Exponential-backoff retry on HTTP 429/502/503/504 (max 5 retries)
- Typed JSON schema mode (`response_schema`) for structured outputs
- 120-second timeout per call (configurable via `settings.yaml` `writing.llm_timeout`)

Used by: extraction, quality assessment, writing, humanizer, style extractor, naturalness scorer. Screening has its own `GeminiScreeningClient` due to different batching and concurrency requirements.

### 7.5 Screening Prompts Design

Every screening prompt opens with a context block: role, goal, topic, research question, domain, and keywords. Structured JSON output is enforced at the end of every prompt. Truncation limits: title/abstract (full content, no truncation), full-text (first 8,000 chars), extraction (first 10,000 chars).

Reviewer A prompt emphasizes inclusion: "Include this paper if ANY inclusion criterion is plausibly met." Reviewer B prompt emphasizes exclusion: "Exclude this paper if ANY exclusion criterion clearly applies." The adjudicator sees both decisions and reasons before making a final call.

---

## 8. Persistence and Resume

### 8.1 SQLite Schema (19 Tables)

Each run creates its own `runtime.db`. Schema defined in `src/db/schema.sql`.

| Table | Purpose |
|-------|---------|
| `papers` | All candidate papers with display_label |
| `search_results` | Per-database search metadata (dates, queries, counts) |
| `screening_decisions` | Every individual reviewer decision (paper-level persistence) |
| `dual_screening_results` | Aggregated dual-reviewer final decisions |
| `extraction_records` | Full ExtractionRecord JSON per paper |
| `claims` | Atomic factual claims from manuscript sections |
| `citations` | Bibliographic references (citekey unique) |
| `evidence_links` | Claim -> citation mappings with evidence span and score |
| `rob_assessments` | RoB 2 / ROBINS-I / CASP assessment JSON per paper |
| `grade_assessments` | GRADEOutcomeAssessment JSON per outcome |
| `section_drafts` | Versioned manuscript sections (unique per workflow+section+version) |
| `gate_results` | Quality gate outcomes per phase |
| `decision_log` | Append-only audit trail for all decisions |
| `cost_records` | LLM call cost tracking (model, tokens, USD, latency, phase) |
| `workflows` | Per-run metadata (topic, config_hash, status, dedup_count) |
| `checkpoints` | Phase completion markers (key: phase string, status: completed / partial) |
| `synthesis_results` | SynthesisFeasibility + NarrativeSynthesis JSON per outcome |
| `event_log` | Persisted SSE event log for replay; loaded by history/attach endpoint |
| `paper_chunks_meta` | RAG chunk store: chunk_id, paper_id, chunk_index, content (text), embedding (JSON float array, 768-dim); indexed by workflow_id and paper_id |

SQLite connection settings: WAL journal mode (concurrent reads + single writer), NORMAL synchronous (~2-3x faster writes), foreign keys ON (SQLite does NOT enforce FKs by default), 40MB cache, temp tables in memory. On open, `repair_foreign_key_integrity()` inserts stub papers for orphaned paper_id refs (e.g. from migration) to avoid FOREIGN KEY constraint failures.

All per-run file paths (runtime.db, app log, run_summary.json, output documents, figures) are resolved via `create_run_paths(run_root, workflow_description)` in `src/utils/logging_paths.py`, which returns a frozen `RunPaths` dataclass. Every log and output artifact lives under a single `run_dir` -- there is no separate log directory or output directory.

### 8.2 Central Registry

`{run_root}/workflows_registry.db` holds a single `workflows_registry` table:

```
workflow_id | topic | config_hash | db_path | status | created_at | updated_at
```

This maps (topic, config_hash) to the absolute path of the per-run `runtime.db`, enabling resume without filesystem scanning. The per-run `workflows` table still exists in `runtime.db` for local workflow metadata.

### 8.3 Canonical Phase Key Strings

These strings MUST be identical in `src/orchestration/resume.py` (`PHASE_ORDER` list) and in every `save_checkpoint()` call in `workflow.py`. Any mismatch causes silent resume failures.

```
PHASE_ORDER = [
    "phase_2_search",
    "phase_3_screening",
    "phase_4_extraction_quality",
    "phase_5_synthesis",
    "phase_6_writing",
    "finalize",
]
```

Phase 1 (Foundation) has no checkpoint -- the existence of the `workflows` row serves as the completion marker.

### 8.4 Resume Flow

```
resume --topic "my question"
    |
    v
Query workflows_registry.db for matching topic + config_hash
    |
    v
Open runtime.db at registry db_path
    |
    v
load_resume_state() reads checkpoints table
    |
    v
ResumeStartNode -> routes to first phase NOT in completed checkpoints
    |
    v
Within that phase: query per-paper table for already-processed IDs
    |
    v
Skip processed papers -> process remaining -> write to SQLite immediately
```

Topic-based auto-resume: if `run` is called and a workflow already exists for the same `config_hash`, the CLI prompts: "Found existing run for this topic (phase N/8 complete). Resume? [Y/n]".

Fallback for old runs: if the registry is missing, `resume --workflow-id` scans `run_summary.json` files under the run root to locate the runtime.db.

### 8.5 run_summary.json

`FinalizeNode` writes this to `{log_dir}/run_summary.json`. The `status`, `validate`, `export`, and web UI `artifacts` endpoint all read this file to locate output artifact paths. Fixed artifact keys used by all downstream consumers:

```
artifacts:
  prisma_flow -> fig_prisma_flow.png
  rob_traffic_light -> fig_rob_traffic_light.png
  timeline -> fig_publication_timeline.png
  geographic -> fig_geographic_distribution.png
  manuscript -> doc_manuscript.md
  narrative_synthesis -> data_narrative_synthesis.json
  run_summary -> run_summary.json
  search_appendix -> doc_search_strategies_appendix.md
  protocol -> doc_protocol.md
```

---

## 9. Web UI Architecture

### 9.1 Two-Process Split

```
Dev mode:
  Vite dev server (:5173) -- proxies /api/* to FastAPI (:8001)
  Browser opens http://localhost:5173

Production:
  pnpm run build -> frontend/dist/
  FastAPI serves frontend/dist/ as StaticFiles at /
  Browser opens http://localhost:8001
```

PM2 is the primary process manager. `ecosystem.config.js` starts `litreview-api` (port 8001) and `litreview-ui` (Vite on port 5173). Overmind (`Procfile.dev`) is the alternative for tmux-based dev.

```
# PM2 (primary)
pm2 start ecosystem.config.js

# Overmind (alternative)
api: uv run uvicorn src.web.app:app --port ${PORT:-8001} --reload --reload-dir src --reload-dir config
ui:  cd frontend && pnpm run dev -- --port ${UI_PORT:-5173}
```

PM2: `pm2 start ecosystem.config.js` then `pm2 logs`. Overmind: `overmind start` then `overmind connect api`.

### 9.2 SSE Event Flow

```
user submits form
    |
    v
POST /api/run -> FastAPI creates _RunRecord (queue + task)
                  returns {run_id, topic}
    |
    v
Browser: GET /api/run/{run_id}/events  (prefetch replay buffer)
          -> gets all buffered events so far
    |
    v
Browser: GET /api/stream/{run_id}     (open live SSE connection)
    |
    v
run_workflow() emits via WebRunContext._emit(event)
    -> event_dict goes into asyncio.Queue  (live stream)
    -> event_dict appended to _RunRecord.event_log  (replay buffer)
    |
    v
EventSourceResponse dequeues and sends as SSE
    |
    v
useSSEStream.ts deduplicates replay buffer + live stream events by timestamp
setState({events: deduped}) -> all views re-render
```

Heartbeat events are sent every 15 seconds of inactivity to keep the connection alive through long phases. `useSSEStream` silently discards heartbeat events.

### 9.3 View Model

The frontend is run-centric. The sidebar is a run list, not a navigation menu. Selecting a run sets `selectedRun` in App state. `RunView` renders 6 tabs in workflow order: Config, Activity, Data, Cost, Results (plus Review Screening when awaiting_review). The selected tab is persisted in localStorage.

| View | Purpose |
|------|---------|
| SetupView | Structured PICO form + keyword/criteria tag inputs + database checkboxes + YAML builder; "Load from past run" dropdown reuses a stored config via `GET /api/history/{workflow_id}/config` |
| RunView | 6-tab shell (Config, Activity, Data, Cost, Results; Review Screening when awaiting_review) for a selected run |
| ConfigView | Shows research question and timestamped review.yaml for the run; used by agents and for copy-to-clipboard |
| ActivityView | Phase timeline + stats strip + filter chips + event log; works for live SSE runs and historical fetched runs |
| CostView | Recharts bar chart grouped by model/phase + sortable cost/token tables; reads from cost_records DB via /api/db/{run_id}/costs (primary, polls every 5s while active); SSE api_call events used as fallback before first DB response |
| ResultsView | Download links for all output artifacts (available when run is done) |
| DatabaseView | Paginated papers (with search), filterable screening decisions, cost records from runtime.db |
| HistoryView | Past runs from workflows_registry; "Open" button attaches any run to the DB explorer |

### 9.4 DB Explorer Flow

```
user clicks "Open" on a past run
    |
    v
POST /api/history/attach {workflow_id, topic, db_path}
    -> creates _RunRecord with db_path set, status=done
    -> loads event_log from event_log table in runtime.db
    returns {run_id}
    |
    v
Frontend sets selectedRun.id = run_id; hasRun = true; all tabs unlock
    |
    v
GET /api/db/{run_id}/papers|screening|costs
    -> FastAPI opens runtime.db at record.db_path via aiosqlite
    -> returns typed paginated response
```

`runId` (live SSE target) is always distinct from `dbRunId` (DB explorer target). Attaching a historical run does not affect any active live stream.

### 9.5 Design System

Dark-only theme. All colors from Tailwind utility classes.

| Role | Class | Hex |
|------|-------|-----|
| Page background | bg-[#09090b] | #09090b |
| Card background | bg-zinc-900 | #18181b |
| Card border | border-zinc-800 | #27272a |
| Body text | text-zinc-200 | #e4e4e7 |
| Muted text | text-zinc-500 | #71717a |
| Active accent | bg-violet-600 / text-violet-400 | #7c3aed / #a78bfa |
| Success / cost | text-emerald-400 | #34d399 |
| Error | text-red-400 | #f87171 |
| Warning | text-amber-400 | #fbbf24 |

Typography: Inter via Google Fonts. `font-mono` for log output and cost figures.

Run card status border (2px left): emerald = completed, violet = running/connecting, red = error/failed, amber = cancelled, zinc = idle/unknown.

---

## 10. API Contract

### 10.1 REST Endpoints (25 total)

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/run | Start new review; inject API keys as env vars; returns `{run_id, topic}` |
| GET | /api/stream/{run_id} | SSE stream of ReviewEvent JSON; heartbeat every 15s; ends with done/error/cancelled |
| POST | /api/cancel/{run_id} | Cancel active run; sets cancellation event |
| GET | /api/runs | List all in-memory active runs |
| GET | /api/results/{run_id} | Artifact paths for completed run |
| GET | /api/download | Download artifact file (restricted to runs/) |
| GET | /api/config/review | Default review.yaml content (pre-fills Setup form) |
| GET | /api/health | Health check; polled every 6s by useBackendHealth hook |
| GET | /api/history | Past runs from workflows_registry.db |
| GET | /api/history/{workflow_id}/config | Original review.yaml written at run completion |
| POST | /api/history/attach | Attach historical run for DB explorer; loads event_log from DB |
| POST | /api/history/resume | Resume a historical run by workflow_id; body may include from_phase (e.g. phase_3_screening) to re-run from that phase onward |
| DELETE | /api/history/{workflow_id} | Delete run directory from disk; cannot delete if run is actively in progress |
| GET | /api/db/{run_id}/papers | Paginated + searchable papers from runtime.db |
| GET | /api/db/{run_id}/papers-all | All papers with optional text filters (year, source, decisions) |
| GET | /api/db/{run_id}/papers-facets | Distinct facet values (sources, decisions) for filter UI |
| GET | /api/db/{run_id}/papers-suggest | Autocomplete suggestions for paper search |
| GET | /api/db/{run_id}/screening | Screening decisions with stage/decision filters |
| GET | /api/db/{run_id}/costs | Cost records grouped by model and phase |
| GET | /api/run/{run_id}/artifacts | Full run_summary.json for any run (live or historical) |
| GET | /api/run/{run_id}/events | Replay buffer snapshot (all buffered events) |
| GET | /api/workflow/{workflow_id}/events | Events from event_log table by workflow ID |
| POST | /api/run/{run_id}/export | Package IEEE LaTeX submission; calls package_submission() |
| GET | /api/run/{run_id}/submission.zip | Download the submission ZIP package |
| GET | /api/run/{run_id}/manuscript.docx | Download the Word DOCX manuscript |
| GET | /api/logs/stream | SSE tail of per-run PM2 log file; filtered by run_id |

### 10.2 SSE Event Types

All events carry a `ts` field (UTC ISO-8601). `ReviewEvent` discriminated union in `frontend/src/lib/api.ts` is the canonical TypeScript type.

| Type | Key Fields | Description |
|------|-----------|-------------|
| phase_start | phase, description, total | A pipeline phase began |
| phase_done | phase, summary (object), total, completed | A phase finished |
| progress | phase, current, total | Progress within a phase |
| api_call | source, status, phase, call_type, model, paper_id, latency_ms, tokens_in, tokens_out, cost_usd, records, section_name, word_count | One LLM call completed; used for client-side cost aggregation |
| connector_result | name, status, records, error | One search connector returned results |
| screening_decision | paper_id, stage, decision, confidence | One paper screening outcome; confidence (0-1) when available |
| extraction_paper | paper_id, design, rob_judgment | One paper extracted |
| synthesis | feasible, groups, n_studies, direction | Meta-analysis summary |
| rate_limit_wait | tier, slots_used, limit | Rate limiter pausing |
| db_ready | (none) | Run DB is open; DB Explorer tabs unlock immediately |
| done | outputs (label -> path) | Run completed successfully |
| error | msg | Run failed |
| cancelled | (none) | Run was cancelled by user |
| heartbeat | (none) | Keep-alive every 15s; sent as a raw SSE frame (not a JSON ReviewEvent), never enters the TypeScript ReviewEvent union; silently discarded by useSSEStream before JSON parsing |

### 10.3 In-Memory Run State

Each active run in `src/web/app.py` is tracked as a `_RunRecord` class (not a dataclass):
- `run_id`: short UUID prefix used as SSE endpoint key
- `queue`: asyncio.Queue receiving ReviewEvent JSON strings from WebRunContext
- `task`: background asyncio.Task running run_workflow()
- `event_log`: in-memory replay buffer for prefetch endpoint
- `db_path`: path to runtime.db (set when db_ready event fires)
- `workflow_id`: set after workflow starts; used for export and history
- `topic`: research question string for the run
- `done`: bool flag set when the run completes or errors
- `error`: optional error message string
- `outputs`: artifact label->path dict populated at finalize
- `run_root`: root directory for this run's artifacts
- `created_at`: ISO timestamp of run creation
- `review_yaml`: original review.yaml content stored at run start

---

## 11. Development Workflow

### 11.1 Prerequisites

- Python 3.11+, uv (`pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Node 20.19+ or 22.12+, pnpm 10 (`npm install -g pnpm`)
- PM2 (`npm install -g pm2`) -- primary dev process manager; or Overmind + tmux (`brew install overmind`) as alternative
- pdflatex (for IEEE export compilation; part of TeX Live or MacTeX)
- API keys in `.env` (see Section 4.1)

### 11.2 One-Time Setup

```
# Install Python dependencies
uv sync

# Install frontend dependencies
cd frontend && pnpm install

# Copy .env.example to .env and fill in API keys
cp .env.example .env
```

### 11.3 Daily Development

```
pm2 start ecosystem.config.js                    # Start FastAPI + Vite together (recommended)
# Open http://localhost:5173 -- Vite proxies /api to FastAPI on :8001

# Run CLI only (no frontend needed):
uv run python -m src.main run --config config/review.yaml
uv run python -m src.main run --config config/review.yaml --verbose
uv run python -m src.main run --config config/review.yaml --debug
uv run python -m src.main run --config config/review.yaml --offline     # heuristic screening only
uv run python -m src.main run --config config/review.yaml --fresh       # ignore existing run for same config_hash
uv run python -m src.main run --config config/review.yaml --settings config/settings.yaml
uv run python -m src.main run --config config/review.yaml --run-root runs/

# Resume / manage runs:
uv run python -m src.main resume --topic "my research question"
uv run python -m src.main resume --workflow-id abc123
uv run python -m src.main resume --topic "my research question" --config config/review.yaml --settings config/settings.yaml --run-root runs/
uv run python -m src.main status --workflow-id abc123 --run-root runs/
uv run python -m src.main validate --workflow-id abc123 --run-root runs/
uv run python -m src.main export --workflow-id abc123 --run-root runs/
```

### 11.4 Testing

```
uv run ruff check . --fix && uv run ruff format .   # Python lint + format
cd frontend && pnpm fix && pnpm typecheck           # ESLint + TypeScript
uv run pytest tests/unit -q                         # 105 unit tests
uv run pytest tests/integration -q                 # integration tests (require config/review.yaml)
uv run python -m src.main --help                    # confirm CLI loads without error
```

After each phase, run all commands and confirm clean output before proceeding.

### 11.5 Production Frontend Build

```
cd frontend && pnpm run build         # tsc strict mode + Vite chunk split -> frontend/dist/
# FastAPI serves frontend/dist/ at / automatically when the directory exists
# Open http://localhost:8000
```

TypeScript strict mode catches all type errors. There is no separate ESLint step required.

### 11.6 Output Artifact Naming

All runtime artifacts use type-based prefixes for clarity:
- `fig_*` (PNG figures): prisma_flow, publication_timeline, geographic_distribution, rob_traffic_light, forest_plot, funnel_plot
- `doc_*` (Markdown): manuscript, protocol, search_strategies_appendix, fulltext_retrieval_coverage, disagreements_report
- `data_*` (JSON): narrative_synthesis
- `run_summary.json` (in log dir, not output dir)

---

## 12. Methodology Standards

The tool enforces these academic standards structurally -- via typed data models, quality gates, and validators -- not through LLM judgment.

| Standard | Tool / Phase | Requirement |
|----------|-------------|-------------|
| PRISMA 2020 | All phases | 27-item checklist; >= 24/27 required at export; two-column flow diagram (databases left, other sources right); per-database counts; exclusion reasons categorized |
| PRISMA-S | Phase 2 | Full Boolean search string documented for every database with dates and record limits |
| PROSPERO protocol | Phase 2 | 22-field protocol document generated from ReviewConfig before search |
| Cochrane dual-reviewer | Phase 3 | Two independent reviewers with different prompts; disagreements adjudicated; Cohen's kappa computed; disagreements report generated |
| RoB 2 | Phase 4 | 5-domain Cochrane tool for RCTs; domain-based judgments only (Low / Some concerns / High); NEVER a single summary score; overall judgment via algorithm |
| ROBINS-I | Phase 4 | 7-domain tool for non-randomized studies; separate judgment scale (Low / Moderate / Serious / Critical / No Information) |
| CASP | Phase 4 | Qualitative appraisal checklist for qualitative studies |
| GRADE | Phase 4/6 | Per-outcome certainty across 5 downgrading + 3 upgrading factors; output High / Moderate / Low / Very Low; Summary of Findings table in manuscript |
| Meta-analysis | Phase 5 | Fixed-effect (I-squared < 50%) or random-effects DerSimonian-Laird (>= 50%); Cochran's Q + I-squared reported; forest plot per outcome; funnel plot when >= 10 studies |
| IEEE submission | Phase 8 | IEEEtran.cls; abstract 150-250 words; 7-10 pages; numbered BibTeX references; PRISMA checklist as supplementary |

**Citation lineage rule:** Every factual claim in the manuscript must trace through: `ClaimRecord -> EvidenceLinkRecord -> CitationEntryRecord -> papers.paper_id`. The `block_export_on_unresolved` gate enforces this at export time. LLMs are constrained to the provided citation catalog; they cannot introduce new references.

**LLMs write prose about what the structured data shows. They do not compute or invent the data itself.**

**Benchmark reference:** `reference/benchmark-systematic-reviews-pharmacy-automation.md` summarizes 6 published systematic/scoping reviews (Jeffrey et al. 2024, Batson et al. 2020, Zheng et al. 2021, Jung et al. 2025, Osman et al. 2026, Abimanyu et al. 2025) on pharmacy automation and medication dispensing. Use for validating manuscript structure (IMRaD sections, PRISMA flow, GRADE SoF), methodology (databases, dual screening, RoB tools), and reporting completeness.

---

## 13. Implementation Status

Living section -- update as work completes.

| Component | Status | Notes |
|-----------|--------|-------|
| Phase 1: Foundation | DONE | Models, SQLite, 6 gates, citation ledger, LLM provider, rate limiter |
| Phase 2: Search | DONE | All 7 connectors + ClinicalTrials.gov grey literature, MinHash LSH dedup (datasketch + thefuzz), forward citation chasing (Semantic Scholar + OpenAlex), BM25 ranking, protocol generator, SearchConfig |
| Phase 3: Screening | DONE | Dual reviewer with cross-model validation (Reviewer A=flash-lite tier, Reviewer B=flash tier -- see config/settings.yaml), keyword filter, BM25 cap, kappa injected into writing, Ctrl+C proceed-with-partial, confidence fast-path, protocol-only auto-exclusion |
| Phase 4: Extraction + Quality | DONE | LLM extraction with PyMuPDF full-text parsing (32K char context, up from 8K), async RoB 2 / ROBINS-I / CASP with heuristic fallback tagged by assessment_source, GRADE auto-wired from RoB data (assess_from_rob), study router, RoB traffic-light figure |
| Phase 5: Synthesis | DONE | Hardened feasibility (requires effect_size+se in >= 2 studies), statsmodels pooling (DL), forest + funnel plots, LLM-based narrative direction classification, sensitivity analysis (leave-one-out + subgroup), synthesis_results table |
| Phase 6: Writing | DONE | Section writer, humanizer, citation validation, style extractor, naturalness scorer, per-section checkpoint, WritingGroundingData (includes kappa, sensitivity_results, n_studies_reporting_count, separated search sources), GRADE table injected into manuscript |
| Phase 7: PRISMA + Viz | DONE | PRISMA diagram (prisma-flow-diagram + fallback), timeline, geographic, ROBINS-I in RoB figure, uniform artifact naming |
| Phase 8: Export + Orchestration | DONE | Run/resume, IEEE LaTeX, BibTeX, validators, Word DOCX export (pypandoc + python-docx), submission packager, pdflatex, CLI subcommands |
| Web UI | DONE | FastAPI SSE backend (30+ endpoints incl. screening-summary, approve-screening, living-refresh, prisma-checklist), React/Vite/TypeScript frontend, structured Setup form, run-centric sidebar, 6-tab RunView in workflow order (Config -> Activity -> Data -> Cost -> Results, with step numbers and chevron connectors; Review Screening when awaiting_review), Config tab shows research question and timestamped review.yaml for agent reference, DB explorer with heuristic RoB filter, cost tracking, grouped Results panel with PRISMA checklist panel, ScreeningReviewView for HITL approval, living refresh button |
| Human-in-the-Loop | DONE | HumanReviewCheckpointNode pauses run at awaiting_review status; approve-screening API resumes; frontend shows Review Screening tab with AI decisions + confidence |
| Living Review | DONE | living_review + last_search_date in review.yaml; SearchNode skips previously-screened DOIs; POST /api/run/{id}/living-refresh creates incremental re-run |
| Resume | DONE | Central registry, topic auto-resume, mid-phase resume, resume-from-phase (backend API supports from_phase param; UI phase-picker modal removed -- resume via CLI --from-phase flag or direct API call), fallback scan of run_summary.json |
| Post-build improvements | DONE | display_label (single source of truth in papers table), synthesis_results table, dedup_count column, SearchConfig per-connector limits, BM25 cap with LOW_RELEVANCE_SCORE exclusions |
| Post-build: Hybrid RAG + PRISMA fixes | DONE | Hybrid BM25+dense RAG (RRF) in WritingNode, PydanticAI Embedder replacing google-generativeai SDK, PRISMA endpoint registry fallback, duplicate Discussion heading dedup, PRISMACounts field name fixes |
| Post-build: HyDE + Gemini listwise reranker | DONE | HyDE (hypothetical doc embeddings, Gao et al. 2022) for rich dense query vectors; Gemini Flash listwise reranker (single LLM call ranks 20 candidates to top 8); removed sentence-transformers/torch (382 MB) in favour of zero-new-dep PydanticAI calls |
| Validation benchmark | DONE | scripts/benchmark.py measures screening recall, extraction field accuracy, RoB kappa vs. gold-standard corpus |
| Enhancement #4: Semantic Chunking | DONE | Sentence-boundary chunker (nltk sent_tokenize) replaces fixed 512-word windows; chunks stay under ~400 words, 2-sentence overlap; fallback to regex split if nltk unavailable; settings: CHUNK_MAX_WORDS, OVERLAP_SENTENCES in chunker.py |
| Enhancement #5: PICO-Aware Retrieval | DONE | PICO terms from review.yaml injected into HyDE prompt and BM25 query string; controlled by rag.pico_query_boost in settings.yaml |
| Enhancement #6: Living Review Auto-Refresh | DONE | Delta pipeline: search from last_search_date, screen/embed new papers only, merge into previous DB, re-run synthesis+writing only if new evidence added |
| Enhancement #7: Multi-Modal Evidence | DONE | 6-tier full-text retrieval (Unpaywall, Semantic Scholar, CORE, Europe PMC, ScienceDirect, PMC -> abstract fallback); unified resolver used by extraction and screening; Gemini vision extracts quantitative outcome rows from PDFs; vision+text outcomes merged; table rows chunked as separate embeddings; GET /api/db/{run_id}/tables endpoint; Scopus abstract gap fixed via enrich_scopus_abstracts() |
| Enhancement #8: Contradiction-Aware Synthesis | DONE | contradiction_detector.py surfaces conflict pairs; WritingNode injects "Conflicting Evidence" subsection into Discussion with citation keys and reconciliation hypothesis |
| Enhancement #9: Adaptive Screening Threshold | DONE | Active-learning calibration loop: 30-paper sample, kappa computed, thresholds adjusted via bisection until kappa > 0.7 or 3 iterations; settings: screening.calibration_sample_size |
| Enhancement #10: GRADE Evidence Profile | DONE | Full GRADE Summary of Findings table (studies, participants, effect estimate, certainty, reason); build_sof_table() in grade.py; GradeSoFTable + GradeSoFRow models; LaTeX longtable export; GET /api/run/{run_id}/grade-sof endpoint |
| Search quality sprint | DONE | Scopus connector (src/search/scopus.py, TITLE-ABS-KEY field codes, 5 req/sec limit, 429 back-off); Web of Science connector (src/search/web_of_science.py, TS= prefix syntax, Starter API); default target_databases updated to scopus + web_of_science + openalex + pubmed + semantic_scholar; ieee_xplore + perplexity_search + crossref + arxiv moved to opt-in |
| OpenAlex query fix + config generator | DONE | OpenAlex received the broad boolean OR fallback causing ~500 off-topic results. Fix: (1) strategy.py added openalex branch returning short_query (same pattern as semantic_scholar); (2) config_generator.py added openalex field to _SearchOverrides model and updated _STRUCTURE_PROMPT to generate all six database overrides; all descriptions and examples made domain-agnostic so generator works for any topic. |
| Manuscript quality sprint | DONE | Root causes fixed in pipeline: assemble_submission_manuscript() includes GRADE SoF table, search appendix, excluded-studies footnote; abstract prompt includes kappa framing; semicolon parsing in citation extraction; IMRaD heading prompts tightened. finalize_manuscript.py is a thin regeneration utility for historical runs; _strip_unresolved_citekeys() is the only remaining safety net. Citation lineage gate: FinalizeNode validates manuscript; block_export_on_unresolved respected. |
| Zero-papers manuscript | DONE | WritingNode guard: when 0 papers included (gates.profile=warning allows continuation past screening_safeguard), produces minimal manuscript without LLM calls via _build_minimal_sections_for_zero_papers(). Appendix B (Characteristics of Included Studies) includes Full Text Retrieved column. Sidebar RunCardMetrics displays 0/0 for found/included. |

**Test status:** 105 unit tests, 13 integration tests (`uv run pytest tests/unit tests/integration -q`).

---

## 14. Next Steps

Living section -- update as items complete.

The core 8-phase pipeline and all 10 post-build enhancements are complete and running in production.

### Completed Enhancements

| # | Enhancement | Status | Key Files |
|---|-------------|--------|-----------|
| 1 | Hybrid BM25 + Dense RAG (RRF) | DONE | src/rag/retriever.py |
| 2 | HyDE (Hypothetical Document Embeddings) | DONE | src/rag/hyde.py |
| 3 | Gemini listwise reranking | DONE | src/rag/reranker.py |
| 4 | Semantic Chunking | DONE | src/rag/chunker.py |
| 5 | PICO-Aware Retrieval | DONE | src/rag/hyde.py, src/orchestration/workflow.py |
| 6 | Living Review Auto-Refresh | DONE | src/web/app.py, src/orchestration/workflow.py |
| 7 | Multi-Modal Evidence (full-text + vision tables) | DONE | src/extraction/table_extraction.py, src/search/scopus.py |
| 8 | Contradiction-Aware Synthesis | DONE | src/synthesis/contradiction_detector.py, src/writing/orchestration.py |
| 9 | Adaptive Screening Threshold | DONE | src/screening/reliability.py |
| 10 | GRADE Evidence Profile (SoF table + LaTeX) | DONE | src/quality/grade.py, src/export/ieee_latex.py |

### Active Priorities

All major features are shipped. Current priorities for the next session:

- **Embase connector:** Institutional API token required (`apisupport@elsevier.com`). Implementation pattern matches `src/search/scopus.py`.
- **Higher kappa target:** Cohen's kappa was 0.118 on first real run (borderline-only subset). Enhancement #9 (adaptive threshold) is implemented; verify calibration reduces this on next run.
- **End-to-end IEEE submission:** Run the full pipeline on a new topic, verify all Definition of Done criteria pass, produce submission package.

---

## Definition of Done (First IEEE Submission)

All of the following must be true before the first submission:

- Protocol auto-generated with all PICO elements
- Search strategies documented for every database with dates and Boolean strings
- Dual-reviewer screening produces Cohen's kappa >= 0.6
- Full-text exclusion reasons categorized using ExclusionReason enum
- RoB 2 completed for all RCTs (5 domains, domain-based judgments)
- ROBINS-I completed for all non-randomized studies (7 domains)
- Risk-of-bias traffic-light figure generated
- GRADE Summary of Findings table with all 8 factors per outcome
- PRISMA 2020 two-column diagram with correct arithmetic at every stage
- Forest plot generated for each poolable outcome
- Funnel plot generated when >= 10 studies
- Methods section references all tools used + Cohen's kappa value
- All claims traceable via citation ledger (ClaimRecord -> EvidenceLinkRecord -> CitationEntryRecord)
- Zero unresolved citations at export
- IEEE LaTeX compiles with IEEEtran.cls without errors
- Abstract <= 300 words
- PRISMA checklist >= 24/27 items reported
- All 6 quality gates pass in strict mode
- All unit and integration tests pass
- submission/ directory contains: manuscript.tex, manuscript.pdf, references.bib, figures/, supplementary/
