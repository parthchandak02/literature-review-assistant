"""LLM-based review config generator.

Given a plain-English research question, uses a two-stage Gemini pipeline:

Stage 1 -- Research (WebSearchTool + WebFetchTool, plain text):
  Gemini searches the web AND fetches relevant pages to discover brand names,
  domain terminology, and other facts that may not be in its training data.
  Returns a structured research brief as plain text.

Stage 2 -- Structure (NativeOutput, no web search):
  Uses the research brief + original question to generate a validated
  _GeneratedConfig (PICO, keywords, criteria, domain, scope) as JSON, then
  serializes to YAML compatible with the frontend parseYaml() parser.

Why two stages: Gemini's Google Search grounding (WebSearchTool) cannot be
combined with built-in output schema enforcement (NativeOutput/responseSchema)
in a single call -- the Gemini API does not support function/output tools
alongside built-in tools. Splitting the calls resolves this constraint while
giving us the best of both: real-time web knowledge + validated structure.

This module is intentionally lightweight: no DB logging (pre-run, no run_id),
no rate-limiter wrapping (single calls, not part of a pipeline batch).
"""

from __future__ import annotations

import datetime
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_ai import Agent, NativeOutput, StructuredDict, WebFetchTool, WebSearchTool

from src.models import ReviewConfig

logger = logging.getLogger(__name__)

# Lightweight defaults struct: extracted from review.yaml with safe fallbacks.
# Used when full ReviewConfig validation fails (schema drift, partial YAML).
_DefaultConfigDict = dict[str, Any]

# Fallback model used only when settings.yaml cannot be loaded.
# In production the model is resolved from agents.search in settings.yaml.
_MODEL_FALLBACK = "google-gla:gemini-2.5-flash"
_TEMPERATURE = 0.3


def _resolve_model() -> str:
    """Resolve the config-generator model from settings.yaml at call time."""
    try:
        from src.config.loader import load_configs

        _, settings = load_configs(settings_path="config/settings.yaml")
        search_agent = settings.agents.get("search")
        if search_agent:
            return search_agent.model
    except Exception:
        pass
    return _MODEL_FALLBACK


# Structural defaults that are never LLM-generated (kept stable across all reviews).
_DEFAULT_DATE_START = 2010
_DEFAULT_DATE_END = datetime.datetime.now().year
_DEFAULT_DATABASES = [
    "scopus",
    "web_of_science",
    "openalex",
    "pubmed",
    "semantic_scholar",
]
_DEFAULT_SECTIONS = [
    "abstract",
    "introduction",
    "methods",
    "results",
    "discussion",
    "conclusion",
]


def _extract_defaults_from_review(review: ReviewConfig) -> _DefaultConfigDict:
    """Convert ReviewConfig to a dict for safe, schema-agnostic access."""
    return {
        "target_databases": list(review.target_databases),
        "target_sections": list(review.target_sections),
        "date_range_start": review.date_range_start,
        "date_range_end": review.date_range_end,
        "living_review": review.living_review,
        "last_search_date": review.last_search_date,
        "search_limitation": review.search_limitation,
        "protocol": {
            "registered": review.protocol.registered,
            "registry": review.protocol.registry,
            "registration_number": review.protocol.registration_number,
            "url": review.protocol.url,
        },
        "funding": {
            "source": review.funding.source,
            "grant_number": review.funding.grant_number,
            "funder": review.funding.funder,
        },
        "conflicts_of_interest": review.conflicts_of_interest,
        "search_overrides": dict(review.search_overrides) if review.search_overrides else None,
    }


def _extract_defaults_from_raw(raw: dict[str, Any]) -> _DefaultConfigDict:
    """Extract structural fields from raw YAML dict. Tolerates missing/odd types."""

    def _list(val: Any, default: list[str]) -> list[str]:
        if not isinstance(val, list):
            return default
        out = [str(x) for x in val if x]
        return out if out else default

    def _int(val: Any, default: int) -> int:
        if isinstance(val, int):
            return val
        try:
            return int(val) if val is not None else default
        except (TypeError, ValueError):
            return default

    def _str(val: Any, default: str = "") -> str:
        return str(val).strip() if val is not None and str(val).strip() else default

    def _dict(val: Any) -> dict[str, str] | None:
        if not isinstance(val, dict):
            return None
        return {str(k): str(v) for k, v in val.items() if v}

    protocol_raw = raw.get("protocol") or {}
    funding_raw = raw.get("funding") or {}

    return {
        "target_databases": _list(raw.get("target_databases"), _DEFAULT_DATABASES),
        "target_sections": _list(raw.get("target_sections"), _DEFAULT_SECTIONS),
        "date_range_start": _int(raw.get("date_range_start"), _DEFAULT_DATE_START),
        "date_range_end": _int(raw.get("date_range_end"), _DEFAULT_DATE_END),
        "living_review": bool(raw.get("living_review", False)),
        "last_search_date": raw.get("last_search_date") if raw.get("last_search_date") else None,
        "search_limitation": _str(raw.get("search_limitation")) or None,
        "protocol": {
            "registered": bool(protocol_raw.get("registered", False)),
            "registry": _str(protocol_raw.get("registry"), "PROSPERO"),
            "registration_number": _str(protocol_raw.get("registration_number")),
            "url": _str(protocol_raw.get("url")),
        },
        "funding": {
            "source": _str(funding_raw.get("source"), "No funding received"),
            "grant_number": _str(funding_raw.get("grant_number")),
            "funder": _str(funding_raw.get("funder")),
        },
        "conflicts_of_interest": _str(
            raw.get("conflicts_of_interest"), "The authors declare no conflicts of interest."
        ),
        "search_overrides": _dict(raw.get("search_overrides")),
    }


def _load_default_config(review_path: str = "config/review.yaml") -> _DefaultConfigDict | None:
    """Load config/review.yaml as source of truth for structural settings.

    Tries full ReviewConfig validation first. If that fails (schema drift,
    new required fields, etc.), falls back to raw YAML extraction with
    safe defaults. Returns None only if the file does not exist.
    """
    path = Path(review_path)
    if not path.exists():
        return None

    # Path 1: full validation
    try:
        from src.config.loader import load_configs

        review, _ = load_configs(review_path=review_path, settings_path="config/settings.yaml")
        return _extract_defaults_from_review(review)
    except Exception as exc:
        logger.debug("Full config validation failed, trying raw YAML: %s", exc)

    # Path 2: raw YAML extraction (schema-agnostic)
    try:
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        if not isinstance(raw, dict):
            logger.warning("review.yaml root is not a dict, using hardcoded defaults")
            return None
        return _extract_defaults_from_raw(raw)
    except Exception as exc:
        logger.warning("Could not load default config from %s: %s", review_path, exc)
        return None


# ---------------------------------------------------------------------------
# Structured output schema
# ---------------------------------------------------------------------------


class _Pico(BaseModel):
    population: str = Field(description="Who or what is being studied")
    intervention: str = Field(description="The intervention, exposure, or technology being evaluated")
    comparison: str = Field(description="What the intervention is compared against (controls, baselines, alternatives)")
    outcome: str = Field(description="Outcomes measured (efficacy, safety, efficiency, cost, etc.)")


class _SearchOverrides(BaseModel):
    pubmed: str | None = Field(
        default=None,
        description=(
            "PubMed-optimized query using MeSH terms and [Title/Abstract] field codes. "
            "Use the actual MeSH terms and keywords specific to this review's topic. "
            "Pattern: (MeSHTerm[MeSH Terms] OR keyword[Title/Abstract] OR ...) AND "
            "(setting_term[Title/Abstract] OR outcome_term[Title/Abstract] OR ...) "
            "CRITICAL for the second AND group: each term must be a SINGLE ROOT WORD -- "
            "not a multi-word phrase. A single broad word returns 10-50x more records than "
            "an exact two-word phrase. Example: 'school'[Title/Abstract] retrieves ~500+ "
            "records; 'school setting'[Title/Abstract] retrieves ~20 records (25x fewer). "
            "Use single root words that describe the relevant setting or outcome for this topic. "
            "Do NOT use exact multi-word phrases as [Title/Abstract] field terms -- they require "
            "both words to appear adjacent in title/abstract and drastically cut recall. "
            "Also avoid overly narrow secondary MeSH terms in the AND group unless they are "
            "the primary topic -- many relevant papers are not indexed under narrow MeSH headings."
        ),
    )
    scopus: str | None = Field(
        default=None,
        description=(
            "Scopus TITLE-ABS-KEY query. Use two AND-joined TITLE-ABS-KEY clauses with "
            "quoted keyword groups (max 8 keywords each) plus PUBYEAR filter. "
            "Clause 1: core intervention/technology terms. Clause 2: outcome/setting terms. "
            'Pattern: TITLE-ABS-KEY("term1" OR "term2") AND TITLE-ABS-KEY("term3" OR "term4") '
            "AND PUBYEAR > YYYY AND PUBYEAR < YYYY"
        ),
    )
    web_of_science: str | None = Field(
        default=None,
        description=(
            "Web of Science Starter API query. Each keyword needs its own TS= prefix. "
            "Group terms in parenthesized OR blocks, join groups with AND. Year: PY=YYYY-YYYY. "
            'CORRECT: (TS="term1" OR TS="term2") AND (TS="term3" OR TS="term4") AND PY=2010-2026. '
            'WRONG (causes 512 error): TS=("term1" OR "term2").'
        ),
    )
    ieee_xplore: str | None = Field(
        default=None,
        description=(
            "IEEE Xplore query using parenthesized OR groups joined with AND. "
            "Use short quoted keyword phrases -- not full sentences, not field codes. "
            'Pattern: ("core term1" OR "core term2" OR "synonym") AND '
            '("outcome term1" OR "outcome term2" OR "setting term")'
        ),
    )
    semantic_scholar: str | None = Field(
        default=None,
        description=(
            "Semantic Scholar query: 5-8 space-separated keywords specific to this review -- "
            "no quotes, no boolean operators, no long sentences. "
            "Use natural academic language as it appears in paper abstracts, not compound tech-speak. "
            "Structure: [key_intervention] [condition_or_setting] [outcome] [process_term] "
            "Good (online learning review): 'online learning student engagement outcomes implementation' "
            "Good (renewable energy review): 'solar energy adoption barriers policy efficiency' "
            "Bad (any topic): stacked compound nouns that read like a product spec, not a paper abstract. "
            "Include one specific technology/intervention term, one setting term, one outcome term."
        ),
    )
    openalex: str | None = Field(
        default=None,
        description=(
            "OpenAlex full-text relevance search query: 5-8 space-separated keywords. "
            "NO quotes, NO boolean operators. Same natural-language guidance as semantic_scholar. "
            "CRITICAL: always pair generic outcome words ('outcomes', 'efficacy', 'barriers') with "
            "a specific domain term from this review's topic -- alone they match unrelated industries. "
            "Example A (educational technology review): 'educational technology student learning outcomes effectiveness' "
            "Example B (autonomous vehicles review): 'autonomous vehicle safety performance urban deployment' "
            "Bad (any topic): generic adjective clusters without a domain anchor ('automated advanced system outcomes')."
        ),
    )
    clinicaltrials_gov: str | None = Field(
        default=None,
        description=(
            "ClinicalTrials.gov plain-text search query. Use OR-joined quoted keyword phrases "
            "specific to the intervention and condition. No field codes, no MeSH terms. "
            "Include specific technology names, brand names, and condition/setting terms. "
            'Pattern: "technology term" OR "brand name" OR "condition term" OR "setting term". '
            "Keep to 8-12 terms. Do NOT include full PICO descriptions as search terms."
        ),
    )


class _GeneratedConfig(BaseModel):
    research_question: str = Field(description="Refined, precise systematic review research question")
    review_type: str = Field(description="Always 'systematic'")
    pico: _Pico
    keywords: list[str] = Field(
        description="18-24 specific search keywords including intervention synonyms, abbreviations, commercial brand names, population/setting terms, outcome terms, and implementation terms",
        min_length=15,
        max_length=28,
    )
    domain: str = Field(description="One-line domain description (topic area and setting)")
    scope: str = Field(
        description="2-4 sentence scope statement: what is covered, what populations and settings, what specific systems or technologies, what outcomes"
    )
    inclusion_criteria: list[str] = Field(
        description="6-8 specific inclusion criteria as full sentences",
        min_length=4,
        max_length=10,
    )
    exclusion_criteria: list[str] = Field(
        description="5-7 specific exclusion criteria as full sentences",
        min_length=3,
        max_length=8,
    )
    search_overrides: _SearchOverrides | None = Field(
        default=None,
        description=(
            "Database-specific search queries optimized for each database's query syntax. "
            "Generate all six fields (pubmed, scopus, web_of_science, ieee_xplore, semantic_scholar, openalex) "
            "using the keywords and PICO above."
        ),
    )


# ---------------------------------------------------------------------------
# YAML serializer (mirrors frontend buildYaml() exactly)
# ---------------------------------------------------------------------------


def _yaml_str(s: str) -> str:
    """Wrap a string value in double quotes with escaping."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _build_yaml(cfg: _GeneratedConfig, defaults: _DefaultConfigDict | None = None) -> str:
    """Build YAML from LLM output, using defaults for structural settings when provided."""
    if defaults is not None:
        date_start = defaults.get("date_range_start", _DEFAULT_DATE_START)
        date_end = defaults.get("date_range_end", _DEFAULT_DATE_END)
        databases = defaults.get("target_databases") or _DEFAULT_DATABASES
        sections = defaults.get("target_sections") or _DEFAULT_SECTIONS
    else:
        date_start = _DEFAULT_DATE_START
        date_end = _DEFAULT_DATE_END
        databases = _DEFAULT_DATABASES
        sections = _DEFAULT_SECTIONS

    # Ensure lists are non-empty (defensive)
    if not databases:
        databases = _DEFAULT_DATABASES
    if not sections:
        sections = _DEFAULT_SECTIONS

    lines: list[str] = []
    lines.append(f"research_question: {_yaml_str(cfg.research_question)}")
    lines.append(f"review_type: {_yaml_str(cfg.review_type)}")
    lines.append("")

    if defaults is not None:
        lines.append("# Living review settings (optional)")
        lines.append("# Set living_review: true to enable incremental updates.")
        lines.append("# last_search_date is updated automatically after each run.")
        lines.append(f"living_review: {str(defaults.get('living_review', False)).lower()}")
        last_date = defaults.get("last_search_date")
        lines.append(f"last_search_date: {last_date!r}" if last_date else "last_search_date: null")
        lines.append("")

    lines.append("pico:")
    lines.append(f"  population: {_yaml_str(cfg.pico.population)}")
    lines.append(f"  intervention: {_yaml_str(cfg.pico.intervention)}")
    lines.append(f"  comparison: {_yaml_str(cfg.pico.comparison)}")
    lines.append(f"  outcome: {_yaml_str(cfg.pico.outcome)}")
    lines.append("")
    lines.append("keywords:")
    for kw in cfg.keywords:
        lines.append(f"  - {_yaml_str(kw)}")
    lines.append("")
    lines.append(f"domain: {_yaml_str(cfg.domain)}")
    lines.append(f"scope: {_yaml_str(cfg.scope)}")
    lines.append("")
    lines.append("inclusion_criteria:")
    for c in cfg.inclusion_criteria:
        lines.append(f"  - {_yaml_str(c)}")
    lines.append("")
    lines.append("exclusion_criteria:")
    for c in cfg.exclusion_criteria:
        lines.append(f"  - {_yaml_str(c)}")
    lines.append("")
    lines.append(f"date_range_start: {date_start}")
    lines.append(f"date_range_end: {date_end}")
    lines.append("")

    search_limitation = defaults.get("search_limitation") if defaults else None
    if search_limitation:
        lines.append("# Research limitation: institutional access, etc.")
        lines.append(f"search_limitation: {_yaml_str(search_limitation)}")
        lines.append("")

    lines.append("target_databases:")
    for db in databases:
        lines.append(f"  - {db}")
    lines.append("")
    lines.append("target_sections:")
    for s in sections:
        lines.append(f"  - {s}")
    lines.append("")

    if defaults is not None:
        protocol = defaults.get("protocol") or {}
        funding = defaults.get("funding") or {}
        lines.append("protocol:")
        lines.append(f"  registered: {str(protocol.get('registered', False)).lower()}")
        lines.append(f"  registry: {_yaml_str(protocol.get('registry', 'PROSPERO'))}")
        lines.append(f"  registration_number: {_yaml_str(protocol.get('registration_number', ''))}")
        lines.append(f"  url: {_yaml_str(protocol.get('url', ''))}")
        lines.append("")
        lines.append("funding:")
        lines.append(f"  source: {_yaml_str(funding.get('source', 'No funding received'))}")
        lines.append(f"  grant_number: {_yaml_str(funding.get('grant_number', ''))}")
        lines.append(f"  funder: {_yaml_str(funding.get('funder', ''))}")
        lines.append("")
        lines.append(
            f"conflicts_of_interest: {_yaml_str(defaults.get('conflicts_of_interest', 'The authors declare no conflicts of interest.'))}"
        )
        # Merge search_overrides: LLM-generated wins, config/review.yaml fills missing keys.
        llm_overrides: dict[str, str] = {}
        if cfg.search_overrides:
            for db_name in (
                "pubmed",
                "scopus",
                "web_of_science",
                "ieee_xplore",
                "semantic_scholar",
                "openalex",
                "clinicaltrials_gov",
            ):
                val = getattr(cfg.search_overrides, db_name, None)
                if val and isinstance(val, str):
                    llm_overrides[db_name] = val
        default_overrides: dict[str, str] = {}
        if defaults:
            raw_default = defaults.get("search_overrides") or {}
            if isinstance(raw_default, dict):
                for k, v in raw_default.items():
                    if isinstance(v, str) and k not in llm_overrides:
                        default_overrides[k] = v
        merged_overrides = {**default_overrides, **llm_overrides}
        if merged_overrides:
            lines.append("")
            lines.append("# Optional: override auto-generated queries per database. Omit a database to use default.")
            lines.append("search_overrides:")
            for key, val in merged_overrides.items():
                lines.append(f"  {key}: {_yaml_str(val)}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Stage 1 -- Research prompt (WebSearchTool + WebFetchTool, plain text output)
# ---------------------------------------------------------------------------

_RESEARCH_PROMPT = (
    "You are helping set up a systematic literature review. Search the web to "
    "research the following topic thoroughly, then return a concise research brief.\n\n"
    "Topic: {research_question}\n\n"
    "Search for and report back:\n"
    "1. The main technology, system, or intervention -- all synonyms, abbreviations,\n"
    "   and alternate names used in the academic literature.\n"
    "2. Specific commercial products and vendor brand names in this space that appear\n"
    "   in published studies (e.g. for an educational technology review: 'Coursera', 'Canvas LMS',\n"
    "   'Duolingo'; for an automation review: 'RPA', 'UiPath', 'Blue Prism'). Include as many as\n"
    "   you can find. These are critical for database search coverage.\n"
    "3. The typical population or setting studied and any relevant sub-settings.\n"
    "4. Key quantitative outcome measures and metrics used to evaluate this intervention\n"
    "   (e.g. for an engineering review: 'accuracy', 'throughput', 'error rate', 'latency';\n"
    "   for a social science review: 'mean score improvement', 'effect size', 'adherence rate').\n"
    "5. Common implementation or adoption challenges and workflow terms.\n"
    "6. Any adjacent or overlapping technologies that should be distinguished from the\n"
    "   main intervention (so they can be excluded from the review).\n\n"
    "Format as a concise bullet-point brief. Be specific. Include real brand names,\n"
    "real pathogen names, real metric names. Do not generalize."
)

# ---------------------------------------------------------------------------
# Stage 2 -- Structuring prompt (NativeOutput, no web search)
# ---------------------------------------------------------------------------

_STRUCTURE_PROMPT = (
    "You are an expert systematic review methodologist. Using the research brief\n"
    "below, generate a complete, publication-quality systematic review configuration.\n\n"
    "Original research question:\n"
    "{research_question}\n\n"
    "Research brief (from web search):\n"
    "{research_brief}\n\n"
    "Instructions:\n"
    "- Refine the research question into a precise, well-formed systematic review\n"
    "  research question that follows PICO structure. Keep it close to the user's\n"
    "  intent but make it specific and academically precise.\n"
    "- Generate all PICO components: population (who/what is studied), intervention\n"
    "  (technology/treatment/system being evaluated), comparison (controls, baselines,\n"
    "  alternatives, or pre-implementation state), outcome (all relevant measurable\n"
    "  outcomes).\n"
    "- Generate 18-24 specific search keywords. Draw directly from the research\n"
    "  brief above. Cover ALL of:\n"
    "  (a) the core intervention technology and its synonyms and abbreviations from\n"
    "      the research brief,\n"
    "  (b) the specific commercial brand names and product lines found in the\n"
    "      research brief -- these MUST be included verbatim,\n"
    "  (c) the population, setting, and context keywords from the research brief,\n"
    "  (d) the specific outcome measure terms and measurable targets found in the\n"
    "      research brief (e.g. exact pathogen names, metric names),\n"
    "  (e) implementation-related terms (barriers, facilitators, adoption, workflow).\n"
    "- Generate 6-8 inclusion criteria as complete, specific sentences covering:\n"
    "  study type, setting, intervention specificity, outcome reporting, language, and\n"
    "  publication type.\n"
    "  IMPORTANT -- recall vs. precision balance: if the research question targets a\n"
    "  narrow or niche setting, broaden the setting criterion to capture related\n"
    "  literature that addresses the same intervention and outcomes in adjacent settings.\n"
    "  Use exclusion criteria to filter out clearly irrelevant contexts rather than\n"
    "  restricting inclusion to a single institution type or sub-population.\n"
    "  A systematic review with zero included studies is less useful than one with a\n"
    "  broader but well-bounded scope.\n"
    "- Generate 5-7 exclusion criteria as complete, specific sentences. Include\n"
    "  adjacent technologies identified in the research brief that should be excluded.\n"
    "- Generate a one-line domain description and a 2-4 sentence scope statement.\n"
    "- Set review_type to exactly 'systematic'.\n"
    "- Generate search_overrides with database-optimized queries for ALL seven databases\n"
    "  (pubmed, scopus, web_of_science, ieee_xplore, semantic_scholar, openalex,\n"
    "  clinicaltrials_gov). Use the actual keywords and terms from this review's topic --\n"
    "  do NOT use generic placeholder keywords. Tailor every query to the specific\n"
    "  intervention, population, and outcomes identified in the research brief above.\n"
    "  * pubmed: Use MeSH terms where available plus [Title/Abstract] field codes.\n"
    "    Pattern: (MeSHTerm[MeSH Terms] OR keyword[Title/Abstract] OR ...) AND\n"
    "    (setting_term[Title/Abstract] OR outcome_term[Title/Abstract] OR ...)\n"
    "    CRITICAL for the second AND group: every term must be a SINGLE ROOT WORD.\n"
    "    A single broad word captures 10-50x more records than a two-word exact phrase.\n"
    "    Example: 'school'[Title/Abstract] retrieves ~500 records;\n"
    "    'school setting'[Title/Abstract] retrieves ~20 records (25x fewer).\n"
    "    Use single root words that describe settings or outcomes for this specific topic.\n"
    "    Do NOT use multi-word exact phrases in [Title/Abstract] field codes -- they require\n"
    "    both words to appear adjacent in title/abstract and drastically cut recall.\n"
    "    Also avoid narrow secondary MeSH headings in the AND group unless they ARE the\n"
    "    primary topic -- many relevant papers are not indexed under specific narrow MeSH terms.\n"
    "  * scopus: Use TITLE-ABS-KEY field code with two AND-joined clauses of quoted keywords.\n"
    "    Clause 1: core intervention terms (up to 8). Clause 2: outcome/setting terms (up to 8).\n"
    "    Add: AND PUBYEAR > YYYY AND PUBYEAR < YYYY using the date range.\n"
    '    Pattern: TITLE-ABS-KEY("kw1" OR "kw2") AND TITLE-ABS-KEY("kw3" OR "kw4")\n'
    "    AND PUBYEAR > 2009 AND PUBYEAR < 2027\n"
    "  * web_of_science: Each keyword needs its own TS= prefix. Group in parenthesized OR\n"
    "    blocks joined with AND. Use PY=YYYY-YYYY (no parentheses around year range).\n"
    '    CORRECT: (TS="kw1" OR TS="kw2") AND (TS="kw3" OR TS="kw4") AND PY=2010-2026\n'
    '    WRONG (causes 512 server error): TS=("kw1" OR "kw2")\n'
    "  * ieee_xplore: Two OR-groups joined with AND, using parentheses (not field codes).\n"
    '    Pattern: ("kw1" OR "kw2" OR "kw3") AND ("kw4" OR "kw5" OR "kw6")\n'
    "  * semantic_scholar: 5-8 space-separated keywords ONLY. No quotes, no boolean operators.\n"
    "    Use natural academic language as it appears in paper abstracts, not compound tech-speak.\n"
    "    Structure: [key_intervention] [condition_or_setting] [outcome] [process_term]\n"
    "    Good (online learning review): 'online learning student engagement outcomes implementation'\n"
    "    Good (renewable energy review): 'solar energy adoption barriers policy efficiency'\n"
    "    Bad (any topic): stacked compound nouns that read like a product spec, not a paper abstract.\n"
    "    Include one specific technology/intervention term, one setting term, one outcome term.\n"
    "  * openalex: 5-8 space-separated keywords ONLY. No quotes, no boolean operators.\n"
    "    Same natural-language guidance as semantic_scholar above.\n"
    "    CRITICAL: always pair generic outcome words with a specific domain term from this topic.\n"
    "    Generic words like 'efficiency', 'accuracy', 'barriers' alone match unrelated industries.\n"
    "    Good (educational technology review): 'educational technology student learning outcomes effectiveness'\n"
    "    Good (autonomous vehicles review): 'autonomous vehicle safety performance urban deployment'\n"
    "    Bad (any topic): generic adjectives and nouns without a domain anchor.\n"
    "  * clinicaltrials_gov: OR-joined quoted keyword phrases for this intervention/condition.\n"
    "    Plain text only -- no MeSH terms, no field codes. Include technology names, brand names,\n"
    "    and condition/setting terms. 8-12 terms maximum.\n"
    '    Pattern: "technology term" OR "brand name" OR "condition term"\n'
    "    Do NOT include full PICO descriptions as search terms.\n"
    "  CRITICAL for all databases: Use only short quoted keyword phrases -- NEVER full\n"
    "  sentences or PICO descriptions as search terms. Full PICO strings never appear\n"
    "  verbatim in papers and will always return zero results.\n\n"
    "Return the response as a JSON object matching the schema exactly. All text fields\n"
    "must be in English. Do not truncate or omit any field."
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def generate_config_yaml(
    research_question: str,
    progress_cb: Callable[[str], None] | None = None,
) -> str:
    """Generate a complete review config YAML from a research question.

    Two-stage pipeline:
    - Stage 1: Gemini + WebSearchTool + WebFetchTool performs a real web search
      and fetches pages to discover brand names, metrics, and domain terminology.
    - Stage 2: Gemini + NativeOutput structures the research brief into a
      validated _GeneratedConfig, then serializes it to YAML.

    progress_cb is called with a step key at each stage transition:
      "web_research" -> "web_research_done" -> "structuring" -> "finalizing"

    Raises RuntimeError on LLM or validation failure.
    """

    def emit(step: str) -> None:
        if progress_cb:
            try:
                progress_cb(step)
            except Exception:
                pass

    rq = research_question.strip()

    # ------------------------------------------------------------------
    # Stage 1: web-grounded research brief
    # ------------------------------------------------------------------
    emit("web_research")
    _model = _resolve_model()
    research_prompt = _RESEARCH_PROMPT.format(research_question=rq)
    research_agent: Agent[None, str] = Agent(
        _model,
        output_type=str,
        builtin_tools=[WebSearchTool(), WebFetchTool()],
    )
    try:
        research_result = await research_agent.run(research_prompt)
        research_brief = research_result.output
        logger.info("Config gen Stage 1 complete: brief length=%d chars", len(research_brief))
    except Exception as exc:
        logger.warning("Config gen Stage 1 (web search+fetch) failed, falling back to model knowledge: %s", exc)
        # Graceful degradation: skip the research brief, rely on model knowledge.
        research_brief = "(Web search unavailable -- rely on training knowledge only.)"

    emit("web_research_done")

    # ------------------------------------------------------------------
    # Stage 2: structured output from research brief
    # ------------------------------------------------------------------
    emit("structuring")
    structure_prompt = _STRUCTURE_PROMPT.format(
        research_question=rq,
        research_brief=research_brief,
    )
    schema = _GeneratedConfig.model_json_schema()
    output_type = NativeOutput(StructuredDict(schema))
    structure_agent: Agent = Agent(_model, output_type=output_type)  # type: ignore[arg-type]

    try:
        structure_result = await structure_agent.run(
            structure_prompt,
            model_settings={"temperature": _TEMPERATURE},
        )
        output = structure_result.output
        result_json = json.dumps(output) if isinstance(output, dict) else str(output)
    except Exception as exc:
        logger.error("Config gen Stage 2 (structure) failed: %s", exc)
        raise RuntimeError(f"LLM structuring failed: {exc}") from exc

    emit("finalizing")

    try:
        parsed = _GeneratedConfig.model_validate_json(result_json)
    except Exception as exc:
        logger.error("Config gen response failed validation: %s\nRaw: %s", exc, result_json[:500])
        try:
            raw_dict = json.loads(result_json)
            parsed = _GeneratedConfig.model_validate(raw_dict)
        except Exception:
            raise RuntimeError(f"Generated config failed schema validation: {exc}") from exc

    parsed = parsed.model_copy(update={"review_type": "systematic"})
    defaults = _load_default_config()
    return _build_yaml(parsed, defaults)
