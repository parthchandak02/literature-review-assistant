"""Agentic placement planner for inline custom diagram insertion."""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel

from src.llm.pydantic_client import PydanticAIClient
from src.models.diagrams import (
    DiagramBriefPack,
    DiagramPlacementDecision,
    DiagramPlacementPlan,
    ResearchDiagramBrief,
)

logger = logging.getLogger(__name__)

_DEFAULT_SECTION_BY_TYPE: dict[str, str] = {
    "method_flow": "methods",
    "layered_architecture": "results",
    "evidence_map": "discussion",
    "theme_relationship": "discussion",
}


class _PlacementEnvelope(BaseModel):
    decisions: list[DiagramPlacementDecision]


def _split_sections(markdown_body: str) -> dict[str, str]:
    """Return canonical section-key to section-body mapping."""
    section_map: dict[str, list[str]] = {
        k: [] for k in ("introduction", "methods", "results", "discussion", "conclusion")
    }
    current: str | None = None
    heading_re = re.compile(r"^##\s+(.+?)\s*$")
    for raw_line in markdown_body.splitlines():
        m = heading_re.match(raw_line.strip())
        if m:
            heading = m.group(1).strip().lower()
            if heading.startswith("introduction"):
                current = "introduction"
            elif heading.startswith("methods"):
                current = "methods"
            elif heading.startswith("results"):
                current = "results"
            elif heading.startswith("discussion"):
                current = "discussion"
            elif heading.startswith("conclusion"):
                current = "conclusion"
            else:
                current = None
            continue
        if current:
            section_map[current].append(raw_line)
    return {k: "\n".join(v).strip() for k, v in section_map.items()}


def _pick_anchor(section_text: str, default_anchor: str) -> str:
    """Pick a short anchor phrase from section text for deterministic fallback."""
    stripped = section_text.strip()
    if not stripped:
        return default_anchor
    sentence = re.split(r"(?<=[.!?])\s+", stripped, maxsplit=1)[0].strip()
    sentence = re.sub(r"\s+", " ", sentence)
    return sentence[:220] if sentence else default_anchor


def _fallback_decision(brief: ResearchDiagramBrief, section_text: str) -> DiagramPlacementDecision:
    target = _DEFAULT_SECTION_BY_TYPE.get(brief.diagram_type, "results")
    anchor = _pick_anchor(section_text, f"{target.title()} summary")
    return DiagramPlacementDecision(
        diagram_id=brief.diagram_id,
        target_section=target,  # type: ignore[arg-type]
        anchor_text=anchor,
        fallback_policy="append_to_figures_section",
        confidence=0.55,
        rationale="Deterministic fallback placement.",
    )


async def plan_inline_diagram_placements(
    *,
    workflow_id: str,
    brief_pack: DiagramBriefPack,
    manuscript_body: str,
    model: str,
    temperature: float = 0.1,
    max_validation_retries: int = 2,
) -> tuple[DiagramPlacementPlan, dict[str, int]]:
    """Generate agent-selected placement decisions with deterministic fallback."""
    section_map = _split_sections(manuscript_body)
    section_digest = "\n\n".join(f"## {k}\n{(v[:1400] if v else '[missing section]')}" for k, v in section_map.items())
    brief_digest = []
    for brief in brief_pack.diagrams:
        labels = ", ".join(brief.required_labels[:6]) or "n/a"
        brief_digest.append(
            "\n".join(
                [
                    f"- diagram_id: {brief.diagram_id}",
                    f"  type: {brief.diagram_type}",
                    f"  title: {brief.title}",
                    f"  objective: {brief.objective}",
                    f"  required_labels: {labels}",
                ]
            )
        )
    prompt = (
        "You are deciding inline placement for custom research diagrams in a manuscript.\n"
        "Choose exactly one target section and one anchor_text for each diagram_id.\n"
        "Allowed sections: introduction, methods, results, discussion, conclusion.\n"
        "Rules:\n"
        "- method_flow usually belongs in methods/results.\n"
        "- architecture/evidence maps usually belong in results/discussion.\n"
        "- anchor_text must be an exact short phrase from that section snippet.\n"
        "- prefer spreading diagrams across relevant sections, not all in one section.\n"
        "- fallback_policy must be append_to_figures_section.\n"
        "- confidence in [0,1].\n\n"
        f"Workflow: {workflow_id}\n\n"
        "Diagram briefs:\n"
        f"{chr(10).join(brief_digest)}\n\n"
        "Manuscript sections:\n"
        f"{section_digest}\n"
    )

    usage = {"tokens_in": 0, "tokens_out": 0, "cache_write_tokens": 0, "cache_read_tokens": 0, "validation_retries": 0}
    try:
        client = PydanticAIClient()
        parsed, tok_in, tok_out, cache_write, cache_read, retries_used = await client.complete_validated(
            prompt,
            model=model,
            temperature=temperature,
            response_model=_PlacementEnvelope,
            max_validation_retries=max_validation_retries,
        )
        usage = {
            "tokens_in": int(tok_in),
            "tokens_out": int(tok_out),
            "cache_write_tokens": int(cache_write),
            "cache_read_tokens": int(cache_read),
            "validation_retries": int(retries_used),
        }
        by_id: dict[str, DiagramPlacementDecision] = {}
        for decision in parsed.decisions:
            by_id[decision.diagram_id] = decision

        decisions: list[DiagramPlacementDecision] = []
        warnings: list[str] = []
        for brief in brief_pack.diagrams:
            decision = by_id.get(brief.diagram_id)
            if decision is None:
                warnings.append(f"{brief.diagram_id}: missing placement decision; used fallback")
                decision = _fallback_decision(
                    brief, section_map.get(_DEFAULT_SECTION_BY_TYPE.get(brief.diagram_type, "results"), "")
                )
            decisions.append(decision)
        return DiagramPlacementPlan(workflow_id=workflow_id, decisions=decisions, warnings=warnings), usage
    except Exception as exc:  # noqa: BLE001
        logger.warning("Diagram placement planner failed; using deterministic fallback: %s", exc)
        fallback: list[DiagramPlacementDecision] = []
        for brief in brief_pack.diagrams:
            target = _DEFAULT_SECTION_BY_TYPE.get(brief.diagram_type, "results")
            fallback.append(_fallback_decision(brief, section_map.get(target, "")))
        return (
            DiagramPlacementPlan(
                workflow_id=workflow_id,
                decisions=fallback,
                warnings=[f"placement agent failed: {exc}"],
            ),
            usage,
        )
