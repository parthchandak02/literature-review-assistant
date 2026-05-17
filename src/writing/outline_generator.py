"""Pre-writing outline generation for section-level ratchet guidance."""

from __future__ import annotations

import hashlib
import logging
import re
import time

from src.llm.pydantic_client import PydanticAIClient
from src.models import OutlineNode, SectionOutline, SettingsConfig
from src.writing.context_builder import WritingGroundingData
from src.writing.evidence_assembler import build_results_evidence_pack
from src.writing.prompts.outline import build_outline_prompt, fallback_outline_headings

logger = logging.getLogger(__name__)

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _outline_grounding_hash(grounding: WritingGroundingData, citation_catalog: str) -> str:
    payload = grounding.model_dump_json() + "\n" + citation_catalog
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _slugify(value: str) -> str:
    slug = _NON_ALNUM_RE.sub("_", str(value or "").strip().lower()).strip("_")
    return slug or "outline_node"


def _dedupe_nodes(nodes: list[OutlineNode]) -> list[OutlineNode]:
    deduped: list[OutlineNode] = []
    seen: set[str] = set()
    for node in nodes:
        key = f"{node.node_id.casefold()}::{node.heading.casefold()}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(node)
    return deduped


def build_fallback_section_outline(
    section: str,
    grounding: WritingGroundingData,
    citation_catalog: str,
) -> SectionOutline:
    """Build a deterministic outline from the existing writing prompt scaffold."""
    headings = fallback_outline_headings(section, grounding=grounding)
    included_citekeys = list(getattr(grounding, "included_study_citekeys", []) or [])
    nodes = [
        OutlineNode(
            node_id=_slugify(heading),
            heading=heading,
            intent=f"Cover the required {heading.lower()} content for the {section} section using grounded evidence only.",
            required_citekeys=included_citekeys
            if section == "results" and heading.lower() != "study selection"
            else [],
            evidence_chunk_ids=[],
        )
        for heading in headings
    ]
    if not nodes:
        nodes = [
            OutlineNode(
                node_id=_slugify(section),
                heading=section.replace("_", " ").title(),
                intent=f"Cover the core grounded content for the {section} section.",
                required_citekeys=included_citekeys[:3] if section == "results" else [],
                evidence_chunk_ids=[],
            )
        ]
    return SectionOutline(
        section_key=section,
        nodes=_dedupe_nodes(nodes),
        grounding_hash=_outline_grounding_hash(grounding, citation_catalog),
    )


def _merge_results_outline(
    generated: SectionOutline,
    grounding: WritingGroundingData,
    citation_catalog: str,
) -> SectionOutline:
    pack = build_results_evidence_pack(grounding)
    result_citekeys = [study.citekey for study in pack.studies if study.citekey]
    seeded = [
        OutlineNode(
            node_id="study_selection",
            heading="Study Selection",
            intent=pack.study_selection_sentence,
            required_citekeys=[],
            evidence_chunk_ids=[],
        ),
        OutlineNode(
            node_id="study_characteristics",
            heading="Study Characteristics",
            intent=pack.characteristics_summary,
            required_citekeys=result_citekeys,
            evidence_chunk_ids=[],
        ),
        OutlineNode(
            node_id="synthesis_of_findings",
            heading="Synthesis of Findings",
            intent=pack.synthesis_summary,
            required_citekeys=result_citekeys,
            evidence_chunk_ids=[],
        ),
    ]
    merged = list(seeded)
    seen_headings = {node.heading.casefold() for node in seeded}
    for node in generated.nodes:
        if node.heading.casefold() in seen_headings:
            continue
        merged.append(node)
        seen_headings.add(node.heading.casefold())
    return SectionOutline(
        section_key="results",
        nodes=_dedupe_nodes(merged),
        grounding_hash=_outline_grounding_hash(grounding, citation_catalog),
    )


async def generate_section_outline(
    *,
    section: str,
    settings: SettingsConfig,
    grounding: WritingGroundingData,
    citation_catalog: str,
    provider=None,
    on_llm_call=None,
) -> SectionOutline:
    """Generate a section outline with deterministic fallback."""
    fallback = build_fallback_section_outline(section, grounding, citation_catalog)
    agent_cfg = settings.agents.get("writing") or next(iter(settings.agents.values()))
    prompt = build_outline_prompt(section, grounding, citation_catalog)
    client = PydanticAIClient(
        timeout_seconds=float(getattr(getattr(settings, "llm", None), "request_timeout_seconds", 180))
    )
    if provider is not None:
        await provider.reserve_call_slot("writing")
    started = time.perf_counter()
    try:
        outline, tokens_in, tokens_out, cache_write, cache_read, validation_retries = await client.complete_validated(
            prompt,
            model=agent_cfg.model,
            temperature=agent_cfg.temperature,
            response_model=SectionOutline,
        )
        outline = outline.model_copy(
            update={
                "section_key": section,
                "grounding_hash": _outline_grounding_hash(grounding, citation_catalog),
                "nodes": _dedupe_nodes(list(outline.nodes)),
            }
        )
        if section == "results":
            outline = _merge_results_outline(outline, grounding, citation_catalog)
        latency_ms = int((time.perf_counter() - started) * 1000)
        if provider is not None:
            cost_usd = provider.estimate_cost_usd(agent_cfg.model, tokens_in, tokens_out, cache_write, cache_read)
            await provider.log_cost(
                model=agent_cfg.model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                phase="phase_6_writing_outline",
                cache_read_tokens=cache_read,
                cache_write_tokens=cache_write,
            )
        if on_llm_call is not None:
            on_llm_call(
                source="writing",
                status="success",
                details=f"{section} outline",
                records=len(outline.nodes),
                call_type="llm_outline",
                raw_response=outline.model_dump_json(indent=2),
                latency_ms=latency_ms,
                model=agent_cfg.model,
                phase="phase_6_writing",
            )
        if validation_retries > 0:
            logger.info(
                "Section outline for '%s' succeeded after %d validation retry(ies).",
                section,
                validation_retries,
            )
        return outline
    except Exception as exc:
        logger.warning("Outline generation failed for section '%s': %s", section, exc)
        if section == "results":
            return _merge_results_outline(fallback, grounding, citation_catalog)
        return fallback
