"""Active learning: refine screening criteria from human corrections.

When a human reviewer overrides AI screening decisions via the approve-screening
endpoint, this module:
1. Persists the corrections to screening_corrections table
2. Calls CriteriaRefinementAgent (pro-tier LLM) to generate refined criteria
3. Saves the refined criteria to learned_criteria table
4. Provides a function to load refined criteria for injection into screener prompts

All text is sanitized before DB writes to prevent prompt injection.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

import aiosqlite

logger = logging.getLogger(__name__)

_MAX_CRITERION_LENGTH = 500
_INJECTION_PATTERNS = re.compile(
    r"(ignore previous|ignore all|forget|disregard|new instruction|system prompt)",
    re.IGNORECASE,
)

_REFINEMENT_PROMPT_TEMPLATE = (
    "You are a systematic review screening expert.\n"
    "A human reviewer has corrected the following AI screening decisions:\n\n"
    "{corrections}\n\n"
    "Based on these corrections, derive 1-3 refined screening criteria that would "
    "have led to the correct decisions. Each criterion should be a single, clear "
    "statement of what SHOULD be included or excluded.\n\n"
    "Format your response as JSON:\n"
    "[\n"
    "  {{\"criterion_type\": \"refined_inclusion\", \"criterion_text\": \"...\"}},\n"
    "  {{\"criterion_type\": \"refined_exclusion\", \"criterion_text\": \"...\"}}\n"
    "]\n\n"
    "Return ONLY valid JSON -- no markdown, no explanation.\n"
    "Each criterion_text must be <= 500 characters.\n"
)


@dataclass
class ScreeningCorrection:
    """A single human override of an AI screening decision."""

    paper_id: str
    ai_decision: str
    human_decision: str
    human_reason: Optional[str] = None


@dataclass
class LearnedCriterion:
    """A refined criterion generated from human corrections."""

    criterion_type: str  # 'refined_inclusion' | 'refined_exclusion'
    criterion_text: str
    source_paper_ids: list[str]
    version: int = 1


def _sanitize_criterion(text: str) -> str:
    """Strip prompt injection patterns and enforce length limit."""
    cleaned = _INJECTION_PATTERNS.sub("[REMOVED]", text)
    return cleaned[:_MAX_CRITERION_LENGTH].strip()


def _format_corrections_for_prompt(
    corrections: list[ScreeningCorrection],
    papers: dict[str, str],
) -> str:
    """Format corrections as a readable block for the LLM prompt."""
    lines: list[str] = []
    for c in corrections[:10]:
        title = papers.get(c.paper_id, c.paper_id[:16])[:80]
        line = f"- Paper: \"{title}\""
        line += f"\n  AI decision: {c.ai_decision} -> Human decision: {c.human_decision}"
        if c.human_reason:
            line += f"\n  Reason: {c.human_reason[:200]}"
        lines.append(line)
    return "\n".join(lines)


def _call_refinement_llm_sync(
    corrections: list[ScreeningCorrection],
    papers: dict[str, str],
    model_name: str,
    api_key: str,
) -> list[LearnedCriterion]:
    """Synchronous LLM call for criteria refinement."""
    try:
        import google.generativeai as genai  # type: ignore[import-untyped]
    except ImportError:
        return []

    if not api_key:
        return []

    genai.configure(api_key=api_key)
    prompt = _REFINEMENT_PROMPT_TEMPLATE.format(
        corrections=_format_corrections_for_prompt(corrections, papers)
    )

    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        if not isinstance(data, list):
            return []

        source_ids = [c.paper_id for c in corrections]
        results: list[LearnedCriterion] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            ct = item.get("criterion_type", "refined_inclusion")
            text = item.get("criterion_text", "")
            if not text:
                continue
            results.append(
                LearnedCriterion(
                    criterion_type=ct,
                    criterion_text=_sanitize_criterion(text),
                    source_paper_ids=source_ids,
                )
            )
        return results

    except (json.JSONDecodeError, Exception) as exc:
        logger.warning("Criteria refinement LLM failed: %s", exc)
        return []


async def refine_criteria_from_corrections(
    corrections: list[ScreeningCorrection],
    papers: dict[str, str],
    model_name: str = "gemini-2.5-pro",
    api_key: Optional[str] = None,
) -> list[LearnedCriterion]:
    """Generate refined screening criteria from human corrections.

    Args:
        corrections: List of human override decisions.
        papers: Dict mapping paper_id -> title for context.
        model_name: LLM to use for refinement.
        api_key: Gemini API key.

    Returns:
        List of LearnedCriterion objects.
    """
    if not corrections:
        return []

    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    raw_model = model_name.replace("google-gla:", "").replace("google-vertex:", "")

    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _call_refinement_llm_sync, corrections, papers, raw_model, key
    )


async def save_corrections(
    db: aiosqlite.Connection,
    workflow_id: str,
    corrections: list[ScreeningCorrection],
) -> None:
    """Persist human corrections to screening_corrections table."""
    for c in corrections:
        await db.execute(
            """
            INSERT INTO screening_corrections
                (workflow_id, paper_id, ai_decision, human_decision, human_reason)
            VALUES (?, ?, ?, ?, ?)
            """,
            (workflow_id, c.paper_id, c.ai_decision, c.human_decision, c.human_reason),
        )
    await db.commit()


async def save_learned_criteria(
    db: aiosqlite.Connection,
    workflow_id: str,
    criteria: list[LearnedCriterion],
) -> None:
    """Persist learned criteria to learned_criteria table."""
    for c in criteria:
        await db.execute(
            """
            INSERT INTO learned_criteria
                (workflow_id, criterion_type, criterion_text, source_paper_ids, version)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                workflow_id,
                c.criterion_type,
                c.criterion_text,
                json.dumps(c.source_paper_ids),
                c.version,
            ),
        )
    await db.commit()


async def load_learned_criteria(
    db: aiosqlite.Connection,
    workflow_id: str,
) -> list[LearnedCriterion]:
    """Load all learned criteria for a workflow."""
    criteria: list[LearnedCriterion] = []
    async with db.execute(
        """
        SELECT criterion_type, criterion_text, source_paper_ids, version
        FROM learned_criteria
        WHERE workflow_id = ?
        ORDER BY id ASC
        """,
        (workflow_id,),
    ) as cursor:
        async for row in cursor:
            try:
                source_ids = json.loads(row[2]) if row[2] else []
            except (json.JSONDecodeError, TypeError):
                source_ids = []
            criteria.append(
                LearnedCriterion(
                    criterion_type=row[0],
                    criterion_text=row[1],
                    source_paper_ids=source_ids,
                    version=row[3] or 1,
                )
            )
    return criteria


def format_learned_criteria_block(criteria: list[LearnedCriterion]) -> str:
    """Format learned criteria for injection into screener prompt templates.

    Returns an empty string if no criteria exist (backward-compatible behavior).
    """
    if not criteria:
        return ""

    inclusions = [c for c in criteria if c.criterion_type == "refined_inclusion"]
    exclusions = [c for c in criteria if c.criterion_type == "refined_exclusion"]

    lines: list[str] = ["REFINED CRITERIA (from prior human review):"]
    if inclusions:
        lines.append("Additional inclusion criteria:")
        for c in inclusions:
            lines.append(f"  - {c.criterion_text}")
    if exclusions:
        lines.append("Additional exclusion criteria:")
        for c in exclusions:
            lines.append(f"  - {c.criterion_text}")
    lines.append("")
    return "\n".join(lines)
