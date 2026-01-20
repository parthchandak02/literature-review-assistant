# Project Structure and Dependency Analysis

## Overview

This document provides a comprehensive overview of the Research Article Writer project structure, dependencies, and workflow architecture.

## Project Architecture

### Entry Point

- **`main.py`**: Main entry point that initializes `WorkflowManager` and executes the systematic review workflow

### Core Components

#### 1. Orchestration (`src/orchestration/`)
- **`workflow_manager.py`**: Main workflow orchestrator managing 12 sequential phases
- **`database_connector_factory.py`**: Factory for creating database connectors
- **`workflow_graph.py`**: LangGraph-based workflow (NOT CURRENTLY USED)

#### 2. Search (`src/search/`)
- **`database_connectors.py`**: Database connector implementations (PubMed, arXiv, Semantic Scholar, etc.)
- **`search_strategy.py`**: Search strategy builder
- **`multi_database_searcher.py`**: Coordinates searches across multiple databases
- **`search_logger.py`**: PRISMA-S compliant search logging

#### 3. Screening (`src/screening/`)
- **`base_agent.py`**: Base class for screening agents
- **`title_abstract_agent.py`**: Title/abstract screening agent
- **`fulltext_agent.py`**: Full-text screening agent

#### 4. Extraction (`src/extraction/`)
- **`data_extractor_agent.py`**: Extracts structured data from papers

#### 5. Writing (`src/writing/`)
- **`introduction_agent.py`**: Writes introduction section
- **`methods_agent.py`**: Writes methods section
- **`results_agent.py`**: Writes results section
- **`discussion_agent.py`**: Writes discussion section
- **`abstract_agent.py`**: Generates PRISMA 2020 abstract

#### 6. PRISMA (`src/prisma/`)
- **`prisma_generator.py`**: Generates PRISMA 2020 flow diagrams
- **`checklist_generator.py`**: Generates PRISMA 2020 checklist

#### 7. Quality Assessment (`src/quality/`)
- **`risk_of_bias_assessor.py`**: Assesses risk of bias using RoB 2/ROBINS-I
- **`grade_assessor.py`**: Assesses certainty of evidence using GRADE

#### 8. Export (`src/export/`)
- **`latex_exporter.py`**: Exports to LaTeX format
- **`word_exporter.py`**: Exports to Word format
- **`extraction_form_generator.py`**: Generates data extraction forms

#### 9. Visualization (`src/visualization/`)
- **`charts.py`**: Generates bibliometric visualizations (network graphs, charts)

#### 10. Citations (`src/citations/`)
- **`citation_manager.py`**: Manages citations and references
- **`ieee_formatter.py`**: Formats citations in IEEE style
- **`bibtex_formatter.py`**: Formats citations in BibTeX format

#### 11. Tools (`src/tools/`)
- **`tool_registry.py`**: Tool registry for agent function calling
- **`database_search_tool.py`**: Database search tool
- **`exa_tool.py`**: Exa search tool
- **`tavily_tool.py`**: Tavily search tool
- **`query_builder_tool.py`**: Query builder tool

#### 12. Utils (`src/utils/`)
- **`state_serialization.py`**: Serializes/deserializes workflow state
- **`pdf_retriever.py`**: Retrieves full-text PDFs
- **`screening_validator.py`**: Validates screening decisions

#### 13. Validation (`src/validation/`)
- **`prisma_validator.py`**: Validates PRISMA 2020 compliance

## Workflow Phases

The system executes 12 sequential phases:

1. **Build Search Strategy** - Creates search queries for each database
2. **Search Databases** - Searches PubMed, arXiv, Semantic Scholar, Crossref, ACM
3. **Deduplication** - Removes duplicate papers
4. **Title/Abstract Screening** - Screens papers based on title and abstract
5. **Full-text Screening** - Screens papers based on full-text content
6. **Final Inclusion** - Determines final included papers
7. **Paper Enrichment** - Enriches papers with missing metadata
8. **Data Extraction** - Extracts structured data from papers
9. **Quality Assessment** - Assesses risk of bias and certainty of evidence
10. **PRISMA Diagram Generation** - Generates PRISMA 2020 flow diagram
11. **Visualization Generation** - Generates bibliometric visualizations
12. **Article Writing** - Writes Introduction, Methods, Results, Discussion, Abstract
13. **Final Report Compilation** - Compiles final report with all sections

## Checkpoint System

The workflow automatically saves checkpoints after each phase, allowing resumption from any point. Checkpoints are saved in `data/workflows/{workflow_id}/` directory.

### Phase Dependencies

```
search_databases -> []
deduplication -> [search_databases]
title_abstract_screening -> [deduplication]
fulltext_screening -> [title_abstract_screening]
paper_enrichment -> [fulltext_screening]
data_extraction -> [paper_enrichment]
quality_assessment -> [data_extraction]
article_writing -> [data_extraction]
```

## Data Flow

```
main.py
  -> WorkflowManager.run()
    -> Phase 1: Build Search Strategy
      -> SearchStrategyBuilder
    -> Phase 2: Search Databases
      -> MultiDatabaseSearcher
        -> DatabaseConnectors (PubMed, arXiv, etc.)
    -> Phase 3: Deduplication
      -> Deduplicator
    -> Phase 4: Title/Abstract Screening
      -> TitleAbstractScreener (LLM Agent)
    -> Phase 5: Full-text Screening
      -> FullTextScreener (LLM Agent)
    -> Phase 6: Paper Enrichment
      -> PaperEnricher
    -> Phase 7: Data Extraction
      -> DataExtractorAgent (LLM Agent)
    -> Phase 8: Quality Assessment
      -> RiskOfBiasAssessor, GradeAssessor
    -> Phase 9: PRISMA Diagram
      -> PRISMAGenerator
    -> Phase 10: Visualizations
      -> ChartsGenerator
    -> Phase 11: Article Writing
      -> IntroductionWriter, MethodsWriter, ResultsWriter, DiscussionWriter, AbstractGenerator
    -> Phase 12: Final Report
      -> ReportCompiler
```

## Dependency Relationships

See `dependency_diagram.mmd` for visual dependency graph.

### Key Dependencies

- **WorkflowManager** depends on:
  - Search components (database connectors, search strategy)
  - Screening agents
  - Extraction agents
  - Writing agents
  - PRISMA generator
  - Visualization generator
  - Export generators

- **Writing Agents** depend on:
  - BaseScreeningAgent (LLM integration)
  - CitationManager
  - ToolRegistry (for function calling)

- **PRISMA Generator** depends on:
  - PRISMACounter (count tracking)
  - prisma-flow-diagram library

## Output Files

All outputs are saved to `data/outputs/`:

- `final_report.md` - Complete systematic review article
- `references.bib` - BibTeX citation file
- `prisma_diagram.png` - PRISMA 2020 flow diagram
- `prisma_checklist.json` - PRISMA 2020 checklist
- `search_strategies.md` - Search strategies for each database
- `data_extraction_form.md` - Data extraction form
- `*.png` - Bibliometric visualizations
- `network_graph.html` - Interactive citation network

## Configuration

- **`config/workflow.yaml`**: Unified configuration file for:
  - Research topic and research question
  - Database selection
  - Agent configurations (LLM models, temperature)
  - Inclusion/exclusion criteria
  - Output settings

## Testing

- **`tests/unit/`**: Unit tests for individual components
- **`tests/integration/`**: Integration tests for component interactions
- **`tests/e2e/`**: End-to-end workflow tests
- **`scripts/test_*.py`**: Test scripts for specific functionality

## Scripts

- **`scripts/test_database_health.py`**: Tests database connectors
- **`scripts/test_stage.py`**: Tests individual workflow stages
- **`scripts/validate_workflow_outputs.py`**: Validates generated outputs
- **`scripts/run_prisma_tests.py`**: Runs PRISMA compliance tests
- **`scripts/analyze_dependencies.py`**: Analyzes project dependencies
- **`scripts/check_broken_imports.py`**: Checks for broken imports

## Recent Fixes

### PRISMA Count Calculation
- Fixed `assessed` count calculation to properly track papers assessed
- Improved validation logic to catch count mismatches
- Fixed auto-correction to not violate PRISMA rules

### Import Error
- Verified `get_llm_tool` import error is resolved (not present in current codebase)

### Missing Checkpoint
- `paper_enrichment` checkpoint handling improved with fallback logic

## Visualization Files

Generated dependency analysis files:
- `docs/dependency_analysis/dependency_map.json` - Module dependency map
- `docs/dependency_analysis/dependency_diagram.mmd` - Mermaid dependency diagram
- `docs/dependency_analysis/workflow_architecture.mmd` - Workflow architecture diagram
- `docs/dependency_analysis/import_analysis.json` - Import analysis report
