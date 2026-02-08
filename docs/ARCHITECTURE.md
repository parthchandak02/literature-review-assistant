# Architecture Overview

## Summary

This document describes the modernized architecture of the research article writer system. The system automates systematic literature reviews from search through manuscript generation.

## Architecture Principles

1. **Phase-Based Workflow**: Each major step is an independent phase
2. **Type Safety**: Typed state management throughout
3. **Error Boundaries**: Graceful error handling at phase boundaries
4. **Agent Abstraction**: Clear separation between agent types
5. **Modularity**: Easy to test, modify, and extend

## Core Components

### 1. Workflow Phases (`src/orchestration/phases/`)

Each phase is a self-contained module with clear responsibilities:

#### Phase Structure

```python
class WorkflowPhase(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass
    
    @abstractmethod
    def execute(self, **kwargs) -> PhaseResult:
        pass
```

#### Available Phases

1. **SearchPhase** - Multi-database search and deduplication
2. **TitleAbstractScreeningPhase** - Initial screening
3. **FullTextScreeningPhase** - Detailed screening with PDFs
4. **PaperEnrichmentPhase** - Metadata enrichment
5. **DataExtractionPhase** - Structured data extraction
6. **QualityAssessmentPhase** - Quality and bias assessment
7. **ArticleWritingPhase** - Manuscript generation
8. **PRISMAGenerationPhase** - PRISMA diagram generation
9. **VisualizationGenerationPhase** - Charts and visualizations
10. **ReportGenerationPhase** - Final report assembly
11. **ManubotExportPhase** - Manubot export (optional)

#### Benefits

- Each phase <300 lines
- Independently testable
- Clear inputs and outputs
- Easy to add new phases

### 2. Agent Hierarchy (`src/agents/`)

```
BaseLLMAgent (abstract)
├── BaseScreeningAgent (for screening)
│   ├── TitleAbstractScreeningAgent
│   └── FullTextScreeningAgent
│
└── BaseWritingAgent (for writing)
    ├── IntroductionAgent
    ├── MethodsAgent
    ├── ResultsAgent
    ├── DiscussionAgent
    └── AbstractAgent
```

#### BaseLLMAgent

Common functionality for all LLM agents:
- LLM client initialization
- Retry logic
- Error handling
- Context management

#### BaseScreeningAgent

Specialized for screening tasks:
- `screen(paper: Paper) -> ScreeningResult`
- Criteria evaluation
- Confidence scoring

#### BaseWritingAgent

Specialized for manuscript writing:
- `write_section(context: Dict) -> str`
- Section formatting
- Length validation

### 3. Typed State Management (`src/orchestration/workflow_state.py`)

```python
class WorkflowState(TypedDict):
    # Search
    all_papers: List[Paper]
    unique_papers: List[Paper]
    
    # Screening
    screened_papers: List[Paper]
    eligible_papers: List[Paper]
    final_papers: List[Paper]
    
    # Extraction
    extracted_data: List[ExtractedData]
    
    # Writing
    manuscript_sections: Dict[str, str]
    manuscript: Optional[str]
    
    # ... more fields
```

#### Benefits

- IDE autocomplete
- Type checking catches errors early
- Clear documentation of state structure
- Validation at transition points

### 4. Error Boundaries (`src/orchestration/error_boundary.py`)

```python
class PhaseErrorBoundary:
    def execute_with_boundary(
        self,
        phase: WorkflowPhase,
        state: WorkflowState,
        **kwargs
    ) -> PhaseResult:
        try:
            return phase.execute(**kwargs)
        except ValidationError as e:
            return self._handle_validation_error(phase, state, e)
        except LLMError as e:
            return self._handle_llm_error(phase, state, e)
        # ... other error types
```

#### Error Types

- `ValidationError` - Data validation failures
- `LLMError` - LLM API or parsing failures
- `DatabaseError` - Database connection/query failures
- Generic `Exception` - Unexpected errors

#### Recovery Strategy

1. Log error with full context
2. Attempt retry if configured
3. Return failed PhaseResult
4. Allow workflow to decide: continue, skip, or abort

### 5. Phase Registry (`src/orchestration/phase_registry.py`)

Declarative phase registration with dependency management:

```python
registry.register(
    PhaseDefinition(
        name="data_extraction",
        phase_number=7,
        dependencies=["paper_enrichment"],
        handler=self._extract_data,
        checkpoint=True,
        description="Extract structured data"
    )
)
```

#### Features

- Topological sort for execution order
- Dependency validation
- Optional phases (config-based)
- Checkpoint support

### 6. Checkpoint Manager (`src/orchestration/checkpoint_manager.py`)

State persistence for resume capability:

- Saves state after each phase
- Enables resume from any phase
- Prevents data loss on crashes
- Useful for long-running workflows

## Data Flow

```
1. Search Phase
   └> all_papers: List[Paper]

2. Deduplication Phase
   └> unique_papers: List[Paper]

3. Title/Abstract Screening Phase
   └> screened_papers: List[Paper]

4. Full-Text Screening Phase
   └> eligible_papers: List[Paper]
       └> final_papers: List[Paper]

5. Paper Enrichment Phase
   └> enriched final_papers

6. Data Extraction Phase
   └> extracted_data: List[ExtractedData]

7. Quality Assessment Phase
   └> quality_assessment_data: Dict

8. Writing Phase
   └> manuscript_sections: Dict[str, str]
       └> manuscript: str

9. Export Phase
   └> report_path: str
```

## State Transitions

Each phase validates state before execution:

```python
def validate_state_transition(
    from_phase: str,
    to_phase: str,
    state: WorkflowState
) -> bool:
    # Ensure required data exists
    # Example: can't screen without papers
    if to_phase == "title_abstract_screening":
        return len(state.get("unique_papers", [])) > 0
```

## Error Handling Strategy

### Phase-Level Errors

1. **Validation Errors**: Invalid input data
   - Log error
   - Return failed result
   - Workflow decides next step

2. **LLM Errors**: API failures, parsing errors
   - Log with metrics
   - Retry with backoff (up to 3 attempts)
   - Use fallback parsing if available
   - Return failed result if exhausted

3. **Database Errors**: Connection, timeout, rate limit
   - Log error
   - Retry with exponential backoff
   - Use circuit breaker to prevent cascade
   - Return failed result

### Workflow-Level Errors

- Critical phases (search, screening) abort on failure
- Optional phases (manubot, visualizations) skip on failure
- Checkpoint before critical operations
- Audit trail for cost tracking

## Adding New Phases

1. Create phase class in `src/orchestration/phases/`
2. Inherit from `WorkflowPhase`
3. Implement `name` property and `execute()` method
4. Register in workflow_manager `_register_all_phases()`
5. Add tests in `tests/unit/`

Example:

```python
class NewPhase(WorkflowPhase):
    @property
    def name(self) -> str:
        return "new_phase"
    
    def execute(self, **kwargs) -> PhaseResult:
        self.log_start()
        try:
            # Phase logic here
            result = self._create_result(
                status=PhaseStatus.COMPLETED,
                data=output,
                message="Success"
            )
            self.log_completion(result)
            return result
        except Exception as e:
            return self._create_result(
                status=PhaseStatus.FAILED,
                error=e
            )
```

## Testing Strategy

### Unit Tests

- Test each phase independently
- Mock external dependencies (LLM, database)
- Use recorded fixtures for LLM responses
- Fast execution (<5s total)

### Integration Tests

- Test phase interactions
- Use recorded responses (zero API cost)
- Verify state transitions
- Test error handling

### E2E Tests

- Full workflow validation
- Mock LLM for determinism
- Test checkpoint resume
- Performance benchmarks

## Performance Optimizations

1. **Parallel Execution**: pytest-xdist for tests
2. **Caching**: Database results, PDF downloads
3. **Rate Limiting**: Respect API limits
4. **Circuit Breakers**: Prevent cascade failures
5. **Checkpointing**: Resume without re-running

## Observability

### Metrics (`src/observability/llm_metrics.py`)

- LLM call tracking
- Response time monitoring
- Parsing failure rates
- Cost tracking
- Token usage

### Logging

- Structured logging with context
- Phase-level progress tracking
- Error traces with full context
- Audit trail for debugging

## Future Enhancements

1. **Async/Await**: Parallel phase execution
2. **Streaming**: Real-time progress updates
3. **Plugin System**: External phase contributions
4. **DAG Visualization**: Visual workflow editor
5. **State Snapshots**: Time-travel debugging

## Migration Notes

### From Legacy to Modern

The modernization preserves all functionality while improving structure:

- **Before**: Single 5000-line file
- **After**: Modular phase files <300 lines each

- **Before**: Mixed agent types
- **After**: Clear agent hierarchy

- **Before**: Untyped state
- **After**: Type-safe WorkflowState

- **Before**: Ad-hoc error handling
- **After**: Systematic error boundaries

### Breaking Changes

None! The API remains the same. Internal structure improved.

## Resources

- [MODERNIZATION_PLAN.md](../MODERNIZATION_PLAN.md) - Full modernization strategy
- [TESTING_IMPROVEMENTS.md](../TESTING_IMPROVEMENTS.md) - Testing strategy
- [tests/README.md](../tests/README.md) - Testing guide

## Questions?

Check the main README or contact the development team.
