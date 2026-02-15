# Cursor Rules, Skills & Commands Reference

Copy-paste ready content for creating all Cursor rules, skills, and commands for the Holy Grail systematic review build. Use with `/cursor` then select `create-rule` or `create-skill`, or paste directly into chat.

---

## Quick Start

### How to Use

1. **Invoke via chat**: Type `/cursor` in Cursor chat, select `create-rule` or `create-skill`, then paste the content block when the agent asks for it
2. **Paste directly**: In a new chat, "Create this rule: [paste content]"
3. **Create files manually**: Copy content into `.cursor/rules/`, `.cursor/skills/`, `.cursor/commands/` as appropriate

### Gitignore Change

Remove `.cursor/` from `.gitignore` so project rules, skills, and commands are version-controlled and shared with collaborators.

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
│   │   └── prompt-patterns-auto.mdc
│   ├── domain/
│   │   └── systematic-review-methodology-agent.mdc
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

### create-subagent Note

Cursor's built-in skills are: `create-rule`, `create-skill`, `migrate-to-skills`, `update-cursor-settings`. There is no `create-subagent` skill. The agent transcript showed "Subagent" as an internal tool for parallel exploration. Add a custom skill or command if you need subagent-like workflows.

---

## RULES

### Rule 1: project-overview-always.mdc

**Path:** `.cursor/rules/core/project-overview-always.mdc`

```
/create-rule
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
- `src/writing/` — Section writer, per-section prompts, humanizer, style_extractor.py, naturalness_scorer.py
- `src/citation/` — Citation ledger (claim -> evidence -> citation chain)
- `src/export/` — IEEE LaTeX, submission packager, PRISMA checklist validator
- `config/` — review.yaml (per-review), settings.yaml (system behavior)

## Key Tables
- `workflows` — topic, config_hash, status for topic-based auto-resume

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

---

### Rule 2: build-phase-gate-always.mdc

**Path:** `.cursor/rules/core/build-phase-gate-always.mdc`

```
/create-rule
---
description:
globs:
alwaysApply: true
---

# Build Phase Discipline

## Current Build Order
Phase 1: Foundation -> Phase 2: Search -> Phase 3: Screening -> Phase 4: Extraction & Quality -> Phase 5: Synthesis -> Phase 6: Writing -> Phase 7: PRISMA & Viz -> Phase 8: Export & Orchestration

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

---

### Rule 3: no-untyped-dicts-always.mdc

**Path:** `.cursor/rules/core/no-untyped-dicts-always.mdc`

```
/create-rule
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

---

### Rule 4: pydantic-contracts-auto.mdc

**Path:** `.cursor/rules/python/pydantic-contracts-auto.mdc`

```
/create-rule
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

---

### Rule 5: async-io-auto.mdc

**Path:** `.cursor/rules/python/async-io-auto.mdc`

```
/create-rule
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

---

### Rule 6: systematic-review-methodology-agent.mdc

**Path:** `.cursor/rules/domain/systematic-review-methodology-agent.mdc`

```
/create-rule
---
description: Core systematic review methodology rules. Apply when implementing any phase of the systematic review pipeline, writing screening logic, implementing quality assessment, or generating manuscript sections. Contains PRISMA 2020, GRADE, and Cochrane methodology requirements.
globs:
alwaysApply: false
---

# Systematic Review Methodology

## Seven Core Steps (must execute in order)
1. Define research question (PICO/PICo/PICOT)
2. Develop and register protocol (PROSPERO format)
3. Conduct search (>=3 databases + grey literature, full Boolean strings documented)
4. Screen studies (dual independent review, two-stage: title/abstract -> full-text)
5. Assess quality (domain-based RoB tools, NEVER summary quality scores)
6. Extract and synthesize (dual extraction, meta-analysis when feasible)
7. Present findings (GRADE SoF table, PRISMA diagram, structured manuscript)

## Risk of Bias Tool Routing
- RCTs -> RoB 2 (5 domains: randomization, deviations, missing data, measurement, selection)
- Non-randomized -> ROBINS-I (7 domains, different judgment scale: Low/Moderate/Serious/Critical/No Info)
- Qualitative -> CASP
- NEVER use summary quality scores — always domain-based assessment

## Meta-Analysis Thresholds
- I^2 < 40%: fixed-effect model
- I^2 >= 40%: random-effects (DerSimonian-Laird)
- Funnel plot: only when >= 10 studies
- Statistics computed by scipy/statsmodels ONLY, never by LLM

## GRADE: 8 Factors
- 5 downgrade: risk of bias, inconsistency, indirectness, imprecision, publication bias
- 3 upgrade: large effect, dose-response, residual confounding
- Starting: High for RCTs, Low for observational
```

---

### Rule 7: sqlite-patterns-auto.mdc (with delta updates)

**Path:** `.cursor/rules/tool/sqlite-patterns-auto.mdc`

```
/create-rule
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

---

### Rule 8: pydanticai-graph-agent.mdc (with delta updates)

**Path:** `.cursor/rules/tool/pydanticai-graph-agent.mdc`

```
/create-rule
---
description: PydanticAI Graph API patterns and conventions. Apply when working on src/orchestration/graph.py, implementing workflow nodes, or connecting phases together. Uses the stable BaseNode API, not the beta GraphBuilder API.
globs:
alwaysApply: false
---

# PydanticAI Graph Patterns

## Use the stable BaseNode API (NOT beta GraphBuilder)
Import from pydantic_graph (see https://ai.pydantic.dev/graph/):
```python
from pydantic_graph import BaseNode, End, Graph, GraphRunContext

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

## Resume Logic (paper-level)
1. `resume --topic` queries `workflows` table (case-insensitive match)
2. For matching workflow, query `checkpoints` for last completed phase
3. Determine next phase; within that phase, query per-paper tables for already-processed paper_ids
4. Skip processed papers, continue from where it left off
5. Crash mid-screening (50/200 done) -> resume at paper 51

## Auto-Resume on `run`
If `run` is called and workflow exists for same topic (by config_hash):
-> Prompt: "Found existing run for this topic (phase 4/8 complete). Resume? (Y/n)"
```

---

### Rule 9: statsmodels-meta-analysis-agent.mdc

**Path:** `.cursor/rules/tool/statsmodels-meta-analysis-agent.mdc`

```
/create-rule
---
description: Meta-analysis implementation patterns using statsmodels. Apply when working on src/synthesis/ files, implementing effect size calculations, forest plots, or funnel plots. Critical rule: LLMs must NEVER compute statistics.
globs:
alwaysApply: false
---

# Meta-Analysis Patterns (statsmodels)

## CRITICAL: No LLM Statistics
LLMs must NEVER compute effect sizes, p-values, confidence intervals, or any statistical measures.
Extract raw data from ExtractionRecord -> pass to deterministic scipy/statsmodels functions.

## Effect Sizes
See https://www.statsmodels.org/dev/generated/statsmodels.stats.meta_analysis.effectsize_smd.html
```python
from statsmodels.stats.meta_analysis import effectsize_smd, effectsize_2proportions
# Continuous: effectsize_smd(mean1, sd1, nobs1, mean2, sd2, nobs2)
# Dichotomous: effectsize_2proportions(count1, nobs1, count2, nobs2, statistic="rd"|"rr"|"or"|"as")
# statistic: "diff"/"rd", "risk-ratio"/"rr", "odds-ratio"/"or", "arcsine"/"as"
```

## Pooling
See https://www.statsmodels.org/dev/generated/statsmodels.stats.meta_analysis.combine_effects.html
```python
from statsmodels.stats.meta_analysis import combine_effects
# Fixed: combine_effects(effect, variance, method_re="iterated", use_t=False)
# Random (DL): combine_effects(effect, variance, method_re="chi2"|"dl", use_t=True)
# method_re: "iterated"/"pm" (Paule-Mandel) or "chi2"/"dl" (DerSimonian-Laird)
# Choose based on I^2: fixed if < 40%, random if >= 40%
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

---

### Rule 10: test-patterns-auto.mdc

**Path:** `.cursor/rules/testing/test-patterns-auto.mdc`

```
/create-rule
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

---

### Rule 11: prompt-patterns-auto.mdc (NEW from delta)

**Path:** `.cursor/rules/python/prompt-patterns-auto.mdc`

```
/create-rule
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
- Papers between thresholds -> sent to adjudicator
```

---

## SKILLS

### Skill 1: build-phase/SKILL.md (with Phase 6 updates)

**Path:** `.cursor/skills/build-phase/SKILL.md`

```
/create-skill
---
name: build-phase
description: Guides the agent through implementing each build phase of the systematic review tool step-by-step. Use when implementing phases 1-8, running acceptance criteria, or determining current build phase.
---

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
| 6: Writing | Section writer, Prompts, SoF, Humanizer, style_extractor, naturalness_scorer; per-section checkpoint; naturalness >= 0.75 | test_writing_pipeline |
| 7: PRISMA/Viz | PRISMA diagram, Timeline, Geographic | test_prisma_diagram |
| 8: Export | Graph wiring, IEEE LaTeX, CLI | test_ieee_export, test_ieee_validator, test_full_review |

## Phase 6 Acceptance Criteria (updated)
- Style patterns extracted from included papers (when enabled)
- Per-section checkpoint: kill during writing, restart, picks up at next unwritten section
- Naturalness score >= 0.75 for all sections after humanization

## References
@file:docs/Holy Grail Build Specification.md
```

---

### Skill 2: search-connector/SKILL.md

**Path:** `.cursor/skills/search-connector/SKILL.md`

```
/create-skill
---
name: search-connector
description: Implements database connectors conforming to SearchConnector protocol. Use when adding OpenAlex, PubMed, arXiv, IEEE Xplore connectors or implementing search strategy.
---

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

---

### Skill 3: dual-reviewer/SKILL.md (with prompt engineering updates)

**Path:** `.cursor/skills/dual-reviewer/SKILL.md`

```
/create-skill
---
name: dual-reviewer
description: Implements dual-reviewer screening with two independent AI reviewers and adjudicator. Use when building screening logic, prompts, or reliability computation.
---

# Dual-Reviewer Screening System

Guide for implementing the core screening architecture with two independent AI reviewers and an adjudicator.

## Architecture

```
Paper -> Reviewer A (Flash-Lite, temp=0.1, inclusion-emphasis)
      -> Reviewer B (Flash-Lite, temp=0.3, exclusion-emphasis)
      
If agree -> final_decision = agreed decision
If disagree -> Adjudicator (Pro, temp=0.2) sees both decisions -> final
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

## Prompt Engineering Patterns
- **Topic context injection**: Every prompt starts with Role/Goal/Backstory/Topic/Research Question/Domain/Keywords header block
- **Structured output**: All prompts end with "Return ONLY valid JSON matching this exact schema"
- **Truncation**: Title/abstract = full text; full-text = first 8,000 chars; extraction = first 10,000 chars
- **Confidence thresholds**: Auto-include >= 0.85, auto-exclude >= 0.80, between -> adjudicator

## References
- Prompt templates: `src/screening/prompts.py`
- Reliability: `src/screening/reliability.py`
```

---

### Skill 4: meta-analysis/SKILL.md

**Path:** `.cursor/skills/meta-analysis/SKILL.md`

```
/create-skill
---
name: meta-analysis
description: Implements meta-analysis using statsmodels. Use when building effect size calculations, forest plots, funnel plots, or synthesis pipeline.
---

# Meta-Analysis Implementation

Guide for implementing statistical synthesis using statsmodels.

## CRITICAL RULE
LLMs must NEVER compute statistics. All calculations use deterministic functions.

## Workflow

1. **Feasibility check** (LLM-assisted): Are studies clinically similar enough to pool?
2. **Extract raw data** from `ExtractionRecord` (means, SDs, counts, events)
3. **Compute effect sizes** using statsmodels functions
4. **Assess heterogeneity** (I^2, Q, tau^2)
5. **Select model**: fixed if I^2 < 40%, random-effects if I^2 >= 40%
6. **Pool effects** using `combine_effects()`
7. **Generate forest plot** using `.plot_forest()`
8. **Generate funnel plot** (matplotlib scatter) if >= 10 studies
9. **Store results** as `MetaAnalysisResult` in SQLite

## Effect Size Functions
- Continuous: `effectsize_smd(mean1, sd1, n1, mean2, sd2, n2)`
- Dichotomous: `effectsize_2proportions(count1, n1, count2, n2, statistic="log-rr")`

## Known Limitations
- Mantel-Haenszel NOT available in statsmodels — use DerSimonian-Laird
- statsmodels meta-analysis API is marked "experimental"
- Verify results against R metafor if possible
```

---

### Skill 5: section-writer/SKILL.md (with style extraction + naturalness updates)

**Path:** `.cursor/skills/section-writer/SKILL.md`

```
/create-skill
---
name: section-writer
description: Implements manuscript section writing with citation lineage. Use when building section writer, humanizer, or citation ledger integration.
---

# Manuscript Section Writing

Guide for implementing the section writer with full citation lineage enforcement.

## Per-Section Requirements

### Abstract (<= 250 words)
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

## Style Extraction (new)
- `src/writing/style_extractor.py` analyzes included papers for writing patterns
- Feeds patterns into section writer prompts for style matching
- Configurable via `writing.style_extraction` in settings.yaml

## Naturalness Scoring (new)
- `src/writing/naturalness_scorer.py` scores AI-generated text (0.0 - 1.0)
- Sections must achieve >= `writing.naturalness_threshold` (0.75) after humanization
- If below threshold: humanizer runs another iteration (up to `humanization_iterations`)
```

---

### Skill 6: ieee-export/SKILL.md

**Path:** `.cursor/skills/ieee-export/SKILL.md`

```
/create-skill
---
name: ieee-export
description: Implements IEEE LaTeX export and submission packaging. Use when building export, PRISMA checklist validator, or IEEE compliance checks.
---

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
- PRISMA checklist >= 24/27 items reported
- Citation lineage: zero unresolved citations
```

---

## COMMANDS

Create these files in `.cursor/commands/`. The file content IS the command prompt.

### Command 1: run-tests.md

**Path:** `.cursor/commands/run-tests.md`

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

---

### Command 2: validate-prisma.md

**Path:** `.cursor/commands/validate-prisma.md`

```markdown
Run PRISMA 2020 checklist validation on the current manuscript.

1. Load the latest section drafts from SQLite
2. Run `src/export/prisma_checklist.py` validator
3. Report status for all 27 items: REPORTED / PARTIAL / MISSING
4. Highlight any items below the 24/27 threshold
```

---

### Command 3: check-gates.md

**Path:** `.cursor/commands/check-gates.md`

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

---

### Command 4: run-review.md

**Path:** `.cursor/commands/run-review.md`

```markdown
Run the full systematic review pipeline.

```bash
python -m src.main run --config config/review.yaml
```

Monitor progress and report any gate failures or HITL checkpoints that need attention.
```

---

## HOOKS

**Path:** `.cursor/hooks.json`

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
