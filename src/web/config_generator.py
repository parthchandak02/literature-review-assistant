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
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_ai import Agent, NativeOutput, StructuredDict, WebFetchTool, WebSearchTool

from src.models import DomainExpertConfig, ReviewConfig

logger = logging.getLogger(__name__)

# Lightweight defaults struct: extracted from review.yaml with safe fallbacks.
# Used when full ReviewConfig validation fails (schema drift, partial YAML).
_DefaultConfigDict = dict[str, Any]

_TEMPERATURE = 0.3


def _resolve_model() -> str:
    """Resolve the config-generator model from settings.yaml at call time."""
    try:
        from src.config.loader import load_configs

        _, settings = load_configs(settings_path="config/settings.yaml")
        agent = settings.agents.get("config_generation") or settings.agents.get("search")
        if agent:
            return agent.model
    except Exception:
        pass
    from src.llm.model_fallback import get_fallback_model

    return get_fallback_model("lite")


# Structural defaults that are never LLM-generated (kept stable across all reviews).
_DEFAULT_DATE_START = 2010
_DEFAULT_DATE_END = datetime.datetime.now().year
_DEFAULT_DATABASES = [
    "scopus",
    "web_of_science",
    "openalex",
    "pubmed",
    "semantic_scholar",
    "ieee_xplore",
    "clinicaltrials_gov",
]
_NON_BIOMED_DEFAULT_DATABASES = [
    "scopus",
    "web_of_science",
    "openalex",
    "semantic_scholar",
    "ieee_xplore",
]
_AMBIGUOUS_DEFAULT_DATABASES = [
    "scopus",
    "web_of_science",
    "openalex",
    "semantic_scholar",
    "ieee_xplore",
    "pubmed",
]
_DEFAULT_SECTIONS = [
    "abstract",
    "introduction",
    "methods",
    "results",
    "discussion",
    "conclusion",
]

_GENERIC_NOISE_TERMS = {
    "automation",
    "automations",
    "efficiency",
    "outcomes",
    "intervention",
    "implementation",
    "effectiveness",
    "quality",
    "performance",
    "analysis",
    "evaluation",
    "approach",
    "system",
    "systems",
    "tool",
    "tools",
    "workflow",
    "workflows",
    "technology",
    "technologies",
    "methods",
}

_MIN_KEYWORD_TOKEN_LEN = 2
_MAX_BRAND_KEYWORD_RATIO = 0.35
_MAX_BRAND_KEYWORD_ABS = 8

_SUPPORTED_DATABASES = [
    "openalex",
    "pubmed",
    "semantic_scholar",
    "scopus",
    "web_of_science",
    "ieee_xplore",
    "clinicaltrials_gov",
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
        "domain_expert": review.domain_expert.model_dump(mode="python"),
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
        "domain_expert": raw.get("domain_expert") if isinstance(raw.get("domain_expert"), dict) else None,
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


class _GeneratedDomainExpert(BaseModel):
    expert_role: str = ""
    domain_summary: str = ""
    canonical_terms: list[str] = Field(default_factory=list)
    related_terms: list[str] = Field(default_factory=list)
    excluded_terms: list[str] = Field(default_factory=list)
    methodological_focus: list[str] = Field(default_factory=list)
    outcome_focus: list[str] = Field(default_factory=list)


class _GeneratedConfig(BaseModel):
    research_question: str = Field(description="Refined, precise systematic review research question")
    review_type: str = Field(description="Always 'systematic'")
    pico: _Pico
    keywords: list[str] = Field(
        description="18-24 specific search keywords including intervention synonyms, abbreviations, population/setting terms, outcome terms, and implementation terms; brands/acronyms may appear but must remain supplemental; each keyword must include at least one token with length >= 2",
        min_length=15,
        max_length=28,
    )
    domain: str = Field(description="One-line domain description (topic area and setting)")
    scope: str = Field(
        description="2-4 sentence scope statement: what is covered, what populations and settings, what specific systems or technologies, what outcomes"
    )
    domain_expert: _GeneratedDomainExpert = Field(
        default_factory=_GeneratedDomainExpert,
        description=(
            "Structured domain brief with preferred terminology, adjacent synonyms, "
            "outcome focus, and methodology expectations for expertized downstream prompts."
        ),
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


_BIOMEDICAL_HINTS = {
    "clinical",
    "medicine",
    "medical",
    "medication",
    "patient",
    "hospital",
    "nursing",
    "oncology",
    "cardiology",
    "psychiatry",
    "diagnosis",
    "therapy",
    "treatment",
    "public health",
    "healthcare",
    "pharmac",
    "disease",
    "trial",
    "biomedical",
    "elderly",
}

_GENERIC_HINTS = {
    "software",
    "developer",
    "education",
    "students",
    "manufacturing",
    "supply chain",
    "finance",
    "retail",
    "logistics",
    "marketing",
    "productivity",
    "agriculture",
    "transportation",
    "engineering",
    "usability",
    "prototype",
    "prototyping",
    "human factors",
    "user experience",
    "ux",
    "interface",
    "dashboard",
    "workflow design",
}


@dataclass
class _DomainRoute:
    domain: str  # biomedical | generic | ambiguous
    confidence: float
    matched_biomedical_terms: list[str]
    matched_generic_terms: list[str]
    policy: str


def _is_biomedical_topic(cfg: _GeneratedConfig) -> bool:
    """Heuristic detector used to keep non-medical defaults neutral."""
    text = " ".join(
        [
            cfg.research_question,
            cfg.domain,
            cfg.scope,
            cfg.pico.population,
            cfg.pico.intervention,
            cfg.pico.outcome,
        ]
    ).lower()
    return any(token in text for token in _BIOMEDICAL_HINTS)


def _match_terms(text: str, terms: set[str]) -> list[str]:
    matched: list[str] = []
    for term in terms:
        if re.search(rf"\b{re.escape(term)}\b", text):
            matched.append(term)
    return sorted(matched)


def _route_topic_with_confidence(cfg: _GeneratedConfig) -> _DomainRoute:
    """Route topic domain with confidence and explicit fallback policy."""
    text = " ".join(
        [
            cfg.research_question,
            cfg.domain,
            cfg.scope,
            cfg.pico.population,
            cfg.pico.intervention,
            cfg.pico.outcome,
        ]
    ).lower()
    matched_bio = _match_terms(text, _BIOMEDICAL_HINTS)
    matched_generic = _match_terms(text, _GENERIC_HINTS)

    bio_score = float(len(matched_bio))
    generic_score = float(len(matched_generic))
    total_signal = max(1.0, bio_score + generic_score)

    if bio_score >= generic_score and bio_score >= 2.5:
        confidence = round(bio_score / total_signal, 3)
        if confidence >= 0.67:
            return _DomainRoute(
                domain="biomedical",
                confidence=confidence,
                matched_biomedical_terms=matched_bio,
                matched_generic_terms=matched_generic,
                policy="high_confidence_biomedical",
            )
    if generic_score > bio_score and generic_score >= 2.0:
        confidence = round(generic_score / total_signal, 3)
        if confidence >= 0.6:
            return _DomainRoute(
                domain="generic",
                confidence=confidence,
                matched_biomedical_terms=matched_bio,
                matched_generic_terms=matched_generic,
                policy="high_confidence_generic",
            )

    confidence = round(abs(bio_score - generic_score) / total_signal, 3)
    return _DomainRoute(
        domain="ambiguous",
        confidence=confidence,
        matched_biomedical_terms=matched_bio,
        matched_generic_terms=matched_generic,
        policy="low_confidence_fallback",
    )


def _resolve_target_databases(
    cfg: _GeneratedConfig,
    defaults: _DefaultConfigDict | None = None,
) -> tuple[list[str], _DomainRoute]:
    """Apply confidence-routed domain policy for target databases."""
    configured = list((defaults or {}).get("target_databases") or [])
    known_configured = [db for db in configured if db in _SUPPORTED_DATABASES]
    databases = list(dict.fromkeys(known_configured + _SUPPORTED_DATABASES))

    route = _route_topic_with_confidence(cfg)
    if route.policy == "high_confidence_biomedical":
        selected = [db for db in databases if db in _DEFAULT_DATABASES]
        for must_have in ("pubmed",):
            if must_have not in selected:
                selected.append(must_have)
    elif route.policy == "high_confidence_generic":
        selected = [db for db in databases if db not in {"pubmed", "clinicaltrials_gov"}]
        if not selected:
            selected = list(_NON_BIOMED_DEFAULT_DATABASES)
    else:
        # Low-confidence fallback keeps broad discovery but avoids niche clinical trials.
        selected = [db for db in databases if db != "clinicaltrials_gov"]
        if not selected:
            selected = list(_AMBIGUOUS_DEFAULT_DATABASES)

    return list(dict.fromkeys(selected)), route


def _build_yaml(
    cfg: _GeneratedConfig,
    defaults: _DefaultConfigDict | None = None,
    resolved_databases: list[str] | None = None,
) -> str:
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
    if resolved_databases is not None:
        databases = list(resolved_databases)
    else:
        databases, _ = _resolve_target_databases(cfg, defaults)
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
    if defaults is not None and isinstance(defaults.get("domain_expert"), dict):
        merged_domain_expert = DomainExpertConfig.model_validate(
            {
                **defaults.get("domain_expert", {}),
                **cfg.domain_expert.model_dump(mode="python"),
            }
        )
    else:
        merged_domain_expert = DomainExpertConfig.model_validate(cfg.domain_expert.model_dump(mode="python"))
    if not merged_domain_expert.domain_summary:
        merged_domain_expert.domain_summary = cfg.scope or cfg.domain
    if not merged_domain_expert.expert_role:
        merged_domain_expert.expert_role = f"Systematic review expert for {cfg.domain}"
    if not merged_domain_expert.canonical_terms:
        merged_domain_expert.canonical_terms = list(cfg.keywords[:8])
    if not merged_domain_expert.related_terms:
        merged_domain_expert.related_terms = list(cfg.keywords[8:14])
    if not merged_domain_expert.outcome_focus:
        merged_domain_expert.outcome_focus = [cfg.pico.outcome]
    lines.append("domain_expert:")
    lines.append(f"  expert_role: {_yaml_str(merged_domain_expert.expert_role)}")
    lines.append(f"  domain_summary: {_yaml_str(merged_domain_expert.domain_summary)}")
    for field_name in (
        "canonical_terms",
        "related_terms",
        "excluded_terms",
        "methodological_focus",
        "outcome_focus",
    ):
        values = list(getattr(merged_domain_expert, field_name))
        if values:
            lines.append(f"  {field_name}:")
            for item in values:
                lines.append(f"    - {_yaml_str(item)}")
        else:
            lines.append(f"  {field_name}: []")
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
        allowed_db_names = set(databases)
        merged_overrides = {k: v for k, v in merged_overrides.items() if k in allowed_db_names}
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
    "2. Broad domain terms and alternative phrasing used by different fields for the same\n"
    "   concept (maximize synonym and wording coverage for recall).\n"
    "3. Representative product/vendor names only when they are common in the literature.\n"
    "   Keep this supplemental, not dominant.\n"
    "4. The typical population or setting studied and relevant sub-settings.\n"
    "5. Key quantitative outcome measures and metrics used to evaluate this intervention.\n"
    "6. Common implementation or adoption challenges and workflow terms.\n"
    "7. Any adjacent or overlapping technologies that should be distinguished from the\n"
    "   main intervention (so they can be excluded from the review).\n\n"
    "Format as a concise bullet-point brief. Be specific. Include real brand names,\n"
    "real domain terms, and real metric names. Do not generalize."
)

# ---------------------------------------------------------------------------
# Stage 2 -- Structuring prompt (NativeOutput, no web search)
# ---------------------------------------------------------------------------

_STRUCTURE_PROMPT = (
    "You are an expert in systematic review configuration design. Using the research brief\n"
    "below, generate a complete systematic review configuration with neutral language.\n\n"
    "Original research question:\n"
    "{research_question}\n\n"
    "Research brief (from web search):\n"
    "{research_brief}\n\n"
    "Instructions:\n"
    "- Refine the research question into a precise, well-formed systematic review\n"
    "  research question that follows PICO structure. Keep it close to the user's\n"
    "  intent but make it specific and academically precise.\n"
    "- Language style guardrail: Use plain, neutral wording. Do NOT inject clinical\n"
    "  or medical phrasing unless the user topic is explicitly biomedical.\n"
    "- Few-shot style example (generic):\n"
    "  Input topic: 'AI code assistants for software teams'\n"
    "  Good question style: 'What is the impact of AI code assistants on developer productivity and code quality in software teams?'\n"
    "  Good scope style: concise, non-clinical, focused on engineering workflows.\n"
    "- Few-shot style example (biomedical):\n"
    "  Input topic: 'voice reminder robots for medication adherence'\n"
    "  Good question style: 'What is the effectiveness of voice reminder systems for improving medication adherence in older adults?'\n"
    "  Good scope style: clinical wording allowed because topic is biomedical.\n"
    "- Generate all PICO components: population (who/what is studied), intervention\n"
    "  (technology/treatment/system being evaluated), comparison (controls, baselines,\n"
    "  alternatives, or pre-implementation state), outcome (all relevant measurable\n"
    "  outcomes).\n"
    "- Generate 18-24 specific search keywords. Draw directly from the research\n"
    "  brief above. Cover ALL of:\n"
    "  (a) the core intervention technology and its synonyms and abbreviations from\n"
    "      the research brief,\n"
    "  (b) optional representative commercial brand names and product lines from the\n"
    "      research brief when they are frequently used in studies,\n"
    "  (c) the population, setting, and context keywords from the research brief,\n"
    "  (d) the specific outcome measure terms and measurable targets found in the\n"
    "      research brief (e.g. exact metric names),\n"
    "  (e) implementation-related terms (barriers, facilitators, adoption, workflow).\n"
    "  CRITICAL -- these keywords are used to pre-filter paper ABSTRACTS via substring\n"
    "  matching, NOT as database query strings. Four mandatory rules:\n"
    "  RULE 1 -- Include SHORT ROOT FORMS: For every multi-word concept, also include\n"
    "  the single most discriminative word as its own keyword entry, because abstracts\n"
    "  vary phrasing. The root word catches all variants that multi-word phrases miss.\n"
    "  Example (mindfulness and anxiety topic):\n"
    "    'mindfulness-based stress reduction' -> also add 'mindfulness' as a separate entry\n"
    "    'anxiety disorder' -> also add 'anxiety' as a separate entry\n"
    "    'cognitive behavioural therapy' -> 'CBT' also covers this variant\n"
    "  Apply this root-form pattern to YOUR specific topic.\n"
    "  RULE 2 -- Avoid generic cross-domain terms: NEVER include terms that appear\n"
    "  across unrelated domains, such as 'outcomes', 'intervention', 'patient',\n"
    "  'effectiveness', 'implementation', or 'quality of life'.\n"
    "  These can match papers from any field and reduce screening precision.\n"
    "  Only include terms that are specific to YOUR topic domain.\n"
    "  RULE 3 -- Ban fragments: NEVER include single letters, single-character tokens,\n"
    "  or parsing artifacts (e.g. 'n', 'x', '_'). Every keyword must have at least one\n"
    "  alphanumeric token with length >= 2.\n"
    "  RULE 4 -- Balance keyword mix: at least 60% of keywords must be domain concepts,\n"
    "  intervention synonyms, setting terms, or outcome metrics. Brand/acronym keywords\n"
    "  are supplemental and must not dominate the list.\n"
    "  RULE 5 -- Recall-first coverage: include phrasing variants and adjacent synonyms so\n"
    "  downstream screening can filter later; avoid overly narrow phrase locking.\n"
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
    "- Generate search_overrides with database-optimized queries for databases relevant\n"
    "  to this topic. Always include scopus, web_of_science, ieee_xplore, semantic_scholar,\n"
    "  and openalex. Include pubmed and clinicaltrials_gov only when topic evidence is clearly\n"
    "  biomedical/clinical. Use actual terms from this review's topic, not placeholders.\n"
    "  * pubmed: Use MeSH terms where available plus [Title/Abstract] field codes.\n"
    "    Pattern: (MeSHTerm[MeSH Terms] OR keyword[Title/Abstract] OR ...) AND\n"
    "    (setting_term[Title/Abstract] OR outcome_term[Title/Abstract] OR ...)\n"
    "    CRITICAL for the second AND group: every term must be a SINGLE ROOT WORD.\n"
    "    Prefer single root words that capture variant phrasing for recall.\n"
    "    Use setting and outcome terms that broaden capture without drifting off-topic.\n"
    "    Do NOT use multi-word exact phrases in [Title/Abstract] field codes -- they require\n"
    "    both words to appear adjacent in title/abstract and drastically cut recall.\n"
    "    Also avoid narrow secondary MeSH headings in the AND group unless they ARE the\n"
    "    primary topic -- many relevant papers are not indexed under specific narrow MeSH terms.\n"
    "  * scopus: Use TITLE-ABS-KEY field code with two AND-joined clauses of quoted keywords.\n"
    "    Clause 1: intervention/synonym terms (up to 8). Clause 2: outcome/setting terms (up to 8).\n"
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
    "    Include at least one intervention term, one setting term, and one outcome term.\n"
    "  * openalex: 5-8 space-separated keywords ONLY. No quotes, no boolean operators.\n"
    "    Same natural-language guidance as semantic_scholar above.\n"
    "    CRITICAL: pair generic outcome words with a specific domain term from this topic.\n"
    "    Generic words like 'efficiency', 'accuracy', 'barriers' alone match unrelated industries.\n"
    "    Good (educational technology review): 'educational technology student learning outcomes effectiveness'\n"
    "    Good (autonomous vehicles review): 'autonomous vehicle safety performance urban deployment'\n"
    "    Bad (any topic): generic adjectives and nouns without a domain anchor.\n"
    "  * clinicaltrials_gov: OR-joined quoted keyword phrases for this intervention/condition.\n"
    "    Plain text only -- no MeSH terms, no field codes. Include technology names, brand names,\n"
    "    and condition/setting terms. 8-12 terms maximum.\n"
    '    Pattern: "technology term" OR "brand name" OR "condition term"\n'
    "    Do NOT include full PICO descriptions as search terms.\n"
    "  CRITICAL for all databases: Use short keyword phrases -- NEVER full\n"
    "  sentences or PICO descriptions as search terms. Full PICO strings never appear\n"
    "  verbatim in papers and will always return zero results.\n\n"
    "Return the response as a JSON object matching the schema exactly. All text fields\n"
    "must be in English. Do not truncate or omit any field."
)


# ---------------------------------------------------------------------------
# Keyword post-processing
# ---------------------------------------------------------------------------


def _extract_root_terms(keywords: list[str]) -> list[str]:
    """Extract short discriminative root terms from multi-word keywords.

    The LLM generates multi-word keyword phrases that work as database query
    strings but miss abstract variants when used for substring pre-filtering.
    This function extracts the single most discriminative word from each
    multi-word keyword and adds it to the list (if not already present).

    For example: 'automated dispensing systems' -> adds 'dispensing' because
    abstracts say 'dispensing robot', 'dispensing cabinet', 'robotic dispenser',
    none of which contain the full phrase.
    """
    _STOPWORDS = {
        "and",
        "or",
        "the",
        "of",
        "in",
        "for",
        "to",
        "a",
        "an",
        "with",
        "from",
        "by",
        "at",
        "on",
        "use",
        "using",
        "based",
        # Plural/variant forms of generic structural words
        "system",
        "systems",
        "approach",
        "approaches",
        "method",
        "methods",
        "model",
        "models",
        "process",
        "processes",
        "framework",
        "frameworks",
        # Cross-domain generic terms that cause false positives across topics
        "efficiency",
        "safety",
        "quality",
        "management",
        "operational",
        "implementation",
        "barriers",
        "facilitators",
        "integration",
        "patient",
        "clinical",
        "health",
        "care",
        "technology",
        "outcomes",
        "analysis",
        "review",
        "study",
        "research",
        "assessment",
        "evaluation",
        "impact",
        "effect",
        "role",
        "performance",
        "strategy",
        "strategies",
        "practice",
        "practices",
        "adoption",
        "workflow",
        "workload",
        "utilization",
        "usage",
    }
    _MIN_LENGTH = 5  # skip short noise like "AI", "IT", "mg", "drug"

    existing = {kw.lower() for kw in keywords}
    additions: list[str] = []
    for kw in keywords:
        parts = kw.split()
        if len(parts) < 2:
            continue  # already a single word
        words = [w.strip("()-,") for w in kw.lower().split()]
        candidates = [w for w in words if len(w) >= _MIN_LENGTH and w not in _STOPWORDS]
        # Prefer the LAST significant word (usually the most specific noun)
        for candidate in reversed(candidates):
            if candidate not in existing:
                additions.append(candidate)
                existing.add(candidate)
                break
    return keywords + additions


def _sanitize_keywords(keywords: list[str]) -> list[str]:
    """De-noise and de-duplicate keywords while preserving schema minimum size."""

    def _normalize(text: str) -> str:
        return " ".join(text.strip().split())

    def _has_substantive_token(text: str) -> bool:
        parts = [p for p in re.split(r"[^a-z0-9]+", text.lower()) if p]
        if not parts:
            return False
        return any(len(p) >= _MIN_KEYWORD_TOKEN_LEN for p in parts)

    def _is_brand_or_acronym_keyword(text: str) -> bool:
        parts = [p for p in re.split(r"[^A-Za-z0-9]+", text) if p]
        if not parts:
            return False
        for part in parts:
            if any(ch.isdigit() for ch in part):
                return True
            if len(part) >= 2 and part.isupper():
                return True
        if re.search(r"[A-Z][a-z]+[A-Z]", text):
            return True
        return False

    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in keywords:
        kw = _normalize(str(raw))
        if not kw:
            continue
        if not _has_substantive_token(kw):
            continue
        lowered = kw.lower()
        parts = [p for p in re.split(r"[^a-z0-9]+", lowered) if p]
        if lowered in _GENERIC_NOISE_TERMS:
            continue
        if parts and all(part in _GENERIC_NOISE_TERMS for part in parts):
            continue
        if lowered in seen:
            continue
        cleaned.append(kw)
        seen.add(lowered)

    # Keep the schema-safe minimum by backfilling from originals if needed.
    if len(cleaned) < 15:
        for raw in keywords:
            kw = _normalize(str(raw))
            lowered = kw.lower()
            parts = [p for p in re.split(r"[^a-z0-9]+", lowered) if p]
            if not kw or lowered in seen:
                continue
            if not _has_substantive_token(kw):
                continue
            if lowered in _GENERIC_NOISE_TERMS:
                continue
            if parts and all(part in _GENERIC_NOISE_TERMS for part in parts):
                continue
            cleaned.append(kw)
            seen.add(lowered)
            if len(cleaned) >= 15:
                break

    # Cap brand/acronym-heavy terms so domain concepts dominate.
    brand_like = [k for k in cleaned if _is_brand_or_acronym_keyword(k)]
    cap = min(_MAX_BRAND_KEYWORD_ABS, max(3, int(len(cleaned) * _MAX_BRAND_KEYWORD_RATIO)))
    if len(brand_like) > cap:
        keep: list[str] = []
        kept_brand = 0
        for kw in cleaned:
            if _is_brand_or_acronym_keyword(kw):
                if kept_brand >= cap:
                    continue
                kept_brand += 1
            keep.append(kw)
        cleaned = keep

    return cleaned[:24]


def _keywords_need_repair(keywords: list[str]) -> bool:
    if len(keywords) < 15:
        return True
    roots: set[str] = set()
    for kw in keywords:
        parts = [p for p in re.split(r"[^a-z0-9]+", kw.lower()) if p]
        if not parts or all(len(p) < _MIN_KEYWORD_TOKEN_LEN for p in parts):
            return True
        for p in parts:
            if len(p) >= 4 and p not in _GENERIC_NOISE_TERMS:
                roots.add(p)
    if len(roots) < 10:
        return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def generate_config_yaml(
    research_question: str,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
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

    def emit(step: str, **metadata: Any) -> None:
        if progress_cb:
            try:
                payload: dict[str, Any] = {"step": step}
                payload.update(metadata)
                progress_cb(payload)
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
        emit("web_research_fallback")

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

    async def _run_structure(prompt: str) -> str:
        structure_result = await structure_agent.run(
            prompt,
            model_settings={"temperature": _TEMPERATURE},
        )
        output = structure_result.output
        return json.dumps(output) if isinstance(output, dict) else str(output)

    repair_instruction = (
        "\\n\\nREPAIR INSTRUCTION:\\n"
        "Return valid keywords only. Must include 18-24 items, each with at least one token of "
        "length >= 2. Do not return single letters/fragments. Keep brands/acronyms supplemental "
        "(<= 35% of keywords), and prioritize domain/setting/outcome terms."
    )

    try:
        result_json = await _run_structure(structure_prompt)
    except Exception as exc:
        logger.error("Config gen Stage 2 (structure) failed: %s", exc)
        raise RuntimeError(f"LLM structuring failed: {exc}") from exc

    emit("finalizing")

    try:
        parsed = _GeneratedConfig.model_validate_json(result_json)
    except Exception as exc:
        logger.warning("Config gen response failed validation; retrying once with repair instruction: %s", exc)
        emit("structuring_retry")
        try:
            result_json = await _run_structure(structure_prompt + repair_instruction)
            parsed = _GeneratedConfig.model_validate_json(result_json)
        except Exception as retry_exc:
            logger.error(
                "Config gen response failed validation after retry: %s\nRaw: %s",
                retry_exc,
                result_json[:500],
            )
            raise RuntimeError(f"Generated config failed schema validation: {retry_exc}") from retry_exc

    parsed = parsed.model_copy(update={"review_type": "systematic"})

    # Post-process: add short root forms for multi-word keywords so the
    # abstract substring pre-filter catches phrasing variants the LLM missed.
    enriched_keywords = _extract_root_terms(list(parsed.keywords))
    sanitized_keywords = _sanitize_keywords(enriched_keywords)
    if _keywords_need_repair(sanitized_keywords):
        emit("structuring_retry")
        try:
            result_json = await _run_structure(structure_prompt + repair_instruction)
            parsed_retry = _GeneratedConfig.model_validate_json(result_json)
            enriched_keywords = _extract_root_terms(list(parsed_retry.keywords))
            sanitized_keywords = _sanitize_keywords(enriched_keywords)
        except Exception as retry_exc:
            logger.warning("Keyword repair retry failed; continuing with first pass: %s", retry_exc)
    parsed = parsed.model_copy(update={"keywords": sanitized_keywords})

    defaults = _load_default_config()
    resolved_databases, route = _resolve_target_databases(parsed, defaults)
    emit(
        "topic_routing",
        domain=route.domain,
        confidence=route.confidence,
        policy=route.policy,
        matched_biomedical_terms=route.matched_biomedical_terms,
        matched_generic_terms=route.matched_generic_terms,
    )
    return _build_yaml(parsed, defaults, resolved_databases=resolved_databases)


def evaluate_config_quality_dict(raw_cfg: dict[str, Any]) -> dict[str, Any]:
    """Deterministic quality score for generated config dictionaries."""
    keywords_raw = raw_cfg.get("keywords") or []
    keywords = [str(k).strip().lower() for k in keywords_raw if str(k).strip()]
    unique_keywords = set(keywords)
    diversity = len(unique_keywords) / max(1, len(keywords))
    generic_hits = sum(1 for k in unique_keywords if k in _GENERIC_NOISE_TERMS)
    specificity = 1.0 - (generic_hits / max(1, len(unique_keywords)))
    keyword_quality = max(0.0, min(100.0, 100.0 * (0.6 * diversity + 0.4 * specificity)))

    overrides = raw_cfg.get("search_overrides") or {}
    override_values = [str(v) for v in overrides.values() if isinstance(v, str)]

    def _is_balanced(text: str) -> bool:
        stack: list[str] = []
        pairs = {")": "(", "]": "["}
        for ch in text:
            if ch in ("(", "["):
                stack.append(ch)
            elif ch in pairs:
                if not stack or stack.pop() != pairs[ch]:
                    return False
        return not stack

    if override_values:
        valid_syntax = [1.0 if _is_balanced(v) else 0.0 for v in override_values]
        syntax_sanity = 100.0 * (sum(valid_syntax) / len(valid_syntax))
        avg_len = sum(len(v) for v in override_values) / len(override_values)
    else:
        syntax_sanity = 75.0
        avg_len = 0.0

    if avg_len == 0.0:
        length_complexity = 70.0
    elif avg_len < 40:
        length_complexity = 45.0
    elif avg_len <= 900:
        length_complexity = 100.0
    elif avg_len <= 1800:
        length_complexity = 70.0
    else:
        length_complexity = 45.0

    dbs_raw = raw_cfg.get("target_databases") or _DEFAULT_DATABASES
    dbs = [str(db) for db in dbs_raw]

    cfg_like = _GeneratedConfig(
        research_question=str(raw_cfg.get("research_question") or ""),
        review_type="systematic",
        pico=_Pico(
            population=str((raw_cfg.get("pico") or {}).get("population") or ""),
            intervention=str((raw_cfg.get("pico") or {}).get("intervention") or ""),
            comparison=str((raw_cfg.get("pico") or {}).get("comparison") or ""),
            outcome=str((raw_cfg.get("pico") or {}).get("outcome") or ""),
        ),
        keywords=(keywords[:28] if keywords else ["placeholder"] * 15),
        domain=str(raw_cfg.get("domain") or ""),
        scope=str(raw_cfg.get("scope") or ""),
        inclusion_criteria=["placeholder inclusion"] * 4,
        exclusion_criteria=["placeholder exclusion"] * 3,
        search_overrides=None,
    )
    route = _route_topic_with_confidence(cfg_like)
    topic_blob = " ".join(
        [
            cfg_like.research_question,
            cfg_like.domain,
            cfg_like.scope,
            cfg_like.pico.population,
            cfg_like.pico.intervention,
            cfg_like.pico.outcome,
            " ".join(list(unique_keywords)),
        ]
    ).lower()
    topic_terms = {
        tok
        for tok in re.findall(r"[a-z0-9]+", topic_blob)
        if len(tok) >= 4 and tok not in _GENERIC_NOISE_TERMS
    }
    topic_anchor_floor = max(8, min(20, len(topic_terms)))
    specificity_scores: list[float] = []
    for override in override_values:
        override_terms = {tok for tok in re.findall(r"[a-z0-9]+", override.lower()) if len(tok) >= 4}
        anchored = len(override_terms & topic_terms)
        generic_penalty = len(override_terms & _GENERIC_NOISE_TERMS)
        raw_specificity = (100.0 * anchored / topic_anchor_floor) - (7.0 * generic_penalty)
        specificity_scores.append(max(0.0, min(100.0, raw_specificity)))
    specificity_score = (
        sum(specificity_scores) / len(specificity_scores) if specificity_scores else 70.0
    )
    override_complexity = round((0.6 * length_complexity) + (0.4 * specificity_score), 2)
    db_relevance = 100.0
    if route.policy == "high_confidence_generic":
        if "pubmed" in dbs:
            db_relevance -= 20.0
        if "clinicaltrials_gov" in dbs:
            db_relevance -= 35.0
    elif route.policy == "high_confidence_biomedical":
        if "pubmed" not in dbs:
            db_relevance -= 30.0
    else:
        if "clinicaltrials_gov" in dbs:
            db_relevance -= 20.0
    db_relevance = max(0.0, db_relevance)

    total = (
        0.35 * syntax_sanity
        + 0.3 * keyword_quality
        + 0.2 * db_relevance
        + 0.15 * override_complexity
    )

    return {
        "total": round(total, 2),
        "syntax_sanity": round(syntax_sanity, 2),
        "keyword_quality": round(keyword_quality, 2),
        "database_relevance": round(db_relevance, 2),
        "override_complexity": round(override_complexity, 2),
        "route_domain": route.domain,
        "route_confidence": route.confidence,
        "route_policy": route.policy,
    }


def evaluate_config_quality_yaml(yaml_text: str) -> dict[str, Any]:
    """Deterministic quality score for generated config YAML snapshots."""
    try:
        raw = yaml.safe_load(yaml_text) or {}
    except Exception:
        return {
            "total": 0.0,
            "syntax_sanity": 0.0,
            "keyword_quality": 0.0,
            "database_relevance": 0.0,
            "override_complexity": 0.0,
            "route_domain": "ambiguous",
            "route_confidence": 0.0,
            "route_policy": "invalid_yaml",
        }
    if not isinstance(raw, dict):
        return {
            "total": 0.0,
            "syntax_sanity": 0.0,
            "keyword_quality": 0.0,
            "database_relevance": 0.0,
            "override_complexity": 0.0,
            "route_domain": "ambiguous",
            "route_confidence": 0.0,
            "route_policy": "invalid_shape",
        }
    return evaluate_config_quality_dict(raw)
