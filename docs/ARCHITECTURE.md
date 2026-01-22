# Architecture

Architecture overview and design patterns used in the Literature Review Assistant.

## Table of Contents

- [Overview](#overview)
- [Phase Registry Pattern](#phase-registry-pattern)
- [Core Components](#core-components)
- [Data Flow](#data-flow)
- [Module Dependencies](#module-dependencies)

## Overview

The workflow uses a Phase Registry pattern for declarative phase management with automatic dependency resolution, simplifying workflow execution and making it easy to add new phases.

## Phase Registry Pattern

The system uses a declarative phase registration system:

- **PhaseRegistry**: Registers phases with dependencies and metadata
- **CheckpointManager**: Centralized checkpoint save/load
- **PhaseExecutor**: Handles phase execution with dependency checking

This architecture simplifies workflow management and makes it easy to add new phases.

## Core Components

### Entry Point

- `main.py` - CLI entry point that initializes and runs WorkflowManager

### Orchestration Layer

- `src/orchestration/workflow_manager.py` - Main orchestrator
- `src/orchestration/phase_registry.py` - Phase management
- `src/orchestration/checkpoint_manager.py` - State management
- `src/orchestration/workflow_initializer.py` - Component initialization
- `src/orchestration/phase_executor.py` - Phase execution logic

### Core Workflow Modules

- `src/search/` - Database connectors and search functionality
- `src/screening/` - LLM-powered screening agents
- `src/extraction/` - Data extraction agents
- `src/writing/` - Article writing agents
- `src/prisma/` - PRISMA diagram generation
- `src/visualization/` - Chart and graph generation

### Supporting Modules

- `src/export/` - Export formats and submission packages
- `src/citations/` - Citation management and formatting
- `src/quality/` - Quality assessment
- `src/enrichment/` - Paper metadata enrichment
- `src/utils/` - Utility functions
- `src/config/` - Configuration management

### Optional Modules

- `src/tools/` - Additional tools (mermaid, tables, etc.)
- `src/version_control/` - Git integration
- `src/observability/` - Metrics and tracing
- `src/search/bibliometric_enricher.py` - Bibliometric features (requires extra dependencies)

## Data Flow

1. **Initialization**: WorkflowInitializer loads config and creates all components
2. **Phase Registration**: All phases registered with dependencies
3. **Execution**: PhaseExecutor runs phases in dependency order
4. **Checkpointing**: After each phase (2-8), state is saved
5. **Resumption**: On restart, latest checkpoint is loaded and execution resumes

## Module Dependencies

### Core Dependency Chain

```
main.py
  -> WorkflowManager
    -> WorkflowInitializer
      -> SearchStrategyBuilder
      -> MultiDatabaseSearcher
      -> Deduplicator
      -> TitleAbstractScreener
      -> FullTextScreener
      -> DataExtractorAgent
      -> Writing Agents (Introduction, Methods, Results, Discussion, Abstract)
      -> PRISMAGenerator
      -> ChartGenerator
```

### Optional Dependencies

- Bibliometric features require: `pybliometrics`, `scholarly`
- Manuscript pipeline requires: `manubot`, `pypandoc`
- PDF generation requires: `pandoc` (system dependency)

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
