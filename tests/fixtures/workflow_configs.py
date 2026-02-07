"""
Test configurations.
"""

from typing import Any, Dict


def get_test_workflow_config() -> Dict[str, Any]:
    """Get test workflow configuration."""
    return {
        "topic": {
            "topic": "Test Research Topic",
            "keywords": ["test", "research"],
            "domain": "testing",
            "research_question": "What is the test research question?",
            "context": "Test context",
        },
        "agents": {
            "title_abstract_screener": {
                "role": "Test Title/Abstract Screener",
                "goal": "Screen test papers by title/abstract",
                "backstory": "Test backstory",
                "llm_model": "gemini-2.5-flash-lite",
                "temperature": 0.2,
                "max_iterations": 10,
            },
            "fulltext_screener": {
                "role": "Test Fulltext Screener",
                "goal": "Screen test papers by fulltext",
                "backstory": "Test backstory",
                "llm_model": "gemini-2.5-flash-lite",
                "temperature": 0.2,
                "max_iterations": 5,
            },
            "extraction_agent": {
                "role": "Test Extraction Agent",
                "goal": "Extract test data",
                "backstory": "Test backstory",
                "llm_model": "gemini-2.5-pro",
                "temperature": 0.1,
                "max_iterations": 5,
            },
        },
        "workflow": {
            "databases": ["PubMed", "Scopus"],
            "date_range": {"start": 2020, "end": 2022},
            "language": "English",
            "max_results_per_db": 10,
            "similarity_threshold": 85,
        },
        "criteria": {
            "inclusion": ["Papers about test topic", "Published in English"],
            "exclusion": ["Editorials", "Conference abstracts"],
        },
        "search_terms": {"test_term": ["test", "testing", "tested"]},
        "output": {
            "directory": "data/outputs",
            "formats": ["markdown", "json"],
            "generate_prisma": True,
            "generate_charts": True,
        },
        "quality_assessment": {
            "enabled": True,
            "framework": "CASP",  # Updated from legacy "risk_of_bias_tool": "RoB 2"
            "grade_outcomes": ["Primary outcome", "Secondary outcome"],
            "template_path": None,  # Will be generated if not provided
        },
        "protocol": {
            "registered": True,
            "registry": "PROSPERO",
            "registration_number": "CRD123456",
            "url": "https://www.crd.york.ac.uk/prospero/display_record.php?ID=CRD123456",
        },
        "funding": {
            "source": "National Institute of Health",
            "grant_number": "R01-TEST-123",
        },
        "supplementary_materials": {
            "include_search_strategies": True,
            "include_extraction_forms": True,
            "include_prisma_checklist": True,
        },
    }
