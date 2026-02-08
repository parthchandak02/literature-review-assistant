# Week 1 Quick Start: Split workflow_manager.py

## Goal
Split the 5,008-line `workflow_manager.py` into manageable phase files.

**Time**: 4 hours  
**Risk**: Low (each step tested)  
**Benefit**: 70% file size reduction

## Before You Start

```bash
# 1. Create a branch
git checkout -b modernize-architecture

# 2. Run tests to establish baseline
pytest -m "fast" -v

# 3. Commit current state
git add -A
git commit -m "Baseline before modernization"
```

## Step 1: Create Phase Directory (15 min)

```bash
mkdir -p src/orchestration/phases
touch src/orchestration/phases/__init__.py
```

Create base class:

```python
# src/orchestration/phases/__init__.py
"""
Workflow phases - each phase is self-contained.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List
from dataclasses import dataclass

@dataclass
class PhaseResult:
    """Result from executing a phase"""
    success: bool
    data: Any
    message: str = ""
    
class WorkflowPhase(ABC):
    """Base class for workflow phases"""
    
    def __init__(self, manager: 'WorkflowManager'):
        self.manager = manager
        self.config = manager.config
        self.logger = manager.logger
    
    @abstractmethod
    def execute(self) -> PhaseResult:
        """Execute this phase"""
        pass
    
    @property
    @abstractmethod
    def phase_name(self) -> str:
        """Name of this phase"""
        pass
```

## Step 2: Extract Search Phase (1 hour)

Create the search phase file:

```python
# src/orchestration/phases/search_phase.py
"""
Paper search phase - handles multi-database search and deduplication.
"""

import logging
from typing import List
from . import WorkflowPhase, PhaseResult
from ...search.connectors.base import Paper

logger = logging.getLogger(__name__)

class SearchPhase(WorkflowPhase):
    """Executes paper search across databases"""
    
    @property
    def phase_name(self) -> str:
        return "search"
    
    def execute(self) -> PhaseResult:
        """Execute search phase"""
        try:
            # Copy existing search logic from workflow_manager.py
            papers = self._search_databases()
            deduplicated = self._deduplicate_papers(papers)
            
            # Store in manager state
            self.manager.unique_papers = deduplicated
            
            return PhaseResult(
                success=True,
                data=deduplicated,
                message=f"Found {len(deduplicated)} unique papers"
            )
        except Exception as e:
            logger.error(f"Search phase failed: {e}")
            return PhaseResult(
                success=False,
                data=None,
                message=str(e)
            )
    
    def _search_databases(self) -> List[Paper]:
        """Copy from workflow_manager._search_databases()"""
        # Paste the existing logic here
        pass
    
    def _deduplicate_papers(self, papers: List[Paper]) -> List[Paper]:
        """Copy from workflow_manager dedupe logic"""
        # Paste the existing logic here
        pass
```

**Implementation steps:**

1. Copy `_search_databases()` method from `workflow_manager.py` (lines ~XXX-XXX)
2. Copy deduplication logic
3. Test it:

```python
# Quick test
from src.orchestration.phases.search_phase import SearchPhase
phase = SearchPhase(workflow_manager)
result = phase.execute()
assert result.success
```

## Step 3: Extract Screening Phase (1 hour)

```python
# src/orchestration/phases/screening_phase.py
"""
Screening phase - title/abstract and full-text screening.
"""

from . import WorkflowPhase, PhaseResult

class ScreeningPhase(WorkflowPhase):
    """Executes paper screening"""
    
    @property
    def phase_name(self) -> str:
        return "screening"
    
    def execute(self) -> PhaseResult:
        """Execute screening phase"""
        try:
            # Title/abstract screening
            if self.config.get("screening", {}).get("title_abstract"):
                self._screen_title_abstract()
            
            # Full-text screening
            if self.config.get("screening", {}).get("fulltext"):
                self._screen_fulltext()
            
            return PhaseResult(
                success=True,
                data=self.manager.included_papers,
                message=f"Screened to {len(self.manager.included_papers)} papers"
            )
        except Exception as e:
            return PhaseResult(
                success=False,
                data=None,
                message=str(e)
            )
    
    def _screen_title_abstract(self):
        """Copy from workflow_manager._screen_title_abstract()"""
        pass
    
    def _screen_fulltext(self):
        """Copy from workflow_manager._screen_fulltext()"""
        pass
```

## Step 4: Update workflow_manager.py (1 hour)

Simplify the main file to use phases:

```python
# src/orchestration/workflow_manager.py (simplified)

from .phases import WorkflowPhase
from .phases.search_phase import SearchPhase
from .phases.screening_phase import ScreeningPhase
# ... import other phases as you create them

class WorkflowManager:
    """Orchestrates the systematic review workflow using phases"""
    
    def __init__(self, config_path: str):
        # Existing initialization
        self.phases = self._initialize_phases()
    
    def _initialize_phases(self) -> List[WorkflowPhase]:
        """Create phase instances"""
        return [
            SearchPhase(self),
            ScreeningPhase(self),
            # Add others as you create them
        ]
    
    def run(self):
        """Execute workflow using phases"""
        for phase in self.phases:
            if not self._should_run_phase(phase):
                continue
            
            self.logger.info(f"Starting phase: {phase.phase_name}")
            result = phase.execute()
            
            if not result.success:
                self.logger.error(f"Phase {phase.phase_name} failed: {result.message}")
                if not self.config.get("continue_on_error", False):
                    raise Exception(f"Phase {phase.phase_name} failed")
            
            self.logger.info(f"Phase {phase.phase_name} completed: {result.message}")
    
    def _should_run_phase(self, phase: WorkflowPhase) -> bool:
        """Check if phase should run based on config/checkpoints"""
        # Existing checkpoint logic
        pass
```

## Step 5: Test Everything (45 min)

```bash
# 1. Run unit tests
pytest tests/unit/ -v

# 2. Run integration tests
pytest tests/integration/ -v

# 3. Run a small end-to-end test
python -c "
from src.orchestration.workflow_manager import WorkflowManager
manager = WorkflowManager('test_config.yaml')
manager.run()
"

# 4. Check code quality
uvx ruff check src/
uvx ruff format src/
```

## Step 6: Commit (15 min)

```bash
# Add new files
git add src/orchestration/phases/

# Commit
git commit -m "Week 1: Extract search and screening phases

- Created WorkflowPhase base class
- Extracted SearchPhase (was 800 lines in workflow_manager)
- Extracted ScreeningPhase (was 600 lines)
- Updated WorkflowManager to use phases
- All tests passing

Next: Extract remaining phases (extraction, quality, writing, export)"

# Push to branch
git push origin modernize-architecture
```

## Verification Checklist

- [ ] `src/orchestration/phases/` directory exists
- [ ] `SearchPhase` works independently
- [ ] `ScreeningPhase` works independently
- [ ] All existing tests still pass
- [ ] Code is formatted with `ruff`
- [ ] Changes committed to branch
- [ ] Can still run full workflow

## What You've Achieved

**Before:**
```
workflow_manager.py: 5,008 lines (everything in one file)
```

**After:**
```
workflow_manager.py:        ~800 lines (orchestration only)
phases/search_phase.py:     ~400 lines
phases/screening_phase.py:  ~300 lines
```

**Benefits:**
- 70% smaller main file
- Each phase testable independently
- Clear separation of concerns
- Easy to add new phases
- Easier to debug

## Next Week

Week 2 will extract the remaining phases:
- `extraction_phase.py` - Data extraction
- `quality_phase.py` - Quality assessment
- `writing_phase.py` - Manuscript generation
- `export_phase.py` - Final export

## Troubleshooting

**Q: Tests failing after extraction?**
```bash
# Check what changed
git diff HEAD~1

# Run tests with verbose output
pytest -v -s tests/unit/test_workflow_manager.py

# Check imports
python -c "from src.orchestration.phases.search_phase import SearchPhase; print('OK')"
```

**Q: Import errors?**
- Make sure `__init__.py` exists in `phases/`
- Check relative imports are correct
- Restart Python interpreter

**Q: Logic not working?**
- Compare with original code in `workflow_manager.py`
- Check you copied all helper methods
- Verify state (self.manager.xxx) is accessed correctly

## Tips

1. **Small commits** - Commit after each phase extraction
2. **Test frequently** - Run tests after every change
3. **Keep original** - Don't delete from workflow_manager until phase works
4. **Copy-paste first** - Get it working, then refactor
5. **Use ruff** - Auto-format as you go

## Need Help?

If stuck, you can:
1. Check git diff to see what changed
2. Revert and try again: `git checkout -- src/orchestration/`
3. Ask for help with specific error messages
4. Take a break and come back fresh

**Remember**: This is incremental. Each step adds value!
