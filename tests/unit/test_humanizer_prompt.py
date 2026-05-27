"""Unit tests for humanizer prompt builders."""

from __future__ import annotations

from src.writing.prompts.humanizer_prompt import (
    build_humanize_system_prompt,
    load_humanizer_skill_text,
)


def test_skill_loader_contains_full_reference_markers() -> None:
    text = load_humanizer_skill_text()
    assert "## Step 10: Final Pass/Fail Checklist" in text
    assert "## Step 9: Post-Rewrite Verification Loop" in text


def test_system_prompt_includes_overlay_and_skill() -> None:
    prompt = build_humanize_system_prompt("results")
    assert "Current section: results" in prompt
    assert "FULL HUMANIZER SKILL" in prompt
    assert "Academic Manuscript Overlay" in prompt
