# Research Article Writer

An open source tool that automates systematic literature reviews end-to-end -- from a research question to an IEEE-submission-ready manuscript.

It runs a full PRISMA 2020-compliant pipeline: searches 7 academic databases (OpenAlex, PubMed, arXiv, IEEE Xplore, Semantic Scholar, Crossref, Perplexity), dual-reviews every paper with independent AI reviewers, extracts data, assesses risk of bias (RoB 2, ROBINS-I, GRADE), synthesizes evidence (meta-analysis or narrative), and writes the manuscript with citation lineage enforced throughout.

**Use it via browser (web UI) or terminal (CLI).**

---

## What It Produces

After a run completes, you get a `submission/` folder containing:

- `manuscript.tex` + `manuscript.pdf` -- IEEE-formatted manuscript (IEEEtran)
- `references.bib` -- all citations
- `figures/` -- PRISMA flow diagram, RoB traffic-light, forest plot, funnel plot, publication timeline, geographic distribution
- `supplementary/` -- search strategies appendix, screening decisions CSV, extracted data CSV

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.11+ | [python.org](https://www.python.org/downloads/) or `brew install python` |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js | 20+ | [nodejs.org](https://nodejs.org/) or `brew install node` |
| pnpm | latest | `npm install -g pnpm` or `brew install pnpm` |

---

## Quick Start (Web UI)

The web UI is the easiest way to get started. No config files needed -- you fill in your research question and API keys in the browser.

**1. Clone the repo**

```bash
git clone https://github.com/yourusername/research-article-writer
cd research-article-writer
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
uv run uvicorn src.web.app:app --port 8000
```

**5. Open your browser**

Go to `http://localhost:8000`. Click "+" in the sidebar to start a new review. The form has structured fields: PICO (Population, Intervention, Comparison, Outcome), keywords, inclusion/exclusion criteria, date range, and database checkboxes. It builds the YAML config automatically -- you do not need to write YAML by hand.

Enter your API keys and click Run. Your keys are saved in your browser (localStorage) and restored on the next visit. You can also paste your entire `.env` file into the "Paste .env" panel -- the form will detect and fill all recognised keys automatically (GEMINI_API_KEY, OPENALEX_API_KEY, PUBMED_EMAIL, etc.).

The sidebar shows all your runs (live and historical) with status colors (emerald = completed, violet = running, red = error, amber = cancelled) and a stats strip (papers found, papers included, artifacts, cost). Selecting a run opens its 4-tab dashboard: Activity (phase timeline + event log), Results, Database, Cost. The selected tab persists when you switch between runs.

**Tip -- reuse a past config:** Click "+" to open the form, then use the "Load from past run" dropdown to pre-populate the form from any previous run's config. Useful for iterating on the same research question with different parameters.

---

## Quick Start (CLI)

Prefer the terminal? Use this path.

**1. Clone and install**

```bash
git clone https://github.com/yourusername/research-article-writer
cd research-article-writer
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
OPENALEX_API_KEY=your-key-here            # Required -- free at openalex.org
PUBMED_EMAIL=your-email@example.com       # Required for PubMed (any email)
PUBMED_API_KEY=your-key-here              # Optional -- faster PubMed rate limits
IEEE_API_KEY=your-key-here                # Optional -- IEEE Xplore access
PERPLEXITY_SEARCH_API_KEY=your-key-here   # Optional -- auxiliary discovery
SEMANTIC_SCHOLAR_API_KEY=your-key-here    # Optional -- higher rate limits
CROSSREF_EMAIL=your-email@example.com     # Optional -- polite crawling for Crossref
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
| `OPENALEX_API_KEY` | [openalex.org](https://openalex.org/sign-up) | Yes (since Feb 2026) |
| `PUBMED_EMAIL` | Any email address | Yes (for PubMed Entrez) |
| `PUBMED_API_KEY` | [ncbi.nlm.nih.gov/account](https://www.ncbi.nlm.nih.gov/account/settings/) | No (higher rate limits) |
| `IEEE_API_KEY` | [developer.ieee.org](https://developer.ieee.org) | No |
| `PERPLEXITY_SEARCH_API_KEY` | [docs.perplexity.ai](https://docs.perplexity.ai) | No |
| `SEMANTIC_SCHOLAR_API_KEY` | [api.semanticscholar.org](https://api.semanticscholar.org) | No (higher rate limits) |
| `CROSSREF_EMAIL` | Any email address | No (polite Crossref crawling) |

The free Gemini tier (Flash-Lite / Flash / Pro) is sufficient for most reviews. A full run typically costs under $5.

**Cost control tip:** Screening is the biggest cost driver (it calls the LLM once per paper). To cap costs on exploratory runs, set `max_llm_screen` in `config/settings.yaml`:

```yaml
screening:
  max_llm_screen: 200  # BM25-rank all candidates; send top 200 to LLM; exclude the rest
```

When `max_llm_screen` is set, all candidate papers are BM25-ranked by relevance to your research question. The top N go to LLM dual-review; the remainder are excluded with their BM25 score logged to the database so the PRISMA flow diagram counts are always accurate.

Remove the line (or set it to `null`) to send all candidate papers through LLM screening.

---

## CLI Reference

```bash
# Start a new review
uv run python -m src.main run --config config/review.yaml

# Run with verbose output (shows each LLM call)
uv run python -m src.main run --config config/review.yaml --verbose

# Resume after a crash or Ctrl+C
uv run python -m src.main resume --topic "your research question"
uv run python -m src.main resume --workflow-id abc123

# Export submission package
uv run python -m src.main export --workflow-id abc123

# Validate IEEE compliance and PRISMA checklist
uv run python -m src.main validate --workflow-id abc123

# Check run status and artifact paths
uv run python -m src.main status --workflow-id abc123
```

**Tip:** Press Ctrl+C once during screening to proceed with already-screened papers. Press Ctrl+C twice to abort. Re-running with the same topic automatically prompts you to resume.

---

## Configuration

Two config files control behavior:

**`config/review.yaml`** -- change this for every new review:
- `research_question`, `pico`, `keywords`, `domain`
- `inclusion_criteria`, `exclusion_criteria`
- `date_range_start`, `date_range_end`
- `target_databases` (openalex, pubmed, arxiv, ieee_xplore, semantic_scholar, crossref, perplexity)

**`config/settings.yaml`** -- change this rarely:
- LLM model assignments (which Gemini tier handles screening vs. writing)
- Screening thresholds (include/exclude confidence cutoffs)
- `max_llm_screen` -- hard cap on LLM screening volume (cost control)
- Quality gate thresholds
- Search depth (records per database)

Full documentation of every config field is in `spec.md` Section 4.

---

## How It Works

The pipeline runs as a 6-phase PydanticAI graph plus a FinalizeNode that handles visualization and export. Each phase writes its results to SQLite immediately so a crash can resume from the exact paper where it stopped.

```text
Phase 1: Load config, initialize DB, set up LLM provider
Phase 2: Search 7 databases, deduplicate, generate PROSPERO protocol
Phase 3: Dual-reviewer screening (AI Reviewer A + B, adjudicator on disagreement)
Phase 4: Data extraction + risk of bias (RoB 2 / ROBINS-I / CASP / GRADE)
Phase 5: Meta-analysis or narrative synthesis
Phase 6: Write manuscript sections (abstract through conclusion)
Finalize: Generate PRISMA diagram, RoB traffic-light, timeline, geographic chart
          + Export IEEE LaTeX + compile PDF
```

Every factual claim in the manuscript is traced back to a citation via the citation ledger. The LLM is given only the real extracted data -- it cannot hallucinate statistics.

---

## Development

**Dev servers (hot-reload):**

The primary dev workflow uses [PM2](https://pm2.keymetrics.io/). Install it once:

```bash
npm install -g pm2
```

Then start both the FastAPI backend (port 8001, `--reload`) and Vite frontend (port 5173, HMR) with:

```bash
pm2 start ecosystem.dev.config.js
```

Open `http://localhost:5173`. The Vite dev server proxies `/api` to the backend automatically.

Useful PM2 commands:

```bash
pm2 logs              # tail logs from all processes
pm2 logs api          # tail backend logs only
pm2 restart api       # restart backend (e.g. after adding a dependency)
pm2 restart ui        # restart frontend dev server
pm2 stop all          # stop all processes
pm2 delete all        # remove all processes from PM2 registry
pm2 status            # show process status table
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
```

**Project layout:**

| Directory | What's in it |
|-----------|-------------|
| `src/models/` | Pydantic data contracts (every phase boundary) |
| `src/db/` | SQLite schema, typed repositories, workflow registry |
| `src/orchestration/` | PydanticAI Graph nodes, quality gates, resume logic |
| `src/search/` | Database connectors + deduplication + search strategy |
| `src/screening/` | Dual reviewer, Cohen's kappa, keyword pre-filter |
| `src/extraction/` | Study design classifier, data extractor |
| `src/quality/` | RoB 2, ROBINS-I, CASP, GRADE |
| `src/synthesis/` | Feasibility checker, meta-analysis, narrative synthesis |
| `src/writing/` | Section writer, humanizer, style extractor, grounding |
| `src/citation/` | Citation ledger -- claim-to-evidence-to-BibTeX lineage |
| `src/export/` | IEEE LaTeX exporter, BibTeX builder, PRISMA validator |
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
| `scripts/finalize_manuscript.py` | Retroactively regenerate `doc_manuscript.md` sections (Figures, Declarations, Study Characteristics Table, References) for an existing run directory. Also injects missing IMRaD headings. Usage: `uv run python scripts/finalize_manuscript.py --run-dir runs/<date>/<topic>/run_<time>` |
| `scripts/migrate_to_runs.py` | One-time migration to move legacy run artifacts into the current `runs/<date>/<topic>/` directory structure. |

---

## Troubleshooting

**SSL errors (`CERTIFICATE_VERIFY_FAILED`):**
- macOS: run `Install Certificates.command` from your Python.app folder
- Corporate proxy: set `SSL_CERT_FILE` to your org CA bundle
- Dev only (insecure): `RESEARCH_AGENT_SSL_SKIP_VERIFY=1`

**Rate limit errors:** The tool respects Gemini free-tier limits automatically. If you hit them, wait a minute and resume.

**"No papers found":** Check that your keywords are broad enough and that `OPENALEX_API_KEY` is set. Try lowering `keyword_filter_min_matches` to `0` in `config/settings.yaml` to disable pre-filtering.

---

## License

MIT
