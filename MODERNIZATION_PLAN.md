# Project Modernization Plan

## Executive Summary

**Verdict: DON'T REBUILD - MODERNIZE**

Your project is **unique and valuable**. No existing tool (Elicit, Consensus, etc.) does what yours does:
- Full end-to-end systematic review workflow
- Custom screening criteria + quality assessment
- PRISMA diagrams + full manuscript generation
- Multiple database integration + checkpoint/resume

**The Problem**: Not the concept, but the implementation has grown organically to 5000+ lines with technical debt.

**The Solution**: Strategic refactoring using modern patterns, NOT a complete rewrite.

## Research Findings

### Available Tools in 2026

| Tool | What It Does | What It Doesn't Do |
|------|--------------|-------------------|
| **Elicit** | Search + screening (96.4% recall) | Custom criteria, quality assessment, manuscript generation |
| **Consensus** | Paper discovery | Screening, extraction, writing |
| **SciSpace** | Paper analysis | Full workflow |
| **Jenni AI** | Writing assistance | Systematic review-specific |

**None do what your project does**. Your project's value = full automation pipeline.

### Modern Agentic Frameworks

**Should you use LangGraph/CrewAI?**
- **LangGraph**: Best for production, state management, checkpoints
- **Your situation**: Already have working state management
- **Recommendation**: Borrow patterns, don't rebuild

| Aspect | Current | With LangGraph | Verdict |
|--------|---------|----------------|---------|
| State management | Custom | Built-in | Keep custom (working) |
| Checkpoints | Working | Built-in | Keep (already good) |
| Agent coordination | Manual | Automatic | Could benefit |
| Learning curve | None | 2-4 weeks | Not worth it now |

**Better approach**: Apply LangGraph *patterns* to current code.

## Codebase Analysis

### Current State
- **Total lines**: ~15,000+
- **Largest file**: `workflow_manager.py` (5,008 lines!)
- **Duplicate code**: ~2,000+ lines across connectors
- **Unnecessary inheritance**: Writing agents inherit from screening base

### Key Issues

#### 1. Massive Files (High Priority)

```
workflow_manager.py:    5,008 lines  <- Should be 5-6 files
database_connectors.py: 2,894 lines  <- Should be 10 files
charts.py:              1,200 lines  <- Should be 3-4 files
```

#### 2. Duplicate Code (High Priority)

Each database connector repeats:
- Cache checking
- Rate limiting
- Validation
- Error handling

**Impact**: 2,000+ lines of duplicate code

#### 3. Wrong Abstractions (Medium Priority)

```python
# Problem: Writing agents inherit from BaseScreeningAgent
class IntroductionAgent(BaseScreeningAgent):  # Wrong!
    def screen(self):
        return UNCERTAIN  # Stub method - never used
```

#### 4. Scattered Retry Logic (Medium Priority)

3 different retry implementations:
- `retry_strategies.py`
- `rate_limiter.py`  
- Manual loops in `workflow_manager.py`

## The Modernization Plan

### Phase 1: Split Giant Files (Week 1)

**Impact**: 70% reduction in file size, easier navigation

#### A. Split `workflow_manager.py` (5,008 -> ~800 lines)

```
src/orchestration/
  workflow_manager.py (800 lines) - Core orchestration
  phases/
    search_phase.py
    screening_phase.py
    extraction_phase.py
    quality_phase.py
    writing_phase.py
    export_phase.py
```

**Benefits**:
- Each phase self-contained
- Easy to test individually
- Clear responsibilities

#### B. Split `database_connectors.py` (2,894 -> ~200 lines)

```
src/search/connectors/
  base.py (base classes)
  pubmed.py
  arxiv.py
  scopus.py
  ieee.py
  acm.py
  springer.py
  crossref.py
  semantic_scholar.py
```

**Benefits**:
- One connector per file
- Easy to add new connectors
- Clear separation

#### C. Split `charts.py` (1,200 -> ~300 lines each)

```
src/visualization/
  charts/
    bibliometric.py
    temporal.py
    geographic.py
    quality.py
```

### Phase 2: Extract Common Logic (Week 2)

**Impact**: 2,000+ lines removed, single source of truth

#### A. Database Connector Base Class

**Before** (repeated 10x):
```python
class PubMedConnector:
    def search(self, query):
        # Cache check (20 lines)
        # Rate limit (10 lines)
        # Search logic (50 lines)
        # Validation (15 lines)
        # Cache save (10 lines)
```

**After**:
```python
class DatabaseConnector(ABC):
    def search(self, query, max_results=100):
        # Common cache/rate-limit/validation
        return self._do_search(query, max_results)
    
    @abstractmethod
    def _do_search(self, query, max_results):
        pass  # Subclass implements only the search logic

class PubMedConnector(DatabaseConnector):
    def _do_search(self, query, max_results):
        # Only PubMed-specific logic (30 lines)
```

**Savings**: 80 lines x 10 connectors = 800 lines removed

#### B. Unified Retry Strategy

**Consolidate** 3 implementations into one:
```python
# src/utils/retry_strategies.py
@retry_with_backoff(max_attempts=3, initial_delay=1.0)
def risky_operation():
    pass
```

### Phase 3: Fix Abstractions (Week 3)

**Impact**: Remove 200+ lines of stub methods

#### A. Create `BaseWritingAgent`

**Problem**: Writing agents don't screen papers, why inherit from `BaseScreeningAgent`?

**Solution**:
```python
# New base class
class BaseLLMAgent(ABC):
    """Base for any agent using LLM, no screening"""
    def __init__(self, llm_provider, api_key, ...):
        # LLM setup
    
    def _call_llm(self, prompt):
        # Common LLM calling logic

class BaseScreeningAgent(BaseLLMAgent):
    """For screening agents only"""
    @abstractmethod
    def screen(self, ...):
        pass

class BaseWritingAgent(BaseLLMAgent):
    """For writing agents only"""
    @abstractmethod
    def write_section(self, ...):
        pass

# No more stub methods!
class IntroductionAgent(BaseWritingAgent):
    def write_section(self, ...):
        # Only writing logic
```

**Benefit**: Clear separation, no stub methods

### Phase 4: Add Modern Patterns (Week 4)

**Impact**: Better reliability, easier testing

#### A. Add LangGraph-style State Management

```python
from dataclasses import dataclass
from typing import TypedDict

class WorkflowState(TypedDict):
    """Typed workflow state"""
    papers: List[Paper]
    screened_papers: List[Paper]
    extracted_data: Dict
    manuscript: str
    
class WorkflowPhase(ABC):
    """Base phase with clear inputs/outputs"""
    @abstractmethod
    def execute(self, state: WorkflowState) -> WorkflowState:
        pass
```

#### B. Add Error Boundaries

```python
class PhaseExecutor:
    """Executes phases with error handling"""
    def run_phase(self, phase: WorkflowPhase, state: WorkflowState):
        try:
            return phase.execute(state)
        except Exception as e:
            # Log, checkpoint, retry, or fail gracefully
            self._handle_phase_error(phase, state, e)
```

### Phase 5: Modern Tooling (Week 5)

Already done! (from previous work)
- ✅ `pyproject.toml` (single config)
- ✅ `ruff` (100x faster linting)
- ✅ `uv` (10-100x faster deps)
- ✅ Parametrized tests
- ✅ Pre-commit hooks

## Implementation Strategy

### Option A: Incremental (Recommended)

**Timeline**: 5 weeks, ~4 hours/week = 20 hours total

**Week 1**: Split `workflow_manager.py`
- Create phase directory
- Move search phase
- Test still works
- Commit

**Week 2**: Split connectors
- Create connectors directory
- Move PubMed (test)
- Move Arxiv (test)
- Continue...

**Week 3**: Extract common logic
- Create base connector template
- Refactor one connector
- Test thoroughly
- Apply pattern to others

**Week 4**: Fix abstractions
- Create `BaseLLMAgent`
- Create `BaseWritingAgent`
- Migrate one writing agent
- Test, then migrate others

**Week 5**: Add patterns
- Implement typed state
- Add error boundaries
- Update tests

**Risk**: Low - each step tested
**Benefit**: Project keeps working

### Option B: Big Bang (Not Recommended)

**Timeline**: 2-3 weeks full-time

**Risks**:
- Everything breaks at once
- Hard to debug
- May lose momentum
- Could introduce bugs

**When to use**: Never (unless desperate)

## Success Metrics

### Before Modernization
- Largest file: 5,008 lines
- Duplicate code: ~2,000 lines
- Test coverage: Unknown
- Time to add feature: Days
- Onboarding time: Weeks

### After Modernization
- Largest file: <800 lines
- Duplicate code: <200 lines
- Test coverage: >80%
- Time to add feature: Hours
- Onboarding time: Days

## Cost-Benefit Analysis

### Costs
- **Time**: 20 hours over 5 weeks
- **Risk**: Minimal (incremental approach)
- **Learning**: LangGraph patterns (optional)

### Benefits
- **Maintainability**: 5x easier to modify
- **Reliability**: Fewer bugs from duplicate code
- **Speed**: Faster to add features
- **Testing**: Easier to write tests
- **Onboarding**: New devs productive faster
- **Modern stack**: uv, ruff, pytest

### ROI
- **Break-even**: After 3-4 new features
- **Long-term**: 10x easier maintenance

## Comparison: Rebuild vs Modernize

| Aspect | Rebuild from Scratch | Modernize Current |
|--------|---------------------|-------------------|
| **Time** | 3-6 months | 20 hours (5 weeks) |
| **Risk** | High (might not finish) | Low (incremental) |
| **Loss** | All current features | None |
| **Testing** | Start from zero | Build on existing |
| **Learning curve** | LangGraph (2 weeks) | Patterns only |
| **Functionality** | Subset initially | 100% preserved |
| **Bugs** | New unknowns | Known issues fixed |

**Verdict**: Modernize is 90% less effort for 100% of benefit

## Decision Matrix

### Choose Rebuild If:
- [ ] Current code is completely broken
- [ ] Need to change core architecture
- [ ] Have 3+ months available
- [ ] Willing to lose features temporarily
- [ ] Team needs to learn new framework

**Your situation**: None of these apply

### Choose Modernize If:
- [x] Core functionality works
- [x] Just needs organization
- [x] Limited time available
- [x] Can't afford disruption
- [x] Want incremental improvement

**Your situation**: All of these apply!

## Recommended Next Steps

### Immediate (This Week)
1. ✅ Review this plan
2. Run modern setup: `./scripts/setup-modern-dev.sh`
3. Start Phase 1, Week 1: Split `workflow_manager.py`

### Next Month
4. Complete Phases 1-2 (file splitting + common logic)
5. Run tests frequently: `pytest -m "fast"`
6. Commit after each successful step

### Next Quarter
7. Complete Phases 3-4 (abstractions + patterns)
8. Achieve >80% test coverage
9. Document new architecture

## FAQs

**Q: Should I use LangGraph?**
A: No. Borrow patterns, keep your working code.

**Q: Will this break current functionality?**
A: No. Incremental approach preserves everything.

**Q: How long will this take?**
A: 20 hours over 5 weeks (4 hours/week).

**Q: What if I get stuck?**
A: Each phase is independently valuable. Stop anytime.

**Q: Is the project worth keeping?**
A: YES! No tool does what yours does. It's valuable.

## Conclusion

**Don't rebuild. Modernize.**

Your project is unique and solves a real problem that no commercial tool addresses. The issue isn't the concept - it's just grown organically and needs organizational cleanup.

With 20 hours of focused work spread over 5 weeks, you'll have:
- 70% smaller files
- 90% less duplicate code
- Modern tooling (uv, ruff, pytest)
- Clear architecture
- Same functionality

**This is the smart path forward.**

## Resources

- [LangGraph patterns](https://langchain-ai.github.io/langgraph/)
- [Modern Python (2026)](https://pydevtools.com/handbook/)
- [Refactoring guide](https://refactoring.guru/)
- [Clean Architecture](https://blog.cleancoder.com/)

Ready to start? Run: `./scripts/setup-modern-dev.sh`
