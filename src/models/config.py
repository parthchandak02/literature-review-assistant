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
    keyword_filter_min_matches: int = Field(ge=0, default=1, description="Minimum keyword hits required to send a paper to LLM screening; 0 disables pre-filter.")
    skip_fulltext_if_no_pdf: bool = Field(default=True, description="Skip stage 2 when no real PDFs are retrieved; treats stage-1 survivors as included.")
    screening_concurrency: int = Field(ge=1, le=20, default=5, description="Number of papers screened concurrently by the LLM dual-reviewer.")
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


class DualReviewConfig(BaseModel):
    enabled: bool = True
    kappa_warning_threshold: float = Field(ge=0.0, le=1.0, default=0.4)
    reviewer_b_model: str = Field(
        default="gemini-2.0-flash",
        description=(
            "Model used for Reviewer B. Using a different model than Reviewer A "
            "enables genuine cross-model validation rather than intra-model disagreement."
        ),
    )


class GatesConfig(BaseModel):
    profile: str = "strict"
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
    llm_timeout: int = 120


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
        description=(
            "Fetch full text from Europe PMC fullTextXML (OA subset, 6.5M articles). "
            "No API key required."
        ),
    )
    semanticscholar_full_text: bool = Field(
        default=True,
        description=(
            "Fetch PDF from Semantic Scholar openAccessPdf URL. "
            "Optional SEMANTIC_SCHOLAR_API_KEY for higher rate limits."
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
        default="google-gla:gemini-2.5-flash",
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


class RagConfig(BaseModel):
    """RAG retrieval configuration including HyDE and cross-encoder reranking settings."""

    use_hyde: bool = Field(
        default=True,
        description="Use HyDE (Hypothetical Document Embeddings) for RAG section retrieval.",
    )
    hyde_model: str = Field(
        default="google-gla:gemini-2.0-flash",
        description="Fast LLM model used to generate hypothetical document excerpts for RAG queries.",
    )
    rerank: bool = Field(
        default=True,
        description="Use cross-encoder reranking on hybrid retrieval candidates before WritingNode.",
    )
    reranker_model: str = Field(
        default="google-gla:gemini-2.0-flash",
        description="LLM model used for listwise reranking of retrieved chunks (Gemini Flash recommended).",
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
    llm: LLMRateLimitConfig | None = None
    human_in_the_loop: HumanInTheLoopConfig = Field(default_factory=HumanInTheLoopConfig)
