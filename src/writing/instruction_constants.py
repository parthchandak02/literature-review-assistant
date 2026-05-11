"""Shared writing instruction constants used across grounding and prompts."""

from __future__ import annotations

NARRATIVE_ONLY_META_ANALYSIS_RULE = (
    "Do NOT write 'we conducted a meta-analysis', 'pooled effect sizes', "
    "'meta-analysis showed', or any phrase implying quantitative pooling was performed. "
    "Write ONLY that narrative synthesis was conducted."
)
