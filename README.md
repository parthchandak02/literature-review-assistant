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

# Install optional dependencies for manuscript pipeline (optional but recommended)
uv pip install -e ".[manubot-full]"

# Or install individually:
uv pip install manubot gitpython pypandoc

# Install Pandoc (system-level dependency, required for PDF/DOCX generation)
# macOS:
brew install pandoc

# Linux:
# apt-get install pandoc
# or
# yum install pandoc

# Windows: Download from https://pandoc.org/installing.html
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
# Basic run (automatically resumes from latest checkpoint if available)
python main.py

# Force fresh start (ignore all checkpoints, start from scratch)
python main.py --force-fresh

# With manuscript pipeline features
python main.py --manubot-export --build-package --journal ieee

# Verbose output with logging
python main.py --verbose --log-to-file --log-file logs/workflow.log

# Or use Makefile
make setup    # Create venv
make install  # Install dependencies
make run      # Run workflow
```

### Step 5: Check Outputs

Results are saved to `data/outputs/workflow_{topic}_{timestamp}/`:
- Each workflow run gets its own directory to prevent overwriting
- `final_report.md` - Complete systematic review article
- `references.bib` - BibTeX citation file (if BibTeX export enabled)
- `prisma_diagram.png` - PRISMA 2020 flow diagram
- `papers_per_year.png` - Publication timeline
- `network_graph.html` - Interactive citation/co-occurrence network
- `papers_by_country.png` - Geographic distribution
- `papers_by_subject.png` - Subject area distribution
- `workflow_state.json` - Workflow metadata

Search logs (PRISMA-compliant) are saved to `data/outputs/workflow_{topic}_{timestamp}/search_logs/`:
- `prisma_search_report_*.json` - PRISMA-S compliant search report
- `search_summary_*.csv` - CSV summary of all searches

## Workflow Overview

The system executes 16+ sequential phases: Build Search Strategy, Search Databases, Deduplication, Title/Abstract Screening, Full-text Screening, Paper Enrichment, Data Extraction, Quality Assessment, PRISMA Diagram Generation, Visualization Generation, Article Writing, Final Report Compilation, Search Strategy Export, PRISMA Checklist Generation, Data Extraction Forms, Export to Formats, Manubot Export (optional), and Submission Package Generation (optional).

**Checkpoint System**: The workflow automatically saves checkpoints after each phase in `data/checkpoints/workflow_{id}/`, allowing you to resume from any point. When running `python main.py` with the same topic, it automatically resumes from the latest checkpoint. Each workflow run gets a unique ID based on topic and timestamp, ensuring outputs and checkpoints are organized separately.

**Force Fresh Start**: To ignore checkpoints and start from scratch:
```bash
# Force fresh start from phase 1 (ignores all checkpoints)
python main.py --force-fresh

# Or explicitly specify starting phase
python main.py --start-from-phase 1
```

**Disable Checkpoint Saving**: To prevent saving new checkpoints:
```bash
python main.py --no-save-checkpoints
```

**Phase Registry Architecture**: The workflow uses a Phase Registry pattern for declarative phase management with automatic dependency resolution, simplifying workflow execution and making it easy to add new phases.

## Text Humanization

The system includes an advanced text humanization feature that improves the naturalness and human-like quality of generated manuscripts.

### How It Works

1. **Style Pattern Extraction**: After full-text screening, the system extracts writing patterns from eligible papers (reuses cached full-text, no additional API calls)
2. **Enhanced Prompts**: Writing agents receive style guidelines based on extracted patterns
3. **Naturalness Scoring**: LLM evaluates text quality across multiple dimensions
4. **Post-Processing**: Text is refined iteratively until naturalness threshold is met

### Configuration

Enable/configure in `config/workflow.yaml`:

```yaml
writing:
  style_extraction:
    enabled: true                    # Extract writing patterns from eligible papers
    model: "gemini-2.5-pro"          # LLM model for section extraction
    max_papers: null                 # Max papers to analyze (null = all eligible)
    min_papers: 3                    # Minimum papers required for pattern extraction
  
  humanization:
    enabled: true                    # Enable text humanization post-processing
    model: "gemini-2.5-pro"          # LLM model for humanization
    temperature: 0.3                  # Temperature for variation
    max_iterations: 2                # Max refinement iterations
    naturalness_threshold: 0.75      # Minimum naturalness score (0.0-1.0)
    section_specific: true            # Use section-specific strategies
```

### Naturalness Dimensions

The system evaluates text across:
- **Sentence Structure Diversity**: Variation in sentence types (simple, compound, complex)
- **Vocabulary Richness**: Synonym usage and domain-specific terms
- **Citation Naturalness**: Natural placement and varied phrasing
- **Transition Quality**: Natural connectors, avoiding formulaic phrases
- **Overall Human-Like Quality**: Weighted average of all dimensions

### Efficiency Benefits

- **No Additional API Calls**: Reuses full-text already retrieved during screening
- **Domain-Relevant**: Patterns extracted from papers in the same topic area
- **Workflow-Integrated**: Patterns extracted before writing, stored in checkpoints
- **Automatic**: Runs automatically when enabled, no manual intervention needed

## Manuscript Pipeline

The system includes an integrated manuscript pipeline for generating submission-ready packages. Phases 17-18 are automatically executed when enabled in configuration.

### Enabling Manuscript Pipeline

Edit `config/workflow.yaml`:

```yaml
manubot:
  enabled: true  # Enable Manubot export (Phase 17)
  output_dir: "manuscript"
  citation_style: "ieee"
  auto_resolve_citations: true

submission:
  enabled: true  # Enable submission package generation (Phase 18)
  default_journal: "ieee"
  generate_pdf: true
  generate_docx: true
  generate_html: true
```

### Manubot Integration (Phase 17)

Export your systematic review to Manubot-compatible structure:

```bash
# Automatic execution when enabled in config
python main.py

# Or manual export
python main.py --manubot-export
```

This creates a `manuscript/` directory with:
- `content/` - Structured markdown files for each section
- `manubot.yaml` - Manubot configuration
- Organized sections ready for collaborative editing

**Checkpoint Support**: Phase 17 checkpoints are saved automatically, allowing resumption from this phase.

### Submission Package Generation (Phase 18)

Build complete submission packages for journals:

```bash
# Automatic execution when enabled in config
python main.py

# Or manual package building
python main.py --build-package --journal ieee
```

This generates a `submission_package_ieee/` directory containing:
- Manuscript in PDF, DOCX, and HTML formats
- Figures directory with all visualizations
- Supplementary materials (search strategies, PRISMA checklist, etc.)
- References in BibTeX and RIS formats
- Submission checklist for validation

**Checkpoint Support**: Phase 18 checkpoints are saved automatically, allowing resumption from this phase.

## Citation Resolution

The system supports automatic citation resolution from identifiers using Manubot. This allows you to cite papers without manually entering metadata.

### Supported Identifier Types

- **DOI**: `doi:10.1038/nbt.3780` or `10.1038/nbt.3780`
- **PubMed ID**: `pmid:29424689` or `29424689`
- **arXiv ID**: `arxiv:1407.3561` or `arXiv:1407.3561`
- **Generic citekeys**: Any Manubot-supported citekey format

### Manual Resolution

Resolve a single citation from command line:

```bash
python main.py --resolve-citation doi:10.1038/nbt.3780
python main.py --resolve-citation pmid:29424689
python main.py --resolve-citation arxiv:1407.3561
```

### Auto-Resolution

Enable automatic citation resolution during export:

```yaml
manubot:
  enabled: true
  auto_resolve_citations: true
```

When enabled, citations in Manubot format (`[@doi:...]`, `[@pmid:...]`) are automatically resolved and added to the citation list during manuscript export.

### Error Handling

If citation resolution fails:
- Verify identifier format is correct
- Check internet connection
- Try manual resolution: `python main.py --resolve-citation doi:10.1038/...`
- Some identifiers may require Manubot package: `pip install manubot`

### Journal Support

List available journals:

```bash
python main.py --list-journals
```

Validate submission package:

```bash
python main.py --validate-submission --journal ieee
```

## CSL Citation Styles

The system supports Citation Style Language (CSL) styles for flexible citation formatting.

### Supported Styles

- IEEE
- APA
- Nature
- PLOS ONE
- PLOS Computational Biology
- BMJ
- AMA
- Vancouver
- Harvard
- Chicago
- MLA

### Changing Citation Style

Edit `config/workflow.yaml`:

```yaml
manubot:
  citation_style: "apa"  # Change from "ieee" to "apa"
```

### Custom Styles

1. Download CSL style from https://github.com/citation-style-language/styles
2. Place in `data/cache/csl_styles/`
3. Reference by filename (without .csl extension)

Styles are automatically downloaded and cached on first use.

## Submission Packages

Generate complete submission packages for journal submission with all required files.

### Package Contents

A submission package includes:
- Manuscript in PDF, DOCX, and HTML formats
- Figures directory with all visualizations
- Tables directory (if applicable)
- Supplementary materials (search strategies, PRISMA checklist, data extraction forms)
- References in BibTeX and RIS formats
- Submission checklist for validation

### Building Packages

#### Single Journal

```bash
python main.py --build-package --journal ieee
```

#### Multiple Journals

Edit `config/workflow.yaml`:

```yaml
submission:
  enabled: true
  journals: ["ieee", "nature", "plos"]
```

Or use Python:

```python
from src.export.submission_package import SubmissionPackageBuilder
from pathlib import Path

# Note: Use workflow-specific output directory (e.g., data/outputs/workflow_{topic}_{timestamp}/)
builder = SubmissionPackageBuilder(Path("data/outputs/workflow_{topic}_{timestamp}"))
packages = builder.build_for_multiple_journals(
    workflow_outputs,
    journals=["ieee", "nature", "plos"],
    manuscript_markdown=Path("data/outputs/workflow_{topic}_{timestamp}/final_report.md"),
)
```

### Validation

Validate submission package:

```bash
python main.py --validate-submission --journal ieee
```

Or check the `submission_checklist.md` file in the package directory.

### Journal-Specific Requirements

Each journal has specific requirements defined in `config/journals.yaml`:
- Required sections
- Page limits
- Figure formats
- Citation styles

## Journal Templates

The system includes LaTeX templates for journal-specific formatting.

### Available Templates

Templates are in `templates/journals/`:
- `ieee.latex` - IEEE Transactions template
- `nature.latex` - Nature template
- `plos.latex` - PLOS template

### Custom Templates

Create custom template:

```python
from src.export.template_manager import TemplateManager

manager = TemplateManager()
template_content = """
% Custom Template
\\documentclass{article}
...
"""
manager.create_custom_template("myjournal", template_content)
```

Templates are automatically used when generating PDFs via Pandoc.

## Git Integration

The system includes Git integration for manuscript version control.

### Initialize Repository

```python
from src.version_control.git_manager import GitManuscriptManager
from pathlib import Path

# Note: Use workflow-specific manuscript directory (e.g., data/outputs/workflow_{topic}_{timestamp}/manuscript)
git_manager = GitManuscriptManager(Path("data/outputs/workflow_{topic}_{timestamp}/manuscript"))
git_manager.initialize_repo()
git_manager.commit_changes("Initial manuscript export")
```

### Create Branch

```python
git_manager.create_branch("revisions")
```

### Check Status

```python
status = git_manager.get_status()
print(status)
```

### CI/CD Integration

GitHub Actions workflow (`.github/workflows/manuscript-build.yml`) automatically:
- Runs workflow on push/PR
- Builds Manubot manuscript
- Generates PDF/DOCX/HTML
- Uploads artifacts

### Configuration

Enable Manubot and submission package generation in `config/workflow.yaml`:

```yaml
manubot:
  enabled: true
  output_dir: "manuscript"
  citation_style: "ieee"
  auto_resolve_citations: true

submission:
  enabled: true
  default_journal: "ieee"
  generate_pdf: true
  generate_docx: true
  generate_html: true
  include_supplementary: true
  validate_before_package: true
```

### Journal Configuration

Configure journals in `config/journals.yaml`:

```yaml
journals:
  ieee:
    name: "IEEE Transactions"
    citation_style: "ieee"
    template: "ieee.latex"
    max_pages: 12
    required_sections:
      - "abstract"
      - "introduction"
      - "methods"
      - "results"
      - "discussion"
```

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

### Optional: Manuscript Pipeline Dependencies

**Manubot** (for citation resolution):
```bash
pip install manubot
```
Note: Manubot features are optional. The system gracefully degrades if not installed.

**Pandoc** (for PDF/DOCX/HTML generation):
- System-level dependency (not a Python package)
- Install separately: `brew install pandoc` (macOS) or `apt-get install pandoc` (Linux)
- Required for PDF/DOCX/HTML generation

### Optional: Bibliometric Features

**Bibliometric Dependencies** (for enhanced Scopus and Google Scholar features):
```bash
pip install -e ".[bibliometrics]"
# or
pip install pybliometrics scholarly
```

**pybliometrics** (for enhanced Scopus features):
- Author profiles, citation metrics, affiliation details
- Requires Scopus API key: `SCOPUS_API_KEY`

**scholarly** (for Google Scholar integration):
- Author search, citation tracking, related articles
- Proxy highly recommended: Set `SCRAPERAPI_KEY` or enable proxy in config

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

**Google Scholar** (Optional, requires bibliometrics dependencies):
```bash
# Install bibliometric dependencies
pip install -e ".[bibliometrics]"

# Set proxy (highly recommended to avoid CAPTCHAs)
SCRAPERAPI_KEY=your_scraperapi_key
# Or configure proxy in workflow.yaml
```

**Scopus** (Enhanced features with pybliometrics):
```bash
# Install bibliometric dependencies
pip install -e ".[bibliometrics]"

# Set API key
SCOPUS_API_KEY=your_scopus_api_key
```

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

**Screening Safeguards**:
```yaml
screening_safeguards:
  minimum_papers: 10  # Minimum papers required to pass full-text screening
  enable_manual_review: true  # Pause workflow for manual review if threshold not met
  show_borderline_papers: true  # Show borderline papers for review
```

The screening safeguard system monitors inclusion rates and flags when fewer than the minimum required papers pass screening. This helps identify when:
- Inclusion criteria are too strict
- Exclusion criteria are too broad
- Search strategy needs refinement

When the threshold is not met, the workflow will:
- Display warnings/errors with recommendations
- Identify borderline papers (excluded but with low confidence)
- Export borderline papers to `borderline_papers_for_review.json` for manual review
- Pause the workflow (if `enable_manual_review: true`) to allow criteria adjustment

**Interpreting Safeguard Warnings**:
- **Title/Abstract Stage**: Warning only - workflow continues but recommends reviewing criteria
- **Full-Text Stage**: Error - workflow pauses (if enabled) requiring manual review before proceeding

**Best Practices**:
- Review borderline papers to determine if criteria should be relaxed
- Adjust inclusion/exclusion criteria in `config/workflow.yaml` if needed
- Consider refining search strategy if too few papers are found initially
- Document any criteria adjustments in your methods section

All agent configurations are in the YAML file - no code changes needed to modify agent behavior!

**Text Humanization Configuration**:
```yaml
writing:
  style_extraction:
    enabled: true                    # Extract writing patterns from eligible papers
    model: "gemini-2.5-pro"          # LLM model for section extraction
    max_papers: null                 # Max papers to analyze (null = all eligible)
    min_papers: 3                    # Minimum papers required for pattern extraction
  
  humanization:
    enabled: true                    # Enable text humanization post-processing
    model: "gemini-2.5-pro"          # LLM model for humanization
    temperature: 0.3                  # Temperature for variation
    max_iterations: 2                # Max refinement iterations
    naturalness_threshold: 0.75      # Minimum naturalness score (0.0-1.0)
    section_specific: true            # Use section-specific strategies
```

The humanization system:
- Extracts writing style patterns from eligible papers (reuses full-text already retrieved)
- Enhances writing agent prompts with extracted patterns
- Post-processes generated text to improve naturalness
- Scores text quality across multiple dimensions (sentence structure, vocabulary, citations, transitions)
- Iteratively refines text until naturalness threshold is met

## Project Structure

```
literature-review-assistant/
├── src/                    # Source code
│   ├── orchestration/     # Workflow orchestration
│   │   ├── workflow_manager.py      # Main orchestrator
│   │   ├── phase_registry.py        # Phase registry system
│   │   ├── checkpoint_manager.py    # Checkpoint management
│   │   ├── phase_executor.py        # Phase execution logic
│   │   └── ...
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

**Test Manuscript Pipeline (E2E):**
```bash
python scripts/test_manuscript_pipeline_e2e.py
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

**Test Phase Registry System:**
```bash
pytest tests/unit/orchestration/ -v
pytest tests/integration/test_workflow_registry_integration.py -v
```

**Test Checkpoint Resumption:**
```bash
# Run workflow once to create checkpoints
python main.py

# Run again - should resume from latest checkpoint
python main.py

# Force fresh start (ignore checkpoints)
python main.py --force-fresh

# Verify phases 17-18 checkpoints exist
ls -la data/checkpoints/workflow_*/manubot_export_state.json
ls -la data/checkpoints/workflow_*/submission_package_state.json
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

## Architecture

The workflow uses a Phase Registry pattern for declarative phase management:
- **PhaseRegistry**: Registers phases with dependencies and metadata
- **CheckpointManager**: Centralized checkpoint save/load
- **PhaseExecutor**: Handles phase execution with dependency checking

This architecture simplifies workflow management and makes it easy to add new phases.

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

**"Manubot not available"**
- Install Manubot: `pip install manubot`
- Citation resolution features will be disabled if not installed

**"Pandoc not found"**
- Install Pandoc on your system (see Quick Start Step 1)
- PDF/DOCX/HTML generation requires Pandoc
- System-level installation required (not a Python package)

**"Citation resolution failed"**
- Verify identifier format (DOI, PMID, etc.)
- Check internet connection
- Try manual resolution: `python main.py --resolve-citation doi:10.1038/...`
- Some identifiers may require network access

**"Submission package incomplete"**
- Check `submission_checklist.md` for missing items
- Verify all workflow phases completed successfully
- Ensure figures and supplementary materials exist
- Run validation: `python main.py --validate-submission --journal ieee`

**"CSL style not found"**
- Styles are downloaded automatically on first use
- Check internet connection
- Manually download from https://github.com/citation-style-language/styles
- Place in `data/cache/csl_styles/`

## Features

- **Phase Registry Architecture**: Declarative phase management with automatic dependency resolution
- **Multi-Database Search**: PubMed, arXiv, Semantic Scholar, Crossref, ACM, Google Scholar (optional)
- **Bibliometric Features**: Author profiles, citation metrics, citation networks (requires optional dependencies)
- **PRISMA 2020 Compliance**: Automatic PRISMA-compliant reports and diagrams
- **LLM-Powered Screening**: Intelligent screening with cost optimization
- **Screening Safeguards**: Automatic detection of low inclusion rates with borderline paper identification
- **Structured Data Extraction**: Pydantic schemas for type-safe extraction
- **Quality Assessment**: Risk of bias (RoB 2, ROBINS-I) and GRADE assessments
- **Automatic Checkpointing**: Resume from any phase, force fresh start with `--force-fresh`
- **Text Humanization**: Style pattern extraction from eligible papers and LLM-based naturalness refinement
- **Bibliometric Visualizations**: Charts and interactive network graphs
- **Citation Management**: IEEE-formatted references and BibTeX export
- **Export Formats**: LaTeX and Word document export
- **Manubot Integration**: Export to Manubot structure for collaborative writing
- **Automatic Citation Resolution**: Resolve citations from DOI, PubMed ID, arXiv ID
- **Multi-Journal Support**: Generate submission packages for multiple journals
- **Submission Package Builder**: Complete packages with all required files
- **CSL Citation Styles**: Support for IEEE, APA, Nature, PLOS, and more

## Bibliometric Features (Optional)

The system includes enhanced bibliometric capabilities powered by pybliometrics (Scopus) and scholarly (Google Scholar). These features are optional and require additional dependencies.

### Installation

Install bibliometric dependencies:

```bash
pip install -e ".[bibliometrics]"
# or
pip install pybliometrics scholarly
```

### Features

**Enhanced Scopus Connector:**
- Author profile retrieval with h-index, citation counts, coauthors
- Affiliation details (institution, country, city)
- Subject area classifications
- Citation metrics per author

**Google Scholar Connector:**
- Publication search
- Author search and profiles
- Citation tracking (find papers citing a given paper)
- Related articles discovery

**Author Service:**
- Unified interface for author retrieval across databases
- Author profile aggregation from multiple sources
- Bibliometric metrics collection

**Citation Network Builder:**
- Build citation networks from papers
- Track citation relationships
- Export network graphs for visualization

### Configuration

Enable bibliometric features in `config/workflow.yaml`:

```yaml
workflow:
  databases: ["PubMed", "arXiv", "Semantic Scholar", "Crossref", "ACM", "Google Scholar"]
  
  # Bibliometrics settings
  bibliometrics:
    enabled: true
    include_author_metrics: true
    include_citation_networks: true
    include_subject_areas: true
    include_coauthors: true
    include_affiliations: true
  
  # Google Scholar specific settings
  google_scholar:
    enabled: true
    use_proxy: true  # Highly recommended to avoid CAPTCHAs
    proxy_type: "scraperapi"  # Options: scraperapi, free, none
```

### Usage Examples

**Retrieve Author Profile:**

```python
from src.search.author_service import AuthorService
from src.search.database_connectors import ScopusConnector

# Create connectors
scopus = ScopusConnector(api_key="your_scopus_key")
connectors = {"Scopus": scopus}

# Create author service
author_service = AuthorService(connectors)

# Get author by ID
author = author_service.get_author("12345678", database="Scopus")
print(f"Author: {author.name}, h-index: {author.h_index}")

# Search authors
authors = author_service.search_author("John Smith", database="Scopus")
```

**Build Citation Network:**

```python
from src.search.citation_network import CitationNetworkBuilder
from src.search.connectors.google_scholar_connector import GoogleScholarConnector

# Create citation network builder
gs_connector = GoogleScholarConnector(use_proxy=True)
network_builder = CitationNetworkBuilder(google_scholar_connector=gs_connector)

# Add papers and build network
network_data = network_builder.build_network_from_papers(papers)
stats = network_builder.get_citation_statistics()

# Export as NetworkX graph
G = network_builder.export_networkx_graph()
```

**Enhanced Scopus Search:**

```python
from src.search.database_connectors import ScopusConnector

scopus = ScopusConnector(api_key="your_key")

# Search papers (now includes citation_count, subject_areas, eid)
papers = scopus.search("machine learning", max_results=10)

# Retrieve author by ID
author = scopus.get_author_by_id("12345678")

# Retrieve affiliation details
affiliation = scopus.get_affiliation_by_id("60105007")

# Search authors
authors = scopus.search_authors("AUTHLAST(Smith) AND AUTHFIRST(John)")
```

## Examples

### Citation Resolution

Resolve citations during workflow:

```bash
# Resolve single citation
python main.py --resolve-citation doi:10.1038/nbt.3780

# Use in manuscript (auto-resolved if enabled)
# Write: "Previous work [@doi:10.1038/nbt.3780] showed..."
# System resolves to: "Previous work [1] showed..."
```

### Multi-Journal Submission

Generate packages for multiple journals:

```python
from src.export.submission_package import SubmissionPackageBuilder
from pathlib import Path

builder = SubmissionPackageBuilder(Path("data/outputs"))
packages = builder.build_for_multiple_journals(
    workflow_outputs,
    journals=["ieee", "nature", "plos"],
    manuscript_markdown=Path("data/outputs/final_report.md"),
)

for journal, package_dir in packages.items():
    print(f"{journal}: {package_dir}")
```

### Custom Template

Create and use custom journal template:

```python
from src.export.template_manager import TemplateManager

manager = TemplateManager()
template_content = """
\\documentclass{article}
\\usepackage{...}
\\begin{document}
$body$
\\end{document}
"""
manager.create_custom_template("myjournal", template_content)
```

### Git Workflow

Version control for manuscript:

```python
from src.version_control.git_manager import GitManuscriptManager
from pathlib import Path

# Initialize repository
git_manager = GitManuscriptManager(Path("data/outputs/manuscript"))
git_manager.initialize_repo()

# Make changes to manuscript files...

# Commit changes
git_manager.commit_changes("Updated introduction section")

# Create revision branch
git_manager.create_branch("revision-round-1")
git_manager.commit_changes("Addressed reviewer comments")
```

### Complete Workflow with Manuscript Pipeline

```bash
# Run full workflow with Manubot export and submission package
python main.py --manubot-export --build-package --journal ieee

# Or enable in config/workflow.yaml and run normally
python main.py
```

## License

MIT
