"""Unit tests for PICO-aware HyDE enhancements (Enhancement #5)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pytest

from src.rag.hyde import _build_pico_block, _HYDE_PROMPT, generate_hyde_document


@dataclass
class _MockPICO:
    population: str = ""
    intervention: str = ""
    comparison: str = ""
    outcome: str = ""


def test_build_pico_block_all_fields() -> None:
    """All four PICO fields -> block contains all four labels."""
    pico = _MockPICO(
        population="elderly patients over 65",
        intervention="atorvastatin 10mg daily",
        comparison="placebo",
        outcome="LDL-C reduction",
    )
    block = _build_pico_block(pico)
    assert "Population" in block
    assert "Intervention" in block
    assert "Comparison" in block
    assert "Outcome" in block
    assert "elderly patients over 65" in block
    assert "atorvastatin 10mg daily" in block


def test_build_pico_block_partial_fields() -> None:
    """Only population set -> block contains Population only, no empty labels."""
    pico = _MockPICO(population="children aged 5-12")
    block = _build_pico_block(pico)
    assert "Population" in block
    assert "children aged 5-12" in block
    assert "Intervention" not in block
    assert "Comparison" not in block
    assert "Outcome" not in block


def test_build_pico_block_all_empty() -> None:
    """All fields blank -> returns empty string."""
    pico = _MockPICO()
    block = _build_pico_block(pico)
    assert block == ""


def test_build_pico_block_none() -> None:
    """pico=None -> returns empty string."""
    block = _build_pico_block(None)
    assert block == ""


def test_hyde_prompt_includes_pico_block() -> None:
    """When PICO block is injected, the rendered prompt contains PICO terms."""
    pico = _MockPICO(
        population="adults with type 2 diabetes",
        intervention="metformin",
        comparison="diet alone",
        outcome="HbA1c reduction",
    )
    block = _build_pico_block(pico)
    prompt = _HYDE_PROMPT.format(
        section="results (summarising key findings)",
        research_question="What is the effect of metformin on HbA1c?",
        pico_block=block,
    )
    assert "adults with type 2 diabetes" in prompt
    assert "metformin" in prompt
    assert "HbA1c reduction" in prompt


def test_hyde_prompt_no_pico_renders_cleanly() -> None:
    """When pico block is empty, the prompt renders without extra whitespace artifacts."""
    prompt = _HYDE_PROMPT.format(
        section="methods (describing search strategy)",
        research_question="What is the effect of exercise on depression?",
        pico_block="",
    )
    assert "What is the effect of exercise on depression?" in prompt
    # No raw '{pico_block}' literal left in the rendered string.
    assert "{pico_block}" not in prompt


@pytest.mark.asyncio
async def test_hyde_abstract_returns_empty_without_calling_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """generate_hyde_document for 'abstract' returns '' before constructing any Agent."""

    def _no_agent(*args: object, **kwargs: object) -> None:
        raise AssertionError("Agent should not be constructed for the abstract section")

    monkeypatch.setattr("src.rag.hyde.Agent", _no_agent)

    result = await generate_hyde_document(
        section="abstract",
        research_question="Any question.",
    )
    assert result == ""
