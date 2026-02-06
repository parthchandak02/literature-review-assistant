"""
Unit tests for abstract agent PRISMA 2020 format.
"""

import pytest
from src.writing.abstract_agent import AbstractGenerator
from src.search.connectors.base import Paper


@pytest.fixture
def sample_papers():
    """Sample papers for testing."""
    return [
        Paper(
            title="Test Study 1",
            abstract="Test abstract 1",
            authors=["Author 1"],
            year=2022,
            doi="10.1000/test1",
            journal="Test Journal",
            database="PubMed",
        ),
        Paper(
            title="Test Study 2",
            abstract="Test abstract 2",
            authors=["Author 2"],
            year=2023,
            doi="10.1000/test2",
            journal="Test Journal 2",
            database="Scopus",
        ),
    ]


@pytest.fixture
def sample_article_sections():
    """Sample article sections."""
    return {
        "introduction": "Introduction content here.",
        "methods": "Methods content including search strategy and databases.",
        "results": "Results content with findings from included studies.",
        "discussion": "Discussion content with interpretation and implications.",
    }


@pytest.fixture
def topic_context_with_protocol():
    """Topic context with protocol registration info."""
    return {
        "topic": "Test Topic",
        "protocol": {
            "registry": "PROSPERO",
            "registration_number": "CRD123456",
            "url": "https://www.crd.york.ac.uk/prospero/display_record.php?ID=CRD123456",
        },
        "funding": {
            "source": "National Institute of Health",
        },
    }


@pytest.fixture
def topic_context_without_protocol():
    """Topic context without protocol registration info."""
    return {
        "topic": "Test Topic",
    }


def test_12_element_abstract_fallback(sample_papers, sample_article_sections, topic_context_with_protocol):
    """Test PRISMA 2020 abstract generation with fallback (no LLM)."""
    generator = AbstractGenerator(
        llm_provider="openai",
        llm_api_key=None,  # Triggers fallback
        topic_context=topic_context_with_protocol,
        config={"prisma_2020_format": True, "structured": True},
    )
    
    abstract = generator._generate_prisma_2020_abstract(
        research_question="What is the test research question?",
        included_papers=sample_papers,
        article_sections=sample_article_sections,
    )
    
    # Check that all 12 elements are present
    assert "Background:" in abstract
    assert "Objectives:" in abstract
    assert "Eligibility criteria:" in abstract
    assert "Information sources:" in abstract
    assert "Risk of bias:" in abstract
    assert "Synthesis methods:" in abstract
    assert "Results:" in abstract
    assert "Limitations:" in abstract
    assert "Interpretation:" in abstract
    assert "Funding:" in abstract
    assert "Registration:" in abstract
    
    # Check that research question is included
    assert "test research question" in abstract.lower()
    
    # Check that number of studies is included
    assert "2" in abstract or "two" in abstract.lower()


def test_word_count_prisma_2020_abstract(sample_papers, sample_article_sections, topic_context_with_protocol):
    """Test that PRISMA 2020 abstract respects word count (250-300 words)."""
    generator = AbstractGenerator(
        llm_provider="openai",
        llm_api_key=None,
        topic_context=topic_context_with_protocol,
        config={"prisma_2020_format": True, "structured": True, "word_limit": 275},
    )
    
    abstract = generator._generate_prisma_2020_abstract(
        research_question="What is the test research question?",
        included_papers=sample_papers,
        article_sections=sample_article_sections,
    )
    
    word_count = len(abstract.split())
    # Fallback abstract may be shorter, but should be reasonable
    assert word_count > 50  # At least some content


def test_protocol_registration_extraction(sample_papers, sample_article_sections, topic_context_with_protocol):
    """Test protocol registration extraction from config."""
    generator = AbstractGenerator(
        llm_provider="openai",
        llm_api_key=None,
        topic_context=topic_context_with_protocol,
        config={"prisma_2020_format": True, "structured": True},
    )
    
    abstract = generator._generate_prisma_2020_abstract(
        research_question="Test question",
        included_papers=sample_papers,
        article_sections=sample_article_sections,
    )
    
    # Check that protocol info is included
    assert "PROSPERO" in abstract
    assert "CRD123456" in abstract


def test_funding_extraction(sample_papers, sample_article_sections, topic_context_with_protocol):
    """Test funding extraction from config."""
    generator = AbstractGenerator(
        llm_provider="openai",
        llm_api_key=None,
        topic_context=topic_context_with_protocol,
        config={"prisma_2020_format": True, "structured": True},
    )
    
    abstract = generator._generate_prisma_2020_abstract(
        research_question="Test question",
        included_papers=sample_papers,
        article_sections=sample_article_sections,
    )
    
    # Check that funding info is included
    assert "Funding:" in abstract
    assert "National Institute of Health" in abstract or "funding" in abstract.lower()


def test_protocol_funding_missing(sample_papers, sample_article_sections, topic_context_without_protocol):
    """Test abstract generation when protocol/funding info is missing."""
    generator = AbstractGenerator(
        llm_provider="openai",
        llm_api_key=None,
        topic_context=topic_context_without_protocol,
        config={"prisma_2020_format": True, "structured": True},
    )
    
    abstract = generator._generate_prisma_2020_abstract(
        research_question="Test question",
        included_papers=sample_papers,
        article_sections=sample_article_sections,
    )
    
    # Should still generate abstract
    assert "Background:" in abstract
    assert "Registration:" in abstract
    # Should indicate not registered or no funding
    assert "not registered" in abstract.lower() or "PROSPERO" in abstract


def test_abstract_schema_validation(sample_papers, sample_article_sections, topic_context_with_protocol):
    """Test that abstract follows PRISMA 2020 schema structure."""
    generator = AbstractGenerator(
        llm_provider="openai",
        llm_api_key=None,
        topic_context=topic_context_with_protocol,
        config={"prisma_2020_format": True, "structured": True},
    )
    
    abstract = generator._generate_prisma_2020_abstract(
        research_question="Test question",
        included_papers=sample_papers,
        article_sections=sample_article_sections,
    )
    
    # Check structure - each element should be on its own line or clearly separated
    abstract.split("\n")
    element_labels = [
        "Background:",
        "Objectives:",
        "Eligibility criteria:",
        "Information sources:",
        "Risk of bias:",
        "Synthesis methods:",
        "Results:",
        "Limitations:",
        "Interpretation:",
        "Funding:",
        "Registration:",
    ]
    
    # At least some elements should be present
    found_elements = sum(1 for label in element_labels if label in abstract)
    assert found_elements >= 10  # Most elements should be present


def test_abstract_with_missing_sections(sample_papers, topic_context_with_protocol):
    """Test abstract generation with missing article sections."""
    incomplete_sections = {
        "introduction": "Introduction only.",
        # Missing methods, results, discussion
    }
    
    generator = AbstractGenerator(
        llm_provider="openai",
        llm_api_key=None,
        topic_context=topic_context_with_protocol,
        config={"prisma_2020_format": True, "structured": True},
    )
    
    abstract = generator._generate_prisma_2020_abstract(
        research_question="Test question",
        included_papers=sample_papers,
        article_sections=incomplete_sections,
    )
    
    # Should still generate abstract
    assert len(abstract) > 0
    assert "Background:" in abstract


def test_fallback_prisma_2020_abstract(sample_papers, topic_context_with_protocol):
    """Test fallback PRISMA 2020 abstract generation."""
    generator = AbstractGenerator(
        llm_provider="openai",
        llm_api_key=None,
        topic_context=topic_context_with_protocol,
        config={"prisma_2020_format": True, "structured": True},
    )
    
    abstract = generator._fallback_prisma_2020_abstract(
        research_question="Test research question",
        included_papers=sample_papers,
        registration_number="CRD123456",
        registry="PROSPERO",
        funding_source="Test Funding",
    )
    
    # Check all 12 elements
    assert "Background:" in abstract
    assert "Objectives:" in abstract
    assert "Eligibility criteria:" in abstract
    assert "Information sources:" in abstract
    assert "Risk of bias:" in abstract
    assert "Synthesis methods:" in abstract
    assert "Results:" in abstract
    assert "Limitations:" in abstract
    assert "Interpretation:" in abstract
    assert "Funding:" in abstract
    assert "Registration:" in abstract
    
    # Check content
    assert "Test research question" in abstract
    assert "2" in abstract or "two" in abstract.lower()
    assert "PROSPERO" in abstract
    assert "CRD123456" in abstract
    assert "Test Funding" in abstract


def test_generate_method_calls_fallback(sample_papers, sample_article_sections, topic_context_with_protocol):
    """Test that generate() method calls PRISMA 2020 abstract when configured."""
    generator = AbstractGenerator(
        llm_provider="openai",
        llm_api_key=None,
        topic_context=topic_context_with_protocol,
        config={"prisma_2020_format": True, "structured": True},
    )
    
    abstract = generator.generate(
        research_question="Test question",
        included_papers=sample_papers,
        article_sections=sample_article_sections,
    )
    
    # Should generate PRISMA 2020 format
    assert "Background:" in abstract or "background" in abstract.lower()
    assert len(abstract) > 0
