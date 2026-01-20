# Literature Review Assistant - Agentic AI System

End-to-end agentic system that automates systematic literature reviews from search to publication-ready articles, including PRISMA 2020-compliant flow diagrams and visualizations.

## Quick Start

### Step 1: Setup Environment

```bash
# Create virtual environment
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
uv pip install -e .
```

### Step 2: Configure Environment Variables

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your API keys
# At minimum, you need an LLM API key (see API Keys Required section)
```

### Step 3: Configure Workflow (Optional)

Edit `config/workflow.yaml` to customize:
- Research topic and research question
- Databases to search (default: PubMed, arXiv, Semantic Scholar, Crossref)
- Date ranges and filters
- Agent configurations (LLM models, temperature, tools)
- Inclusion/exclusion criteria

### Step 4: Run the Workflow

```bash
# Basic run
python main.py

# Or use Makefile
make setup    # Create venv
make install  # Install dependencies
make run      # Run workflow
```

### Step 5: Check Outputs

Results are saved to `data/outputs/`:
- `final_report.md` - Complete systematic review article
- `references.bib` - BibTeX citation file (if BibTeX export enabled)
- `prisma_diagram.png` - PRISMA 2020 flow diagram
- `papers_per_year.png` - Publication timeline
- `network_graph.html` - Interactive citation/co-occurrence network
- `papers_by_country.png` - Geographic distribution
- `papers_by_subject.png` - Subject area distribution
- `workflow_state.json` - Workflow metadata

Search logs (PRISMA-compliant) are saved to `data/outputs/search_logs/`:
- `prisma_search_report_*.json` - PRISMA-S compliant search report
- `search_summary_*.csv` - CSV summary of all searches

## Workflow Overview

The system executes 12 sequential phases: Build Search Strategy, Search Databases, Deduplication, Title/Abstract Screening, Full-text Screening, Paper Enrichment, Data Extraction, Quality Assessment, PRISMA Diagram Generation, Visualization Generation, Article Writing, and Final Report Compilation.

**Checkpoint System**: The workflow automatically saves checkpoints after each phase, allowing you to resume from any point. When running `python main.py` with the same topic, it automatically resumes from the latest checkpoint.

## API Keys Required

### Required for LLM Features

The system requires at least one LLM provider API key:

**Option 1: OpenAI**
```bash
OPENAI_API_KEY=sk-your-key-here
LLM_PROVIDER=openai
```

**Option 2: Anthropic**
```bash
ANTHROPIC_API_KEY=sk-ant-your-key-here
LLM_PROVIDER=anthropic
```

**Option 3: Google GenAI (Gemini)**
```bash
# Use GOOGLE_API_KEY (preferred) or GEMINI_API_KEY
GOOGLE_API_KEY=your-key-here
# OR
GEMINI_API_KEY=your-key-here
LLM_PROVIDER=google
# OR
LLM_PROVIDER=gemini
```
Get API key from: https://aistudio.google.com/app/apikey

**Option 4: Perplexity**
```bash
PERPLEXITY_API_KEY=your-key-here
LLM_PROVIDER=perplexity
```
Get API key from: https://www.perplexity.ai/settings/api

**Note**: If no API keys are provided, the system will use fallback keyword-based methods (limited functionality).

### Optional: Database API Keys

The system works with free databases by default (PubMed, arXiv, Semantic Scholar, Crossref), but API keys improve rate limits:

**PubMed/NCBI** (Optional but recommended):
```bash
PUBMED_API_KEY=your_key
PUBMED_EMAIL=your_email@example.com
```

**Semantic Scholar** (Optional but recommended):
```bash
SEMANTIC_SCHOLAR_API_KEY=your_key
```

**Crossref** (Email recommended):
```bash
CROSSREF_EMAIL=your_email@example.com
```

**Note**: arXiv and ACM work without any API key. PubMed, Semantic Scholar, and Crossref work without API keys but have lower rate limits.

## Configuration

### Workflow Configuration

The system uses a unified YAML configuration file (`config/workflow.yaml`) for all settings:

**Research Topic**:
```yaml
topic:
  topic: "LLM-Powered Health Literacy Chatbots for Low-Income Communities"
  keywords: ["health literacy", "chatbots", "LLM", "low-income"]
  domain: "public health"
  scope: "Focus on LLM-powered chatbots designed to improve health literacy"
  research_question: "What is the effectiveness of LLM-powered health literacy chatbots?"
```

**Workflow Settings**:
```yaml
workflow:
  databases: ["PubMed", "arXiv", "Semantic Scholar", "Crossref", "ACM"]
  date_range:
    start: null
    end: 2025
  max_results_per_db: 100
```

**Inclusion/Exclusion Criteria**:
```yaml
criteria:
  inclusion:
    - "Studies on LLM/chatbot interventions for health literacy"
  exclusion:
    - "Non-LLM chatbots (rule-based or simple keyword matching)"
```

All agent configurations are in the YAML file - no code changes needed to modify agent behavior!

## Project Structure

```
literature-review-assistant/
├── src/                    # Source code
│   ├── orchestration/     # Workflow orchestration
│   ├── search/            # Database connectors & search
│   ├── screening/         # Screening agents
│   ├── extraction/        # Data extraction agents
│   ├── writing/           # Article writing agents
│   ├── prisma/            # PRISMA diagram generation
│   └── ...
├── tests/                 # Test suite
├── scripts/               # Utility scripts
├── config/
│   └── workflow.yaml      # Workflow configuration
├── data/
│   └── outputs/           # Generated outputs
├── main.py                # Entry point
└── README.md             # This file
```

## Testing

**Run All Tests:**
```bash
pytest tests/ -v
```

**Test Database Connectors:**
```bash
python main.py --test-databases
# or
python scripts/test_database_health.py
```

**Test Full Workflow:**
```bash
python scripts/test_full_workflow.py
```

**Validate Outputs:**
```bash
python scripts/validate_workflow_outputs.py
```

**PRISMA Tests:**
```bash
make test-prisma
# or
python scripts/run_prisma_tests.py
```

## Debugging

**Enable Debug Mode:**
```bash
python main.py --debug
```

**Verbose Output:**
```bash
python main.py --verbose
```

**Log to File:**
```bash
python main.py --verbose --log-to-file --log-file logs/workflow.log
```

## Development

**Install in Development Mode:**
```bash
uv pip install -e .
```

**Format Code:**
```bash
make lint
# or
ruff check --fix src/ main.py
ruff format src/ main.py
```

**Dependencies**: Managed via `uv` (see `pyproject.toml`)

## Troubleshooting

**"No papers found"**
- Check search query is not too specific
- Verify databases are enabled in `config/workflow.yaml`
- Test database connectors: `python scripts/test_database_health.py`

**"LLM API Error"**
- Verify LLM API key is set (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.)
- Check API key is valid and has credits
- Try a different LLM provider

**"Rate limit exceeded"**
- Wait a few minutes and retry
- Set API keys for higher rate limits
- Enable caching to reduce API calls

**SSL Certificate Errors**
- Update certificates: `pip install --upgrade certifi`
- Set certificate path: `export SSL_CERT_FILE=$(python -m certifi)`

## Features

- **Multi-Database Search**: PubMed, arXiv, Semantic Scholar, Crossref, ACM
- **PRISMA 2020 Compliance**: Automatic PRISMA-compliant reports and diagrams
- **LLM-Powered Screening**: Intelligent screening with cost optimization
- **Structured Data Extraction**: Pydantic schemas for type-safe extraction
- **Quality Assessment**: Risk of bias (RoB 2, ROBINS-I) and GRADE assessments
- **Automatic Checkpointing**: Resume from any phase
- **Bibliometric Visualizations**: Charts and interactive network graphs
- **Citation Management**: IEEE-formatted references and BibTeX export
- **Export Formats**: LaTeX and Word document export

## License

MIT
