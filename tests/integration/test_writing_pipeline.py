"""Integration tests for writing pipeline."""

from __future__ import annotations

import pytest

from src.models import (
    CandidatePaper,
    FundingInfo,
    PICOConfig,
    ProtocolRegistration,
    ReviewConfig,
    SettingsConfig,
)
from src.models.enums import ReviewType
from src.writing import SectionWriter, StylePatterns, extract_style_patterns
from src.writing.orchestration import build_citation_catalog_from_papers, prepare_writing_context
from src.writing.prompts.sections import SECTIONS, get_section_context, get_section_word_limit


def _minimal_review() -> ReviewConfig:
    return ReviewConfig(
        research_question="How do AI tutors impact learning?",
        review_type=ReviewType.SYSTEMATIC,
        pico=PICOConfig(
            population="Students",
            intervention="AI tutors",
            comparison="Traditional",
            outcome="Learning",
        ),
        keywords=["AI tutor"],
        domain="AI in education",
        scope="",
        inclusion_criteria=["AI in education"],
        exclusion_criteria=["non-AI"],
        date_range_start=2020,
        date_range_end=2026,
        target_databases=["pubmed"],
        target_sections=[],
        protocol=ProtocolRegistration(),
        funding=FundingInfo(),
        conflicts_of_interest="",
        search_overrides={},
    )


def _minimal_settings() -> SettingsConfig:
    from src.models.config import AgentConfig
    return SettingsConfig(
        agents={
            "writing": AgentConfig(model="google-gla:gemini-2.5-pro", temperature=0.2),
        },
    )


def test_extract_style_patterns_returns_style_patterns() -> None:
    patterns = extract_style_patterns(["Paper one abstract.", "Paper two abstract."])
    assert isinstance(patterns, StylePatterns)
    assert isinstance(patterns.sentence_openings, list)
    assert isinstance(patterns.vocabulary, list)


def test_build_citation_catalog_from_papers() -> None:
    papers = [
        CandidatePaper(
            paper_id="p1",
            title="AI Tutors in Education",
            authors=["Smith J", "Doe A"],
            year=2023,
            source_database="pubmed",
            source_category="database",
        ),
    ]
    catalog = build_citation_catalog_from_papers(papers)
    assert "AI Tutors" in catalog
    assert "2023" in catalog


def test_prepare_writing_context() -> None:
    papers = [
        CandidatePaper(
            paper_id="p1",
            title="Test",
            authors=[],
            year=2023,
            source_database="pubmed",
            source_category="database",
        ),
    ]
    settings = _minimal_settings()
    patterns, catalog = prepare_writing_context(papers, None, settings)
    assert isinstance(patterns, StylePatterns)
    assert "Test" in catalog


def test_section_writer_builds_prompt() -> None:
    review = _minimal_review()
    settings = _minimal_settings()
    writer = SectionWriter(review=review, settings=settings, citation_catalog="")
    prompt = writer._build_section_prompt("introduction", "Background context here.")
    assert "introduction" in prompt.lower()
    assert "AI tutors" in prompt
    assert "Of course" in prompt or "prohibited" in prompt.lower()


def test_section_prompts_exist() -> None:
    assert len(SECTIONS) == 6
    for section in SECTIONS:
        ctx = get_section_context(section)
        assert len(ctx) > 0
    assert get_section_word_limit("abstract") == 250
    assert get_section_word_limit("introduction") is None
