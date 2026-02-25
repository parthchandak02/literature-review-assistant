"""Integration tests for writing pipeline."""

from __future__ import annotations

import pytest

from src.citation.ledger import CitationLedger
from src.db.database import get_db
from src.db.repositories import CitationRepository
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
from src.writing.orchestration import (
    build_citation_catalog_from_papers,
    prepare_writing_context,
    register_citations_from_papers,
)
from src.writing.prompts.sections import (
    SECTIONS,
    get_section_context,
    get_section_word_limit,
)


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
    assert get_section_word_limit("abstract") == 300
    assert get_section_word_limit("introduction") == 700


@pytest.mark.asyncio
async def test_register_citations_from_papers() -> None:
    """Citation pre-registration populates citekeys so validate_section passes."""
    import tempfile
    from pathlib import Path

    papers = [
        CandidatePaper(
            paper_id="p1",
            title="AI Tutors in Education",
            authors=["Smith J", "Doe A"],
            year=2023,
            source_database="pubmed",
            source_category="database",
        ),
        CandidatePaper(
            paper_id="p2",
            title="Another Study",
            authors=["Jones M"],
            year=2024,
            source_database="arxiv",
            source_category="database",
        ),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        async with get_db(str(db_path)) as db:
            repo = CitationRepository(db)
            await register_citations_from_papers(repo, papers)
            citekeys = await repo.get_citekeys()
            assert len(citekeys) >= 2
            assert any("Smith" in k or "2023" in k or "Jones" in k or "2024" in k for k in citekeys)
            ledger = CitationLedger(repo)
            text_with_citekey = f"See [{citekeys[0]}] for details."
            result = await ledger.validate_section("test", text_with_citekey)
            assert citekeys[0] not in result.unresolved_citations
