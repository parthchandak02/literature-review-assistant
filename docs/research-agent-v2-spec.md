# Systematic Review Automation Tool -- Build Specification v2.0

**Document Type:** Single Source of Truth for Ground-Up Build
**Date:** February 16, 2026
**Owner:** Parth Chandak
**Purpose:** Produce IEEE-submission-ready systematic review manuscripts meeting PRISMA 2020, Cochrane, and GRADE standards -- fully automated from research question to submission package.

***

# PART 0: STRATEGIC CONTEXT

## 0.1 Why This Exists

The owner needs to publish 3-4 systematic review papers per year in IEEE journals (IEEE Access, IEEE CG&A, IEEE Transactions on Human-Machine Systems) to support an EB-1A extraordinary ability visa petition. Speed to first publication is the #1 priority. The tool must produce manuscripts that pass peer review without requiring the user to manually perform systematic review methodology steps.

## 0.2 Why Fresh Build (Not Enhancement)

A prior prototype exists at `github.com/parthchandak02/literature-review-assistant` with a working 12-phase pipeline. The decision to rebuild from scratch is driven by:[^1]

1. **The old codebase has `Any` types** scattered through `WorkflowState`, making Pydantic contract enforcement a retrofit surgery
2. **The checkpoint system** serializes Python objects to JSON via custom `StateSerializer` -- fragile for citation lineage and dual-reviewer data
3. **9+ database connectors** have inconsistent interfaces with no shared contract
4. **6+ major new systems are needed** (dual-reviewer, citation ledger, meta-analysis, RoB 2, IEEE export, quality gates) -- more new code than existing code
5. **This tool is long-term infrastructure** for years of publications; technical debt now compounds exponentially

**What to carry forward as reference** (copy patterns, not code):
- Database connector API call patterns (PubMed, arXiv, Semantic Scholar, IEEE Xplore, Scopus, Crossref)
- Search strategy Boolean query builder logic
- CASP prompt templates
- Gemini provider integration pattern

## 0.3 Key Architectural Decisions (With Reasoning)

### Orchestration: PydanticAI Graph -- NOT LangGraph, NOT Custom

**Decision:** Use **PydanticAI** with its Graph API for workflow orchestration.

**Reasoning:**
- PydanticAI is built by the Pydantic team -- we already depend on Pydantic for every data contract, so this is a natural fit[^2][^3]
- Its Graph API provides typed, node-based workflow orchestration with explicit state, exactly what we need for phase-to-phase handoff[^4][^5]. **Note:** PydanticAI has two Graph APIs: the original `BaseNode` subclass pattern and a newer beta builder-pattern API (`GraphBuilder`). Use the **original API** (`BaseNode` subclasses with `GraphRunContext` and `End` return) for v1 as it is more stable. The beta API offers cleaner parallel execution (`.map()`, `.broadcast()`) but is newer; migrate to it only if the original proves too verbose.
- It has native **durable execution** support (via Temporal/DBOS/Prefect) for crash recovery and long-running workflows[^6][^7]. **Note:** These require external infrastructure. For v1 (local-first CLI), implement **paper-level SQLite persistence** -- write each individual decision/extraction/assessment to its own table immediately, with a lightweight `checkpoints` table for phase-completion markers. This gives paper-level resume (crash mid-screening -> restart picks up at next unprocessed paper) without adding Postgres or a new framework. Migrating to DBOS later is a one-day decorator change.
- It's **model-agnostic** -- supports Gemini, OpenAI, Anthropic, so we're not locked to one provider[^8]
- LangGraph adds a dependency on the entire LangChain ecosystem, which is heavier than we need and has well-documented abstraction complexity[^9][^10]
- A fully custom orchestrator means writing and maintaining our own state machine, checkpointing, and resume logic -- PydanticAI gives us this for free[^9]
- **Requires Python 3.10+** (PydanticAI minimum)

### Database: SQLite -- NOT Postgres

**Decision:** Use **SQLite** for all persistent storage (citation ledger, decision log, gate results, extraction data).

**Reasoning:**
- This is a **single-user, local-first CLI tool** with zero concurrent write contention[^11][^12]
- SQLite is literally a single file -- trivially portable, zero deployment setup, copy-to-backup[^13]
- SQLite handles databases up to 100GB+ comfortably; our data will never exceed a few MB per review[^14]
- Postgres adds a service dependency (installation, authentication, connection management) with zero benefit at this scale[^11]
- If we ever need Postgres (e.g., for a multi-user web app), SQLite -> Postgres migration is straightforward because we use Pydantic models as the interface layer

### LLM: Google Gemini 2.5 -- 3-Tier Model Selection

**Decision:** Use three Gemini tiers matched to task complexity and volume. This is battle-tested from the existing prototype.

| Tier | Model | Cost (input/output per 1M tokens) | Use For |
|:---|:---|:---|:---|
| Bulk | Gemini 2.5 Flash-Lite | $0.10 / $0.40 | Title/abstract screening, full-text screening (high-volume classification) |
| Balanced | Gemini 2.5 Flash | $0.30 / $2.50 | Search coordination, abstract generation, study type detection |
| Quality | Gemini 2.5 Pro | $1.25 / $10.00 | Extraction, writing, quality assessment, adjudication, humanization, style extraction |

**Reasoning:**
- Flash-Lite is 3x cheaper than Flash and 12.5x cheaper than Pro on input -- ideal for bulk classification where accuracy is "good enough" and volume is high (hundreds of papers)[^15][^16]
- Flash-Lite provides sufficient accuracy for screening classification (keyword pre-filter handles most cases; LLM only processes uncertain papers)
- Flash handles moderate-complexity tasks at good cost/quality ratio
- Pro is reserved for tasks requiring complex reasoning, structured extraction, or polished writing
- All Gemini 2.5 models share a 1M token context window -- can fit entire papers for full-text screening[^17]
- Free tier allows 10 RPM for Flash, 15 RPM for Flash-Lite, and 5 RPM for Pro -- sufficient for a single review run with rate limiting[^18]
- Paid tier: Flash gets 2,000 RPM, 4M TPM -- more than enough[^17]
- Per-agent model assignments are configured in `config/settings.yaml` (see Part 6) to allow tuning without code changes

### Search: OpenAlex (primary) + direct database APIs + auxiliary discovery

**Decision:** Use **OpenAlex** as the primary academic search engine (via direct REST API with `api_key` in URL), supplemented by direct PubMed/arXiv/IEEE Xplore APIs, plus Semantic Scholar and Crossref connectors for recall expansion. Perplexity search may be used as an auxiliary discovery source (other_source only), not as a replacement for academic database evidence.

**Reasoning:**
- OpenAlex indexes 250M+ scholarly works, is CC0 licensed, and requires a free API key (mandatory since Feb 2026; credit-based rate limiting)[^19][^20]
- OpenAlex connector uses direct aiohttp calls with `api_key` as URL parameter (per OpenAlex Feb 2026 requirement); plaintext abstracts derived from `abstract_inverted_index` in code[^19]
- OpenAlex provides broad baseline scholarly coverage, but connector-level retrieval can still vary by topic, indexing lag, and query shape; adding Semantic Scholar and Crossref improves recall for practical runs.
- Supplement with PubMed (for biomedical, via Entrez), arXiv (via arXiv API), IEEE Xplore (via IEEE API), Semantic Scholar (Academic Graph API), and Crossref (Works API).
- Perplexity search can be used as an auxiliary "other sources" connector for discovery and citation leads; items from auxiliary sources require verification against academic records before evidence use.
- Exa/Tavily/Perplexity web-style APIs are discovery tools, not primary systematic review databases; use them only in auxiliary mode.

### Meta-Analysis: statsmodels -- NOT custom implementation

**Decision:** Use `statsmodels.stats.meta_analysis.combine_effects()` for meta-analysis.

**Reasoning:**
- statsmodels has a `combine_effects()` function supporting fixed-effect and random-effects models (DerSimonian-Laird via `method_re="chi2"`, Paule-Mandel via `method_re="iterated"`)[^22][^23]. **Note:** The statsmodels meta-analysis API is marked "experimental" -- results are verified against R metafor but the API may change. Also: **Mantel-Haenszel method is NOT available** in statsmodels; use DerSimonian-Laird for binary outcome pooling.
- Effect size functions available: `effectsize_smd` (standardized mean difference) and `effectsize_2proportions` (risk difference, log risk ratio, log odds ratio, arcsine sqrt)
- It includes a built-in `.plot_forest()` method that produces publication-quality forest plots[^24]
- No need to implement meta-analysis from scratch -- this is well-tested statistical code
- Funnel plots can be generated with simple matplotlib scatter plots using the effect sizes and standard errors from statsmodels output

### Package Management: `uv`

**Decision:** Use `uv` for dependency management and virtual environments.

**Reasoning:** Already in use in the existing project. Fast, reliable, single tool for `pip install`, `venv`, and running tests.

***

# PART 0B: IMPLEMENTATION STATUS

*Living section: update as phases complete.*

| Area | Status | Notes |
|:---|:---|:---|
| Phase 1: Foundation | Implemented | Models, SQLite, gates, citation ledger, LLM provider |
| Phase 2: Search | Implemented | OpenAlex, PubMed, arXiv, IEEE, Semantic Scholar, Crossref, Perplexity, dedup, protocol |
| Phase 3: Screening | Implemented | Dual reviewer, adjudication, kappa, Ctrl+C proceed-with-partial |
| Phase 4: Extraction & Quality | Implemented | LLM extraction (Gemini Pro, ExtractionResponse->ExtractionRecord) with heuristic fallback; async LLM RoB 2, ROBINS-I, CASP assessors (Gemini Pro) with heuristic fallback; GRADE; study router; RoB figure |
| Phase 5: Synthesis | Implemented | Feasibility gates pooling; pool_effects() via statsmodels; render_forest_plot() + render_funnel_plot() wired into SynthesisNode; fig_forest_plot.png/fig_funnel_plot.png in artifacts; narrative fallback when no numeric data |
| Phase 6: Writing | Implemented | Section writer (Gemini Flash); LLM humanizer (Gemini Pro, humanization_iterations from settings.yaml) per section; citation validation; style extractor |
| Phase 7: PRISMA & Viz | Implemented | PRISMA diagram (prisma-flow-diagram + fallback), timeline, geographic, uniform naming, ROBINS-I in RoB figure |
| Phase 8: Export & Orchestration | Implemented | Run/resume done; export/validate/status wired; src/export/ (ieee_latex, submission_packager, ieee_validator, prisma_checklist, bibtex_builder); pdflatex |
| Resume | Implemented | Registry, topic-based auto-resume on run, workflow-id lookup, mid-phase resume, fallback scan of run_summary.json |
| Post-Phase-8 DB Improvements | Implemented | display_label column in papers table; synthesis_results table for typed synthesis persistence; dedup_count column in workflows; compute_display_label() canonical utility in src/models/papers.py as single source of truth |
| Post-Phase-8 Diagram Fixes | Implemented | RoB figure reads display_label from DB instead of local heuristics; bar labels on publication timeline; dynamic label rotation on geographic distribution chart |
| Post-Phase-8 Search Limits | Implemented | SearchConfig model with max_results_per_db (default 500) and per_database_limits (per-connector overrides); replaces hardcoded max_results=100 in workflow.py |
| Phase 3 Screening Efficiency | Implemented | keyword_filter.py pre-filter (ExclusionReason.KEYWORD_FILTER, cuts LLM calls ~80%); BM25 relevance ranking when max_llm_screen is set (bm25s library, top-N by topic score go to LLM, tail papers get LOW_RELEVANCE_SCORE decision written to DB for PRISMA compliance); confidence fast-path; asyncio.Semaphore concurrency; reset_partial_flag() Ctrl+C fix; skip_fulltext_if_no_pdf; max_llm_screen hard cap for cost control |
| Web UI | Implemented | FastAPI SSE backend (16 endpoints: run, stream, cancel, history, attach, DB explorer, events, artifacts, export); React/Vite/TypeScript frontend (7 views: Setup, Overview, Cost, Database, Log, Results, History); client-side cost tracking from api_call events; run history via workflows_registry; DB explorer for papers/screening/costs; static frontend served from frontend/dist/ |

***

# PART 0C: NEXT STEPS

*Living section: remaining work to reach first IEEE submission.*

**All 8 phases complete. Core pipeline is end-to-end and all LLM integrations are wired.**

Verification: `uv run pytest tests/unit -q` (86 pass), `uv run python -m src.main run --config config/review.yaml`.

**What was just implemented (latest wave):**

- **Gap 1 -- Meta-analysis + forest + funnel wired:** `SynthesisNode` calls `pool_effects()` (statsmodels DL), `render_forest_plot()`, and `render_funnel_plot()` when numeric effect data is available from LLM extraction; gracefully falls back to narrative when no numeric data; artifacts `fig_forest_plot.png` / `fig_funnel_plot.png` registered at startup.
- **Gap 2 -- LLM-based extraction:** `ExtractionService._llm_extract()` sends paper text to Gemini Pro with a structured `_ExtractionLLMResponse` JSON schema; populates all `ExtractionRecord` fields including `outcomes[].effect_size` and `outcomes[].se` for downstream pooling; heuristic fallback on API error.
- **Gap 3 -- LLM-based quality assessment:** `Rob2Assessor.assess()`, `RobinsIAssessor.assess()`, `CaspAssessor.assess()` are now `async`; each sends extraction record + full text to Gemini Pro with a typed JSON schema for the respective assessment model; heuristic fallback on API error.
- **Gap 4 -- LLM humanizer:** `humanize_async()` in `src/writing/humanizer.py` makes a real Gemini Pro call using `_HUMANIZE_PROMPT_TEMPLATE`; `WritingNode` applies it for `humanization_iterations` passes per section when `settings.writing.humanization=true`.
- **Gap 5 -- Shared Gemini client:** `src/llm/gemini_client.py` -- reusable `GeminiClient` with exponential-backoff retry on 429/502/503/504 (max 5 retries); used by extraction, quality, and humanizer; separate from screening's `GeminiScreeningClient`.
- **Gap 6 -- Web UI:** Full FastAPI SSE backend (`src/web/app.py`, 16 endpoints) + React/Vite/TypeScript frontend (`frontend/`) with 7 views (Setup, Overview, Cost, Database, Log, Results, History); DB explorer for papers/screening/costs; run history via `workflows_registry`; client-side cost aggregation from `api_call` SSE events; see `docs/frontend-spec.md` for full frontend architecture.
- **Gap 7 -- Screening cost cap + BM25 ranking:** `max_llm_screen` field in `ScreeningConfig` (default 100 in settings.yaml); when set, `bm25_rank_and_cap()` in `keyword_filter.py` BM25-ranks all candidate papers by topic relevance (using the `bm25s` library); top N papers go to LLM dual-review; papers below the cap receive `ExclusionReason.LOW_RELEVANCE_SCORE` decisions written directly to the DB with their BM25 score and rank so PRISMA flow counts are accurate. The keyword pre-filter is bypassed as a hard gate when a cap is active (it reverts to a soft hint).
- **Gap 8 -- Spec updated:** Part 0B, 0C, and file structure reflect current state.

**Remaining work to reach first IEEE submission:**

1. Run the full pipeline end-to-end and review output quality (manuscript, PRISMA diagram, RoB figure, synthesis section).
2. Confirm PRISMA checklist >= 24/27 on a real run.
3. Run `uv run python -m src.main export` and verify IEEE LaTeX compiles to PDF.
4. Build the React frontend production bundle (`pnpm run build` in `frontend/`) and verify static serving from FastAPI.
5. Address any output quality issues found during validation run.

***

# PART 1: SYSTEMATIC REVIEW METHODOLOGY REFERENCE

This section encodes the validated research methodology the tool must implement. Every requirement has been verified against the Cochrane Handbook, PRISMA 2020, and GRADE guidelines.[^25]

## 1.1 The Seven Core Steps

The tool must execute these steps in order:

1. **Define the research question** using the PICO framework (Population, Intervention, Comparison, Outcome) for quantitative studies or PICo (Population, Interest, Context) for qualitative ones[^25]
2. **Develop and register the review protocol** specifying search strategies, eligibility criteria, planned methods, and risk of bias tools -- output PROSPERO-format protocol[^25]
3. **Conduct the search** across at least 3 core databases plus grey literature, documenting full search strings for every database (PRISMA-S requirement)[^25]
4. **Screen the studies** using at least two independent reviewers in a two-stage process (title/abstract -> full-text), documented via PRISMA 2020 flow diagram[^25]
5. **Assess the quality** using domain-based risk of bias tools (RoB 2 for RCTs, ROBINS-I for non-randomized studies) -- never summary quality scores[^25]
6. **Extract and synthesize data** using dual extraction, with meta-analysis (forest plot) when studies are sufficiently similar, and funnel plot to assess publication bias[^25]
7. **Present findings** as a structured manuscript (abstract, introduction, methods, results, discussion, conclusion) with GRADE Summary of Findings table[^25]

## 1.2 PRISMA 2020 Requirements

The manuscript must report ALL 27 PRISMA 2020 checklist items. Critical items:

- **Item 3:** Eligibility criteria with PICO components
- **Item 4:** Information sources with dates of last search
- **Item 5:** Full search strategy for ALL databases (as appendix -- PRISMA-S)
- **Item 6:** Selection process including number of reviewers and agreement mechanism
- **Item 7:** Data collection process
- **Item 8:** Study risk of bias assessment tools
- **Item 13a:** Results of synthesis with forest plot
- **Item 13d:** Assessment of certainty (GRADE)
- **Item 15:** Reporting biases with funnel plot

The PRISMA 2020 flow diagram must use the **two-column structure**:[^25]
- Left column: "Records identified from Databases and Registers" (per-database counts)
- Right column: "Records identified from Other Sources" (citation searching, grey literature)

## 1.3 GRADE Framework

For each outcome, assess certainty of evidence across 8 factors:[^25]

**Five downgrading factors:** Risk of bias, Inconsistency (heterogeneity), Indirectness, Imprecision, Publication bias

**Three upgrading factors:** Large magnitude of effect, Dose-response gradient, Residual confounding reducing demonstrated effect

**Starting certainty:** High for RCTs, Low for observational studies.

## 1.4 Risk of Bias Tool Selection

| Study Design | Required Tool | Key Domains |
|:---|:---|:---|
| Randomized controlled trials | **RoB 2** (Cochrane) | Randomization, deviations, missing data, measurement, reported result[^25] |
| Non-randomized interventions | **ROBINS-I** | Confounding, selection, classification, deviations, missing data, measurement, reported result |
| Cohort / case-control | **Newcastle-Ottawa Scale** | Selection, comparability, outcome/exposure (Note: NOS is out of scope for v1; cohort/case-control studies use ROBINS-I instead) |
| Qualitative research | **CASP** | Various design-specific checklists |

Output: Domain-based judgment per study (Low / Some concerns / High for RoB 2; Low / Moderate / Serious / Critical / No Information for ROBINS-I). Never a single summary score.[^25]

**RoB 2 Signalling Questions (5 domains, per Cochrane guidance):**
- **D1 - Randomization process:** Was the allocation sequence random? Was the allocation sequence concealed until participants were enrolled?
- **D2 - Deviations from intended interventions:** Were participants aware of their assigned intervention? Were there deviations from the intended intervention beyond what would be expected?
- **D3 - Missing outcome data:** Were outcome data available for all (or nearly all) participants? Could missingness depend on the true value of the outcome?
- **D4 - Measurement of the outcome:** Was the method of measuring the outcome appropriate? Could assessment of the outcome have differed between groups?
- **D5 - Selection of the reported result:** Were multiple eligible outcome measurements or analyses available? Was the reported result likely selected from multiple measurements or analyses?

Each domain produces a judgment via algorithm based on signalling question answers. Overall: All Low -> Low; Any High -> High; Otherwise -> Some Concerns.

## 1.5 Meta-Analysis Requirements

When studies are sufficiently clinically and statistically similar:[^25]

- **Effect measures:** OR/RR for dichotomous; MD/SMD for continuous
- **Models:** Fixed-effect when homogeneous; Random-effects (DerSimonian-Laird) when I^2 >= 40%
- **Heterogeneity:** Cochran's Q test + I^2 (0-40% low, 30-60% moderate, 50-90% substantial, 75-100% considerable)
- **Forest plot:** Required for each outcome -- individual + pooled estimates + CIs
- **Funnel plot:** Required when >= 10 studies to assess publication bias[^25]

When meta-analysis is NOT feasible: structured narrative synthesis with effect direction tables.

***

# PART 2: COMPLETE DATA CONTRACTS

All phase IO must use these Pydantic models. **No untyped dictionaries allowed at phase boundaries.**

```python
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime, timezone
import uuid

# ============================================================
# ENUMS
# ============================================================

class ReviewType(str, Enum):
    SYSTEMATIC = "systematic"
    SCOPING = "scoping"
    NARRATIVE = "narrative"

class ScreeningDecisionType(str, Enum):
    INCLUDE = "include"
    EXCLUDE = "exclude"
    UNCERTAIN = "uncertain"

class ReviewerType(str, Enum):
    REVIEWER_A = "reviewer_a"
    REVIEWER_B = "reviewer_b"
    ADJUDICATOR = "adjudicator"
    HUMAN = "human"

class RiskOfBiasJudgment(str, Enum):
    """For RoB 2 (RCTs): Low / Some concerns / High"""
    LOW = "low"
    SOME_CONCERNS = "some_concerns"
    HIGH = "high"

class RobinsIJudgment(str, Enum):
    """For ROBINS-I (non-randomized): separate scale from RoB 2"""
    LOW = "low"
    MODERATE = "moderate"
    SERIOUS = "serious"
    CRITICAL = "critical"
    NO_INFORMATION = "no_information"

class GateStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"

class ExclusionReason(str, Enum):
    WRONG_POPULATION = "wrong_population"
    WRONG_INTERVENTION = "wrong_intervention"
    WRONG_COMPARATOR = "wrong_comparator"
    WRONG_OUTCOME = "wrong_outcome"
    WRONG_STUDY_DESIGN = "wrong_study_design"
    NOT_PEER_REVIEWED = "not_peer_reviewed"
    DUPLICATE = "duplicate"
    INSUFFICIENT_DATA = "insufficient_data"
    WRONG_LANGUAGE = "wrong_language"
    NO_FULL_TEXT = "no_full_text"
    KEYWORD_FILTER = "keyword_filter"  # pre-filter: zero intervention keyword matches; no LLM call made
    OTHER = "other"

class GRADECertainty(str, Enum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    VERY_LOW = "very_low"

class StudyDesign(str, Enum):
    RCT = "rct"
    NON_RANDOMIZED = "non_randomized"
    COHORT = "cohort"
    CASE_CONTROL = "case_control"
    QUALITATIVE = "qualitative"
    MIXED_METHODS = "mixed_methods"
    CROSS_SECTIONAL = "cross_sectional"
    OTHER = "other"

class SourceCategory(str, Enum):
    DATABASE = "database"
    OTHER_SOURCE = "other_source"

# ============================================================
# CONFIGURATION
# ============================================================

class PICOConfig(BaseModel):
    population: str
    intervention: str
    comparison: str
    outcome: str

class ProtocolRegistration(BaseModel):
    """PROSPERO protocol registration info (PRISMA 2020 requirement)."""
    registered: bool = False
    registry: str = "PROSPERO"        # PROSPERO | OSF | Other
    registration_number: str = ""
    url: str = ""

class FundingInfo(BaseModel):
    source: str = "No funding received"
    grant_number: str = ""
    funder: str = ""

class ReviewConfig(BaseModel):
    """Validated from config/review.yaml -- changes every review."""
    project_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    research_question: str
    review_type: ReviewType
    pico: PICOConfig
    keywords: List[str] = Field(min_length=1)
    domain: str
    scope: str
    inclusion_criteria: List[str] = Field(min_length=1)
    exclusion_criteria: List[str] = Field(min_length=1)
    date_range_start: int
    date_range_end: int
    target_databases: List[str] = Field(min_length=1)
    target_sections: List[str] = [
        "abstract", "introduction", "methods", "results", "discussion", "conclusion"
    ]
    protocol: ProtocolRegistration = Field(default_factory=ProtocolRegistration)
    funding: FundingInfo = Field(default_factory=FundingInfo)
    conflicts_of_interest: str = "The authors declare no conflicts of interest."
    search_overrides: Optional[Dict[str, str]] = None  # Per-database query overrides; omit key to use auto-generated query

# ============================================================
# SETTINGS CONFIGURATION (from config/settings.yaml)
# ============================================================

class AgentConfig(BaseModel):
    """Per-agent LLM configuration."""
    model: str                          # e.g. "google-gla:gemini-2.5-flash-lite"
    temperature: float = Field(ge=0.0, le=1.0, default=0.2)

class ScreeningConfig(BaseModel):
    stage1_include_threshold: float = Field(ge=0.0, le=1.0, default=0.85)
    stage1_exclude_threshold: float = Field(ge=0.0, le=1.0, default=0.80)
    screening_concurrency: int = Field(ge=1, le=20, default=5)          # asyncio.Semaphore limit
    skip_fulltext_if_no_pdf: bool = True                                 # skip stage 2 when PDF unavailable
    keyword_filter_min_matches: int = Field(ge=0, default=1)            # 0 = disable pre-filter
    max_llm_screen: Optional[int] = Field(default=None, ge=1)           # hard cap on LLM dual-review calls; None = no cap

class DualReviewConfig(BaseModel):
    enabled: bool = True
    kappa_warning_threshold: float = Field(ge=0.0, le=1.0, default=0.4)

class GatesConfig(BaseModel):
    profile: str = "strict"                          # "strict" or "warning"
    search_volume_minimum: int = 50
    screening_minimum: int = 5
    extraction_completeness_threshold: float = 0.80
    extraction_max_empty_rate: float = 0.35
    cost_budget_max: float = 20.0

class WritingConfig(BaseModel):
    style_extraction: bool = True
    humanization: bool = True
    humanization_iterations: int = Field(ge=1, le=5, default=2)
    naturalness_threshold: float = Field(ge=0.0, le=1.0, default=0.75)
    checkpoint_per_section: bool = True
    llm_timeout: int = 120                           # seconds

class RiskOfBiasConfig(BaseModel):
    rct_tool: str = "rob2"
    non_randomized_tool: str = "robins_i"
    qualitative_tool: str = "casp"

class MetaAnalysisConfig(BaseModel):
    enabled: bool = True
    heterogeneity_threshold: int = 40                # I-squared percentage
    funnel_plot_minimum_studies: int = 10
    effect_measure_dichotomous: str = "risk_ratio"
    effect_measure_continuous: str = "mean_difference"

class IEEEExportConfig(BaseModel):
    enabled: bool = True
    template: str = "IEEEtran"
    bibliography_style: str = "IEEEtran"
    max_abstract_words: int = 250
    target_page_range: List[int] = [7, 10]

class CitationLineageConfig(BaseModel):
    block_export_on_unresolved: bool = True
    minimum_evidence_score: float = 0.5

class LLMRateLimitConfig(BaseModel):
    """Free-tier RPM caps from settings.yaml. Enforced by src/llm/rate_limiter.py."""
    flash_rpm: int = Field(ge=1, le=1000, default=10)
    flash_lite_rpm: int = Field(ge=1, le=1000, default=15)
    pro_rpm: int = Field(ge=1, le=500, default=5)

class SearchConfig(BaseModel):
    """Search depth configuration.

    max_results_per_db is the global default per connector.
    per_database_limits overrides it for specific connectors, allowing
    high-yield databases (crossref, pubmed) to pull more records than
    lower-yield ones (arxiv, ieee_xplore).
    """
    max_results_per_db: int = Field(ge=1, le=10000, default=500)
    per_database_limits: Dict[str, int] = Field(
        default_factory=dict,
        description="Per-connector overrides. Keys: openalex, pubmed, arxiv, ieee_xplore, semantic_scholar, crossref, perplexity_search.",
    )

class SettingsConfig(BaseModel):
    """Validated from config/settings.yaml -- changes rarely."""
    agents: Dict[str, AgentConfig]
    screening: ScreeningConfig = Field(default_factory=ScreeningConfig)
    dual_review: DualReviewConfig = Field(default_factory=DualReviewConfig)
    gates: GatesConfig = Field(default_factory=GatesConfig)
    writing: WritingConfig = Field(default_factory=WritingConfig)
    risk_of_bias: RiskOfBiasConfig = Field(default_factory=RiskOfBiasConfig)
    meta_analysis: MetaAnalysisConfig = Field(default_factory=MetaAnalysisConfig)
    ieee_export: IEEEExportConfig = Field(default_factory=IEEEExportConfig)
    citation_lineage: CitationLineageConfig = Field(default_factory=CitationLineageConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    llm: LLMRateLimitConfig | None = None

# ============================================================
# PHASE IO MODELS
# ============================================================

class CandidatePaper(BaseModel):
    """A candidate paper retrieved from a literature database.

    display_label is the canonical short identifier (e.g. "Smith2023") computed
    once on first save to the DB via compute_display_label() and stored in the
    papers.display_label column. All downstream code (RoB figure, citekey generation)
    reads this field instead of re-deriving it with local heuristics.
    """
    paper_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    title: str
    authors: List[str]
    year: Optional[int] = None
    source_database: str
    doi: Optional[str] = None
    abstract: Optional[str] = None
    url: Optional[str] = None
    keywords: Optional[List[str]] = None
    source_category: SourceCategory = SourceCategory.DATABASE
    openalex_id: Optional[str] = None
    country: Optional[str] = None  # First/corresponding author country for geographic viz
    display_label: Optional[str] = None  # computed on save; used by visualization and citekey generation

# Label derivation constants (single source of truth in src/models/papers.py).
# All consumers MUST call compute_display_label() rather than reimplementing this logic.
_LABEL_GENERIC_AUTHORS: frozenset[str]   # "unknown", "none", "author", "anonymous", etc.
_LABEL_GENERIC_TITLE_WORDS: frozenset[str]  # stop words + generic academic terms

def compute_display_label(paper: CandidatePaper) -> str:
    """Derive canonical short identifier stored in papers.display_label.

    Priority chain:
      1. Author surname (>= 2 chars, not generic) + year  -> e.g. "Smith2023"
      2. First meaningful title word + year               -> e.g. "Chatbot2023"
      3. First 22 chars of title (truncated)              -> e.g. "Conversational AI in.."
      4. Fallback                                         -> "Paper_<paper_id[:6]>"
    """

class SearchResult(BaseModel):
    workflow_id: str
    database_name: str
    source_category: SourceCategory
    search_date: str  # ISO 8601
    search_query: str  # Full Boolean string
    limits_applied: Optional[str] = None
    records_retrieved: int
    papers: List[CandidatePaper]

class ScreeningDecision(BaseModel):
    paper_id: str
    decision: ScreeningDecisionType
    reason: Optional[str] = None
    exclusion_reason: Optional[ExclusionReason] = None
    reviewer_type: ReviewerType
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class DualScreeningResult(BaseModel):
    paper_id: str
    reviewer_a: ScreeningDecision
    reviewer_b: ScreeningDecision
    agreement: bool
    final_decision: ScreeningDecisionType
    adjudication: Optional[ScreeningDecision] = None

class ExtractionRecord(BaseModel):
    paper_id: str
    study_design: StudyDesign
    study_duration: Optional[str] = None
    setting: Optional[str] = None
    participant_count: Optional[int] = None
    participant_demographics: Optional[str] = None
    intervention_description: str
    comparator_description: Optional[str] = None
    outcomes: List[Dict[str, str]]
    results_summary: Dict[str, str]
    funding_source: Optional[str] = None
    conflicts_of_interest: Optional[str] = None
    source_spans: Dict[str, str] = {}

class ClaimRecord(BaseModel):
    claim_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    paper_id: Optional[str] = None
    claim_text: str
    section: str
    confidence: float = Field(ge=0.0, le=1.0)

class EvidenceLinkRecord(BaseModel):
    claim_id: str
    citation_id: str
    evidence_span: str
    evidence_score: float = Field(ge=0.0, le=1.0)

class CitationEntryRecord(BaseModel):
    citation_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    citekey: str
    doi: Optional[str] = None
    title: str
    authors: List[str]
    year: Optional[int] = None
    journal: Optional[str] = None
    bibtex: Optional[str] = None
    resolved: bool = False

class RoB2Assessment(BaseModel):
    paper_id: str
    domain_1_randomization: RiskOfBiasJudgment
    domain_1_rationale: str
    domain_2_deviations: RiskOfBiasJudgment
    domain_2_rationale: str
    domain_3_missing_data: RiskOfBiasJudgment
    domain_3_rationale: str
    domain_4_measurement: RiskOfBiasJudgment
    domain_4_rationale: str
    domain_5_selection: RiskOfBiasJudgment
    domain_5_rationale: str
    overall_judgment: RiskOfBiasJudgment
    overall_rationale: str

class RobinsIAssessment(BaseModel):
    """ROBINS-I uses a different judgment scale than RoB 2: Low/Moderate/Serious/Critical/No Information"""
    paper_id: str
    domain_1_confounding: RobinsIJudgment
    domain_1_rationale: str
    domain_2_selection: RobinsIJudgment
    domain_2_rationale: str
    domain_3_classification: RobinsIJudgment
    domain_3_rationale: str
    domain_4_deviations: RobinsIJudgment
    domain_4_rationale: str
    domain_5_missing_data: RobinsIJudgment
    domain_5_rationale: str
    domain_6_measurement: RobinsIJudgment
    domain_6_rationale: str
    domain_7_reported_result: RobinsIJudgment
    domain_7_rationale: str
    overall_judgment: RobinsIJudgment
    overall_rationale: str

class GRADEOutcomeAssessment(BaseModel):
    outcome_name: str
    number_of_studies: int
    study_designs: str
    starting_certainty: GRADECertainty
    risk_of_bias_downgrade: int = Field(ge=0, le=2)
    inconsistency_downgrade: int = Field(ge=0, le=2)
    indirectness_downgrade: int = Field(ge=0, le=2)
    imprecision_downgrade: int = Field(ge=0, le=2)
    publication_bias_downgrade: int = Field(ge=0, le=2)
    large_effect_upgrade: int = Field(ge=0, le=2)
    dose_response_upgrade: int = Field(ge=0, le=1)
    residual_confounding_upgrade: int = Field(ge=0, le=1)
    final_certainty: GRADECertainty
    justification: str

class SectionDraft(BaseModel):
    workflow_id: str
    section: str
    version: int
    content: str
    claims_used: List[str] = []
    citations_used: List[str] = []
    word_count: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class GateResult(BaseModel):
    workflow_id: str
    gate_name: str
    phase: str
    status: GateStatus
    details: str
    threshold: Optional[str] = None
    actual_value: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class DecisionLogEntry(BaseModel):
    decision_type: str
    paper_id: Optional[str] = None
    decision: str
    rationale: str
    actor: str
    phase: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# ============================================================
# ADDITIONAL MODELS (inter-rater, meta-analysis, PRISMA, protocol, SoF)
# ============================================================

class InterRaterReliability(BaseModel):
    """Tracks Cohen's kappa per screening stage."""
    stage: str  # "title_abstract" or "fulltext"
    total_screened: int
    total_agreements: int
    total_disagreements: int
    cohens_kappa: float
    percent_agreement: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class MetaAnalysisResult(BaseModel):
    """Stores pooled estimates from statsmodels combine_effects()."""
    outcome_name: str
    n_studies: int
    effect_measure: str  # "risk_ratio", "odds_ratio", "mean_difference", "smd"
    pooled_effect: float
    ci_lower: float
    ci_upper: float
    p_value: float
    model: str  # "fixed" or "random"
    method_re: Optional[str] = None  # "chi2" (DL) or "iterated" (PM)
    cochrans_q: float
    i_squared: float
    tau_squared: Optional[float] = None
    forest_plot_path: Optional[str] = None
    funnel_plot_path: Optional[str] = None

class PRISMACounts(BaseModel):
    """Tracks counts at each PRISMA 2020 flow diagram stage."""
    databases_records: Dict[str, int]  # {"openalex": 150, "pubmed": 80, ...}
    other_sources_records: Dict[str, int]  # {"citation_search": 5, ...}
    total_identified_databases: int
    total_identified_other: int
    duplicates_removed: int
    records_screened: int
    records_excluded_screening: int
    reports_sought: int
    reports_not_retrieved: int
    reports_assessed: int
    reports_excluded_with_reasons: Dict[str, int]  # {ExclusionReason: count}
    studies_included_qualitative: int
    studies_included_quantitative: int
    arithmetic_valid: bool  # True if records_in == records_out at every stage

class ProtocolDocument(BaseModel):
    """PROSPERO-format protocol output from Phase 2."""
    workflow_id: str
    research_question: str
    pico: PICOConfig
    eligibility_criteria: List[str]
    planned_databases: List[str]
    planned_screening_method: str  # e.g. "Dual AI reviewer with adjudication"
    planned_rob_tools: List[str]  # e.g. ["rob2", "robins_i", "casp"]
    planned_synthesis_method: str
    prospero_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SummaryOfFindingsRow(BaseModel):
    """One row of the GRADE Summary of Findings table."""
    outcome: str
    participants_studies: str  # e.g. "450 (6 RCTs)"
    certainty: GRADECertainty
    relative_effect: Optional[str] = None  # e.g. "RR 0.75 (0.60-0.94)"
    absolute_effect_control: Optional[str] = None  # e.g. "200 per 1000"
    absolute_effect_intervention: Optional[str] = None  # e.g. "150 per 1000 (120-188)"
    plain_language: str  # e.g. "Probably reduces mortality"

class CostRecord(BaseModel):
    """Tracks LLM call costs for budget gate."""
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    phase: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

## 2B: Phase-Internal Models

These models are used within specific phase modules but cross internal function boundaries. They are defined in the module where they originate (not in `src/models/`) because they are internal to that phase's implementation. An AI agent should define them exactly as specified here.

### Synthesis Phase (src/synthesis/)

```python
# src/synthesis/feasibility.py
class SynthesisFeasibility(BaseModel):
    """Meta-analysis feasibility verdict from assess_meta_analysis_feasibility()."""
    feasible: bool
    rationale: str
    groupings: list[str]  # outcome group names; e.g. ["learning_outcomes", "engagement"]
                          # generic-only groupings ("primary_outcome", "secondary_outcome")
                          # are treated as NOT feasible in context_builder.py

# src/synthesis/narrative.py
class NarrativeSynthesis(BaseModel):
    """Structured narrative synthesis produced by build_narrative_synthesis()."""
    outcome_name: str
    n_studies: int
    effect_direction_summary: str  # e.g. "mostly positive", "mixed", "negative"
    key_themes: list[str]          # e.g. ["improved retention", "engagement gains"]
    synthesis_table: list[dict[str, str]]  # per-study rows: {title, design, direction, ...}
    narrative_text: str            # paragraph-form prose summary
```

Both are persisted to the `synthesis_results` table via `repository.save_synthesis_result(workflow_id, feasibility, narrative)` and loaded by `repository.load_synthesis_result(workflow_id)` which returns `tuple[SynthesisFeasibility, NarrativeSynthesis] | None`.

### Writing Phase (src/writing/)

```python
# src/writing/style_extractor.py
from dataclasses import dataclass

@dataclass
class StylePatterns:
    """Writing style patterns extracted from included papers for prompt injection."""
    sentence_openings: list[str]    # e.g. ["Studies have shown...", "Evidence suggests..."]
    vocabulary: list[str]           # domain-specific terms from included papers
    citation_patterns: list[str]    # how citations are integrated inline
    transitions: list[str]          # paragraph transition phrases

# src/writing/context_builder.py
class StudySummary(BaseModel):
    """Compact per-study block for the writing prompt (Results section)."""
    paper_id: str
    title: str
    year: Optional[int]
    study_design: str           # normalized label (spaces not underscores)
    participant_count: Optional[int]
    key_finding: str            # from results_summary["summary"] or intervention_description[:200]

class WritingGroundingData(BaseModel):
    """Factual data block injected into every LLM writing prompt.

    Built by build_writing_grounding() from PRISMA counts, extraction records,
    synthesis results, and the citation catalog. The LLM is instructed to use
    these numbers verbatim and is forbidden from inventing any statistic or count.
    """
    # Search metadata
    databases_searched: list[str]     # databases with non-zero search counts
    search_date: str                  # str(datetime.now().year) -- set dynamically

    # PRISMA counts (from PRISMACounts)
    total_identified: int             # databases + other sources total
    duplicates_removed: int
    total_screened: int               # records after dedup
    fulltext_assessed: int            # reports_assessed
    total_included: int               # qualitative + quantitative
    fulltext_excluded: int            # fulltext_assessed - total_included
    excluded_fulltext_reasons: dict[str, int]  # {ExclusionReason.value: count}

    # Study characteristics
    study_design_counts: dict[str, int]   # normalized label -> count
    total_participants: Optional[int]      # None if not consistently reported
    year_range: Optional[str]             # e.g. "2015-2026"

    # Synthesis
    meta_analysis_feasible: bool
    synthesis_direction: str               # e.g. "mostly positive"
    n_studies_synthesized: int
    narrative_text: str
    key_themes: list[str]

    # Per-study summaries for Results section
    study_summaries: list[StudySummary]

    # Citation keys the LLM is allowed to use (parsed from citation_catalog)
    valid_citekeys: list[str]
```

**Important:** `_GENERIC_GROUPINGS = frozenset({"primary_outcome", "secondary_outcome"})` -- if all groupings in `SynthesisFeasibility.groupings` are in this set, `WritingGroundingData.meta_analysis_feasible` is set to `False` regardless of `SynthesisFeasibility.feasible`. This prevents "feasible" from propagating when no real outcome groupings were identified.

### LLM Provider (src/llm/)

```python
# src/llm/provider.py
from dataclasses import dataclass

@dataclass
class AgentRuntimeConfig:
    """Resolved per-call LLM configuration returned by LLMProvider.get_agent_config()."""
    model: str          # e.g. "google-gla:gemini-2.5-flash-lite"
    temperature: float
    tier: str           # "flash-lite" | "flash" | "pro" -- used for rate limiting + cost estimation

class LLMProvider:
    """Provides model config, rate limiting, and cost logging for all LLM calls.

    Instantiated once per workflow run from SettingsConfig.
    """
    def get_agent_config(self, agent_name: str) -> AgentRuntimeConfig: ...
    async def reserve_call_slot(self, agent_name: str) -> AgentRuntimeConfig: ...
    def log_cost(self, config: AgentRuntimeConfig, tokens_in: int, tokens_out: int,
                 latency_ms: int, phase: str, repository: WorkflowRepository) -> None: ...
    def estimate_cost_usd(self, tier: str, tokens_in: int, tokens_out: int) -> float: ...
```

Cost per 1M tokens (input/output): flash-lite $0.10/$0.40, flash $0.30/$2.50, pro $1.25/$10.00.

***

# PART 3: SQLite SCHEMA

Create this schema in `src/db/schema.sql`. The application layer uses Pydantic models; SQLite provides durable storage and querying.

```sql
-- Core paper storage
CREATE TABLE IF NOT EXISTS papers (
    paper_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    authors TEXT NOT NULL,  -- JSON array
    year INTEGER,
    source_database TEXT NOT NULL,
    doi TEXT,
    abstract TEXT,
    url TEXT,
    keywords TEXT,  -- JSON array
    source_category TEXT NOT NULL DEFAULT 'database',
    openalex_id TEXT,
    country TEXT,  -- First/corresponding author country for geographic viz
    display_label TEXT,     -- canonical short label (e.g. "Smith2023") computed by compute_display_label() on first save
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Search results per database
CREATE TABLE IF NOT EXISTS search_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    database_name TEXT NOT NULL,
    source_category TEXT NOT NULL,
    search_date TEXT NOT NULL,
    search_query TEXT NOT NULL,
    limits_applied TEXT,
    records_retrieved INTEGER NOT NULL,
    workflow_id TEXT NOT NULL
);

-- Screening decisions (every individual decision, both reviewers)
-- Paper-level persistence: each decision is durable the instant it is written.
-- Resume pattern: query for completed paper_ids before processing, skip already-done.
CREATE TABLE IF NOT EXISTS screening_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    paper_id TEXT NOT NULL REFERENCES papers(paper_id),
    stage TEXT NOT NULL,  -- 'title_abstract' or 'fulltext'
    decision TEXT NOT NULL,
    reason TEXT,
    exclusion_reason TEXT,
    reviewer_type TEXT NOT NULL,
    confidence REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Aggregated dual-reviewer results
CREATE TABLE IF NOT EXISTS dual_screening_results (
    workflow_id TEXT NOT NULL,
    paper_id TEXT NOT NULL REFERENCES papers(paper_id),
    stage TEXT NOT NULL,
    agreement INTEGER NOT NULL,  -- 0 or 1
    final_decision TEXT NOT NULL,
    adjudication_needed INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workflow_id, paper_id, stage)
);

-- Data extraction (paper-level persistence: written immediately after each paper)
CREATE TABLE IF NOT EXISTS extraction_records (
    workflow_id TEXT NOT NULL,
    paper_id TEXT NOT NULL REFERENCES papers(paper_id),
    study_design TEXT NOT NULL,
    data TEXT NOT NULL,  -- JSON of ExtractionRecord
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workflow_id, paper_id)
);

-- Claims (atomic factual statements)
CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY,
    paper_id TEXT,
    claim_text TEXT NOT NULL,
    section TEXT NOT NULL,
    confidence REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Citation entries (bibliographic references)
-- NOTE: Must be created BEFORE evidence_links (FK dependency)
CREATE TABLE IF NOT EXISTS citations (
    citation_id TEXT PRIMARY KEY,
    citekey TEXT UNIQUE NOT NULL,
    doi TEXT,
    title TEXT NOT NULL,
    authors TEXT NOT NULL,  -- JSON array
    year INTEGER,
    journal TEXT,
    bibtex TEXT,
    resolved INTEGER NOT NULL DEFAULT 0
);

-- Evidence links (claim -> citation mapping)
CREATE TABLE IF NOT EXISTS evidence_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    citation_id TEXT NOT NULL REFERENCES citations(citation_id),
    evidence_span TEXT NOT NULL,
    evidence_score REAL NOT NULL
);

-- Risk of bias assessments (paper-level persistence)
CREATE TABLE IF NOT EXISTS rob_assessments (
    workflow_id TEXT NOT NULL,
    paper_id TEXT NOT NULL REFERENCES papers(paper_id),
    tool_used TEXT NOT NULL,  -- 'rob2', 'robins_i', 'casp', 'nos'
    assessment_data TEXT NOT NULL,  -- JSON of assessment model
    overall_judgment TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workflow_id, paper_id)
);

-- GRADE outcome assessments
CREATE TABLE IF NOT EXISTS grade_assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    outcome_name TEXT NOT NULL,
    assessment_data TEXT NOT NULL,  -- JSON of GRADEOutcomeAssessment
    final_certainty TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Section drafts (versioned)
CREATE TABLE IF NOT EXISTS section_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    section TEXT NOT NULL,
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    claims_used TEXT,  -- JSON array of claim_ids
    citations_used TEXT,  -- JSON array of citation_ids
    word_count INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(workflow_id, section, version)
);

-- Quality gate results
CREATE TABLE IF NOT EXISTS gate_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    gate_name TEXT NOT NULL,
    phase TEXT NOT NULL,
    status TEXT NOT NULL,
    details TEXT NOT NULL,
    threshold TEXT,
    actual_value TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Decision audit log (append-only)
CREATE TABLE IF NOT EXISTS decision_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_type TEXT NOT NULL,
    paper_id TEXT,
    decision TEXT NOT NULL,
    rationale TEXT NOT NULL,
    actor TEXT NOT NULL,
    phase TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- LLM cost tracking (for budget gate)
CREATE TABLE IF NOT EXISTS cost_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model TEXT NOT NULL,
    tokens_in INTEGER NOT NULL,
    tokens_out INTEGER NOT NULL,
    cost_usd REAL NOT NULL,
    latency_ms INTEGER NOT NULL,
    phase TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Workflow registry (for topic-based auto-resume)
CREATE TABLE IF NOT EXISTS workflows (
    workflow_id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,               -- research_question from review.yaml
    config_hash TEXT NOT NULL,         -- SHA256 of review.yaml for change detection
    status TEXT NOT NULL DEFAULT 'running',  -- running | completed | failed
    dedup_count INTEGER,               -- stored by SearchNode; read by resume.py to avoid recompute
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Typed synthesis results (feasibility + narrative) persisted after SynthesisNode.
-- WritingNode loads these first; falls back to data_narrative_synthesis.json for old runs.
CREATE TABLE IF NOT EXISTS synthesis_results (
    workflow_id TEXT NOT NULL,
    outcome_name TEXT NOT NULL,
    feasibility_data TEXT NOT NULL,   -- JSON of SynthesisFeasibility model
    narrative_data TEXT NOT NULL,     -- JSON of NarrativeSynthesis model
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workflow_id, outcome_name)
);

-- Phase completion markers (lightweight -- actual data lives in per-paper tables)
-- The old approach serialized entire ReviewState into state_json. The new approach
-- writes each decision/extraction/assessment to its own table as it happens, so
-- checkpoints only need to record "phase X is done" for orchestration ordering.
CREATE TABLE IF NOT EXISTS checkpoints (
    workflow_id TEXT NOT NULL REFERENCES workflows(workflow_id),
    phase TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'completed',  -- completed | partial
    papers_processed INTEGER,          -- how many papers were processed in this phase
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workflow_id, phase)
);
-- status: 'completed' = phase finished normally; 'partial' = user proceeded with partial results (e.g. Ctrl+C during screening)

-- Indexes
CREATE UNIQUE INDEX IF NOT EXISTS idx_papers_doi_unique ON papers(doi) WHERE doi IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi);
CREATE INDEX IF NOT EXISTS idx_screening_paper ON screening_decisions(workflow_id, paper_id, stage);
CREATE INDEX IF NOT EXISTS idx_claims_section ON claims(section);
CREATE INDEX IF NOT EXISTS idx_evidence_claim ON evidence_links(claim_id);
CREATE INDEX IF NOT EXISTS idx_evidence_citation ON evidence_links(citation_id);
CREATE INDEX IF NOT EXISTS idx_decision_log_phase ON decision_log(phase);
CREATE INDEX IF NOT EXISTS idx_gate_results_phase ON gate_results(phase);
```

**Central workflow registry** (separate from per-run schema):

Each run creates a new `runtime.db` in `logs/{date}/{topic-slug}/run_HH-MM-SS/`. To find which db to open for resume without scanning the filesystem, a central registry is used:

- **File:** `{log_root}/workflows_registry.db`
- **Table:** `workflows_registry(workflow_id, topic, config_hash, db_path, status, created_at, updated_at)`
- **Purpose:** Maps (topic, config_hash) to absolute `db_path` so resume can open the correct runtime.db
- The per-run `workflows` table in runtime.db remains for workflow metadata; the registry is the cross-run index

## Part 3B: Checkpoint Phase Keys (CRITICAL for Resume)

The `checkpoints` table uses exact string phase keys. `workflow.py` and `resume.py` **must use identical strings** or resume will silently fail. These are the canonical phase key strings:

```python
# src/orchestration/resume.py
PHASE_ORDER = [
    "phase_2_search",
    "phase_3_screening",
    "phase_4_extraction_quality",
    "phase_5_synthesis",
    "phase_6_writing",
    "finalize",
]
```

Each phase node in `workflow.py` saves its checkpoint with the matching key:

| Phase Node | Checkpoint Key | When Saved |
|:---|:---|:---|
| `SearchNode` | `"phase_2_search"` | After dedup + protocol generation |
| `ScreeningNode` | `"phase_3_screening"` | After full-text screening; status='partial' if Ctrl+C |
| `ExtractionQualityNode` | `"phase_4_extraction_quality"` | After GRADE + RoB figure |
| `SynthesisNode` | `"phase_5_synthesis"` | After narrative synthesis + plots saved to DB |
| `WritingNode` | `"phase_6_writing"` | After all manuscript sections complete |
| `FinalizeNode` | (no checkpoint) | Writes `run_summary.json` and sets registry status = "completed" |

Note: Phase 1 (Foundation) does not create a checkpoint -- the existence of the workflow row in `workflows` table serves as the Phase 1 completion marker.

## Part 3C: run_summary.json Schema

`FinalizeNode` writes this JSON to `{log_dir}/run_summary.json`. The `status`, `validate`, and `export` CLI subcommands read this file to locate output artifact paths.

```json
{
  "run_id": "<12-char UUID prefix>",
  "workflow_id": "<12-char UUID prefix>",
  "log_dir": "/absolute/path/to/logs/2026-02-18/topic-slug/run_HH-MM-SS/",
  "output_dir": "/absolute/path/to/data/outputs/2026-02-18/topic-slug/run_HH-MM-SS/",
  "search_counts": {
    "openalex": 450,
    "pubmed": 120,
    "arxiv": 80,
    "semantic_scholar": 200
  },
  "dedup_count": 95,
  "connector_init_failures": {
    "ieee_xplore": "IEEE_API_KEY not set"
  },
  "included_papers": 14,
  "extraction_records": 14,
  "artifacts": {
    "prisma_flow": "/absolute/path/fig_prisma_flow.png",
    "rob_traffic_light": "/absolute/path/fig_rob_traffic_light.png",
    "timeline": "/absolute/path/fig_publication_timeline.png",
    "geographic": "/absolute/path/fig_geographic_distribution.png",
    "manuscript": "/absolute/path/doc_manuscript.md",
    "narrative_synthesis": "/absolute/path/data_narrative_synthesis.json",
    "run_summary": "/absolute/path/run_summary.json",
    "search_appendix": "/absolute/path/doc_search_strategies_appendix.md",
    "protocol": "/absolute/path/doc_protocol.md"
  }
}
```

The `artifacts` dictionary keys are fixed strings that `submission_packager.py` and `ieee_validator.py` use to locate files. An AI implementing these must use the same keys.

***

# PART 4: PROJECT FILE STRUCTURE

Build this exact directory tree. Every file listed below must be created. Project name in `pyproject.toml` is `research-article-writer`; the root directory may be named `systematic-review-tool` or `research-article-writer`.

```
systematic-review-tool/
|-- pyproject.toml
|-- README.md
|-- .env.example                      # API key template (copy to .env)
|-- config/
|   |-- review.yaml               # Per-review research config (changes every review)
|   `-- settings.yaml             # System behavior config (changes rarely)
|-- docs/
|   |-- research-agent-v2-spec.md # Master specification (this file)
|   `-- frontend-spec.md          # Web UI frontend architecture spec (stack, layout, SSE events, API contract)
|-- frontend/                         # React/Vite/TypeScript web UI (single-user local dashboard)
|   |-- index.html
|   |-- vite.config.ts
|   |-- tsconfig.json
|   |-- package.json
|   |-- pnpm-lock.yaml
|   `-- src/
|       |-- main.tsx
|       |-- App.tsx                   # Root layout: navigation, run state, view routing
|       |-- lib/
|       |   `-- api.ts                # Typed fetch wrappers for all 14 backend endpoints
|       |-- hooks/
|       |   |-- useSSEStream.ts       # SSE client (@microsoft/fetch-event-source); events -> ReviewEvent[]
|       |   |-- useCostStats.ts       # Aggregates api_call events into cost breakdown by model/phase
|       |   `-- useBackendHealth.ts   # Polls /api/health every 6s; detects backend offline
|       |-- components/
|       |   |-- Sidebar.tsx           # Fixed left nav with tab items, run status pill, cost footer
|       |   |-- RunForm.tsx           # Review YAML + API key inputs; fires handleStart
|       |   |-- PhaseProgress.tsx     # Phase cards with progress bars (search->finalize)
|       |   |-- LogStream.tsx         # Scrollable event log; maps ReviewEvent -> log line
|       |   |-- ResultsPanel.tsx      # Download links for output artifacts
|       |   `-- ui/
|       |       `-- tooltip.tsx       # shadcn/ui tooltip (collapsed sidebar tooltips)
|       `-- views/
|           |-- SetupView.tsx         # New review form (wraps RunForm)
|           |-- OverviewView.tsx      # Live run dashboard: stats cards + phase timeline
|           |-- CostView.tsx          # Cost breakdown: Recharts bar chart + model/phase tables
|           |-- LogView.tsx           # Filterable event log (All / Phases / LLM / Search / Screening)
|           |-- ResultsView.tsx       # Output artifacts list (shown when run is done)
|           |-- DatabaseView.tsx      # DB explorer: paginated papers/screening/costs tabs (available post-run)
|           `-- HistoryView.tsx       # Past runs table; Open button attaches DB explorer to historical run
|-- src/
|   |-- __init__.py
|   |-- main.py                       # CLI entry point
|   |-- config/
|   |   |-- __init__.py
|   |   `-- loader.py                 # YAML loader for review.yaml + settings.yaml
|   |-- models/
|   |   |-- __init__.py
|   |   |-- enums.py                  # All enums from Part 2
|   |   |-- config.py                 # PICOConfig, ReviewConfig, SettingsConfig, SearchConfig, LLMRateLimitConfig
|   |   |-- papers.py                 # CandidatePaper, SearchResult, compute_display_label()
|   |   |-- screening.py              # ScreeningDecision, DualScreeningResult
|   |   |-- extraction.py             # ExtractionRecord
|   |   |-- claims.py                 # ClaimRecord, EvidenceLinkRecord, CitationEntryRecord
|   |   |-- quality.py                # RoB2Assessment, RobinsIAssessment, GRADEOutcomeAssessment
|   |   |-- writing.py                # SectionDraft
|   |   |-- additional.py             # InterRaterReliability, MetaAnalysisResult, PRISMACounts, ProtocolDocument
|   |   `-- workflow.py               # GateResult, DecisionLogEntry
|   |-- db/
|   |   |-- __init__.py
|   |   |-- schema.sql                # Full schema from Part 3
|   |   |-- database.py               # SQLite connection manager + migration runner
|   |   |-- repositories.py           # CRUD operations for each table (typed)
|   |   `-- workflow_registry.py      # Central registry (register, find_by_topic, find_by_workflow_id, update_status)
|   |-- orchestration/
|   |   |-- __init__.py
|   |   |-- workflow.py               # PydanticAI Graph + ReviewState + all phase nodes
|   |   |-- context.py                # RunContext (console, verbose/debug/offline, progress; proceed_with_partial_requested + should_proceed_with_partial for Ctrl+C early-exit during screening)
|   |   |-- resume.py                # load_resume_state, next_phase logic
|   |   |-- state.py                 # ReviewState dataclass
|   |   `-- gates.py                  # Quality gate runner + 6 gate implementations
|   |-- search/
|   |   |-- __init__.py
|   |   |-- base.py                   # Abstract SearchConnector protocol
|   |   |-- openalex.py               # OpenAlex via direct REST (api_key in URL)
|   |   |-- pubmed.py                 # PubMed via Entrez
|   |   |-- arxiv.py                  # arXiv API
|   |   |-- ieee_xplore.py            # IEEE Xplore API
|   |   |-- semantic_scholar.py        # Semantic Scholar Academic Graph API
|   |   |-- crossref.py               # Crossref Works API
|   |   |-- perplexity_search.py       # Auxiliary other-source discovery
|   |   |-- strategy.py               # Boolean query builder + search coordinator
|   |   |-- deduplication.py          # Fuzzy dedup (DOI match + title similarity)
|   |   `-- pdf_retrieval.py          # PDF retrieval (Unpaywall, open access URLs)
|   |-- screening/
|   |   |-- __init__.py
|   |   |-- dual_screener.py          # Dual-reviewer screening (both stages); confidence fast-path; concurrent via Semaphore
|   |   |-- keyword_filter.py         # Pre-LLM keyword pre-filter; auto-excludes zero-match papers (KEYWORD_FILTER reason)
|   |   |-- prompts.py                # Reviewer A + B + Adjudicator prompt templates
|   |   |-- reliability.py            # Cohen's kappa computation
|   |   `-- gemini_client.py          # Gemini API client (ScreeningLLMClient impl)
|   |-- extraction/
|   |   |-- __init__.py
|   |   |-- extractor.py              # LLM-powered structured extraction
|   |   `-- study_classifier.py       # Study design classifier
|   |-- quality/
|   |   |-- __init__.py
|   |   |-- rob2.py                   # RoB 2 assessor (5 domains)
|   |   |-- robins_i.py               # ROBINS-I assessor (7 domains)
|   |   |-- casp.py                   # CASP assessor (carry from old repo)
|   |   |-- grade.py                  # GRADE certainty assessor
|   |   `-- study_router.py           # Routes studies to correct RoB tool
|   |-- synthesis/
|   |   |-- __init__.py
|   |   |-- feasibility.py            # Meta-analysis feasibility checker
|   |   |-- meta_analysis.py          # statsmodels combine_effects wrapper
|   |   |-- effect_size.py            # Effect size calculators (scipy)
|   |   `-- narrative.py              # Narrative synthesis fallback
|   |-- writing/
|   |   |-- __init__.py
|   |   |-- section_writer.py         # Generic section writing agent
|   |   |-- context_builder.py        # Builds WritingGroundingData (PRISMA counts, extraction records, synthesis) fed to prompts
|   |   |-- orchestration.py          # Style extraction, citation ledger, section writer wiring; citekey generation
|   |   |-- prompts/                  # Section-specific prompt templates (consolidated)
|   |   |   |-- __init__.py
|   |   |   |-- base.py               # Shared patterns: prohibited phrases, citation catalog constraint
|   |   |   `-- sections.py           # Per-section prompts: abstract, introduction, methods, results, discussion, conclusion
|   |   |-- humanizer.py              # Academic writing style refinement
|   |   |-- style_extractor.py        # Extract writing patterns from included papers
|   |   `-- naturalness_scorer.py     # Score AI-generated text naturalness (0-1)
|   |-- citation/
|   |   |-- __init__.py
|   |   `-- ledger.py                 # Citation ledger (claim -> evidence -> citation)
|   |-- protocol/
|   |   |-- __init__.py
|   |   `-- generator.py              # PROSPERO-format protocol generator
|   |-- prisma/                       # (Phase 7 - implemented)
|   |   |-- __init__.py
|   |   `-- diagram.py                # PRISMA 2020 flow diagram (prisma-flow-diagram + matplotlib fallback)
|   |-- visualization/
|   |   |-- __init__.py
|   |   |-- forest_plot.py            # Forest plot (statsmodels + matplotlib)
|   |   |-- funnel_plot.py            # Funnel plot (matplotlib)
|   |   |-- rob_figure.py             # Risk of bias traffic-light summary
|   |   |-- timeline.py               # Publication timeline
|   |   `-- geographic.py             # Geographic distribution
|   |-- export/
|   |   |-- __init__.py
|   |   |-- ieee_latex.py             # IEEE LaTeX exporter (IEEEtran.cls)
|   |   |-- bibtex_builder.py         # BibTeX generation + IEEE style (NOTE: NOT in citation/; lives here)
|   |   |-- submission_packager.py    # Full submission directory assembler
|   |   |-- prisma_checklist.py       # PRISMA 2020 27-item auto-validator
|   |   `-- ieee_validator.py         # IEEE compliance checks
|   |-- llm/
|   |   |-- __init__.py
|   |   |-- provider.py               # PydanticAI agent factory (Gemini config) + cost logging
|   |   |-- gemini_client.py          # Shared GeminiClient (generateContent, JSON schema mode, retry); used by extraction, quality, writing
|   |   `-- rate_limiter.py           # Token bucket rate limiter
|   |-- web/
|   |   |-- __init__.py
|   |   `-- app.py                    # FastAPI server: 16 endpoints (run, stream, cancel, history, attach, DB explorer, events, artifacts, export); SSE via asyncio.Queue + replay buffer; static frontend serving
|   `-- utils/
|       |-- __init__.py
|       |-- structured_log.py         # Structured logging (JSONL, decision log)
|       |-- logging_paths.py          # Per-run log directory resolution
|       |-- ssl_context.py            # SSL/certifi setup for HTTP clients
|       |-- text.py                   # Text cleaning (optional, not yet implemented)
|       `-- retry.py                  # Async retry (optional, not yet implemented)
|-- templates/
|   |-- IEEEtran.cls                  # IEEE LaTeX class file
|   |-- IEEEtran.bst                  # IEEE BibTeX style
|   `-- cover_letter.md               # Cover letter template
|-- tests/
|   |-- __init__.py
|   |-- unit/
|   |   |-- test_models.py
|   |   |-- test_database.py
|   |   |-- test_gates.py
|   |   |-- test_citation_ledger.py
|   |   |-- test_screening.py
|   |   |-- test_reliability.py
|   |   |-- test_rob2.py
|   |   |-- test_robins_i.py
|   |   |-- test_effect_size.py
|   |   |-- test_meta_analysis.py
|   |   |-- test_prisma_diagram.py
|   |   |-- test_protocol.py
|   |   |-- test_perplexity_source_inference.py
|   |   |-- test_export.py              # covers ieee_latex, ieee_validator, bibtex, prisma_checklist
|   |   |-- test_main_cli.py
|   |   |-- test_logging_paths.py
|   |   |-- test_rate_limiter.py
|   |   |-- test_study_classifier.py
|   |   |-- test_workflow_registry.py
|   |   `-- test_resume_state.py
|   |-- integration/
|   |   |-- test_dual_screening.py
|   |   |-- test_run_command.py
|   |   |-- test_phase1_smoke.py
|   |   |-- test_extraction_pipeline.py
|   |   |-- test_quality_pipeline.py
|   |   |-- test_synthesis_pipeline.py
|   |   `-- test_writing_pipeline.py   # NOTE: test_checkpoint_resume.py not yet implemented
|   `-- e2e/                           # NOTE: e2e directory and test_full_review.py not yet implemented
|       `-- test_full_review.py        # (placeholder -- requires full API keys to run)
`-- data/
    `-- outputs/                      # Runtime output directory (gitignored)
```

**Notes on the frontend build:**
- Dev mode: `cd frontend && pnpm run dev` starts Vite on port 5173 with `/api` proxied to FastAPI on port 8000.
- Production: `cd frontend && pnpm run build` emits `frontend/dist/`; FastAPI serves it as static files at `/`.
- The `frontend/dist/` directory is gitignored (generated artifact).

## Part 4A: Output Artifact Naming

All runtime artifacts use type-based prefixes for clarity:

- **fig_** (figures): `fig_prisma_flow.png`, `fig_publication_timeline.png`, `fig_geographic_distribution.png`, `fig_rob_traffic_light.png`, `fig_forest_plot.png`, `fig_funnel_plot.png`
- **doc_** (markdown): `doc_manuscript.md`, `doc_protocol.md`, `doc_search_strategies_appendix.md`, `doc_fulltext_retrieval_coverage.md`, `doc_disagreements_report.md`
- **data_** (JSON): `data_narrative_synthesis.json`; `run_summary.json` in log dir

***

# PART 4B: HOW TO BUILD FROM THIS DOCUMENT

This section tells an AI agent (or human developer) exactly how to use this specification.

## Step 0: Bootstrap the Project

```bash
# Create project directory and initialize
mkdir systematic-review-tool
cd systematic-review-tool
git init
uv init --name systematic-review-tool --python 3.11

# Create the full directory tree from Part 4
mkdir -p config
mkdir -p src/{models,db,orchestration,search,screening,extraction,quality,synthesis,writing/prompts,citation,protocol,prisma,visualization,export,llm,utils}
mkdir -p templates
mkdir -p tests/{unit,integration,e2e}
mkdir -p data/outputs

# Add __init__.py files
touch src/__init__.py
for dir in models db orchestration search screening extraction quality synthesis writing writing/prompts citation protocol prisma visualization export llm utils; do
  touch "src/$dir/__init__.py"
done
touch tests/__init__.py

# Create .env from the template (fill in your API keys)
cat > .env << 'EOF'
GEMINI_API_KEY=your-gemini-key
OPENALEX_API_KEY=your-openalex-key   # Required since Feb 2026; free at openalex.org
IEEE_API_KEY=your-ieee-key           # Optional; for IEEE Xplore connector
NCBI_EMAIL=your-email@example.com    # Required for PubMed Entrez
PERPLEXITY_API_KEY=your-perplexity-key  # Optional; for perplexity_search connector
SEMANTIC_SCHOLAR_API_KEY=your-s2-key    # Optional; improves rate limits for Semantic Scholar
EOF

# Get IEEEtran LaTeX files -- REQUIRED for pdflatex to compile the manuscript
# Option 1 (recommended): download from CTAN
curl -L "https://ctan.org/tex-archive/macros/latex/contrib/IEEEtran/IEEEtran.cls" -o templates/IEEEtran.cls
curl -L "https://ctan.org/tex-archive/macros/latex/contrib/IEEEtran/bibtex/IEEEtran.bst" -o templates/IEEEtran.bst
# Option 2: if TeX Live is installed, copy from system
# cp $(kpsewhich IEEEtran.cls) templates/IEEEtran.cls
# cp $(kpsewhich IEEEtran.bst) templates/IEEEtran.bst

# Create cover letter template
cat > templates/cover_letter.md << 'EOF'
# Cover Letter

Dear Editor,

We submit our systematic review manuscript for consideration in [Journal Name].

[Body of cover letter]

Sincerely,
[Author Name]
EOF

# Copy config templates (from Part 6)
# review.yaml and settings.yaml content is specified in Part 6 sections 6.1 and 6.2
```

## Step 1: Build Phase by Phase

**CRITICAL INSTRUCTION:** Build in the exact phase order (Phase 1 through Phase 8). For each phase:

1. Read the phase description in Part 5 below
2. Implement every numbered item in "What to Build"
3. Run the acceptance criteria commands listed at the end of the phase
4. **STOP and show the user the test results**
5. Wait for user approval before starting the next phase

**Do NOT skip phases. Do NOT proceed without approval.**

## Step 2: Reference Materials

While building, use these parts of the document as reference:

- **Part 1** (Methodology): When implementing screening, quality assessment, or synthesis -- verify your logic matches the methodology rules here
- **Part 2** (Data Contracts): All Pydantic models. Copy these into `src/models/` files as specified
- **Part 3** (SQLite Schema): Copy into `src/db/schema.sql` exactly as written
- **Part 4** (File Structure): Every file listed must exist by the end of Phase 8
- **Part 6** (Configuration): YAML templates for `config/review.yaml` and `config/settings.yaml`
- **Part 7** (Rules): Constraints that apply to ALL code you write (async I/O, no untyped dicts, etc.)
- **Part 8** (Test Strategy): Which test files belong to which phase
- **Part 9** (Definition of Done): The final checklist before first submission

***

# PART 5: BUILD PHASES

## BUILD PHASE 1: Foundation
**Estimated Effort: 2-3 days**
**Depends on: Nothing**

### What to Build

1. **`pyproject.toml`** with all dependencies:
   ```
   pydantic >= 2.0
   pydantic-ai >= 0.0.29
   statsmodels >= 0.14
   scipy >= 1.11
   matplotlib >= 3.8
   rich >= 13.0
   pyyaml >= 6.0
   aiohttp >= 3.9
   certifi >= 2024.0       # SSL certificates for aiohttp
   biopython >= 1.83       # for PubMed Entrez
   arxiv >= 2.0            # for arXiv API
   scikit-learn >= 1.3     # for Cohen's kappa
   thefuzz >= 0.22         # for fuzzy dedup
   aiosqlite >= 0.21       # async SQLite (Rule 7: async/await for all I/O)
   python-dotenv >= 1.0    # .env file loading
   structlog >= 24.0       # structured logging (JSONL decision log)
   prisma-flow-diagram >= 0.1.0  # PRISMA 2020 flow diagram (Phase 7); uses matplotlib fallback on ImportError
   colrev >= 0.16.0        # optional; used by some dedup utilities
   ```

2. **All Pydantic models** from Part 2 in `src/models/`

3. **SQLite database layer** (`src/db/`):
   - `database.py`: Connection manager using `aiosqlite` (async wrapper over sqlite3). `get_db()` async context manager. `run_migrations()` reads and executes `schema.sql`. On every new connection, initialize PRAGMAs:
     ```python
     async def _init_connection(db: aiosqlite.Connection):
         await db.execute("PRAGMA journal_mode = WAL")       # concurrent reads + single writer
         await db.execute("PRAGMA synchronous = NORMAL")     # ~2-3x faster writes
         await db.execute("PRAGMA foreign_keys = ON")        # SQLite does NOT enforce FKs by default!
         await db.execute("PRAGMA cache_size = 10000")       # ~40MB in-memory cache
         await db.execute("PRAGMA temp_store = MEMORY")      # temp tables in RAM
     ```
   - `repositories.py`: Typed CRUD for each table. Every method accepts and returns Pydantic models. **Paper-level persistence pattern:** All write operations commit individual decisions/extractions/assessments to SQLite immediately (not batched at phase end). All read operations support a "get already-processed IDs" query for resume:
     ```python
     # Pattern used across screening, extraction, quality assessment:
     async def get_processed_paper_ids(workflow_id: str, stage: str) -> set[str]:
         """Return paper_ids already processed for this workflow+stage."""
         rows = await db.execute_fetchall(
             "SELECT DISTINCT paper_id FROM screening_decisions "
             "WHERE workflow_id = ? AND stage = ?",
             (workflow_id, stage),
         )
         return {row[0] for row in rows}

     # In the processing loop:
     already_done = await repo.get_processed_paper_ids(workflow_id, stage)
     for paper in papers:
         if paper.paper_id in already_done:
             continue  # skip -- already persisted
         result = await process_paper(paper)
         await repo.save_screening_decision(result)  # durable immediately
     ```

4. **Quality gate framework** (`src/orchestration/gates.py`):
   - `GateRunner` class with `run_gate(gate_name, check_fn)` -> persists `GateResult` to DB
   - Six gates:

   | Gate | Passes When |
   |:---|:---|
   | `search_volume` | Total records >= 50 |
   | `screening_safeguard` | Papers passing screening >= 5 |
   | `extraction_completeness` | >= 80% of required fields filled |
   | `citation_lineage` | Zero unresolved citations |
   | `cost_budget` | Cumulative cost < `max_cost_usd` |
   | `resume_integrity` | All checkpoint data valid |

5. **Decision log** integrated into `repositories.py` -- append-only writes to `decision_log` table

6. **Citation ledger** (`src/citation/ledger.py`):
   - `register_claim()`, `register_citation()`, `link_evidence()`
   - `validate_manuscript(text) -> List[unresolved_claims], List[unresolved_citations]`
   - `block_export_if_invalid() -> bool`

7. **LLM provider** (`src/llm/provider.py`):
   - PydanticAI agent factory with 3-tier model selection: Flash-Lite (bulk screening), Flash (search, abstract), Pro (extraction, writing, adjudication). Model assignments read from `config/settings.yaml`.
   - Rate limiter (`src/llm/rate_limiter.py`) respecting Gemini free-tier limits (10 RPM flash, 15 RPM flash-lite, 5 RPM pro)
   - **Cost tracking:** Every LLM call logs a `CostRecord` (model, tokens in/out, cost, latency, phase). Cumulative cost stored in DB for `cost_budget` gate.

8. **Review config loader** -- reads `config/review.yaml` into `ReviewConfig` and `config/settings.yaml` into `SettingsConfig`. Both validated via Pydantic at startup; invalid config = fail fast with clear error. Loads `.env` via `python-dotenv` before any config access.

### Acceptance Criteria
- [ ] `uv run python -c "from src.models import *"` imports all models without error
- [ ] `uv run python -c "from src.db.database import get_db; db = get_db('test.db')"` creates SQLite with all tables
- [ ] All 6 gates runnable in both `strict` and `warning` modes
- [ ] Citation ledger correctly links claims -> evidence -> citations
- [ ] `uv run pytest tests/unit/test_models.py tests/unit/test_database.py tests/unit/test_gates.py tests/unit/test_citation_ledger.py -q` passes

***

## BUILD PHASE 2: Search Infrastructure
**Estimated Effort: 2-3 days**
**Depends on: Phase 1**

### What to Build

1. **`SearchConnector` protocol** (`src/search/base.py`):
   ```python
   from typing import Protocol

   class SearchConnector(Protocol):
       name: str
       source_category: SourceCategory

       async def search(self, query: str, max_results: int = 100,
                        date_start: int = None, date_end: int = None) -> SearchResult:
           ...
   ```

2. **OpenAlex connector** (`src/search/openalex.py`):
   - Uses direct aiohttp REST calls to `api.openalex.org/works` with `api_key` in URL (required since Feb 2026)[^19]
   - **Must set:** `OPENALEX_API_KEY` in `.env`
   - Maps OpenAlex `Work` objects to `CandidatePaper`
   - Converts `abstract_inverted_index` to plaintext in code
   - Filters by year range (`from_publication_date`, `to_publication_date`) and `type:article`

3. **PubMed connector** (`src/search/pubmed.py`):
   - Uses `Bio.Entrez` from Biopython
   - Searches MEDLINE with MeSH terms + text words

4. **arXiv connector** (`src/search/arxiv.py`):
   - Uses `arxiv` Python library
   - Category filtering (cs.HC, cs.AI, etc.)

5. **IEEE Xplore connector** (`src/search/ieee_xplore.py`):
   - Direct REST API with API key
   - Document search with metadata parsing

6. **Semantic Scholar connector** (`src/search/semantic_scholar.py`):
   - Uses Semantic Scholar Academic Graph API paper search
   - Maps `openAccessPdf`/external IDs into `CandidatePaper` metadata

7. **Crossref connector** (`src/search/crossref.py`):
   - Uses Crossref Works API for journal-article metadata expansion
   - Uses polite contact email and bounded result windows

8. **Perplexity auxiliary connector** (`src/search/perplexity_search.py`):
   - Uses Perplexity Search API as `SourceCategory.OTHER_SOURCE`
   - Auxiliary discovery only; not a primary evidence database
   - Perplexity items from `OTHER_SOURCE` may have URLs that map to academic databases (PubMed, arXiv, IEEE, etc.). Use `_infer_source_from_url()` to attribute correctly for PRISMA diagram when a Perplexity-discovered paper is verified against an academic record.

9. **Search coordinator** (`src/search/strategy.py`):
   - Takes `ReviewConfig` -> generates Boolean queries per database; if `search_overrides` is set for a database, uses that query instead of auto-generated
   - Runs all connectors concurrently (asyncio)
   - Collects per-database counts for PRISMA diagram
   - Generates `search_strategies_appendix.md` with full query strings, dates, limits

10. **Deduplication** (`src/search/deduplication.py`):
   - Stage 1: Exact DOI match
   - Stage 2: Fuzzy title match (thefuzz, threshold >= 90%)
   - Records dedup count for PRISMA diagram

11. **Protocol generator** (`src/protocol/generator.py`):
   - Generates PROSPERO-format protocol from `ReviewConfig`
   - 22 PROSPERO fields (current baseline: template-based deterministic rendering; hardening target: optional LLM-drafted narrative sections)

### Acceptance Criteria
- [ ] Each connector returns valid `SearchResult` with `CandidatePaper` list
- [ ] OpenAlex returns results for a test query (e.g., "autonomous vehicle trust")
- [ ] Deduplication correctly merges papers with same DOI
- [ ] `search_strategies_appendix.md` contains full Boolean strings per database
- [ ] Protocol document generates with all 22 fields
- [ ] `search_volume` gate runs after search
- [ ] Connector execution matrix is recorded (success/failure and explicit failure reason per connector)
- [ ] `uv run pytest tests/unit/test_protocol.py -q` passes

***

## BUILD PHASE 3: Screening
**Estimated Effort: 3 days**
**Depends on: Phase 1, Phase 2**

### What to Build

1. **Dual-reviewer screener** (`src/screening/dual_screener.py`):

   Architecture per paper:
   ```
   Reviewer A: gemini-2.5-flash-lite (temp=0.1, inclusion-emphasis prompt)
   Reviewer B: gemini-2.5-flash-lite (temp=0.3, exclusion-emphasis prompt)

   If agree -> final_decision = agreed_decision
   If disagree -> Adjudicator: gemini-2.5-pro sees both decisions -> final

   Log all decisions to decision_log
   Output: DualScreeningResult
   ```
   Uses `GeminiScreeningClient` (gemini_client.py) when API key is set; `HeuristicScreeningClient` when offline or no key.

2. **Prompt templates** (`src/screening/prompts.py`):
   - Reviewer A: "Include this paper if ANY inclusion criterion is plausibly met based on the title/abstract"
   - Reviewer B: "Exclude this paper if ANY exclusion criterion clearly applies"
   - Adjudicator: Receives both decisions + reasoning, makes final call

   **Prompt engineering patterns to implement (battle-tested from prototype):**

   a. **Topic context injection** -- every screening prompt starts with a header block:
      ```
      Role: {role from settings.yaml, e.g. "Title/Abstract Screening Specialist"}
      Goal: {goal with {topic} and {research_question} interpolated}
      Backstory: {backstory with {domain} interpolated}
      Topic: {topic}
      Research Question: {research_question}
      Domain: {domain}
      Keywords: {keywords joined by comma}
      ```
      This provides consistent framing across all prompts.

   b. **Structured output enforcement** -- all prompts end with:
      ```
      Return ONLY valid JSON matching this exact schema:
      {"decision": "include|exclude|uncertain", "confidence": 0.0-1.0,
       "reasoning": "...", "exclusion_reason": "..."}
      ```

   c. **Truncation limits** -- to stay within context windows and control cost:
      - Title/abstract screening: full title + abstract (no truncation needed)
      - Full-text screening: first 8,000 characters of full text
      - Data extraction: first 10,000 characters of full text

   d. **Confidence thresholds** -- from `config/settings.yaml`:
      - Auto-include if confidence >= `stage1_include_threshold` (0.85)
      - Auto-exclude if confidence >= `stage1_exclude_threshold` (0.80)
      - Papers between thresholds -> sent to adjudicator

3. **Two-stage screening:**
   - Stage 1 (title/abstract): Processes all papers from search
   - Stage 2 (full-text): Processes papers passing Stage 1. Requires **PDF retrieval** (`src/search/pdf_retrieval.py`) to fetch full texts via DOI/open-access resolution (Unpaywall + Semantic Scholar OA URLs + source URL fallback) before screening. For every EXCLUDED paper, reviewer must return `ExclusionReason` enum value (including `NO_FULL_TEXT` when PDF is unavailable).

4. **Proceed with partial screening (Ctrl+C):**
   - During screening, user may press Ctrl+C once to request early exit with already-screened papers
   - First Ctrl+C: sets proceed-with-partial flag; screening loop exits after current paper; checkpoint saved with status=partial
   - Second Ctrl+C: raises KeyboardInterrupt (abort)
   - DualReviewerScreener accepts optional `should_proceed_with_partial: Callable[[], bool]` callback; checks it before each paper and breaks when True
   - At screening phase start, emit hint: "Press Ctrl+C once to proceed with partial results, twice to abort."
   - Platform: SIGINT handler registered via `asyncio.add_signal_handler`; on Windows (NotImplementedError), handler is skipped

5. **Inter-rater reliability** (`src/screening/reliability.py`):
   - `compute_cohens_kappa()` using `sklearn.metrics.cohen_kappa_score`
   - Logs kappa to decision log
   - Generates `disagreements_report.md`

6. **Screening safeguard gate** runs after full-text screening

### Acceptance Criteria
- [ ] Two independent LLM calls per paper at each stage
- [ ] Different prompts for Reviewer A (inclusion-emphasis) and B (exclusion-emphasis)
- [ ] Disagreements adjudicated by third LLM call
- [ ] All decisions logged to `decision_log` table
- [ ] Cohen's kappa computed and logged
- [ ] Full-text exclusion reasons use `ExclusionReason` enum
- [ ] `disagreements_report.md` generated
- [ ] Full-text retrieval coverage report is generated (attempted/succeeded/failed counts and reasons)
- [ ] `uv run pytest tests/unit/test_screening.py tests/unit/test_reliability.py -q` passes
- [ ] `uv run pytest tests/integration/test_dual_screening.py -q` passes

***

## BUILD PHASE 4: Extraction & Quality Assessment
**Estimated Effort: 3-4 days**
**Depends on: Phase 3**

### What to Build

1. **Study classifier** (`src/extraction/study_classifier.py`):
   - Single Pro-tier agent classifies each paper into `StudyDesign` enum with typed JSON output
   - Required output fields: `study_design`, `confidence`, `reasoning`
   - Confidence fallback rule: if `confidence < 0.70`, force route to `StudyDesign.NON_RANDOMIZED`
   - Log every classification decision with predicted label, confidence, threshold, and rationale in `decision_log`
   - Routes to correct RoB tool

2. **Structured extractor** (`src/extraction/extractor.py`):
   - Baseline implementation currently uses deterministic extraction scaffolding into `ExtractionRecord` per paper
   - Target hardening path: migrate to Pro-tier LLM extraction with strict typed JSON output
   - Source spans preserved for citation lineage
   - Extraction completeness gate runs after

3. **RoB 2 assessor** (`src/quality/rob2.py`):
   - 5 Cochrane domains for RCTs[^25]
   - Baseline implementation currently uses deterministic domain heuristics
   - Target hardening path: migrate to agentic signalling-question evaluation per domain
   - Each domain: Low / Some concerns / High + rationale
   - Overall judgment algorithm: All Low -> Low; Any High -> High; Otherwise -> Some Concerns

4. **ROBINS-I assessor** (`src/quality/robins_i.py`):
   - 7 domains for non-randomized studies
   - Baseline implementation currently uses deterministic domain heuristics
   - Target hardening path: migrate to agentic domain evaluation with typed outputs
   - Uses `RobinsIJudgment` scale: Low / Moderate / Serious / Critical / No Information (different from RoB 2)

5. **CASP assessor** (`src/quality/casp.py`):
   - Baseline implementation currently uses deterministic checklist heuristics
   - Target hardening path: migrate to prompt-based qualitative appraisal

6. **Study router** (`src/quality/study_router.py`):
   - RCT -> RoB 2; Non-randomized -> ROBINS-I; Qualitative -> CASP

7. **GRADE assessor** (`src/quality/grade.py`):
   - Per-outcome assessment with all 5 downgrading + 3 upgrading factors
   - Outputs `GRADEOutcomeAssessment`

8. **Risk of bias summary figure** (`src/visualization/rob_figure.py`):
   - Traffic-light summary (matplotlib): rows=studies, cols=domains, cells=colored circles

### Acceptance Criteria
- [ ] Study classifier routes papers to correct tool
- [ ] Classifier emits confidence and applies `< 0.70 -> non_randomized` fallback
- [ ] Classification decisions are written to `decision_log` with confidence metadata
- [ ] RoB 2 produces 5-domain assessment for RCTs
- [ ] ROBINS-I produces 7-domain assessment for non-randomized studies
- [ ] GRADE produces per-outcome certainty assessment
- [ ] Traffic-light figure renders correctly
- [ ] Extraction completeness gate passes
- [ ] All assessments stored in SQLite
- [ ] `uv run pytest tests/unit/test_rob2.py tests/unit/test_robins_i.py -q` passes

***

## BUILD PHASE 5: Synthesis & Meta-Analysis
**Estimated Effort: 3-4 days**
**Depends on: Phase 4**

### What to Build

1. **Feasibility checker** (`src/synthesis/feasibility.py`):
   - Current baseline: deterministic similarity and grouping checks from structured extraction outputs
   - Hardening target: LLM-assisted assessment of clinical/methodological similarity
   - Output: `feasible: bool, rationale: str, groupings: List`

2. **Effect size calculator** (`src/synthesis/effect_size.py`):
   - For continuous outcomes: use `statsmodels.stats.meta_analysis.effectsize_smd` for standardized mean difference
   - For dichotomous outcomes: use `statsmodels.stats.meta_analysis.effectsize_2proportions` for risk difference, log risk ratio, log odds ratio, or arcsine square root transformation
   - Also use `scipy.stats` for OR, RR, RD when raw 2x2 tables available; MD for continuous
   - All with 95% CIs
   - **CRITICAL: LLMs must NOT compute statistics. Extract data from `ExtractionRecord`, pass to deterministic functions.**

3. **Meta-analysis engine** (`src/synthesis/meta_analysis.py`):
   - Wraps `statsmodels.stats.meta_analysis.combine_effects()`[^23][^22]
   - Fixed-effect when I^2 < 40%, random-effects (DerSimonian-Laird) when I^2 >= 40%
   - Returns: pooled estimate, CI, I^2, Q, tau^2, p-value

4. **Forest plot** (`src/visualization/forest_plot.py`):
   - Uses `statsmodels` `.plot_forest()` method[^24]
   - One per outcome, labeled with model + heterogeneity stats

5. **Funnel plot** (`src/visualization/funnel_plot.py`):
   - matplotlib scatter: x=effect size, y=standard error (inverted)
   - Only when >= 10 studies
   - Dashed lines for pooled estimate + expected 95% CI bounds

6. **Narrative synthesis fallback** (`src/synthesis/narrative.py`):
   - When meta-analysis infeasible
   - Structured tables + effect direction summary
   - Current baseline: deterministic theme extraction and summary
   - Hardening target: LLM synthesis of cross-study themes/patterns

### Acceptance Criteria
- [ ] Effect sizes computed using scipy/statsmodels (NOT LLM)
- [ ] Forest plot renders with individual + pooled estimates
- [ ] I^2 and Q heterogeneity stats computed and displayed
- [ ] Correct model selection (fixed vs random) based on I^2 threshold
- [ ] Funnel plot generated when >= 10 studies
- [ ] Narrative fallback works when meta-analysis infeasible
- [ ] `uv run pytest tests/unit/test_effect_size.py tests/unit/test_meta_analysis.py -q` passes

***

## BUILD PHASE 6: Article Writing
**Estimated Effort: 3 days**
**Depends on: Phases 1-5**

### What to Build

1. **Section writer** (`src/writing/section_writer.py`):
   - Generic PydanticAI agent that takes section context + writes academic prose
   - For each claim in output text: registers claim in citation ledger + links to evidence

2. **Per-section prompts** (`src/writing/prompts/`):
   - **Abstract**: PRISMA 2020 abstract checklist (12 items), <= 250 words. The 12 abstract items are:
     1. Title -- identify as systematic review/meta-analysis
     2. Objectives -- research question with PICO
     3. Eligibility criteria -- key inclusion/exclusion
     4. Information sources -- databases searched with dates
     5. Risk of bias -- assessment methods used
     6. Included studies -- number and characteristics
     7. Synthesis of results -- pooled estimates with CIs
     8. Results of individual studies -- summary of key findings
     9. Discussion -- strengths and limitations
     10. Other -- funding, registration (PROSPERO)
     11. Registration -- protocol registration number
     12. Funding -- funding sources
   - **Introduction**: Background, gap, objective, significance
   - **Methods**: ALL PRISMA Items 3-16. The implementing agent must cover:
     - Item 3: Eligibility criteria (PICO components)
     - Item 4: Information sources (databases, dates of last search)
     - Item 5: Search strategy (full Boolean strings -- reference appendix)
     - Item 6: Selection process (number of reviewers, agreement mechanism: "Two independent AI reviewers; Cohen's kappa = {value}")
     - Item 7: Data collection process (extraction method)
     - Item 8: Data items (variables extracted)
     - Item 9: Study risk of bias assessment (tools: RoB 2, ROBINS-I, etc.)
     - Item 10: Effect measures (OR, RR, MD, SMD)
     - Item 11: Synthesis methods (meta-analysis model, software)
     - Item 12: Certainty assessment (GRADE)
     - Item 13a-d: Results of synthesis (forest plot, heterogeneity, sensitivity)
     - Item 14: Reporting biases (funnel plot, Egger's test)
     - Item 15: Certainty of evidence (GRADE SoF table)
     - Item 16: Study registration and protocol
   - **Results**: Study selection -> PRISMA diagram ref; Study characteristics table; RoB -> traffic-light ref; Synthesis -> forest plot ref; Certainty -> GRADE SoF table ref
   - **Discussion**: Key findings, comparison with prior work, strengths, limitations, implications
   - **Conclusion**: Summary, implications for practice/research

   **Writing prompt engineering patterns (battle-tested from prototype):**

   a. **Prohibited phrases** -- every writing prompt includes this constraint:
      ```
      NEVER use these phrases: "Of course", "Here is", "As an expert",
      "Certainly", "In this section", "As mentioned above",
      "It is important to note", "It should be noted"
      Do NOT begin with conversational preamble or meta-commentary.
      Do NOT use separator lines (***, ---).
      Output must be suitable for direct insertion into the manuscript.
      ```

   b. **Citation catalog constraint** -- writing agents receive a citation catalog and must obey:
      ```
      Use ONLY citations from the provided catalog below.
      Use exact citekey format: [Smith2023], [Jones2024a]
      Do NOT invent or hallucinate any citations not in the catalog.
      Every factual claim must be supported by at least one citation.
      ```

   c. **Style pattern integration** -- if style extraction is enabled (see item 6 below), each writing prompt receives extracted patterns:
      ```
      Style patterns extracted from included papers:
      - Sentence openings: {list of common academic openings}
      - Vocabulary: {domain-specific terms from included papers}
      - Citation patterns: {how citations are integrated in-text}
      - Transitions: {common transition phrases between paragraphs}
      Emulate these patterns for consistency with the source literature.
      ```

   d. **Study-count adaptation** -- prompts adapt language to the actual number of included studies:
      - 0 studies: empty review (error state)
      - 1 study: singular language, no synthesis/comparison subsections
      - 2+ studies: plural language, full synthesis subsections

   e. **Truncation limits** for writing context:
      - Style extraction from papers: 50,000 characters per paper
      - Naturalness scoring input: 3,000 characters
      - Humanization input: 4,000 characters

3. **GRADE Summary of Findings table** (`src/quality/grade.py` extension):
   - Columns: Outcome, Participants (studies), Certainty, Relative effect, Anticipated absolute effects, Plain language

4. **Humanizer** (`src/writing/humanizer.py`):
   - Second-pass LLM refinement for academic tone, sentence variation, flow

5. **Citation lineage enforcement**: After each section, `CitationLedger.validate_section()` checks all in-text citations resolve

6. **Style pattern extractor** (`src/writing/style_extractor.py`):
   - Before writing begins, analyze included papers to extract writing patterns
   - Extracts: sentence openings, domain vocabulary, citation integration patterns, transition phrases
   - Uses `gemini-2.5-pro` (from `settings.yaml` `agents.style_extraction`)
   - Truncation: 50,000 chars per paper
   - Output: `StylePatterns` dataclass fed to each section writer prompt
   - Controlled by `settings.yaml` `writing.style_extraction` (can be disabled)

7. **Per-section checkpoint** (paper-level persistence pattern):
   - After each section is written and validated by citation ledger, save `SectionDraft` to `section_drafts` table immediately
   - On resume, query `section_drafts` for this `workflow_id` to find completed sections; skip them
   - Controlled by `settings.yaml` `writing.checkpoint_per_section`

8. **Naturalness scorer** (`src/writing/naturalness_scorer.py`):
   - Scores AI-generated text on a 0.0-1.0 scale for academic naturalness
   - Uses `gemini-2.5-pro` to evaluate: vocabulary diversity, sentence structure variation, absence of AI-tell phrases, domain-appropriate register
   - Truncation: 3,000 chars input
   - Threshold from `settings.yaml` `writing.naturalness_threshold` (default 0.75)
   - If below threshold, triggers humanizer refinement (up to `writing.humanization_iterations` passes)

9. **LLM timeout**: All writing LLM calls use a timeout of `settings.yaml` `writing.llm_timeout` (default 120 seconds) to prevent hanging on slow responses. On timeout, retry once, then fail the section with a clear error.

### Acceptance Criteria
- [ ] All 6 manuscript sections generated
- [ ] Methods mentions dual-reviewer screening + kappa
- [ ] Results references all figures and tables
- [ ] Abstract <= 250 words, covers PRISMA abstract checklist
- [ ] All claims registered in citation ledger
- [ ] Citation lineage gate passes
- [ ] Style patterns extracted from included papers (when enabled)
- [ ] Per-section checkpoint: kill during writing, restart, picks up at next unwritten section
- [ ] Naturalness score >= 0.75 for all sections after humanization
- [ ] `uv run pytest tests/integration/test_writing_pipeline.py -q` passes

***

## BUILD PHASE 7: PRISMA Diagram & Visualizations
**Estimated Effort: 2 days**
**Depends on: Phases 2, 3, 5** (PRISMA diagram needs synthesis counts for qualitative vs quantitative split)

### What to Build

1. **PRISMA 2020 diagram** (`src/prisma/diagram.py`):
   - Use `prisma-flow-diagram` library (`plot_prisma2020_new`) when available; fallback to custom matplotlib renderer on ImportError. Map `PRISMACounts` to library format.
   - Two-column structure (databases vs other sources)[^25]
   - Per-database counts in identification box
   - Exclusion reasons categorized from `ExclusionReason` enum
   - Separate qualitative/quantitative synthesis counts
   - **Arithmetic validation**: records in = records out at every stage
   - **KNOWN LIMITATION (v1):** The "other sources" right-hand column is currently disabled in `render_prisma_diagram()` via `if False and counts.other_sources_records:`. All papers (including Perplexity-discovered ones) pass through a single unified screening pipeline so all records appear in the left-hand databases column. This avoids double-counting but means the diagram does not visually distinguish database from other-source records. Restoring the two-column split requires a deduplication-aware PRISMA count builder that can separate already-screened other-source papers.

2. **Publication timeline** (`src/visualization/timeline.py`)

3. **Geographic distribution** (`src/visualization/geographic.py`):
   - Requires `CandidatePaper.country`; enrich from OpenAlex `authorships[].countries` or `institutions[].country_code`, Crossref `author.affiliation[].country`.

4. **ROB traffic light** (`src/visualization/rob_figure.py`): Accept both `list[RoB2Assessment]` and `list[RobinsIAssessment]`; render combined figure with RoB 2 (5 domains) and ROBINS-I (7 domains) blocks.

5. **Uniform naming**: All artifacts use `fig_`, `doc_`, `data_` prefixes per Part 4A.

### Acceptance Criteria
- [ ] PRISMA diagram uses two-column structure
- [ ] Per-database counts displayed
- [ ] Exclusion reasons categorized and counted
- [ ] Arithmetic validation passes
- [ ] `uv run pytest tests/unit/test_prisma_diagram.py -q` passes

***

## BUILD PHASE 8: IEEE Export & Orchestration
**Estimated Effort: 3-4 days**
**Depends on: All previous phases**

### What to Build

1. **PydanticAI Graph wiring** (`src/orchestration/workflow.py`):
   - Define all workflow nodes (one per phase)
   - Define edges (phase dependencies)
   - Wire HITL interrupts at: borderline screening, pre-export citation review
   - Register SIGINT handler at run start: first Ctrl+C sets proceed-with-partial, second aborts; pass callback into ScreeningNode
   - When screening exits via proceed-with-partial, save checkpoint with status='partial'
   - Enable durable execution for crash recovery

2. **IEEE LaTeX exporter** (`src/export/ieee_latex.py`):
   - Markdown -> LaTeX using IEEEtran.cls
   - `\cite{citekey}` numbered references
   - Tables -> `booktabs`; figures -> `\includegraphics`

3. **Submission packager** (`src/export/submission_packager.py`):
   ```
   submission/
   |-- manuscript.tex
   |-- manuscript.pdf
   |-- references.bib
   |-- figures/
   |-- supplementary/
   |   |-- search_strategies_appendix.pdf
   |   |-- prisma_checklist.pdf
   |   |-- extracted_data.csv
   |   `-- screening_decisions.csv
   `-- cover_letter.md
   ```

4. **IEEE validator** (`src/export/ieee_validator.py`):
   - Abstract: 150-250 words
   - Reference count: warn if < 30 or > 80
   - All `\cite{}` resolve in `.bib`
   - No `[?]` or placeholder text

5. **PRISMA checklist validator** (`src/export/prisma_checklist.py`):
   - Checks 27 items against manuscript: REPORTED Reported / PARTIAL Partial / MISSING Missing
   - Gate: >= 24/27 items reported

6. **CLI** (`src/main.py`):
   ```
   python -m src.main run --config config/review.yaml --settings config/settings.yaml
   python -m src.main run --config config/review.yaml --verbose   # Per-phase status, API logs
   python -m src.main run --config config/review.yaml --debug    # Verbose + model dumps
   python -m src.main run --config config/review.yaml --offline  # Heuristic screening only
   python -m src.main resume --topic "conversational AI tutors"
   python -m src.main resume --workflow-id abc123
   python -m src.main validate --workflow-id abc123
   python -m src.main export --workflow-id abc123
   python -m src.main status --workflow-id abc123
   ```
   - Optional: `--log-root`, `--output-root` for paths; `-v`/`--verbose`, `-d`/`--debug`, `--offline` for output and behavior.
   - Resume is implemented; validate/export/status are blocked.

   **Resume logic (paper-level):**
   1. `resume --topic` / `resume --workflow-id` queries **workflows_registry** (central db at `{log_root}/workflows_registry.db`) for matching entry; entry provides `db_path` to the run's `runtime.db`. **Fallback:** If the registry is missing (e.g. runs from before registry existed), `resume --workflow-id` scans `run_summary.json` files under the log root to locate the runtime.db.
   2. For matching workflow, query `checkpoints` table for last completed phase
   3. Determine next phase to run; within that phase, query per-paper tables (e.g. `screening_decisions`) for already-processed paper_ids
   4. Skip processed papers, continue from where it left off -- even mid-phase
   5. If crash happened mid-screening (50 of 200 papers done), resume picks up at paper 51

   **Topic-based auto-resume:** If `run` is called and a workflow already exists for the same topic (by `config_hash` match), prompt user: "Found existing run for this topic (phase 4/8 complete). Resume? [Y/n]"

### Acceptance Criteria
- [ ] Full workflow runs from `python -m src.main run` -> produces `submission/`
- [ ] IEEE LaTeX compiles without errors
- [ ] All 6 quality gates pass in strict mode
- [ ] PRISMA checklist shows >= 24/27 items
- [x] Resume from any phase preserves state (paper-level granularity)
- [x] Resume mid-phase: kill during screening, restart, picks up at next unprocessed paper
- [x] Topic-based auto-resume finds and offers to continue existing workflows
- [ ] `uv run pytest tests/ -q` -- ALL tests pass
- [ ] `uv run pytest tests/e2e/test_full_review.py -q` -- end-to-end passes

***

# PART 5B: WEB UI & API REFERENCE

The web UI is a local single-user dashboard. No authentication. The user supplies API keys at runtime via the Setup form; they are injected into the subprocess environment and never persisted server-side.

**Full frontend architecture spec:** `docs/frontend-spec.md`

---

## FastAPI Server (`src/web/app.py`)

Start both servers together with Overmind (recommended):

```bash
./bin/dev          # foreground
./bin/dev -D       # daemon mode -- survives terminal close
```

Or start only the backend:

```bash
uv run uvicorn src.web.app:app --reload --port 8000
```

See `Procfile.dev` and `docs/frontend-spec.md` Section 9 for full dev workflow details.

The server also serves the built React frontend from `frontend/dist/` when present (root `/` route),
and serves run output files from `data/outputs/` at the `/outputs` static mount.

### API Endpoints

| Method | Path | Request | Response | Description |
|:---|:---|:---|:---|:---|
| `POST` | `/api/run` | `RunRequest` | `RunResponse` | Start a new review run in a background asyncio Task |
| `GET` | `/api/stream/{run_id}` | -- | SSE stream | Stream `ReviewEvent` JSON objects; ends with `done`/`error`/`cancelled`; heartbeat every 15s |
| `POST` | `/api/cancel/{run_id}` | -- | `{"status": "cancelled"}` | Cancel an active run (sets cancellation event) |
| `GET` | `/api/runs` | -- | `list[RunInfo]` | List all in-memory active runs |
| `GET` | `/api/results/{run_id}` | -- | `{run_id, outputs}` | Output artifact paths for a completed run |
| `GET` | `/api/download` | query: `path` | `FileResponse` | Download an artifact file (restricted to `data/outputs/`) |
| `GET` | `/api/config/review` | -- | `{content: str}` | Default `config/review.yaml` content (pre-fills Setup form) |
| `GET` | `/api/history` | query: `log_root` | `list[HistoryEntry]` | All past runs from `workflows_registry.db` |
| `POST` | `/api/history/attach` | `AttachRequest` | `RunResponse` | Attach a historical run for DB explorer without starting SSE |
| `GET` | `/api/db/{run_id}/papers` | query: `offset, limit, search` | `{total, offset, limit, papers[]}` | Paginated + searchable papers from run DB |
| `GET` | `/api/db/{run_id}/screening` | query: `stage, decision, offset, limit` | `{total, offset, limit, decisions[]}` | Screening decisions with filters |
| `GET` | `/api/db/{run_id}/costs` | -- | `{total_cost, records[]}` | Cost records grouped by model and phase |
| `GET` | `/api/run/{run_id}/artifacts` | -- | `{run_id, workflow_id, output_dir, artifacts{}}` | Full `run_summary.json` for any run (live or historical) |
| `POST` | `/api/run/{run_id}/export` | query: `log_root` | `{submission_dir, files[]}` | Package IEEE LaTeX submission; calls `package_submission()` |
| `GET` | `/api/health` | -- | `{"status": "ok"}` | Health check for `useBackendHealth` polling |

### Request/Response Types

```python
class RunRequest(BaseModel):
    review_yaml: str              # Full YAML content of review config
    gemini_api_key: str           # Required; injected as GEMINI_API_KEY
    openalex_api_key: str = ""    # Optional; injected as OPENALEX_API_KEY
    ieee_api_key: str = ""        # Optional; injected as IEEE_API_KEY
    log_root: str = "logs"
    output_root: str = "data/outputs"

class RunResponse(BaseModel):
    run_id: str
    topic: str

class RunInfo(BaseModel):
    run_id: str
    topic: str
    done: bool
    error: Optional[str]

class HistoryEntry(BaseModel):
    workflow_id: str
    topic: str
    status: str
    db_path: Optional[str]
    created_at: Optional[str]

class AttachRequest(BaseModel):
    workflow_id: str
    topic: str
    db_path: str
```

### In-Memory Run State

Each active run is tracked in `_active_runs: dict[str, _RunRecord]`:

```python
@dataclass
class _RunRecord:
    run_id: str
    topic: str
    queue: asyncio.Queue       # ReviewEvent JSON strings flow through here
    task: asyncio.Task         # Background task running run_workflow()
    done: bool
    error: Optional[str]
    outputs: list[str]         # Artifact paths registered on done
    db_path: Optional[str]     # Path to runtime.db for DB explorer
    workflow_id: Optional[str]
    log_root: str
```

---

## SSE Event Types

The `/api/stream/{run_id}` endpoint emits newline-delimited JSON events. Each event has a `type` field.
All events include a `ts` field (UTC ISO-8601 timestamp) injected by `WebRunContext._emit()`.
The frontend `useSSEStream` hook ignores `heartbeat`, prefetches buffered events via `GET /api/run/{run_id}/events`, deduplicates them, then opens the live SSE stream.

| Event type | Key fields | Description |
|:---|:---|:---|
| `phase_start` | `phase: str, description: str, total: int \| None` | A pipeline phase began |
| `phase_done` | `phase: str, summary: dict, total: int \| None, completed: int \| None` | A phase completed |
| `progress` | `phase: str, current: int, total: int` | Progress update within a phase (driven by `advance_screening`) |
| `api_call` | `source: str, status: str, phase: str, call_type: str, model: str \| None, paper_id: str \| None, latency_ms: int \| None, tokens_in: int \| None, tokens_out: int \| None, cost_usd: float \| None, records: int \| None, details: str \| None, section_name: str \| None, word_count: int \| None` | LLM call completed; used for client-side cost aggregation |
| `connector_result` | `name: str, status: str, records: int, error: str \| None` | Search connector returned results |
| `screening_decision` | `paper_id: str, stage: str, decision: str` | Single paper screening result |
| `extraction_paper` | `paper_id: str, design: str, rob_judgment: str` | Paper extracted with study design and RoB judgment |
| `synthesis` | `feasible: bool, groups: int, n_studies: int, direction: str` | Meta-analysis summary |
| `rate_limit_wait` | `tier: str, slots_used: int, limit: int` | Rate limiter pausing |
| `db_ready` | -- | Run DB is open and ready; frontend DB Explorer tabs unlock before run finishes |
| `done` | `outputs: dict[str, Any]` (label -> path), `ts?` | Run completed successfully |
| `error` | `msg: str`, `ts?` | Run failed |
| `cancelled` | `ts?` | Run was cancelled by user |
| `heartbeat` | -- | Keep-alive (every 15s); ignored by frontend |

---

## Frontend Views

| View | File | Description |
|:---|:---|:---|
| Setup | `views/SetupView.tsx` | YAML editor + API key form; starts a new run |
| Overview | `views/OverviewView.tsx` | Live dashboard: stat cards (papers found, included, cost, elapsed) + phase timeline |
| Cost & Usage | `views/CostView.tsx` | Cost by model/phase: Recharts bar chart + sortable tables |
| Event Log | `views/LogView.tsx` | Filterable event log (All / Phases / LLM / Search / Screening) |
| Results | `views/ResultsView.tsx` | Download links for all output artifacts (available when run is done) |
| Database | `views/DatabaseView.tsx` | DB explorer: papers (paginated + search), screening decisions (filterable), cost records |
| History | `views/HistoryView.tsx` | Past runs from registry; Open button attaches any run to DB explorer |

---

## Frontend Architecture Summary

- **Two-process:** Browser -> FastAPI :8000 -> `run_workflow()` -> SQLite
- **SSE flow:** `WebRunContext._emit()` -> `asyncio.Queue` (live) + `_RunRecord.event_log` (replay buffer) -> `/api/stream/{run_id}` and `/api/run/{run_id}/events` -> `useSSEStream` prefetch + dedup + live stream -> `events[]` -> all views
- **Cost tracking:** Client-side only; `useCostStats(events)` aggregates `api_call` events by model and phase
- **DB explorer:** Available for any run that has a `db_path` (live or historical); queries `papers`, `screening_decisions`, `cost_records` tables via DB endpoints
- **History:** `GET /api/history` reads `workflows_registry.db`; `POST /api/history/attach` registers the historical run as an in-memory record, loads event_log from DB, so DB endpoints and LogView can serve it
- **Key separation:** `runId` (live SSE target) is distinct from `dbRunId` (DB explorer target); attaching a historical run does not affect live stream

***

# PART 6: CONFIGURATION

Configuration is split into three layers following the twelve-factor app principle: **secrets in `.env`**, **per-review research config in `review.yaml`**, and **system behavior in `settings.yaml`**. Infrastructure constants (rate limits, cache TTL, proxy defaults) live in Python code, not YAML.

## 6.1 Per-Review Config: `config/review.yaml`

This is the ONLY file you edit per review. A new review = copy this file, change the content.

```yaml
# config/review.yaml -- Changes every review (~30 lines)

research_question: "How do conversational AI tutors impact learning outcomes?"
review_type: "systematic"   # systematic | scoping | narrative

pico:
  population: "Health science students"
  intervention: "Conversational AI tutors"
  comparison: "Traditional instruction"
  outcome: "Learning outcomes, engagement, retention"

keywords:
  - "conversational AI tutor"
  - "AI chatbot education"
  - "virtual teaching assistant"
  - "dialogue-based tutoring"
domain: "AI-powered educational technology in health sciences"
scope: "Focus on conversational AI tutors used in health science education"
inclusion_criteria:
  - "Studies on conversational AI tutors or chatbots for health science education"
  - "Published in English and peer-reviewed"
exclusion_criteria:
  - "Non-conversational educational technology"
  - "Non-health science domains"
  - "Conference abstracts without full papers"

date_range_start: 2015
date_range_end: 2026

# Which databases to search for this review
target_databases:
  - openalex
  - pubmed
  - arxiv
  - ieee_xplore
  - semantic_scholar
  - crossref
  - perplexity_search   # auxiliary other-source discovery only

target_sections:
  - abstract
  - introduction
  - methods
  - results
  - discussion
  - conclusion

# Protocol Registration (PRISMA 2020)
protocol:
  registered: false
  registry: "PROSPERO"        # PROSPERO | OSF | Other
  registration_number: ""     # e.g. "CRD42025XXXXXX"
  url: ""

# Funding and COI (required by PRISMA 2020)
funding:
  source: "No funding received"
  grant_number: ""
  funder: ""
conflicts_of_interest: "The authors declare no conflicts of interest."

# Optional: override auto-generated queries per database. Omit a database to use default.
# Keys: openalex, pubmed, arxiv, ieee_xplore, semantic_scholar, crossref, perplexity_search
search_overrides:
  crossref: '("conversational AI" OR "chatbot" OR "intelligent tutoring system") AND ("health science" OR "medical education" OR "health education")'
```

## 6.2 System Config: `config/settings.yaml`

Changes rarely. Tuned from real runs.

```yaml
# config/settings.yaml -- System behavior

# LLM free-tier RPM caps (enforced by src/llm/rate_limiter.py)
llm:
  flash_rpm: 10
  flash_lite_rpm: 15
  pro_rpm: 5

# Per-agent model assignments (3-tier: Flash-Lite / Flash / Pro)
# Flash-Lite ($0.10/1M in, $0.40/1M out): Bulk classification
# Flash ($0.30/1M in, $2.50/1M out): Balanced speed/cost
# Pro ($1.25/1M in, $10.00/1M out): Quality-critical reasoning
agents:
  screening_reviewer_a:
    model: "google-gla:gemini-2.5-flash-lite"
    temperature: 0.1
  screening_reviewer_b:
    model: "google-gla:gemini-2.5-flash-lite"
    temperature: 0.3
  screening_adjudicator:
    model: "google-gla:gemini-2.5-pro"
    temperature: 0.2
  search:
    model: "google-gla:gemini-2.5-flash"
    temperature: 0.1
  extraction:
    model: "google-gla:gemini-2.5-pro"
    temperature: 0.1
  quality_assessment:
    model: "google-gla:gemini-2.5-pro"
    temperature: 0.2
  study_type_detection:
    model: "google-gla:gemini-2.5-flash"
    temperature: 0.2
  writing:
    model: "google-gla:gemini-2.5-pro"
    temperature: 0.2
  abstract_generation:
    model: "google-gla:gemini-2.5-flash"
    temperature: 0.2
  humanizer:
    model: "google-gla:gemini-2.5-pro"
    temperature: 0.3
  style_extraction:
    model: "google-gla:gemini-2.5-pro"
    temperature: 0.2

# Screening safeguards (tuned thresholds from real runs)
screening:
  stage1_include_threshold: 0.85    # auto-include if confidence >= this
  stage1_exclude_threshold: 0.80    # auto-exclude if confidence >= this
  screening_concurrency: 5          # asyncio.Semaphore: max concurrent paper screenings
  skip_fulltext_if_no_pdf: true     # skip stage 2 when PDF unavailable; use stage 1 result
  keyword_filter_min_matches: 1     # papers with fewer intervention keyword hits are pre-excluded (0 = disable)
  # max_llm_screen: 200             # optional hard cap on LLM dual-review volume; omit to screen all candidates

# Dual reviewer
dual_review:
  enabled: true
  kappa_warning_threshold: 0.4

# Quality gates
gates:
  profile: "strict"                          # strict | warning
  search_volume_minimum: 50
  screening_minimum: 5
  extraction_completeness_threshold: 0.80
  extraction_max_empty_rate: 0.35            # gate if >35% papers have empty core fields
  cost_budget_max: 20.0

# Writing
writing:
  style_extraction: true                     # analyze included papers for style patterns
  humanization: true                         # second-pass academic tone refinement
  humanization_iterations: 2
  naturalness_threshold: 0.75                # minimum naturalness score (0-1)
  checkpoint_per_section: true               # save to SQLite after each section
  llm_timeout: 120                           # seconds per LLM call, prevents hanging

# Risk of Bias
risk_of_bias:
  rct_tool: "rob2"
  non_randomized_tool: "robins_i"
  qualitative_tool: "casp"

# Meta-Analysis
meta_analysis:
  enabled: true
  heterogeneity_threshold: 40                # I-squared percentage
  funnel_plot_minimum_studies: 10
  effect_measure_dichotomous: "risk_ratio"
  effect_measure_continuous: "mean_difference"

# IEEE Export
ieee_export:
  enabled: true
  template: "IEEEtran"
  bibliography_style: "IEEEtran"
  max_abstract_words: 250
  target_page_range: [7, 10]

# Citation Lineage
citation_lineage:
  block_export_on_unresolved: true
  minimum_evidence_score: 0.5

# Search depth: how many records to fetch per database connector.
# max_results_per_db is the global default; per_database_limits overrides it per connector.
# Perplexity is capped internally at 20 regardless of this setting.
search:
  max_results_per_db: 500
  per_database_limits:
    crossref: 1000
    pubmed: 500
    semantic_scholar: 500
    openalex: 500
    arxiv: 200
    ieee_xplore: 200
    perplexity_search: 20
```

## 6.3 Secrets: `.env`

Never committed to git. Loaded via `python-dotenv` in `src/main.py` entry point (`load_dotenv()` before any config access).

```bash
# .env -- Secrets only
GEMINI_API_KEY=your-gemini-key
OPENALEX_API_KEY=your-openalex-key       # Required since Feb 2026; free at openalex.org
IEEE_API_KEY=your-ieee-key               # Optional; for IEEE Xplore connector
NCBI_EMAIL=your-email@example.com        # Required for PubMed Entrez (Biopython)
PERPLEXITY_API_KEY=your-perplexity-key   # Optional; for perplexity_search auxiliary connector
SEMANTIC_SCHOLAR_API_KEY=your-s2-key     # Optional; higher rate limits for Semantic Scholar
```

## 6.4 Infrastructure Defaults (in Python code, NOT YAML)

These are constants of the APIs themselves and do not change per review:

```python
# In each connector file (e.g. src/search/pubmed.py):
RATE_LIMIT_RPS = 3     # PubMed: 3 requests/second with API key

# In src/search/openalex.py:
# Direct aiohttp; no pyalex. api_key passed as URL param per OpenAlex Feb 2026 requirement

# In src/search/arxiv.py:
RATE_LIMIT_RPS = 3     # arXiv: 3 requests/second

# In src/search/ieee_xplore.py:
RATE_LIMIT_RPS = 2     # IEEE Xplore: 2 requests/second
```

## 6.5 Config Validation

Both YAML files are validated into Pydantic models at startup. Invalid config = fail fast with clear error message.

```python
# In src/models/config.py:
class ReviewConfig(BaseModel):
    """Validated from config/review.yaml"""
    research_question: str
    review_type: ReviewType
    pico: PICOConfig
    keywords: List[str] = Field(min_length=1)
    search_overrides: Optional[Dict[str, str]] = None  # Per-database query overrides
    # ... all fields with validation

class SettingsConfig(BaseModel):
    """Validated from config/settings.yaml"""
    agents: Dict[str, AgentConfig]
    screening: ScreeningConfig        # includes concurrency, keyword_filter, skip_fulltext
    dual_review: DualReviewConfig
    gates: GatesConfig
    writing: WritingConfig
    risk_of_bias: RiskOfBiasConfig
    meta_analysis: MetaAnalysisConfig
    ieee_export: IEEEExportConfig
    citation_lineage: CitationLineageConfig
    search: SearchConfig              # max_results_per_db + per_database_limits
    llm: LLMRateLimitConfig | None    # RPM caps for rate limiter
```

***

# PART 7: RULES FOR THE AI AGENT

1. **Build in the exact phase order specified.** Do not skip phases.
2. **Do NOT allow LLMs to compute statistics.** Meta-analysis uses scipy/statsmodels deterministic functions only.
3. **Do NOT bypass Pydantic validation** at phase boundaries. Every function that crosses a phase boundary accepts and returns Pydantic models. **Exception for phase-internal models:** `SynthesisFeasibility` and `NarrativeSynthesis` live in `src/synthesis/` (not `src/models/`) because they are internal to the synthesis module and loaded by the synthesis node only. `StylePatterns`, `StudySummary`, and `WritingGroundingData` live in `src/writing/` (not `src/models/`) because they are internal to the writing module. `AgentRuntimeConfig` lives in `src/llm/provider.py`. These modules are the authoritative definitions; do NOT move them to `src/models/` or you will create circular imports.
4. **Do NOT introduce untyped dictionaries** as phase outputs.
5. **Do NOT hardcode any review topic.** Everything comes from `config.yaml`.
6. **Write tests for every new module.** Each build phase has specified test files.
7. **Use `async/await`** for all I/O operations (database search, LLM calls). **Write each individual decision/extraction/assessment to SQLite immediately** (paper-level persistence). Do NOT batch writes at phase end. Every processing loop must check for already-processed paper_ids before starting, enabling mid-phase resume after crash.
8. **Use `rich`** for CLI output (progress bars, tables, status). Screening and other long-running phases must show a progress bar with completed/total count (e.g. X/Y papers) using Rich BarColumn and MofNCompleteColumn.
9. **Every LLM call must be logged** with: model, tokens in/out, cost, latency. Cumulative cost tracked for budget gate.
10. **After each build phase, the user will review and approve before proceeding to the next phase.** Do not proceed without approval.
11. **Use exact checkpoint phase key strings from Part 3B.** The strings in `PHASE_ORDER` and in `workflow.py`'s `save_checkpoint()` calls must be identical or resume will silently fail. Never rename or shorten these strings.
12. **`submission/supplementary/` PDFs are stubs in v1.** `search_strategies_appendix.pdf` and `prisma_checklist.pdf` are placeholder text files, not real PDFs. The markdown appendix (`doc_search_strategies_appendix.md`) and checklist are the functional deliverables. Do not block export on missing PDF generation.

***

# PART 8: TEST STRATEGY

| Phase | Unit Tests | Integration Tests | E2E |
|:---|:---|:---|:---|
| 1: Foundation | `test_models.py`, `test_database.py`, `test_gates.py`, `test_citation_ledger.py`, `test_rate_limiter.py` | -- | -- |
| 2: Search | `test_protocol.py`, `test_perplexity_source_inference.py` | -- | -- |
| 3: Screening | `test_screening.py`, `test_reliability.py` | `test_dual_screening.py` | -- |
| 4: Extraction/Quality | `test_rob2.py`, `test_robins_i.py` | `test_quality_pipeline.py` | -- |
| 5: Synthesis | `test_effect_size.py`, `test_meta_analysis.py` | `test_synthesis_pipeline.py` | -- |
| 6: Writing | -- | `test_writing_pipeline.py` | -- |
| 7: PRISMA/Viz | `test_prisma_diagram.py` | -- | -- |
| 8: Export/Integration | `test_export.py` (covers ieee_latex + ieee_validator + bibtex + prisma_checklist), `test_workflow_registry.py`, `test_resume_state.py` | `test_run_command.py` | `test_full_review.py` (not yet implemented) |

**Verification commands after each phase:**
```bash
uv run pytest tests/unit -q
uv run pytest tests/integration -q
python -m src.main --help   # CLI loads without error
```

**Final verification (after Phase 8):**
```bash
uv run pytest tests/ -q                              # ALL tests pass
python -m src.main run --config config/review.yaml     # Full run
ls data/outputs/*/submission/                          # Contains manuscript.tex
```

***

# PART 9: DEFINITION OF DONE

The tool is ready for its first IEEE submission when ALL are true:

- [ ] Protocol auto-generated with all PICO elements
- [ ] Search strategies documented for every database with dates
- [ ] Dual-reviewer screening produces kappa >= 0.6
- [ ] Full-text exclusion reasons categorized
- [ ] RoB 2 completed for all RCTs
- [ ] ROBINS-I completed for all non-randomized studies
- [ ] Risk of bias traffic-light figure generated
- [ ] GRADE SoF table with all 8 factors
- [ ] PRISMA 2020 two-column diagram with correct arithmetic
- [ ] Forest plot for each poolable outcome
- [ ] Funnel plot when >= 10 studies
- [ ] Methods references all tools + kappa
- [ ] All claims traceable via citation ledger
- [ ] Zero unresolved citations at export
- [ ] IEEE LaTeX compiles with IEEEtran.cls
- [ ] Abstract <= 250 words
- [ ] PRISMA checklist >= 24/27 items reported
- [ ] All 6 quality gates pass in strict mode
- [ ] All tests pass
- [ ] `submission/` directory contains complete package

**When these criteria are met, run on your first chosen topic and submit to IEEE Access.**

***

# PART 10: BUILD ORDER VISUAL SUMMARY

```
PHASE 1: Foundation ---------------- 2-3 days
  Models + SQLite + Gates + Ledger + LLM Provider
  v CHECKPOINT: Verify contracts, DB, gates [x]

PHASE 2: Search -------------------- 2-3 days
  OpenAlex + PubMed + arXiv + IEEE + Dedup + Protocol
  v CHECKPOINT: Run test search, review protocol [x]

PHASE 3: Screening ----------------- 3 days
  Dual-reviewer + Prompts + Kappa + Disagreement report
  v CHECKPOINT: Screen test papers, verify kappa [x]

PHASE 4: Extraction & Quality ------ 3-4 days
  Extractor + RoB2 + ROBINS-I + CASP + GRADE + RoB figure
  v CHECKPOINT: Review assessments and figure [x]

PHASE 5: Synthesis ----------------- 3-4 days
  Feasibility + Effect sizes + Meta-analysis + Forest + Funnel
  v CHECKPOINT: Run on test data, verify plots [x]

PHASE 6: Writing ------------------- 3-4 days
  Section writer + Prompts + Style extraction + Humanizer + SoF table + Citation lineage
  v CHECKPOINT: Review manuscript quality, naturalness scores [x]

PHASE 7: PRISMA & Visualizations -- 2 days
  PRISMA 2020 diagram + Timeline + Geographic
  v CHECKPOINT: Verify diagram structure [x]

PHASE 8: Export & Orchestration --- 3-4 days
  Graph wiring + IEEE LaTeX + Packager + Validators + CLI
  v CHECKPOINT: Compile LaTeX, review PDF [x]

TOTAL: ~21-26 days of focused development
```

---

## References

1. [# Research Article Writer Agentic AI System


End-to-end agentic system that automates systematic literature reviews from search to publication-ready articles, including PRISMA 2020-compliant flow diagrams and visualizations.


## Table of Contents

...

.../ Directory**: 
  - Contains frontend libraries (vis-network, tom-select) for generated HTML network graphs
  - Referenced by generated HTML files but primarily uses CDN links
  - May be removed if not needed for local file serving


## License


MIT](https://www.perplexity.ai/search/08ea55bf-d48b-463e-9cfa-1616aec76e32) - Perfect. Now I see exactly what you've built. This is powerful, and your theory is sound--but you nee...

2. [Pydantic AI Review 2026 | AI Infrastructure & MLOps Tool](https://aiagentslist.com/agents/pydantic-ai) - Pydantic AI is an AI agent for ai infrastructure & mlops. Pydantic AI is a Python framework for buil...

3. [Pydantic AI: Type-Safe Python Framework for AI Agents & ...](https://pydantic.dev/pydantic-ai) - Build production-grade AI applications with Pydantic AI - a model-agnostic Python framework featurin...

4. [Graph - Pydantic AI](https://ai.pydantic.dev/graph/) - Graphs and finite state machines (FSMs) are a powerful abstraction to model, execute, control and vi...

5. [Beta Graph API - Pydantic AI](https://ai.pydantic.dev/graph/beta/) - GenAI Agent Framework, the Pydantic way

6. [Durable Execution - Pydantic AI](https://ai.pydantic.dev/durable_execution/overview/) - Pydantic AI allows you to build durable agents that can preserve their progress across transient API...

7. [Here's how to build durable AI agents with Pydantic and Temporal](https://temporal.io/blog/build-durable-ai-agents-pydantic-ai-and-temporal) - Find out how you can combine Pydantic AI's type safety with Temporal's Durable Execution to build pr...

8. [PydanticAI Reviews in 2026 - SourceForge](https://sourceforge.net/software/product/PydanticAI/) - Learn about PydanticAI. Read PydanticAI reviews from real users, and view pricing and features of th...

9. [LangChain vs LangGraph vs Custom Python Agents - LinkedIn](https://www.linkedin.com/pulse/langchain-vs-langgraph-custom-python-agents-garvit-sharma-cmalc) - LangChain vs LangGraph vs Custom Python Agents: The Framework Decision That Can Make or Break Your A...

10. [Comparing Top Python Frameworks for AI Agent Orchestration ...](https://efektif.io/2025/09/10/langgraph-vs-langchain-vs-pydanticai-comparing-top-python-frameworks-for-ai-agent-orchestration-2025/) - Choosing the right framework to build, orchestrate, and scale AI agents has never been more crucial--...

11. [PostgreSQL vs SQLite: Dive into Two Very Different ...](https://dev.to/lovestaco/postgresql-vs-sqlite-dive-into-two-very-different-databases-5a90) - Hello, I'm Maneshwar. I'm working on FreeDevTools online currently building *one place for all dev.....

12. [Very small web server: SQLite or PostgreSQL?](https://www.reddit.com/r/django/comments/1ivvs5k/very_small_web_server_sqlite_or_postgresql/) - Very small web server: SQLite or PostgreSQL?

13. [SQLite Vs PostgreSQL - Key Differences - Airbyte](https://airbyte.com/data-engineering-resources/sqlite-vs-postgresql) - Compare SQLite and PostgreSQL to understand their differences in features, performance, and use case...

14. [SQLite vs PostgreSQL: A Detailed Comparison - DataCampwww.datacamp.com > blog > sqlite-vs-postgresql-detailed-comparison](https://www.datacamp.com/blog/sqlite-vs-postgresql-detailed-comparison) - Explore the strengths, use cases, and performance differences between SQLite vs PostgreSQL. Discover...

15. [Gemini 2.5 Flash API Pricing 2026 - Costs, Performance & ...](https://pricepertoken.com/pricing-page/model/google-gemini-2.5-flash) - Gemini 2.5 Flash pricing: $0.30/M input. Compare with 10 similar models, see benchmarks, and find th...

16. [Gemini API Pricing 2026: Complete Per-1M-Token Cost Guide with ...](https://www.aifreeapi.com/en/posts/gemini-api-pricing-2026) - Master Gemini API pricing for 2026 with this comprehensive guide covering all 7 models, from Flash-L...

17. [Rate limits | Gemini API - Google AI for Developers](https://ai.google.dev/gemini-api/docs/rate-limits)

18. [Rate limits - Google Gemini API](https://gemini-api.apidog.io/doc-965865) - Rate limits - Google Gemini API

19. [pyalex/README.md at main - J535D165/pyalex](https://github.com/J535D165/pyalex/blob/main/README.md) - A Python library for OpenAlex (openalex.org). Contribute to J535D165/pyalex development by creating ...

20. [pyalex](https://pypi.org/project/pyalex/0.5/) - One downloader for many scientific data and code repositories!

21. [Exa.ai vs. Tavily - AI Semantic Search API for LLM - Data4AI](https://data4ai.com/blog/tool-comparisons/exa-ai-vs-tavily/) - Compare Exa.ai vs Tavily on semantic ranking, API setup and RAG integration. See which search API fi...

22. [Meta-Analysis in statsmodels](https://www.statsmodels.org/dev/examples/notebooks/generated/metaanalysis1.html) - The combine_effects computes fixed and random effects estimate for the overall mean or effect. The r...

23. [Changing Data To Have...](https://www.statsmodels.org/stable/examples/notebooks/generated/metaanalysis1.html)

24. [python 3.x - How can I create a forest plot? - Stack Overflow](https://stackoverflow.com/questions/65197025/how-can-i-create-a-forest-plot) - The statsmodels library has an API for doing simple meta-analysis and plotting forest plots. It supp...

25. [paste.txt](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/REDACTED/paste.txt) - Redacted leaked signed URL containing temporary credentials.

