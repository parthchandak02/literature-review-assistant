"""Prompt helpers for pre-writing section outline generation."""

from __future__ import annotations

import re

from src.writing.context_builder import WritingGroundingData, format_grounding_block
from src.writing.prompts.base import PROHIBITED_PHRASES, get_citation_catalog_constraint
from src.writing.prompts.sections import get_section_context

_SUBHEADING_RE = re.compile(r"^###\s+(.+)$", flags=re.MULTILINE)

_OUTLINE_HINTS: dict[str, list[str]] = {
    "abstract": [
        "Cover the six structured abstract fields in order.",
        "Keep every node factual and grounded in the provided data block.",
    ],
    "introduction": [
        "Move from topic importance to literature gap to review objective.",
        "Prefer broad framing nodes rather than study-by-study narration.",
    ],
    "methods": [
        "Mirror the PRISMA-aligned procedural steps in the data block.",
        "Preserve methodology disclosure nodes before synthesis details.",
    ],
    "results": [
        "Keep study selection, characteristics, and synthesis nodes explicit.",
        "Reserve citekeys for included primary studies only.",
    ],
    "discussion": [
        "Start with principal findings before comparison and limitations.",
        "End with implications anchored to the review question.",
    ],
    "conclusion": [
        "Focus on the answer to the review question, not process recap.",
        "Keep the close brief and high signal.",
    ],
}

_MANUAL_FALLBACK_HEADINGS: dict[str, list[str]] = {
    "abstract": [
        "Background",
        "Objectives",
        "Methods",
        "Results",
        "Conclusions",
        "Keywords",
    ],
    "methods": [
        "Eligibility Criteria",
        "Information Sources",
        "Selection Process",
        "Synthesis Methods",
    ],
    "results": [
        "Study Selection",
        "Study Characteristics",
        "Synthesis of Findings",
    ],
    "discussion": [
        "Principal Findings",
        "Comparison with Prior Work",
        "Strengths and Limitations",
        "Implications for Practice",
        "Implications for Research",
    ],
}


def fallback_outline_headings(section: str, grounding: WritingGroundingData | None = None) -> list[str]:
    """Extract deterministic fallback headings from the existing section prompt."""
    normalized = section.lower().strip()
    manual = _MANUAL_FALLBACK_HEADINGS.get(normalized)
    if manual:
        return list(manual)
    prompt_context = get_section_context(normalized, grounding=grounding)
    headings = [match.group(1).strip() for match in _SUBHEADING_RE.finditer(prompt_context)]
    deduped: list[str] = []
    seen: set[str] = set()
    for heading in headings:
        key = heading.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(heading)
    return deduped


def build_outline_prompt(
    section: str,
    grounding: WritingGroundingData,
    citation_catalog: str,
) -> str:
    """Return the outline-generation prompt for one section."""
    hints = _OUTLINE_HINTS.get(section.lower(), [])
    fallback_headings = fallback_outline_headings(section, grounding=grounding)
    hint_lines = "\n".join(f"- {hint}" for hint in hints)
    fallback_lines = "\n".join(f"- {heading}" for heading in fallback_headings) or "- No fixed headings"
    return (
        "Role: Build a section outline for a systematic review manuscript.\n"
        f"Section: {section}\n\n"
        "Return JSON only. Build a concise, evidence-grounded outline that can be used as a stable "
        "judge for downstream ratchet scoring.\n"
        "Each node must have:\n"
        "- node_id: stable snake_case identifier\n"
        "- heading: subsection or paragraph label\n"
        "- intent: 1-2 sentence description of what the node must cover\n"
        "- required_citekeys: citekeys that should appear in prose for this node when applicable\n"
        "- evidence_chunk_ids: optional retrieval chunk ids when they are explicitly available; otherwise []\n\n"
        "Rules:\n"
        "- Use only citekeys present in the citation catalog.\n"
        "- Do not invent facts, statistics, or studies.\n"
        "- Prefer 3-6 nodes per section.\n"
        "- Preserve required headings when the section prompt already names them.\n"
        "- Results should focus on deterministic evidence coverage, not stylistic prose.\n\n"
        "Section-specific hints:\n"
        f"{hint_lines or '- None'}\n\n"
        "Existing heading scaffold from the writing prompt:\n"
        f"{fallback_lines}\n\n"
        "FACTUAL DATA BLOCK:\n"
        f"{format_grounding_block(grounding)}\n\n"
        f"{get_citation_catalog_constraint(citation_catalog)}\n\n"
        f"{PROHIBITED_PHRASES}\n"
    )
