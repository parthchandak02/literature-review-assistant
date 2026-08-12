"""Unit tests for humanizer prompt builders."""

from __future__ import annotations

import pytest

from src.writing.prompts.humanizer_prompt import (
    _SKILL_SOURCE_PATH,
    build_humanize_system_prompt,
    load_humanizer_skill_text,
)


@pytest.mark.skipif(
    not _SKILL_SOURCE_PATH.is_file(),
    reason="reference/humanizer-skill.md not yet synced from blader/humanizer",
)
def test_skill_loader_contains_full_reference_markers() -> None:
    text = load_humanizer_skill_text()
    assert "## Step 10: Final Pass/Fail Checklist" in text
    assert "## Step 9: Post-Rewrite Verification Loop" in text


def test_load_humanizer_skill_text_returns_string_without_raising() -> None:
    text = load_humanizer_skill_text()
    assert isinstance(text, str)


def test_system_prompt_overlay_only_when_skill_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.writing.prompts.humanizer_prompt.load_humanizer_skill_text",
        lambda: "",
    )
    prompt = build_humanize_system_prompt("results")
    assert "Current section: results" in prompt
    assert "MANDATORY INVARIANTS" in prompt
    assert "Do not change citation keys in square brackets." in prompt
    assert "Academic Manuscript Overlay" in prompt
    assert "FULL HUMANIZER SKILL" not in prompt


@pytest.mark.skipif(
    not _SKILL_SOURCE_PATH.is_file(),
    reason="reference/humanizer-skill.md not yet synced from blader/humanizer",
)
def test_system_prompt_includes_overlay_and_skill() -> None:
    prompt = build_humanize_system_prompt("results")
    assert "Current section: results" in prompt
    assert "FULL HUMANIZER SKILL" in prompt
    assert "Academic Manuscript Overlay" in prompt
