"""Contradiction resolver: generates an evidence-based disagreement paragraph.

When the contradiction detector identifies high-confidence contradictions,
this module uses the pro-tier LLM to write a concise, balanced paragraph
acknowledging the directional disagreement and potential explanatory factors.

The generated paragraph is injected into the Discussion section.
"""

from __future__ import annotations

import logging
from time import monotonic

from src.config.env_context import get_env
from src.db.repositories import WorkflowRepository
from src.llm.factory import get_chat_client
from src.llm.provider import LLMProvider
from src.synthesis.contradiction_detector import ContradictionFlag

logger = logging.getLogger(__name__)


def _get_model_from_settings() -> str:
    try:
        from src.config.loader import load_configs

        _, s = load_configs(settings_path="config/settings.yaml")
        return s.agents["contradiction_resolver"].model
    except Exception:
        from src.llm.model_fallback import get_fallback_model

        return get_fallback_model("flash")


_RESOLVER_PROMPT_TEMPLATE = (
    "You are writing the Discussion section of a systematic review.\n"
    "The following pairs of studies report opposite findings on the same outcome.\n\n"
    "Contradictions identified:\n"
    "{contradiction_list}\n\n"
    "Write a concise paragraph (100-200 words) for the Discussion section that:\n"
    "1. Acknowledges the directional disagreement between studies\n"
    "2. Notes plausible explanatory factors (population heterogeneity, measurement differences)\n"
    "3. Avoids making a definitive claim about which direction is correct\n"
    "4. Uses hedged academic language (findings were inconsistent, evidence remains inconclusive)\n"
    "5. Does NOT fabricate statistics or effect sizes\n\n"
    "Return ONLY the paragraph text, no headings or labels.\n"
)


def _format_contradiction_list(flags: list[ContradictionFlag]) -> str:
    lines: list[str] = []
    for i, f in enumerate(flags[:5], 1):
        lines.append(
            f"{i}. Paper {f.paper_id_a[:12]} vs {f.paper_id_b[:12]}: "
            f"outcome='{f.outcome_name}', "
            f"directions={f.direction_a} vs {f.direction_b}, "
            f"similarity={f.similarity:.2f}"
        )
    return "\n".join(lines)


def _fallback_paragraph(flags: list[ContradictionFlag]) -> str:
    outcomes = list({f.outcome_name for f in flags[:3]})
    outcome_str = ", ".join(outcomes) if outcomes else "the primary outcomes"
    return (
        f"Some inconsistency was observed across included studies, particularly "
        f"regarding {outcome_str}. These discrepancies may reflect differences in "
        f"study populations, intervention protocols, outcome measurement approaches, "
        f"or follow-up duration. Given the heterogeneity in study designs and "
        f"settings, these conflicting findings should be interpreted with caution "
        f"and further research is needed to reconcile the observed inconsistencies."
    )


async def generate_contradiction_paragraph(
    flags: list[ContradictionFlag],
    model_name: str | None = None,
    api_key: str | None = None,
    repository: WorkflowRepository | None = None,
    workflow_id: str = "",
) -> str:
    """Generate a Discussion paragraph addressing contradictions.

    Returns an empty string if flags is empty.
    """
    if not flags:
        return ""

    if model_name is None:
        model_name = _get_model_from_settings()
    if api_key:
        logger.warning(
            "generate_contradiction_paragraph received api_key argument; explicit key injection is deprecated and ignored."
        )
    if not get_env("GEMINI_API_KEY") and not get_env("DEEPSEEK_API_KEY") and not get_env("OPENROUTER_API_KEY"):
        return _fallback_paragraph(flags)

    prompt = _RESOLVER_PROMPT_TEMPLATE.format(contradiction_list=_format_contradiction_list(flags))
    try:
        from src.config.loader import load_configs

        _, settings = load_configs(settings_path="config/settings.yaml")
        provider = LLMProvider(settings=settings, repository=repository)
        reserve_agent = "contradiction_resolver" if "contradiction_resolver" in settings.agents else "writing"
        await provider.reserve_call_slot(reserve_agent)
        client = get_chat_client()
        started = monotonic()
        raw, tok_in, tok_out, cw, cr = await client.complete_with_usage(prompt, model=model_name, temperature=0.1)
        latency_ms = int((monotonic() - started) * 1000)
        text = str(raw or "").strip()
        if len(text) < 50:
            text = _fallback_paragraph(flags)
        if repository is not None and workflow_id:
            cost = provider.estimate_cost_usd(model_name, tok_in, tok_out, cw, cr)
            await provider.log_cost(
                model_name,
                tok_in,
                tok_out,
                cost,
                latency_ms,
                phase="writing_contradiction_resolver",
                cache_read_tokens=cr,
                cache_write_tokens=cw,
            )
        return text
    except Exception as exc:
        logger.warning("Contradiction resolver LLM call failed: %s", exc)
        return _fallback_paragraph(flags)


def build_conflicting_evidence_section(
    flags: list[ContradictionFlag],
    paper_id_to_label: dict[str, str] | None = None,
) -> str:
    """Build a structured '### Conflicting Evidence' subsection for the Discussion.

    Each detected contradiction pair is listed as a bullet with human-readable
    labels (citekeys when available, short paper_id prefix as fallback), the
    shared outcome name, and the opposing result directions. This section is
    injected into the Discussion draft AFTER the LLM-generated body but BEFORE
    manuscript assembly so it appears in the final DOCX.

    paper_id_to_label: optional mapping from paper_id to citekey/author-year label,
    built from the citation catalog in the caller. When provided, labels replace
    raw UUID fragments in bullet points.

    Returns an empty string when no flags are provided.
    """
    if not flags:
        return ""

    _label_map = paper_id_to_label or {}

    def _display(paper_id: str) -> str:
        return _label_map.get(paper_id, paper_id[:12])

    lines: list[str] = ["### Conflicting Evidence", ""]
    lines.append(
        "The following pairs of included studies reported contradictory findings "
        "on the same outcome. These discrepancies may reflect differences in "
        "study design, population characteristics, implementation context, or "
        "outcome measurement methods."
    )
    lines.append("")

    for flag in flags[:10]:
        lines.append(
            f"- **{flag.outcome_name}**: "
            f"Study `{_display(flag.paper_id_a)}` reported a *{flag.direction_a}* direction, "
            f"while Study `{_display(flag.paper_id_b)}` reported a *{flag.direction_b}* direction "
            f"(outcome similarity: {flag.similarity:.2f})." + (f" Note: {flag.note}" if flag.note else "")
        )

    lines.append("")
    lines.append(
        "These inconsistencies underscore the need for cautious interpretation of "
        "pooled estimates and highlight areas requiring further primary research."
    )

    return "\n".join(lines)
