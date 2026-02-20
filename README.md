# Research Article Writer

An open source tool that automates systematic literature reviews end-to-end -- from a research question to an IEEE-submission-ready manuscript.

It runs a full PRISMA 2020-compliant pipeline: searches 6+ academic databases, dual-reviews every paper with independent AI reviewers, extracts data, assesses risk of bias (RoB 2, ROBINS-I, GRADE), synthesizes evidence (meta-analysis or narrative), and writes the manuscript with citation lineage enforced throughout.

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
| Node.js | 18+ | [nodejs.org](https://nodejs.org/) or `brew install node` |
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

Enter your Gemini API key and click Run. Your API keys are saved in your browser (localStorage) and restored on the next visit.

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
- `target_databases` (openalex, pubmed, arxiv, ieee_xplore, semantic_scholar, crossref)

**`config/settings.yaml`** -- change this rarely:
- LLM model assignments (which Gemini tier handles screening vs. writing)
- Screening thresholds (include/exclude confidence cutoffs)
- `max_llm_screen` -- hard cap on LLM screening volume (cost control)
- Quality gate thresholds
- Search depth (records per database)

Full documentation of every config field is in `docs/research-agent-v2-spec.md` Part 6.

---

## How It Works

The pipeline runs as an 8-phase PydanticAI graph. Each phase writes its results to SQLite immediately so a crash can resume from the exact paper where it stopped.

```text
Phase 1: Load config, initialize DB, set up LLM provider
Phase 2: Search 6+ databases, deduplicate, generate PROSPERO protocol
Phase 3: Dual-reviewer screening (AI Reviewer A + B, adjudicator on disagreement)
Phase 4: Data extraction + risk of bias (RoB 2 / ROBINS-I / CASP / GRADE)
Phase 5: Meta-analysis or narrative synthesis
Phase 6: Write manuscript sections (abstract through conclusion)
Phase 7: Generate PRISMA diagram, RoB traffic-light, timeline, geographic chart
Phase 8: Export IEEE LaTeX + compile PDF
```

Every factual claim in the manuscript is traced back to a citation via the citation ledger. The LLM is given only the real extracted data -- it cannot hallucinate statistics.

---

## Development

**Dev servers (hot-reload):**

Install [Overmind](https://github.com/DarthSim/overmind) and tmux once:

```bash
# macOS
brew install overmind

# Linux (requires Go and tmux)
go install github.com/DarthSim/overmind/v2@latest
sudo apt-get install tmux   # or your distro's equivalent
```

Then from anywhere in the repo, start both servers with a single command:

```bash
./bin/dev
```

This starts the FastAPI backend (port 8000, `--reload`) and Vite frontend (port 5173, HMR)
together. Both auto-restart on crash. Open `http://localhost:5173`.

Useful Overmind commands (run from any directory):

```bash
overmind connect api      # attach to backend terminal (Ctrl-b d to detach)
overmind connect ui       # attach to frontend terminal
overmind restart api      # restart backend only (e.g. after adding a dependency)
overmind stop             # stop all processes
./bin/dev -D              # run as background daemon (survives terminal close)
overmind echo             # tail logs from daemon
overmind quit             # stop daemon
```

No Overmind? Run each process in its own terminal instead:

```bash
# Terminal 1
uv run uvicorn src.web.app:app --reload --port 8000

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
| `src/export/` | IEEE LaTeX exporter, BibTeX builder, PRISMA validator |
| `src/visualization/` | Forest plot, funnel plot, RoB figure, timeline, geographic |
| `src/web/` | FastAPI backend for the browser UI |
| `frontend/` | React + TypeScript web UI |

**Full architecture spec:** `docs/research-agent-v2-spec.md`

**Utility scripts:**

| Script | Purpose |
|--------|---------|
| `scripts/regenerate_figures.py` | Re-render all figures (PRISMA flow, timeline, geographic, RoB, RoB2) from a completed run's SQLite DB without any LLM calls. Useful after figure code fixes. Edit the `DB_PATH`, `WORKFLOW_ID`, `DEDUP_COUNT`, `OUTPUT_DIR` variables at the top of the file before running. Usage: `uv run python scripts/regenerate_figures.py` |

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
