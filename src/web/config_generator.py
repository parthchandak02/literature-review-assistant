"""LLM-based review config generator.

Given a plain-English research question, uses Gemini flash to generate a
complete, structured ReviewConfig (PICO, keywords, inclusion/exclusion criteria,
domain, scope) returned as a YAML string compatible with the frontend parseYaml()
parser and the backend ReviewConfig model.

This module is intentionally lightweight: no DB logging (pre-run, no run_id),
no rate-limiter wrapping (single call, not part of a pipeline batch).
"""

from __future__ import annotations

import datetime
import json
import logging

from pydantic import BaseModel, Field

from src.llm.pydantic_client import PydanticAIClient

logger = logging.getLogger(__name__)

# Use the search agent model tier (flash-grade, fast and cheap).
_MODEL = "google-gla:gemini-2.5-flash"
_TEMPERATURE = 0.3

# Structural defaults that are never LLM-generated (kept stable across all reviews).
_DEFAULT_DATE_START = 2010
_DEFAULT_DATE_END = datetime.datetime.now().year
_DEFAULT_DATABASES = [
    "openalex",
    "pubmed",
    "arxiv",
    "ieee_xplore",
    "semantic_scholar",
    "crossref",
    "perplexity_search",
]
_DEFAULT_SECTIONS = [
    "abstract",
    "introduction",
    "methods",
    "results",
    "discussion",
    "conclusion",
]


# ---------------------------------------------------------------------------
# Structured output schema
# ---------------------------------------------------------------------------

class _Pico(BaseModel):
    population: str = Field(description="Who or what is being studied")
    intervention: str = Field(description="The intervention, exposure, or technology being evaluated")
    comparison: str = Field(description="What the intervention is compared against (controls, baselines, alternatives)")
    outcome: str = Field(description="Outcomes measured (efficacy, safety, efficiency, cost, etc.)")


class _GeneratedConfig(BaseModel):
    research_question: str = Field(description="Refined, precise systematic review research question")
    review_type: str = Field(description="Always 'systematic'")
    pico: _Pico
    keywords: list[str] = Field(
        description="15-22 specific search keywords and phrases covering the topic, intervention, population, and key outcome concepts",
        min_length=10,
        max_length=25,
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


# ---------------------------------------------------------------------------
# YAML serializer (mirrors frontend buildYaml() exactly)
# ---------------------------------------------------------------------------

def _yaml_str(s: str) -> str:
    """Wrap a string value in double quotes with escaping."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _build_yaml(cfg: _GeneratedConfig) -> str:
    lines: list[str] = []
    lines.append(f"research_question: {_yaml_str(cfg.research_question)}")
    lines.append(f"review_type: {_yaml_str(cfg.review_type)}")
    lines.append("")
    lines.append("pico:")
    lines.append(f"  population: {_yaml_str(cfg.pico.population)}")
    lines.append(f"  intervention: {_yaml_str(cfg.pico.intervention)}")
    lines.append(f"  comparison: {_yaml_str(cfg.pico.comparison)}")
    lines.append(f"  outcome: {_yaml_str(cfg.pico.outcome)}")
    lines.append("")
    lines.append(f"domain: {_yaml_str(cfg.domain)}")
    lines.append(f"scope: {_yaml_str(cfg.scope)}")
    lines.append("")
    lines.append("keywords:")
    for kw in cfg.keywords:
        lines.append(f"  - {_yaml_str(kw)}")
    lines.append("")
    lines.append("inclusion_criteria:")
    for c in cfg.inclusion_criteria:
        lines.append(f"  - {_yaml_str(c)}")
    lines.append("")
    lines.append("exclusion_criteria:")
    for c in cfg.exclusion_criteria:
        lines.append(f"  - {_yaml_str(c)}")
    lines.append("")
    lines.append(f"date_range_start: {_DEFAULT_DATE_START}")
    lines.append(f"date_range_end: {_DEFAULT_DATE_END}")
    lines.append("")
    lines.append("target_databases:")
    for db in _DEFAULT_DATABASES:
        lines.append(f"  - {db}")
    lines.append("")
    lines.append("target_sections:")
    for s in _DEFAULT_SECTIONS:
        lines.append(f"  - {s}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATE = """\
You are an expert systematic review methodologist. Your task is to generate a
complete, publication-quality systematic review configuration for the research
question below.

Research question provided by the user:
{research_question}

Instructions:
- Refine the research question into a precise, well-formed systematic review
  research question that follows PICO structure. Keep it close to the user's
  intent but make it specific and academically precise.
- Generate all PICO components: population (who/what is studied), intervention
  (technology/treatment/system being evaluated), comparison (controls, baselines,
  alternatives, or pre-implementation state), outcome (all relevant measurable
  outcomes).
- Generate 15-22 specific search keywords covering: the intervention technology
  and its synonyms, the population/setting, key outcome measures, and well-known
  brand names or specific product names if applicable.
- Generate 6-8 inclusion criteria as complete, specific sentences covering:
  study type, setting, intervention specificity, outcome reporting, language, and
  publication type.
- Generate 5-7 exclusion criteria as complete, specific sentences covering:
  out-of-scope settings, non-empirical publications, languages, and adjacent
  technologies that should be excluded.
- Generate a one-line domain description and a 2-4 sentence scope statement.
- Set review_type to exactly "systematic".

Return the response as a JSON object matching the schema exactly. All text fields
must be in English. Do not truncate or omit any field.
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def generate_config_yaml(research_question: str) -> str:
    """Generate a complete review config YAML from a research question.

    Uses Gemini flash with native structured output (NativeOutput / responseSchema)
    to produce a validated _GeneratedConfig, then serializes it to YAML.

    Raises RuntimeError on LLM or validation failure.
    """
    prompt = _PROMPT_TEMPLATE.format(research_question=research_question.strip())
    schema = _GeneratedConfig.model_json_schema()

    client = PydanticAIClient()
    try:
        result_json = await client.complete(
            prompt,
            model=_MODEL,
            temperature=_TEMPERATURE,
            json_schema=schema,
        )
    except Exception as exc:
        logger.error("Config generation LLM call failed: %s", exc)
        raise RuntimeError(f"LLM generation failed: {exc}") from exc

    try:
        parsed = _GeneratedConfig.model_validate_json(result_json)
    except Exception as exc:
        logger.error("Config generation response failed validation: %s\nRaw: %s", exc, result_json[:500])
        # Attempt to parse as dict and re-validate (handles JSON wrapped in dict)
        try:
            raw_dict = json.loads(result_json)
            parsed = _GeneratedConfig.model_validate(raw_dict)
        except Exception:
            raise RuntimeError(f"Generated config failed schema validation: {exc}") from exc

    # Ensure review_type is exactly "systematic"
    parsed = parsed.model_copy(update={"review_type": "systematic"})

    return _build_yaml(parsed)
