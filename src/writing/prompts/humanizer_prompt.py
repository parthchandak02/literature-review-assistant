"""Prompt builders for runtime humanizer behavior."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from src.writing.humanizer_checks import HumanizerFlag

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SKILL_SOURCE_PATH = _REPO_ROOT / "reference" / "humanizer-skill.md"
_OVERLAY_PATH = Path(__file__).resolve().with_name("humanizer_academic_overlay.md")


@lru_cache(maxsize=1)
def load_humanizer_skill_text() -> str:
    """Return the full humanizer skill text from the canonical source."""
    return _SKILL_SOURCE_PATH.read_text(encoding="utf-8").strip()


@lru_cache(maxsize=1)
def load_humanizer_overlay_text() -> str:
    """Return manuscript-specific runtime overlay guidance."""
    return _OVERLAY_PATH.read_text(encoding="utf-8").strip()


def build_humanize_system_prompt(section: str | None = None) -> str:
    """Build the primary humanizer prompt with full skill + manuscript overlay."""
    section_hint = section or "unknown_section"
    return (
        "You are an expert academic editor for systematic review manuscripts.\n\n"
        f"Current section: {section_hint}\n\n"
        "MANDATORY INVARIANTS:\n"
        "- Do not change citation keys in square brackets.\n"
        "- Do not add or remove citations.\n"
        "- Do not change numeric values, percentages, confidence intervals, p-values, or units.\n"
        "- Do not change section structure or headings.\n"
        "- Return only revised section text.\n\n"
        "MANUSCRIPT OVERLAY:\n"
        f"{load_humanizer_overlay_text()}\n\n"
        "FULL HUMANIZER SKILL (apply all checks and rewrite discipline):\n"
        f"{load_humanizer_skill_text()}\n"
    )


def build_humanize_repair_prompt(section: str, text: str, flags: list[HumanizerFlag]) -> str:
    """Build a compact targeted repair prompt for unresolved high-severity flags."""
    high_flags = [f for f in flags if f.tier == "high"][:12]
    if not high_flags:
        return text
    flag_block = "\n".join(f"- {flag.code}: {flag.message}" for flag in high_flags)
    return (
        "Perform a targeted repair pass for the manuscript section below.\n"
        f"Section: {section}\n\n"
        "Resolve only these high-severity humanizer findings while preserving all citations, numerics, "
        "and section structure exactly:\n"
        f"{flag_block}\n\n"
        "Section text:\n"
        f"{text}\n\n"
        "Return only revised section text."
    )
