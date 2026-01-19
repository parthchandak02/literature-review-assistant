"""
Test configurations.
"""

from typing import Dict, Any


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
            "screening_agent": {
                "role": "Test Screening Agent",
                "goal": "Screen test papers",
                "backstory": "Test backstory",
                "llm_model": "gpt-4",
                "temperature": 0.3,
                "max_iterations": 5,
            },
            "extraction_agent": {
                "role": "Test Extraction Agent",
                "goal": "Extract test data",
                "backstory": "Test backstory",
                "llm_model": "gpt-4",
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
    }
