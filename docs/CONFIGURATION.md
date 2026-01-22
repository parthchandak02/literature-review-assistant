# Configuration Reference

Complete reference for all configuration options in `config/workflow.yaml`.

## Table of Contents

- [Research Topic](#research-topic)
- [Workflow Settings](#workflow-settings)
- [Inclusion/Exclusion Criteria](#inclusionexclusion-criteria)
- [Screening Safeguards](#screening-safeguards)
- [Agent Configurations](#agent-configurations)
- [Quality Assessment](#quality-assessment)
- [Text Humanization](#text-humanization)
- [Manubot Configuration](#manubot-configuration)
- [Submission Configuration](#submission-configuration)

## Research Topic

```yaml
topic:
  topic: "LLM-Powered Health Literacy Chatbots for Low-Income Communities"
  keywords: ["health literacy", "chatbots", "LLM", "low-income"]
  domain: "public health"
  scope: "Focus on LLM-powered chatbots designed to improve health literacy"
  research_question: "What is the effectiveness of LLM-powered health literacy chatbots?"
```

## Workflow Settings

```yaml
workflow:
  databases: ["PubMed", "arXiv", "Semantic Scholar", "Crossref", "ACM"]
  date_range:
    start: null  # null = no start date limit
    end: 2025    # End year
  max_results_per_db: 100
  
  # Bibliometrics settings (optional)
  bibliometrics:
    enabled: true
    include_author_metrics: true
    include_citation_networks: true
    include_subject_areas: true
    include_coauthors: true
    include_affiliations: true
  
  # Google Scholar specific settings (optional)
  google_scholar:
    enabled: true
    use_proxy: true  # Highly recommended to avoid CAPTCHAs
    proxy_type: "scraperapi"  # Options: scraperapi, free, none
```

## Inclusion/Exclusion Criteria

```yaml
criteria:
  inclusion:
    - "Studies on LLM/chatbot interventions for health literacy"
    - "Peer-reviewed articles"
    - "Published in English"
  
  exclusion:
    - "Non-LLM chatbots (rule-based or simple keyword matching)"
    - "Conference abstracts without full papers"
    - "Studies not focused on health literacy outcomes"
```

## Screening Safeguards

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

## Agent Configurations

All agent configurations are in the YAML file - no code changes needed to modify agent behavior!

### Search Strategy Agent

```yaml
agents:
  search_strategy:
    model: "gemini-2.0-flash"
    temperature: 0.7
    tools: ["database_search", "query_builder"]
```

### Screening Agents

```yaml
agents:
  title_abstract_screening:
    model: "gemini-2.0-flash-lite"
    temperature: 0.3
    max_papers_per_batch: 50
  
  fulltext_screening:
    model: "gemini-2.0-flash-lite"
    temperature: 0.3
    max_papers_per_batch: 20
```

### Data Extraction Agent

```yaml
agents:
  data_extraction:
    model: "gemini-2.0-pro"
    temperature: 0.2
    structured_output: true
```

### Writing Agents

```yaml
agents:
  introduction:
    model: "gemini-2.0-pro"
    temperature: 0.7
  
  methods:
    model: "gemini-2.0-pro"
    temperature: 0.5
  
  results:
    model: "gemini-2.0-pro"
    temperature: 0.6
  
  discussion:
    model: "gemini-2.0-pro"
    temperature: 0.7
  
  abstract:
    model: "gemini-2.0-pro"
    temperature: 0.5
```

## Quality Assessment

```yaml
quality_assessment:
  risk_of_bias_tool: "RoB 2"  # Options: "RoB 2", "ROBINS-I", "CASP"
  grade_assessment: true      # Enable GRADE certainty assessment
  auto_fill: true              # Automatically fill assessments using LLM (default: true)
  template_path: "data/quality_assessments/{workflow_id}_assessments.json"
```

## Text Humanization

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

## Manubot Configuration

```yaml
manubot:
  enabled: true  # Enable Manubot export (Phase 17)
  output_dir: "manuscript"
  citation_style: "ieee"  # Options: ieee, apa, nature, plos, etc.
  auto_resolve_citations: true
```

## Submission Configuration

```yaml
submission:
  enabled: true  # Enable submission package generation (Phase 18)
  default_journal: "ieee"
  generate_pdf: true
  generate_docx: true
  generate_html: true
  include_supplementary: true
  validate_before_package: true
  journals: ["ieee", "nature", "plos"]  # For multi-journal packages
```

## Journal Configuration

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

## Environment Variables

See [API Keys Required](../README.md#api-keys-required) in the main README for environment variable configuration.
