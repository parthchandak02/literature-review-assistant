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

from pydantic import BaseModel, Field
from pydantic_ai import Agent, NativeOutput, StructuredDict, WebFetchTool, WebSearchTool

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
    "   in published studies (exact product names like 'Xenex LightStrike',\n"
    "   'Tru-D SmartUVC', 'Pyxis MedStation', 'Omnicell XT'). Include as many as\n"
    "   you can find. These are critical for database search coverage.\n"
    "3. The typical population or setting studied and any relevant sub-settings.\n"
    "4. Key quantitative outcome measures and metrics used to evaluate this technology\n"
    "   (e.g. specific pathogen names like 'C. difficile', 'MRSA', 'VRE'; or specific\n"
    "   metrics like 'dispensing error rate', 'log reduction', 'colony-forming units').\n"
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
    "- Generate 5-7 exclusion criteria as complete, specific sentences. Include\n"
    "  adjacent technologies identified in the research brief that should be excluded.\n"
    "- Generate a one-line domain description and a 2-4 sentence scope statement.\n"
    "- Set review_type to exactly 'systematic'.\n\n"
    "Return the response as a JSON object matching the schema exactly. All text fields\n"
    "must be in English. Do not truncate or omit any field."
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def generate_config_yaml(research_question: str) -> str:
    """Generate a complete review config YAML from a research question.

    Two-stage pipeline:
    - Stage 1: Gemini + WebSearchTool + WebFetchTool performs a real web search
      and fetches pages to discover brand names, metrics, and domain terminology.
    - Stage 2: Gemini + NativeOutput structures the research brief into a
      validated _GeneratedConfig, then serializes it to YAML.

    Raises RuntimeError on LLM or validation failure.
    """
    rq = research_question.strip()

    # ------------------------------------------------------------------
    # Stage 1: web-grounded research brief
    # ------------------------------------------------------------------
    research_prompt = _RESEARCH_PROMPT.format(research_question=rq)
    research_agent: Agent[None, str] = Agent(
        _MODEL,
        output_type=str,
        builtin_tools=[WebSearchTool(), WebFetchTool()],
    )
    try:
        research_result = await research_agent.run(research_prompt)
        research_brief = research_result.output
        logger.info(
            "Config gen Stage 1 complete: brief length=%d chars", len(research_brief)
        )
    except Exception as exc:
        logger.warning(
            "Config gen Stage 1 (web search+fetch) failed, falling back to model knowledge: %s", exc
        )
        # Graceful degradation: skip the research brief, rely on model knowledge.
        research_brief = "(Web search unavailable -- rely on training knowledge only.)"

    # ------------------------------------------------------------------
    # Stage 2: structured output from research brief
    # ------------------------------------------------------------------
    structure_prompt = _STRUCTURE_PROMPT.format(
        research_question=rq,
        research_brief=research_brief,
    )
    schema = _GeneratedConfig.model_json_schema()
    output_type = NativeOutput(StructuredDict(schema))
    structure_agent: Agent = Agent(_MODEL, output_type=output_type)  # type: ignore[arg-type]

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

    try:
        parsed = _GeneratedConfig.model_validate_json(result_json)
    except Exception as exc:
        logger.error(
            "Config gen response failed validation: %s\nRaw: %s", exc, result_json[:500]
        )
        try:
            raw_dict = json.loads(result_json)
            parsed = _GeneratedConfig.model_validate(raw_dict)
        except Exception:
            raise RuntimeError(f"Generated config failed schema validation: {exc}") from exc

    parsed = parsed.model_copy(update={"review_type": "systematic"})
    return _build_yaml(parsed)
