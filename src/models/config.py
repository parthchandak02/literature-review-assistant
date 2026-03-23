"""Configuration models loaded from YAML."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from src.models.enums import ReviewType


class PICOConfig(BaseModel):
    population: str
    intervention: str
    comparison: str
    outcome: str


class ProtocolRegistration(BaseModel):
    registered: bool = False
    registry: str = "PROSPERO"
    registration_number: str = ""
    url: str = ""


class FundingInfo(BaseModel):
    source: str = "No funding received"
    grant_number: str = ""
    funder: str = ""


class ReviewConfig(BaseModel):
    project_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    research_question: str
    review_type: ReviewType
    pico: PICOConfig
    keywords: list[str] = Field(min_length=1)
    domain: str
    scope: str
    inclusion_criteria: list[str] = Field(min_length=1)
    exclusion_criteria: list[str] = Field(min_length=1)
    date_range_start: int
    date_range_end: int
    target_databases: list[str] = Field(min_length=1)
    target_sections: list[str] = Field(
        default_factory=lambda: [
            "abstract",
            "introduction",
            "methods",
            "results",
            "discussion",
            "conclusion",
        ]
    )
    protocol: ProtocolRegistration = Field(default_factory=ProtocolRegistration)
    funding: FundingInfo = Field(default_factory=FundingInfo)
    conflicts_of_interest: str = "The authors declare no conflicts of interest."
    author_name: str = Field(
        default="",
        description=(
            "Full name of the corresponding/first author. "
            "Used in CRediT declarations and the LaTeX \\author{} command. "
            "Leave blank to use the placeholder '[Author name]'."
        ),
    )
    search_overrides: dict[str, str] | None = Field(
        default=None,
        description="Optional per-database query overrides. Keys: openalex, pubmed, arxiv, ieee_xplore, semantic_scholar, crossref, perplexity_search. Omit a database to use auto-generated query.",
    )
    living_review: bool = Field(
        default=False,
        description=(
            "Enable living review mode. When true, connectors only fetch records "
            "published after last_search_date, and papers already screened in a "
            "prior run are skipped automatically."
        ),
    )
    last_search_date: str | None = Field(
        default=None,
        description=(
            "ISO date string (YYYY-MM-DD) of the most recent completed search. "
            "Updated automatically by the workflow after each successful run. "
            "Used as the from_date filter when living_review is true."
        ),
    )
    masterlist_csv_path: str | None = Field(
        default=None,
        description=(
            "Absolute path to a pre-assembled master list CSV (Scopus export format). "
            "When set, SearchNode loads papers from this file instead of running "
            "database connectors. target_databases is still required by validation "
            "but is unused when this field is set."
        ),
    )
    supplementary_csv_paths: list[str] = Field(
        default_factory=list,
        description=(
            "List of absolute paths to supplementary CSV exports (e.g. Embase, CINAHL). "
            "These are ADDED to connector results, not replacing them. Each file is "
            "parsed with flexible column detection supporting Scopus, Embase, CINAHL, "
            "and RIS-derived CSV formats. Papers are deduplicated after merge."
        ),
    )
    search_limitation: str | None = Field(
        default=None,
        description=(
            "Optional statement of search/source limitation (e.g. 'Searches were limited "
            "to Scopus to align with institutional access.'). Injected into Methods section "
            "when present."
        ),
    )


class AgentConfig(BaseModel):
    model: str
    temperature: float = Field(ge=0.0, le=1.0, default=0.2)


class ScreeningConfig(BaseModel):
    stage1_include_threshold: float = Field(ge=0.0, le=1.0, default=0.85)
    stage1_exclude_threshold: float = Field(ge=0.0, le=1.0, default=0.80)
    keyword_filter_min_matches: int = Field(
        ge=0,
        default=1,
        description="Minimum keyword hits required to send a paper to LLM screening; 0 disables pre-filter.",
    )
    auto_exclude_empty_abstract: bool = Field(
        default=True,
        description=(
            "When true, papers with empty abstract text are deterministically excluded "
            "before any LLM screening to reduce low-information calls."
        ),
    )
    secondary_review_patterns: list[str] = Field(
        default_factory=lambda: [
            "systematic review",
            "scoping review",
            "narrative review",
            "umbrella review",
            "meta-analysis",
            "meta analysis",
        ],
        description=(
            "Lowercase title/abstract phrases used for deterministic pre-LLM exclusion "
            "of secondary-review studies."
        ),
    )
    protocol_only_patterns: list[str] = Field(
        default_factory=lambda: [
            "study protocol",
            "trial protocol",
            "protocol for",
            "study design and methods",
            "trial registration",
            "prospero protocol",
        ],
        description=(
            "Lowercase title/abstract phrases used for deterministic pre-LLM exclusion "
            "of protocol-only records."
        ),
    )
    deterministic_allowlist_patterns: list[str] = Field(
        default_factory=list,
        description=(
            "Lowercase phrases that bypass deterministic secondary/protocol exclusions "
            "when matched in title/abstract. Use sparingly for known false positives."
        ),
    )
    deterministic_exclude_qa_sample_size: int = Field(
        default=20,
        ge=0,
        le=200,
        description=(
            "Maximum random sample size emitted for deterministic exclusion QA review "
            "per screening run."
        ),
    )
    empty_abstract_rescue_sample_size: int = Field(
        default=5,
        ge=0,
        le=100,
        description=(
            "Maximum number of empty-abstract records per run that may bypass deterministic "
            "exclusion when title keywords strongly suggest relevance."
        ),
    )
    empty_abstract_rescue_keyword_min_matches: int = Field(
        default=2,
        ge=1,
        le=20,
        description="Minimum title keyword matches required for empty-abstract rescue forwarding.",
    )
    skip_fulltext_if_no_pdf: bool = Field(
        default=True, description="Skip stage 2 when no real PDFs are retrieved; treats stage-1 survivors as included."
    )
    screening_concurrency: int = Field(
        ge=1, le=20, default=5, description="Number of papers screened concurrently by the LLM dual-reviewer."
    )
    max_llm_screen: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Hard cap on the total number of papers sent to LLM dual-review. "
            "Papers beyond this count are skipped and treated as excluded at the "
            "title/abstract stage, controlling API cost for exploratory runs. "
            "Set to null (or omit) to screen all candidate papers."
        ),
    )
    bm25_validation_tail_size: int = Field(
        default=0,
        ge=0,
        le=500,
        description=(
            "Number of near-cutoff papers (just below max_llm_screen) to forward to LLM "
            "for validation instead of hard auto-excluding by BM25. "
            "0 keeps legacy behavior (all tail papers auto-excluded)."
        ),
    )
    cap_overflow_enabled: bool = Field(
        default=True,
        description=(
            "Enable bounded overflow screening beyond max_llm_screen when near-cutoff "
            "validation yield suggests recall risk."
        ),
    )
    cap_overflow_trigger_include_rate: float = Field(
        default=0.20,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum include-or-uncertain rate in the BM25 validation tail required "
            "to trigger overflow screening."
        ),
    )
    cap_overflow_min_validation_n: int = Field(
        default=10,
        ge=1,
        le=200,
        description="Minimum number of validation-tail papers required before overflow can trigger.",
    )
    cap_overflow_slice_size: int = Field(
        default=25,
        ge=1,
        le=200,
        description="Number of near-cutoff papers to add in one overflow screening slice.",
    )
    cap_overflow_max_extra: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Maximum total overflow papers allowed beyond max_llm_screen in a run.",
    )
    calibrate_threshold: bool = Field(
        default=True,
        description=(
            "Run an active-learning kappa calibration pass on a random sample "
            "of papers before the main screening loop. Adjusts stage1_include_threshold "
            "until Cohen's kappa >= calibration_target_kappa or max iterations reached."
        ),
    )
    calibration_sample_size: int = Field(
        default=30,
        ge=5,
        le=200,
        description="Number of papers to screen in the calibration sample.",
    )
    calibration_target_kappa: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Target Cohen's kappa for calibration bisection. Calibration stops when reached.",
    )
    calibration_max_iterations: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum bisection iterations during threshold calibration.",
    )
    calibration_exclude_margin: float = Field(
        default=0.05,
        ge=0.0,
        le=0.5,
        description=(
            "Margin subtracted from the include threshold to derive the temporary "
            "exclude threshold during calibration. Keeps a recall-first buffer."
        ),
    )
    insufficient_content_min_words: int = Field(
        default=5,
        ge=0,
        description=(
            "Minimum abstract word count to allow LLM screening. Papers with fewer words "
            "are auto-excluded as title-only stubs. Lowering increases recall at the cost "
            "of more LLM calls on borderline records. 0 disables the heuristic entirely."
        ),
    )
    batch_screen_enabled: bool = Field(
        default=True,
        description=(
            "Enable batch LLM pre-ranking between BM25 and the dual-reviewer. "
            "A single LLM call scores up to batch_screen_size papers at once and "
            "filters out clearly irrelevant papers before the expensive dual-review step."
        ),
    )
    batch_screen_size: int = Field(
        default=80,
        ge=1,
        le=200,
        description="Number of papers per batch LLM call in the batch pre-ranker.",
    )
    batch_screen_threshold: float = Field(
        default=0.35,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum relevance score (0-1) from the batch LLM ranker to forward a paper "
            "to the dual-reviewer. Papers below this threshold are auto-excluded as "
            "batch_screened_low. Set deliberately low (0.35) to err on the side of recall."
        ),
    )
    batch_screen_uncertain_band: float = Field(
        default=0.0,
        ge=0.0,
        le=0.5,
        description=(
            "Recall-first buffer below batch_screen_threshold. "
            "Papers with scores in [threshold - band, threshold) are forwarded as uncertain "
            "instead of auto-excluded. 0 keeps legacy behavior."
        ),
    )
    batch_screen_validation_fraction: float = Field(
        default=0.10,
        ge=0.01,
        le=0.50,
        description=(
            "Fraction of auto-excluded records to re-score for validation. "
            "Used with min/max sample bounds below."
        ),
    )
    batch_screen_validation_min_sample: int = Field(
        default=20,
        ge=1,
        le=200,
        description="Minimum validation sample size for batch pre-ranker exclusions.",
    )
    batch_screen_validation_max_sample: int = Field(
        default=60,
        ge=1,
        le=500,
        description="Maximum validation sample size for batch pre-ranker exclusions.",
    )
    batch_screen_concurrency: int = Field(
        default=3,
        ge=1,
        le=10,
        description=(
            "Number of batch LLM ranker calls sent concurrently. "
            "Each call scores up to batch_screen_size papers. Lower to stay within RPM limits."
        ),
    )
    pdf_retrieval_concurrency: int = Field(
        ge=1,
        le=32,
        default=20,
        description=(
            "Number of PDFs fetched concurrently during full-text retrieval (phase 3). "
            "Each fetch hits a different upstream host (Unpaywall, CORE, S2, EuropePMC) "
            "so 20 concurrent async requests are safe. "
            "Lower to 8-10 if rate-limit errors appear in the activity log."
        ),
    )
    pdf_retrieval_per_paper_timeout: int = Field(
        ge=10,
        le=300,
        default=45,
        description=(
            "Maximum wall-clock seconds allowed per paper across all retrieval tiers. "
            "Prevents a slow-responding host from holding a semaphore slot for 260+ seconds "
            "(13 tiers x 20s worst-case). Paper is marked failed-timeout and the next paper "
            "in the batch claims the semaphore slot immediately."
        ),
    )
    reviewer_batch_size: int = Field(
        default=0,
        ge=0,
        description=(
            "Papers per LLM call in the dual-reviewer phase. "
            "0 = per-paper mode (current behavior, one call per paper). "
            "10 = send 10 papers per batch call, then apply fast-path and adjudicate disagreements. "
            "Reduces dual-reviewer LLM calls by ~5x at batch_size=10 while preserving all decisions."
        ),
    )
    exclude_fast_path_requires_dual: bool = Field(
        default=False,
        description=(
            "When true, title/abstract exclude decisions never fast-path on Reviewer A alone; "
            "Reviewer B or adjudication is required for exclusion finalization."
        ),
    )


class DualReviewConfig(BaseModel):
    enabled: bool = True
    kappa_warning_threshold: float = Field(ge=0.0, le=1.0, default=0.4)
    reviewer_b_model: str = Field(
        default="",
        description=(
            "Last-resort fallback model for Reviewer B. The primary source is "
            "agents.screening_reviewer_b.model in settings.yaml. This field is "
            "only used if that agent key is absent."
        ),
    )


class GatesConfig(BaseModel):
    profile: str = "strict"
    search_volume_minimum: int = 50
    screening_minimum: int = 5
    extraction_completeness_threshold: float = 0.80
    extraction_max_empty_rate: float = 0.35
    cost_budget_max: float = 20.0
    manuscript_contract_mode: str = Field(
        default="observe",
        description=(
            "Cross-artifact manuscript contract enforcement mode: "
            "observe (log only), soft (block hard defects), strict (block all violations)."
        ),
    )


class WritingConfig(BaseModel):
    humanization: bool = True
    humanization_iterations: int = Field(ge=1, le=5, default=2)
    checkpoint_per_section: bool = True
    llm_timeout: int = 120
    writing_concurrency: int = Field(
        ge=1,
        le=10,
        default=3,
        description="Number of manuscript sections written concurrently. Default 3 balances throughput vs. RPM.",
    )
    background_sr_max_results: int = Field(
        ge=1,
        le=50,
        default=8,
        description="Maximum background systematic review citations to register.",
    )
    background_sr_query_keyword_limit: int = Field(
        ge=1,
        le=30,
        default=6,
        description="Number of research keywords used to build background SR discovery query.",
    )
    background_sr_topic_token_keyword_limit: int = Field(
        ge=1,
        le=50,
        default=10,
        description="Number of keywords used to build topic-token relevance filter for background SRs.",
    )
    background_sr_request_timeout_seconds: int = Field(
        ge=5,
        le=120,
        default=20,
        description="HTTP timeout in seconds for background SR API requests.",
    )
    abstract_trim_headroom_words: int = Field(
        ge=0,
        le=100,
        default=20,
        description=(
            "Word headroom reserved below ieee_export.max_abstract_words before deterministic trim, "
            "to absorb post-processing expansion."
        ),
    )
    abstract_trim_floor_words: int = Field(
        ge=50,
        le=500,
        default=210,
        description="Minimum abstract trim target after applying headroom.",
    )
    fulltext_nonretrieval_caution_threshold: float = Field(
        ge=0.0,
        le=1.0,
        default=0.40,
        description="Trigger threshold for cautionary abstract wording when reports not retrieved is high.",
    )
    abstract_only_caution_threshold: float = Field(
        ge=0.0,
        le=1.0,
        default=0.40,
        description="Trigger threshold for cautionary wording when too many included studies are abstract-only.",
    )
    citation_cluster_chunk_size: int = Field(
        ge=1,
        le=50,
        default=8,
        description="Maximum citekeys per bracket cluster in auto-generated coverage prose.",
    )


class RiskOfBiasConfig(BaseModel):
    rct_tool: str = "rob2"
    non_randomized_tool: str = "robins_i"
    qualitative_tool: str = "casp"


class MetaAnalysisConfig(BaseModel):
    enabled: bool = True
    heterogeneity_threshold: int = 40
    funnel_plot_minimum_studies: int = 10
    effect_measure_dichotomous: str = "risk_ratio"
    effect_measure_continuous: str = "mean_difference"


class IEEEExportConfig(BaseModel):
    enabled: bool = True
    template: str = "IEEEtran"
    bibliography_style: str = "IEEEtran"
    max_abstract_words: int = 250
    target_page_range: list[int] = Field(default_factory=lambda: [7, 10])


class CitationLineageConfig(BaseModel):
    block_export_on_unresolved: bool = True
    minimum_evidence_score: float = 0.5


class LLMRateLimitConfig(BaseModel):
    class PriceFallbackConfig(BaseModel):
        input_per_mtok: float = Field(ge=0.0)
        output_per_mtok: float = Field(ge=0.0)
        cache_read_input_multiplier: float = Field(default=0.1, ge=0.0)

    flash_rpm: int = Field(ge=1, le=1000, default=10)
    flash_lite_rpm: int = Field(ge=1, le=1000, default=15)
    pro_rpm: int = Field(ge=1, le=500, default=5)
    request_timeout_seconds: int = Field(
        ge=10,
        le=600,
        default=120,
        description=(
            "Per-request HTTP timeout in seconds for all LLM calls. "
            "Pro-tier models generating long outputs (e.g. writing sections) "
            "may need 120-180s; flash-lite can use 60s. "
            "Applies to PydanticAI ModelSettings.timeout."
        ),
    )
    price_fallback_per_mtok: dict[str, PriceFallbackConfig] = Field(
        default_factory=dict,
        description=(
            "Optional pricing fallback table for model refs missing in genai-prices. "
            "Keys are bare model refs (without provider prefix), values are per-1M token prices."
        ),
    )


class SearchConfig(BaseModel):
    """Search depth configuration.

    max_results_per_db is the global default per connector.
    per_database_limits overrides it for specific connectors, allowing
    high-yield databases (crossref, pubmed) to pull more records than
    lower-yield ones (arxiv, ieee_xplore).
    """

    max_results_per_db: int = Field(ge=1, le=10000, default=500)
    per_database_limits: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "Per-connector record limits. Keys must match connector names: "
            "openalex, pubmed, arxiv, ieee_xplore, semantic_scholar, crossref, perplexity_search."
        ),
    )
    citation_chasing_enabled: bool = Field(
        default=False,
        description=(
            "Enable PRISMA 2020 snowball forward citation chasing after inclusion decisions. "
            "When true, the citation chaser queries Semantic Scholar and OpenAlex for papers "
            "that cite included papers, adding new candidates to the screening pool."
        ),
    )
    low_recall_warning_threshold: int = Field(
        default=10,
        ge=0,
        description=(
            "Emit a WARNING log when a database connector returns fewer than this many records. "
            "0 disables the warning. Useful for detecting over-restricted search queries early."
        ),
    )
    citation_chasing_concurrency: int = Field(
        default=5,
        ge=1,
        le=20,
        description=(
            "Number of included papers chased concurrently during citation chasing. "
            "Each paper triggers 1-2 HTTP calls to Semantic Scholar and OpenAlex. "
            "Lower if rate-limit errors appear in the activity log."
        ),
    )


class ExtractionConfig(BaseModel):
    """Full-text retrieval and multi-modal extraction settings.

    Controls whether the pipeline fetches actual paper full text (vs. abstract-only)
    and whether Gemini vision is used to extract quantitative data from PDF tables.
    """

    sciencedirect_full_text: bool = Field(
        default=True,
        description=(
            "Fetch full text from the ScienceDirect Article Retrieval API "
            "(https://api.elsevier.com/content/article/doi/{doi}) using SCOPUS_API_KEY. "
            "Returns 100KB+ of content for Elsevier open-access papers. "
            "Gracefully skipped when SCOPUS_API_KEY is absent or the paper is not OA."
        ),
    )
    unpaywall_full_text: bool = Field(
        default=True,
        description=(
            "Fetch open-access PDFs via Unpaywall (https://api.unpaywall.org/v2/{doi}). "
            "Covers ~50% of recent papers. No API key required. "
            "Used as fallback when ScienceDirect returns no content."
        ),
    )
    pmc_full_text: bool = Field(
        default=True,
        description=(
            "Fetch full text from PubMed Central "
            "(https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi). "
            "Covers NIH-funded open-access papers. No API key required. "
            "Used as fallback when ScienceDirect and Unpaywall return no content."
        ),
    )
    core_full_text: bool = Field(
        default=True,
        description=(
            "Fetch full text from CORE (institutional repos, ~43M hosted). "
            "Requires CORE_API_KEY. Helps papers with no Unpaywall OA location."
        ),
    )
    europepmc_full_text: bool = Field(
        default=True,
        description=("Fetch full text from Europe PMC fullTextXML (OA subset, 6.5M articles). No API key required."),
    )
    semanticscholar_full_text: bool = Field(
        default=True,
        description=(
            "Fetch PDF from Semantic Scholar openAccessPdf URL. "
            "Optional SEMANTIC_SCHOLAR_API_KEY for higher rate limits."
        ),
    )
    arxiv_full_text: bool = Field(
        default=True,
        description=(
            "Fetch PDF from arXiv (https://arxiv.org/pdf/{id}.pdf) when paper URL "
            "is an arXiv abs link. Free; applies to papers from arXiv connector."
        ),
    )
    biorxiv_medrxiv_full_text: bool = Field(
        default=True,
        description=("Fetch PDF from bioRxiv/medRxiv when DOI starts with 10.1101/. Free; life sciences preprints."),
    )
    openalex_content_full_text: bool = Field(
        default=False,
        description=(
            "Fetch PDF from OpenAlex Content API (~60M OA works). Costs $0.01/file; 100 free/day with free key. Opt-in."
        ),
    )
    crossref_links_full_text: bool = Field(
        default=True,
        description=(
            "Try PDF URLs from Crossref works API link array (fallback). Many links are paywalled; low yield but free."
        ),
    )
    use_pdf_vision: bool = Field(
        default=True,
        description=(
            "When a PDF is available (from Unpaywall), send it to the Gemini vision model "
            "to extract quantitative outcome data from tables. Merged with text extraction "
            "results; vision takes precedence for numeric fields (effect_size, CI, p-value). "
            "Disable for offline/cost-sensitive runs."
        ),
    )
    pdf_vision_model: str = Field(
        default="",
        description="Gemini model used for PDF table vision extraction.",
    )
    full_text_min_chars: int = Field(
        default=500,
        ge=100,
        description=(
            "Minimum character count for a full-text response to be considered usable. "
            "Responses shorter than this fall through to the next retrieval tier."
        ),
    )
    extraction_concurrency: int = Field(
        ge=1,
        le=16,
        default=4,
        description="Number of papers extracted concurrently in phase 4. Each paper runs classify+extract+RoB sequentially; papers run in parallel.",
    )
    pdf_tier_timeout_seconds: int = Field(
        ge=5,
        le=60,
        default=12,
        description=(
            "Per-tier HTTP timeout (seconds) used inside fetch_full_text(). "
            "Open-access tiers (Unpaywall, CORE, S2, EuropePMC) are raced in parallel, "
            "so this timeout applies to the entire race group rather than per-request. "
            "Set lower (e.g. 8) to fail fast; set higher (e.g. 20) to trade speed for coverage."
        ),
    )


class RagConfig(BaseModel):
    """RAG retrieval configuration including embedding, chunking, HyDE and reranking settings."""

    embed_model: str = Field(
        default="",
        description="Embedding model used to embed paper chunks and queries.",
    )
    embed_dim: int = Field(
        default=768,
        ge=64,
        description=(
            "MRL output dimension requested from the embedding model. "
            "Changing this requires wiping paper_chunks_meta and re-running the embedding phase."
        ),
    )
    embed_batch_size: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Number of texts sent to the embedding API in a single batch call.",
    )
    chunk_max_words: int = Field(
        default=400,
        ge=50,
        description="Target word budget per text chunk before splitting at sentence boundaries.",
    )
    chunk_overlap_sentences: int = Field(
        default=2,
        ge=0,
        description="Number of trailing sentences from the previous chunk included at the start of the next.",
    )
    use_hyde: bool = Field(
        default=True,
        description="Use HyDE (Hypothetical Document Embeddings) for RAG section retrieval.",
    )
    hyde_model: str = Field(
        default="",
        description="Fast LLM model used to generate hypothetical document excerpts for RAG queries.",
    )
    rerank: bool = Field(
        default=True,
        description="Use cross-encoder reranking on hybrid retrieval candidates before WritingNode.",
    )
    reranker_model: str = Field(
        default="",
        description="LLM model used for listwise reranking of retrieved chunks (Gemini Flash recommended).",
    )
    candidate_k: int = Field(
        default=20,
        ge=4,
        le=100,
        description="Number of chunks retrieved before optional reranking.",
    )
    final_k: int = Field(
        default=8,
        ge=1,
        le=50,
        description="Final number of chunks injected into the writing prompt.",
    )
    min_chunks_per_section: int = Field(
        default=1,
        ge=0,
        le=50,
        description="Warn when fewer than this many chunks are retrieved for a section.",
    )
    max_empty_sections: int = Field(
        default=2,
        ge=0,
        le=20,
        description="Maximum sections allowed with empty retrieval before run-level RAG warning/failure.",
    )
    block_writing_on_rag_failure: bool = Field(
        default=False,
        description="If true, fail writing when RAG retrieval health thresholds are violated.",
    )
    embed_concurrency: int = Field(
        default=4,
        ge=1,
        le=16,
        description=(
            "Number of embedding API batches sent concurrently. "
            "Each batch is embed_batch_size texts. Lower if embedding rate-limit errors occur."
        ),
    )


class HumanInTheLoopConfig(BaseModel):
    """Human-in-the-loop review checkpoint configuration.

    When enabled=True, the workflow pauses after screening and waits for
    a human to review and approve AI screening decisions before extraction begins.
    The run status is set to "awaiting_review" and a POST to
    /api/run/{run_id}/approve-screening resumes the workflow.
    """

    enabled: bool = Field(
        default=False,
        description="Enable human review checkpoint between screening and extraction.",
    )
    poll_interval_seconds: int = Field(
        ge=1,
        le=300,
        default=5,
        description="Polling interval while waiting for approve-screening signal.",
    )
    max_wait_seconds: int = Field(
        ge=60,
        le=86400,
        default=7200,
        description="Maximum time to wait for human approval before auto-resuming.",
    )


class WebConfig(BaseModel):
    """FastAPI web server runtime configuration.

    Controls TTL eviction, event flushing, and heartbeat intervals so they can
    be tuned via config/settings.yaml without code changes.
    """

    run_ttl_seconds: int = Field(
        ge=60,
        le=86400,
        default=7200,
        description="Evict completed run records from memory after this many seconds.",
    )
    eviction_interval_seconds: int = Field(
        ge=60,
        le=86400,
        default=1800,
        description="How often (seconds) the eviction loop wakes and removes stale run records.",
    )
    event_flush_interval_seconds: int = Field(
        ge=1,
        le=300,
        default=5,
        description="How often (seconds) buffered SSE events are flushed to SQLite.",
    )
    heartbeat_interval_seconds: int = Field(
        ge=10,
        le=300,
        default=60,
        description="How often (seconds) the heartbeat updates the workflow registry.",
    )


class SettingsConfig(BaseModel):
    agents: dict[str, AgentConfig]
    screening: ScreeningConfig = Field(default_factory=ScreeningConfig)
    dual_review: DualReviewConfig = Field(default_factory=DualReviewConfig)
    gates: GatesConfig = Field(default_factory=GatesConfig)
    writing: WritingConfig = Field(default_factory=WritingConfig)
    risk_of_bias: RiskOfBiasConfig = Field(default_factory=RiskOfBiasConfig)
    meta_analysis: MetaAnalysisConfig = Field(default_factory=MetaAnalysisConfig)
    ieee_export: IEEEExportConfig = Field(default_factory=IEEEExportConfig)
    citation_lineage: CitationLineageConfig = Field(default_factory=CitationLineageConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    rag: RagConfig = Field(default_factory=RagConfig)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    llm: LLMRateLimitConfig = Field(default_factory=LLMRateLimitConfig)
    human_in_the_loop: HumanInTheLoopConfig = Field(default_factory=HumanInTheLoopConfig)
    web: WebConfig = Field(default_factory=WebConfig)
