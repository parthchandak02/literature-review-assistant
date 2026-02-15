# Cursor Rules, Skills & Commands Strategy for the Holy Grail Build

## Understanding the Three Layers

Cursor now provides three distinct mechanisms to customize agent behavior. The key mental model, per Cursor's own official blog, is: **"Rules guide. Skills do. Commands trigger."**[^1][^2]

| Mechanism | What It Is | Activation | Best For |
|:---|:---|:---|:---|
| **Rules** (`.cursor/rules/*.mdc`) | Passive context loaded into every conversation | Always-on, auto-attach by glob, agent-selected, or manual | Standards, conventions, guardrails, project architecture |
| **Skills** (`.cursor/skills/*/SKILL.md`) | Active capabilities with references, scripts, assets | Agent decides or user invokes with `/` | Multi-step workflows, domain knowledge, procedural how-tos |
| **Commands** (`.cursor/commands/*.md`) | Saved prompts | User invokes with `/` only | Quick repeatable tasks |

Rules are **always loaded** (or conditionally by file glob), consuming context window space whether needed or not. Skills use **progressive disclosure** — the agent sees only the name/description and loads full contents on demand, keeping context clean. Commands are the simplest: plain Markdown prompts triggered manually.[^2]

### Rule Types (`.mdc` frontmatter)

Per BMad's code-backed analysis and Cursor's internal implementation:[^3]

| Rule Type | `description` | `globs` | `alwaysApply` | When Used |
|:---|:---|:---|:---|:---|
| **Always** | blank | blank | `true` | Every chat and cmd-k request |
| **Auto-Attach** | blank | glob pattern | `false` | When editing matching files |
| **Agent-Selected** | critical description | blank | `false` | Agent reads description, chooses to apply |
| **Manual** | blank | blank | `false` | User must `@rule-name` in chat |
| **Auto + Description** | included | glob pattern | `false` | Both agent discovery and file matching |

**Critical behavior note:** If `alwaysApply: true` is set, globs are **ignored** entirely — the rule applies globally regardless of file context. Having both `description` and `globs` (without `alwaysApply`) is fully supported and recommended for dual-use rules.[^3]

***

## Recommended Rules for the Holy Grail Project

### Directory Structure

```
.cursor/
├── rules/
│   ├── core/
│   │   ├── project-overview-always.mdc
│   │   ├── build-phase-gate-always.mdc
│   │   └── no-untyped-dicts-always.mdc
│   ├── python/
│   │   ├── pydantic-contracts-auto.mdc
│   │   ├── async-io-auto.mdc
│   │   └── typing-annotations-auto.mdc
│   ├── domain/
│   │   ├── systematic-review-methodology-agent.mdc
│   │   ├── prisma-2020-requirements-agent.mdc
│   │   ├── grade-framework-agent.mdc
│   │   └── rob2-domains-agent.mdc
│   ├── testing/
│   │   └── test-patterns-auto.mdc
│   └── tool/
│       ├── sqlite-patterns-auto.mdc
│       ├── pydanticai-graph-agent.mdc
│       └── statsmodels-meta-analysis-agent.mdc
├── skills/
│   ├── build-phase/
│   │   └── SKILL.md
│   ├── search-connector/
│   │   └── SKILL.md
│   ├── dual-reviewer/
│   │   └── SKILL.md
│   ├── meta-analysis/
│   │   └── SKILL.md
│   ├── section-writer/
│   │   └── SKILL.md
│   └── ieee-export/
│       └── SKILL.md
├── commands/
│   ├── run-tests.md
│   ├── run-review.md
│   ├── validate-prisma.md
│   └── check-gates.md
└── hooks.json
```

***

## RULES (Passive Behavioral Guidance)

### Rule 1: `project-overview-always.mdc`

**Type:** Always | **Purpose:** Universal project context every conversation starts with

```markdown
---
description:
globs:
alwaysApply: true
---

# Systematic Review Automation Tool

## Project Identity
- **Purpose:** Automate systematic literature reviews to produce IEEE-submission-ready manuscripts
- **Stack:** Python 3.10+, PydanticAI (Graph API, BaseNode pattern), SQLite (aiosqlite), Google Gemini 2.5, statsmodels, matplotlib
- **Package manager:** uv
- **Architecture:** PydanticAI Graph with typed state, SQLite persistence, 3-tier LLM model selection

## Key Directories
- `src/models/` — Pydantic data contracts (enums, config, papers, screening, extraction, quality, writing, workflow)
- `src/db/` — SQLite schema, database.py, repositories.py
- `src/orchestration/` — PydanticAI Graph definition, state, quality gates
- `src/search/` — Database connectors (OpenAlex, PubMed, arXiv, IEEE Xplore)
- `src/screening/` — Dual-reviewer screening, prompts, inter-rater reliability
- `src/quality/` — RoB 2, ROBINS-I, CASP, GRADE assessors
- `src/synthesis/` — Meta-analysis (statsmodels), effect sizes, narrative fallback
- `src/writing/` — Section writer, per-section prompts, humanizer
- `src/citation/` — Citation ledger (claim → evidence → citation chain)
- `src/export/` — IEEE LaTeX, submission packager, PRISMA checklist validator
- `config/` — review.yaml (per-review), settings.yaml (system behavior)

## Critical Constraints
- **NO untyped dictionaries** at phase boundaries — only Pydantic models
- **NO LLM-computed statistics** — meta-analysis uses scipy/statsmodels only
- **ALL I/O is async** (aiosqlite, aiohttp)
- **ALL LLM calls logged** with model, tokens, cost, latency to cost_records table
- **Citation lineage enforced** — every claim must trace to evidence to citation
- See `config/review.yaml` for the current review topic
- See `config/settings.yaml` for agent model assignments and thresholds

<example>
# Good: Typed phase boundary
async def screen_paper(paper: CandidatePaper) -> DualScreeningResult:
    ...
</example>

<example type="invalid">
# Bad: Untyped dictionary crossing phase boundary
async def screen_paper(paper: dict) -> dict:
    ...
</example>
```

### Rule 2: `build-phase-gate-always.mdc`

**Type:** Always | **Purpose:** Enforce sequential build discipline

```markdown
---
description:
globs:
alwaysApply: true
---

# Build Phase Discipline

## Current Build Order
Phase 1: Foundation → Phase 2: Search → Phase 3: Screening → Phase 4: Extraction & Quality → Phase 5: Synthesis → Phase 6: Writing → Phase 7: PRISMA & Viz → Phase 8: Export & Orchestration

## Rules
- Build in exact phase order. Do not implement Phase N+1 code before Phase N is approved.
- After completing a phase, run acceptance criteria tests before proceeding.
- Each build phase has specific test files listed in the Holy Grail spec Part 8.
- When in doubt about which phase we're in, ask the user.

## Verification After Each Phase
```bash
uv run pytest tests/unit -q
uv run pytest tests/integration -q
python -m src.main --help
```
```

### Rule 3: `no-untyped-dicts-always.mdc`

**Type:** Always | **Purpose:** Enforce the #1 architectural constraint

```markdown
---
description:
globs:
alwaysApply: true
---

# No Untyped Dictionaries at Phase Boundaries

Every function crossing a phase boundary MUST accept and return Pydantic models from `src/models/`.

- Use `CandidatePaper`, not `dict` for paper data
- Use `ScreeningDecision`, not `dict` for decisions
- Use `ExtractionRecord`, not `dict` for extracted data
- Use `RoB2Assessment` / `RobinsIAssessment`, not `dict` for quality assessments
- Use `GRADEOutcomeAssessment`, not `dict` for GRADE
- Use `SectionDraft`, not `dict` for manuscript sections
- Use `GateResult`, not `dict` for quality gate outputs

Internal helper functions within a single module may use dicts, but any function called from outside the module must use typed models.

<example>
# Correct: typed boundary
from src.models.screening import DualScreeningResult
async def adjudicate(paper_id: str, a: ScreeningDecision, b: ScreeningDecision) -> DualScreeningResult:
    ...
</example>

<example type="invalid">
# Wrong: untyped boundary
async def adjudicate(paper_id: str, a: dict, b: dict) -> dict:
    ...
</example>
```

### Rule 4: `pydantic-contracts-auto.mdc`

**Type:** Auto-Attach | **Purpose:** Enforce patterns when editing model files

```markdown
---
description:
globs: src/models/**/*.py
alwaysApply: false
---

# Pydantic Model Standards

- All models inherit from `pydantic.BaseModel`
- Use `Field()` with constraints (ge, le, min_length) where applicable
- Use `str` enums (`class X(str, Enum)`) for all categorical fields
- Use `datetime` with timezone-aware defaults: `Field(default_factory=lambda: datetime.now(timezone.utc))`
- Use `Optional[X] = None` for nullable fields, never bare `Optional[X]`
- Add docstrings explaining the model's role in the pipeline
- Never use `Any` type — find or create the correct type
```

### Rule 5: `async-io-auto.mdc`

**Type:** Auto-Attach | **Purpose:** Enforce async patterns in I/O code

```markdown
---
description:
globs: src/search/**/*.py, src/db/**/*.py, src/llm/**/*.py, src/screening/**/*.py, src/extraction/**/*.py
alwaysApply: false
---

# Async I/O Standards

- All database calls use `aiosqlite` async context manager
- All HTTP calls use `aiohttp.ClientSession` (not `requests`)
- All LLM calls use PydanticAI async agent.run()
- Use `asyncio.gather()` for independent concurrent operations (e.g., multi-database search)
- Rate limiting: use token bucket pattern in `src/llm/rate_limiter.py`
- Every LLM call must be wrapped to log a `CostRecord` to the database

<example>
async with aiosqlite.connect(db_path) as db:
    await db.execute("INSERT INTO papers ...", params)
    await db.commit()
</example>

<example type="invalid">
import sqlite3
conn = sqlite3.connect(db_path)  # Wrong: synchronous
conn.execute("INSERT INTO papers ...", params)
</example>
```

### Rule 6: `systematic-review-methodology-agent.mdc`

**Type:** Agent-Selected | **Purpose:** Domain knowledge the agent loads when working on review methodology

```markdown
---
description: Core systematic review methodology rules. Apply when implementing any phase of the systematic review pipeline, writing screening logic, implementing quality assessment, or generating manuscript sections. Contains PRISMA 2020, GRADE, and Cochrane methodology requirements.
globs:
alwaysApply: false
---

# Systematic Review Methodology

## Seven Core Steps (must execute in order)
1. Define research question (PICO/PICo/PICOT)
2. Develop and register protocol (PROSPERO format)
3. Conduct search (≥3 databases + grey literature, full Boolean strings documented)
4. Screen studies (dual independent review, two-stage: title/abstract → full-text)
5. Assess quality (domain-based RoB tools, NEVER summary quality scores)
6. Extract and synthesize (dual extraction, meta-analysis when feasible)
7. Present findings (GRADE SoF table, PRISMA diagram, structured manuscript)

## Risk of Bias Tool Routing
- RCTs → RoB 2 (5 domains: randomization, deviations, missing data, measurement, selection)
- Non-randomized → ROBINS-I (7 domains, different judgment scale: Low/Moderate/Serious/Critical/No Info)
- Qualitative → CASP
- NEVER use summary quality scores — always domain-based assessment

## Meta-Analysis Thresholds
- I² < 40%: fixed-effect model
- I² ≥ 40%: random-effects (DerSimonian-Laird)
- Funnel plot: only when ≥ 10 studies
- Statistics computed by scipy/statsmodels ONLY, never by LLM

## GRADE: 8 Factors
- 5 downgrade: risk of bias, inconsistency, indirectness, imprecision, publication bias
- 3 upgrade: large effect, dose-response, residual confounding
- Starting: High for RCTs, Low for observational
```

### Rule 7: `sqlite-patterns-auto.mdc`

**Type:** Auto-Attach | **Purpose:** Consistent database patterns

```markdown
---
description:
globs: src/db/**/*.py
alwaysApply: false
---

# SQLite Patterns

## Connection Setup (every new connection)
```python
await db.execute("PRAGMA journal_mode = WAL")
await db.execute("PRAGMA synchronous = NORMAL")
await db.execute("PRAGMA foreign_keys = ON")
await db.execute("PRAGMA cache_size = 10000")
await db.execute("PRAGMA temp_store = MEMORY")
```

## Repository Pattern
- Every method in repositories.py accepts and returns Pydantic models
- Store JSON arrays as TEXT columns (json.dumps/loads)
- Use parameterized queries (?) — never f-strings for SQL
- All writes commit explicitly
- decision_log table is append-only — never UPDATE or DELETE

## Checkpoint Pattern
- Save ReviewState to checkpoints table after each phase
- On resume: query MAX phase from checkpoints for workflow_id
- Individual screening decisions saved per-paper (not batch) for paper-level resume
```

### Rule 8: `pydanticai-graph-agent.mdc`

**Type:** Agent-Selected | **Purpose:** PydanticAI Graph API patterns

```markdown
---
description: PydanticAI Graph API patterns and conventions. Apply when working on src/orchestration/graph.py, implementing workflow nodes, or connecting phases together. Uses the stable BaseNode API, not the beta GraphBuilder API.
globs:
alwaysApply: false
---

# PydanticAI Graph Patterns

## Use the stable BaseNode API (NOT beta GraphBuilder)
```python
from pydantic_ai.graph import GraphRunContext, BaseNode, End, Graph

class SearchNode(BaseNode[ReviewState]):
    async def run(self, ctx: GraphRunContext[ReviewState]) -> SearchCompleteNode:
        # do work, mutate ctx.state
        return SearchCompleteNode()

class SearchCompleteNode(BaseNode[ReviewState]):
    async def run(self, ctx: GraphRunContext[ReviewState]) -> ScreeningNode | End[ReviewState]:
        if gate_passed:
            return ScreeningNode()
        return End(ctx.state)
```

## State Management
- `ReviewState` is the typed state object passed through all nodes
- Mutate state within nodes, not between them
- After each node completes, persist state to SQLite checkpoints table
- Quality gates run at node boundaries, not within nodes

## HITL (Human-in-the-Loop)
- Implement as checkpoint + CLI prompt at specific nodes
- Borderline screening review: after screening node
- Pre-export citation review: before export node
```

### Rule 9: `statsmodels-meta-analysis-agent.mdc`

**Type:** Agent-Selected | **Purpose:** Correct meta-analysis implementation patterns

```markdown
---
description: Meta-analysis implementation patterns using statsmodels. Apply when working on src/synthesis/ files, implementing effect size calculations, forest plots, or funnel plots. Critical rule: LLMs must NEVER compute statistics.
globs:
alwaysApply: false
---

# Meta-Analysis Patterns (statsmodels)

## CRITICAL: No LLM Statistics
LLMs must NEVER compute effect sizes, p-values, confidence intervals, or any statistical measures.
Extract raw data from ExtractionRecord → pass to deterministic scipy/statsmodels functions.

## Effect Sizes
```python
from statsmodels.stats.meta_analysis import effectsize_smd, effectsize_2proportions
# Continuous: effectsize_smd(mean1, sd1, n1, mean2, sd2, n2)
# Dichotomous: effectsize_2proportions(count1, n1, count2, n2, statistic="rd"|"log-rr"|"log-or"|"arcsine")
```

## Pooling
```python
from statsmodels.stats.meta_analysis import combine_effects
# Fixed: combine_effects(effects, variances, method_re="chi2", use_t=False)
# Random (DL): combine_effects(effects, variances, method_re="chi2", use_t=True)
# Choose based on I²: fixed if < 40%, random if ≥ 40%
```

## Note: Mantel-Haenszel is NOT available in statsmodels
Use DerSimonian-Laird for binary outcome pooling.

## Forest Plot
```python
result = combine_effects(effects, variances)
fig = result.plot_forest()
fig.savefig("forest_plot.png", dpi=300, bbox_inches="tight")
```
```

### Rule 10: `test-patterns-auto.mdc`

**Type:** Auto-Attach | **Purpose:** Test file conventions

```markdown
---
description:
globs: tests/**/*.py
alwaysApply: false
---

# Testing Standards

- Use pytest with async support (pytest-asyncio)
- Unit tests: mock LLM calls, use in-memory SQLite
- Integration tests: may use real LLM calls with small inputs
- E2E tests: full pipeline run
- Each module in src/ has a corresponding test file
- Test Pydantic model validation (both valid and invalid inputs)
- Test quality gates in both strict and warning modes
- Test citation ledger integrity (no orphan claims, no unresolved citations)

## Naming Convention
- `test_<module>.py` for unit tests
- `test_<pipeline>_pipeline.py` for integration tests
- `test_full_review.py` for e2e

## Running
```bash
uv run pytest tests/unit -q          # fast, no LLM
uv run pytest tests/integration -q   # slower, may use LLM
uv run pytest tests/e2e -q           # full run
```
```

***

## SKILLS (Active Capabilities)

Skills are the most powerful mechanism for this project. They package multi-step domain workflows that the agent loads on demand.[^1][^2]

### Skill 1: `build-phase/SKILL.md`

**Purpose:** Guides the agent through implementing each build phase step-by-step

```markdown
# Build Phase Implementation

Procedural guide for implementing each build phase of the systematic review tool.

## Instructions

When the user asks to implement a build phase, follow these steps:

1. **Identify the phase** from the Holy Grail spec (Part 5)
2. **Check prerequisites** — verify all dependency phases are complete
3. **Read the spec** for that phase's "What to Build" section
4. **Create files** in the exact directory structure from Part 4
5. **Implement using data contracts** from Part 2 (never invent new models)
6. **Write tests** listed in Part 8 for this phase
7. **Run acceptance criteria** — every checkbox must pass
8. **Report results** to user before proceeding

## Phase Quick Reference

| Phase | Key Deliverables | Test Files |
|:---|:---|:---|
| 1: Foundation | Models, SQLite, Gates, Ledger, LLM Provider | test_models, test_database, test_gates, test_citation_ledger |
| 2: Search | Connectors, Strategy, Dedup, Protocol | test_protocol |
| 3: Screening | Dual-reviewer, Prompts, Kappa | test_screening, test_reliability, test_dual_screening |
| 4: Extraction | Extractor, RoB2, ROBINS-I, CASP, GRADE | test_rob2, test_robins_i, test_quality_pipeline |
| 5: Synthesis | Effect sizes, Meta-analysis, Forest/Funnel | test_effect_size, test_meta_analysis, test_synthesis_pipeline |
| 6: Writing | Section writer, Prompts, SoF, Humanizer | test_writing_pipeline |
| 7: PRISMA/Viz | PRISMA diagram, Timeline, Geographic | test_prisma_diagram |
| 8: Export | Graph wiring, IEEE LaTeX, CLI | test_ieee_export, test_ieee_validator, test_full_review |

## References
@file:attached_file:213 (Holy Grail Build Specification)
```

### Skill 2: `search-connector/SKILL.md`

**Purpose:** How to implement a new database connector

```markdown
# Search Connector Implementation

Guide for implementing database connectors that conform to the SearchConnector protocol.

## Instructions

Every connector must:
1. Implement the `SearchConnector` protocol from `src/search/base.py`
2. Return `SearchResult` containing `List[CandidatePaper]`
3. Set `source_category` (DATABASE or OTHER_SOURCE) for PRISMA diagram
4. Handle rate limiting internally (constants in the connector file, not YAML)
5. Use async HTTP (aiohttp), never synchronous requests
6. Log search query, date, database name, and result count for PRISMA-S appendix

## Protocol Interface
```python
class SearchConnector(Protocol):
    name: str
    source_category: SourceCategory
    async def search(self, query: str, max_results: int = 100,
                     date_start: int = None, date_end: int = None) -> SearchResult:
        ...
```

## Reference Implementations
- `src/search/openalex.py` — primary connector (pyalex library)
- `src/search/pubmed.py` — Biopython Entrez pattern

## Testing
- Mock API responses for unit tests
- Verify CandidatePaper field mapping
- Test rate limiter behavior
```

### Skill 3: `dual-reviewer/SKILL.md`

**Purpose:** Implementing the dual-reviewer screening system

```markdown
# Dual-Reviewer Screening System

Guide for implementing the core screening architecture with two independent AI reviewers and an adjudicator.

## Architecture

```
Paper → Reviewer A (Flash-Lite, temp=0.1, inclusion-emphasis)
      → Reviewer B (Flash-Lite, temp=0.3, exclusion-emphasis)
      
If agree → final_decision = agreed decision
If disagree → Adjudicator (Pro, temp=0.2) sees both decisions → final
```

## Implementation Steps

1. Create PydanticAI agents for Reviewer A, B, and Adjudicator
2. Each reviewer returns `ScreeningDecision` with decision, reason, exclusion_reason, confidence
3. Compare decisions — if agreement, log and return
4. If disagreement, invoke adjudicator with both decisions + reasoning
5. Log ALL individual decisions to `screening_decisions` table (per-paper, immediately)
6. Log final result to `dual_screening_results` table
7. Compute Cohen's kappa after each stage using sklearn
8. Generate disagreements_report.md

## Critical Rules
- Two-stage: title/abstract first, then full-text for survivors
- Full-text stage requires PDF retrieval first (Unpaywall / open access)
- Every EXCLUDED paper at full-text stage must have `ExclusionReason` enum value
- Paper-level checkpoint: save each decision to SQLite immediately (not batch)

## References
- Prompt templates: `src/screening/prompts.py`
- Reliability: `src/screening/reliability.py`
```

### Skill 4: `meta-analysis/SKILL.md`

**Purpose:** Implementing meta-analysis correctly

```markdown
# Meta-Analysis Implementation

Guide for implementing statistical synthesis using statsmodels.

## CRITICAL RULE
LLMs must NEVER compute statistics. All calculations use deterministic functions.

## Workflow

1. **Feasibility check** (LLM-assisted): Are studies clinically similar enough to pool?
2. **Extract raw data** from `ExtractionRecord` (means, SDs, counts, events)
3. **Compute effect sizes** using statsmodels functions
4. **Assess heterogeneity** (I², Q, τ²)
5. **Select model**: fixed if I² < 40%, random-effects if I² ≥ 40%
6. **Pool effects** using `combine_effects()`
7. **Generate forest plot** using `.plot_forest()`
8. **Generate funnel plot** (matplotlib scatter) if ≥ 10 studies
9. **Store results** as `MetaAnalysisResult` in SQLite

## Effect Size Functions
- Continuous: `effectsize_smd(mean1, sd1, n1, mean2, sd2, n2)`
- Dichotomous: `effectsize_2proportions(count1, n1, count2, n2, statistic="log-rr")`

## Known Limitations
- Mantel-Haenszel NOT available in statsmodels — use DerSimonian-Laird
- statsmodels meta-analysis API is marked "experimental"
- Verify results against R metafor if possible
```

### Skill 5: `section-writer/SKILL.md`

**Purpose:** Writing manuscript sections with citation lineage

```markdown
# Manuscript Section Writing

Guide for implementing the section writer with full citation lineage enforcement.

## Per-Section Requirements

### Abstract (≤ 250 words)
Must cover all 12 PRISMA 2020 abstract items:
1. Title — identify as systematic review/meta-analysis
2. Objectives — research question with PICO
3. Eligibility criteria
4. Information sources with dates
5. Risk of bias methods
6. Included studies count/characteristics
7. Synthesis results with CIs
8. Key findings
9. Strengths and limitations
10. Registration/funding
11. Protocol registration number
12. Funding sources

### Methods (PRISMA Items 3-16)
Must cover: eligibility criteria, information sources, search strategy (reference appendix), selection process (dual reviewer + kappa), data collection, data items, RoB tools, effect measures, synthesis methods, GRADE.

### Results
Must reference: PRISMA diagram, study characteristics table, RoB traffic-light figure, forest plot, GRADE SoF table.

### Discussion
Key findings, comparison with prior work, strengths, limitations, implications.

## Citation Lineage Workflow
For each claim in generated text:
1. `CitationLedger.register_claim(claim_text, section, confidence)`
2. `CitationLedger.link_evidence(claim_id, citation_id, evidence_span, score)`
3. After section complete: `CitationLedger.validate_section()` — zero unresolved claims
4. Export blocks if any claim lacks evidence chain
```

### Skill 6: `ieee-export/SKILL.md`

**Purpose:** IEEE LaTeX export and submission packaging

```markdown
# IEEE Export & Submission Packaging

Guide for implementing LaTeX export and the submission package.

## IEEE LaTeX Requirements
- Use IEEEtran.cls document class
- `\cite{citekey}` numbered references
- Tables: booktabs package
- Figures: \includegraphics with proper paths
- Abstract: 150-250 words

## Submission Package Structure
```
submission/
├── manuscript.tex
├── manuscript.pdf
├── references.bib
├── figures/
├── supplementary/
│   ├── search_strategies_appendix.pdf
│   ├── prisma_checklist.pdf
│   ├── extracted_data.csv
│   └── screening_decisions.csv
└── cover_letter.md
```

## Validation Checks
- Abstract: 150-250 words
- References: warn if < 30 or > 80
- All \cite{} resolve in .bib
- No [?] or placeholder text
- PRISMA checklist ≥ 24/27 items reported
- Citation lineage: zero unresolved citations
```

***

## COMMANDS (Quick Shortcuts)

### Command 1: `run-tests.md`

```markdown
Run the test suite for the current build phase.

1. Determine which build phase we're in based on recent file changes
2. Run the appropriate test files:
   ```bash
   uv run pytest tests/unit -q
   uv run pytest tests/integration -q
   ```
3. Report pass/fail results
4. If failures, analyze the error and suggest fixes
```

### Command 2: `validate-prisma.md`

```markdown
Run PRISMA 2020 checklist validation on the current manuscript.

1. Load the latest section drafts from SQLite
2. Run `src/export/prisma_checklist.py` validator
3. Report status for all 27 items: REPORTED / PARTIAL / MISSING
4. Highlight any items below the 24/27 threshold
```

### Command 3: `check-gates.md`

```markdown
Check all quality gate statuses for the current review.

1. Query gate_results table for the current workflow_id
2. Display status table:
   - search_volume: pass/fail
   - screening_safeguard: pass/fail
   - extraction_completeness: pass/fail
   - citation_lineage: pass/fail
   - cost_budget: current spend vs max
   - resume_integrity: pass/fail
3. Flag any failures with remediation suggestions
```

### Command 4: `run-review.md`

```markdown
Run the full systematic review pipeline.

```bash
python -m src.main run --config config/review.yaml
```

Monitor progress and report any gate failures or HITL checkpoints that need attention.
```

***

## HOOKS (Automated Triggers)

### `.cursor/hooks.json`

```json
{
  "version": 1,
  "hooks": {
    "file_saved": [
      {
        "pattern": "src/models/**/*.py",
        "command": "uv run python -c \"from src.models import *; print('Models OK')\"",
        "description": "Validate all Pydantic models compile after save"
      }
    ]
  }
}
```

***

## Best Practices Applied to This Project

### 1. Keep Rules Short and Focused

Per Cursor's official guidance: "Keep rules focused on the essentials: the commands to run, the patterns to follow, and pointers to canonical examples in your codebase. Reference files instead of copying their contents." BMad recommends targeting 25 lines max, 50 absolute maximum per rule.[^3][^1]

This is why domain knowledge (systematic review methodology, PRISMA requirements, GRADE) lives in **Agent-Selected rules** rather than Always rules — the agent only loads them when working on relevant files, keeping context clean for other tasks.[^2]

### 2. Skills Over Giant Rules

The Cursor changelog (v2.4, January 2026) stated directly: "Compared to always-on, declarative rules, skills are better for dynamic context discovery and procedural 'how-to' instructions." This is why the multi-step build phase workflow, the dual-reviewer implementation guide, and the meta-analysis workflow are **skills**, not rules.[^2]

### 3. Iterate — Don't Over-Optimize Upfront

Per Cursor's best practices blog: "Start simple. Add rules only when you notice the agent making the same mistake repeatedly. Don't over-optimize before you understand your patterns." The rules above cover the known critical constraints from the Holy Grail spec. As you build, add new rules for:[^1]
- Repeated mistakes the agent makes
- Patterns you find yourself correcting often
- Domain-specific corrections (e.g., "always use ExclusionReason enum, not free-text strings")

### 4. Version Control Everything

All `.cursor/rules/`, `.cursor/skills/`, and `.cursor/commands/` should be committed to git. This means when you switch machines or onboard a collaborator, the AI behavior is consistent.[^3][^1]

### 5. Use Description + Globs for Dual Discovery

For rules that are both file-specific AND should be discoverable by the agent (like `pydanticai-graph-agent.mdc`), use both `description` and `globs`. This is confirmed as fully supported and the recommended approach.[^3]

***

## What to Add to the Holy Grail Spec

Add a new **Part 11: Cursor IDE Configuration** to the Holy Grail spec with:

1. The full `.cursor/` directory structure above
2. The 10 rules (actual `.mdc` content)
3. The 6 skills (actual `SKILL.md` content)
4. The 4 commands
5. The hooks.json
6. A note: "Rules and skills evolve during the build. Add new rules when the agent makes repeated mistakes. Prune rules that become unnecessary as the codebase grows."

This ensures any developer (or future you) opening the project in Cursor gets the full AI-assisted development experience from day one.

---

## References

1. [Best practices for coding with agents - Cursor](https://cursor.com/blog/agent-best-practices) - Cursor provides two main ways to customize agent behavior: Rules for static context that applies to ...

2. [Cursor Rules, Skills, and Commands, Oh My! When to Use Each ...](https://www.ibuildwith.ai/blog/cursor-rules-skills-and-commands-oh-my-when-to-use-each/) - Cursor gives you three tools to customize your AI agent. Rules shape behavior, skills provide capabi...

3. [BMad's Best Practices Cursor Custom Agents and Rules Generator](https://gist.github.com/bossjones/1fd99aea0e46d427f671f853900a0f2a) - A way to document some best practices around cursor rules and a simple rule that helps generate the ...



Good — I've now identified all the deltas between the previous spec and this updated version. Here are the specific changes that affect the Cursor rules/skills:

## Changes I Found in the Updated Holy Grail

The new spec has **5 meaningful changes** from the version I based the rules on. Here's what's new and what rules need updating:

### 1. Paper-Level Checkpoint System (Upgraded)

**What changed:** The durable execution section in 0.3 now explicitly specifies the paper-level persistence pattern with the `get_processed_paper_ids()` resume pattern, and the `checkpoints` table is redesigned to be lightweight markers (just `status` + `papers_processed`) instead of serializing entire `ReviewState`. [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/4385264/551e8110-126e-4f1f-88e5-830f6eb0a327/paste.txt)

**New SQLite tables:** `workflows` table with `topic`, `config_hash`, `status` for topic-based auto-resume. [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/4385264/551e8110-126e-4f1f-88e5-830f6eb0a327/paste.txt)

**Rule update needed:** `sqlite-patterns-auto.mdc` — update the checkpoint section:

```markdown
## Checkpoint Pattern (UPDATED)
- `workflows` table: one row per review run, keyed by topic + config_hash
- `checkpoints` table: lightweight phase-completion markers (NOT full state serialization)
- Actual data lives in per-paper tables (screening_decisions, extraction_records, rob_assessments)
- Resume pattern: query for already-processed paper_ids, skip them in the loop

```python
# Resume pattern — used in screening, extraction, quality assessment
already_done = await repo.get_processed_paper_ids(workflow_id, stage)
for paper in papers:
    if paper.paper_id in already_done:
        continue  # skip — already persisted
    result = await process_paper(paper)
    await repo.save_screening_decision(result)  # durable immediately
```

## Topic-Based Auto-Resume
- `run` checks `workflows` table for matching topic (by config_hash)
- If match found: prompt user "Found existing run... Resume? (Y/n)"
- `resume --topic` queries workflows table for matching topic (case-insensitive)
```

### 2. Prompt Engineering Patterns (New Section in Phase 3)

**What changed:** Build Phase 3 now includes explicit prompt engineering patterns from your prototype: [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/4385264/551e8110-126e-4f1f-88e5-830f6eb0a327/paste.txt)

- **Topic context injection** — every prompt starts with Role/Goal/Backstory/Topic/Research Question/Domain/Keywords header block
- **Structured output enforcement** — all prompts end with "Return ONLY valid JSON matching this exact schema"
- **Truncation limits** — title/abstract: full text; full-text screening: first 8,000 chars; extraction: first 10,000 chars
- **Confidence thresholds** — auto-include ≥ 0.85, auto-exclude ≥ 0.80, between thresholds → adjudicator

**Rule update needed:** Add a new rule `prompt-patterns-auto.mdc`:

```markdown
---
description:
globs: src/screening/prompts.py, src/extraction/extractor.py, src/quality/**/*.py, src/writing/**/*.py
alwaysApply: false
---

# LLM Prompt Engineering Patterns

## Topic Context Injection (every prompt header)
Every LLM prompt starts with this context block, populated from ReviewConfig:
```
Role: {role from settings.yaml}
Goal: {goal with topic and research_question interpolated}
Backstory: {backstory with domain interpolated}
Topic: {topic}
Research Question: {research_question}
Domain: {domain}
Keywords: {keywords joined by comma}
```

## Structured Output Enforcement
All prompts end with:
"Return ONLY valid JSON matching this exact schema: {schema}"

## Truncation Limits (context window + cost control)
- Title/abstract screening: full title + abstract (no truncation)
- Full-text screening: first 8,000 characters of full text
- Data extraction: first 10,000 characters of full text

## Confidence Thresholds (from config/settings.yaml)
- Auto-include if confidence >= stage1_include_threshold (0.85)
- Auto-exclude if confidence >= stage1_exclude_threshold (0.80)
- Papers between thresholds → sent to adjudicator
```

### 3. New Files in the File Tree

**What changed:** Two new files added to `src/writing/`: [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/4385264/551e8110-126e-4f1f-88e5-830f6eb0a327/paste.txt)
- `style_extractor.py` — Extract writing patterns from included papers
- `naturalness_scorer.py` — Score AI-generated text naturalness (0-1)

**Rule update needed:** The `project-overview-always.mdc` Key Directories section should mention these. And the `section-writer` skill needs updating:

Add to **section-writer SKILL.md**:
```markdown
## Style Extraction (new)
- `src/writing/style_extractor.py` analyzes included papers for writing patterns
- Feeds patterns into section writer prompts for style matching
- Configurable via `writing.style_extraction` in settings.yaml

## Naturalness Scoring (new)
- `src/writing/naturalness_scorer.py` scores AI-generated text (0.0 - 1.0)
- Sections must achieve >= `writing.naturalness_threshold` (0.75) after humanization
- If below threshold: humanizer runs another iteration (up to `humanization_iterations`)
```

### 4. Phase 6 Writing — Updated Acceptance Criteria

**What changed:** Phase 6 now includes: [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/4385264/551e8110-126e-4f1f-88e5-830f6eb0a327/paste.txt)
- "Style patterns extracted from included papers (when enabled)"
- "Per-section checkpoint: kill during writing, restart, picks up at next unwritten section"
- "Naturalness score >= 0.75 for all sections after humanization"

**Skill update needed:** The `build-phase` SKILL.md Phase 6 entry should note the updated acceptance criteria. No new rule needed — the existing writing rules cover this.

### 5. Phase 8 — Topic-Based Auto-Resume & Mid-Phase Resume

**What changed:** Phase 8 now includes detailed resume logic: [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/4385264/551e8110-126e-4f1f-88e5-830f6eb0a327/paste.txt)
1. `resume --topic` queries `workflows` table
2. Within a phase, queries per-paper tables for already-processed IDs
3. If crash mid-screening (50 of 200 papers), resume picks up at paper 51
4. Auto-resume prompt when existing workflow matches topic

**Rule update needed:** The `pydanticai-graph-agent.mdc` rule needs a resume section:

Add:
```markdown
## Resume Logic (paper-level)
1. `resume --topic` queries `workflows` table (case-insensitive match)
2. For matching workflow, query `checkpoints` for last completed phase
3. Determine next phase; within that phase, query per-paper tables for already-processed paper_ids
4. Skip processed papers, continue from where it left off
5. Crash mid-screening (50/200 done) → resume at paper 51

## Auto-Resume on `run`
If `run` is called and workflow exists for same topic (by config_hash):
→ Prompt: "Found existing run for this topic (phase 4/8 complete). Resume? (Y/n)"
```

## Summary: What's Changed vs What's the Same

| Rule/Skill | Status | What to Update |
|:---|:---|:---|
| `project-overview-always.mdc` | **Minor update** | Add `style_extractor.py`, `naturalness_scorer.py` to file tree, mention `workflows` table |
| `build-phase-gate-always.mdc` | ✅ No change | — |
| `no-untyped-dicts-always.mdc` | ✅ No change | — |
| `pydantic-contracts-auto.mdc` | ✅ No change | — |
| `async-io-auto.mdc` | ✅ No change | — |
| `systematic-review-methodology-agent.mdc` | ✅ No change | — |
| `sqlite-patterns-auto.mdc` | **Update** | New checkpoint pattern, `workflows` table, paper-level resume |
| `pydanticai-graph-agent.mdc` | **Update** | Add resume logic + auto-resume on `run` |
| `statsmodels-meta-analysis-agent.mdc` | ✅ No change | — |
| `test-patterns-auto.mdc` | ✅ No change | — |
| **NEW: `prompt-patterns-auto.mdc`** | **Add** | Topic context injection, structured output, truncation limits, confidence thresholds |
| `build-phase` SKILL | **Minor update** | Phase 6 acceptance criteria additions |
| `section-writer` SKILL | **Update** | Add style extraction + naturalness scoring sections |
| `dual-reviewer` SKILL | **Update** | Add prompt engineering patterns (context injection, truncation, thresholds) |
| All other skills | ✅ No change | — |
| All commands | ✅ No change | — |

The core architecture of the rules system is still correct. The changes are mostly **additive** (one new rule, updates to existing rules) rather than structural, which is exactly what you want — the rules framework was designed for this kind of iterative refinement. [cursor](https://cursor.com/blog/agent-best-practices)