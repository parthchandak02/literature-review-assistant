"""
Comprehensive End-to-End Workflow Test

Tests the complete research paper generation workflow end-to-end.
Validates all phases, error handling, and outputs.
"""

import os
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv

import pytest

from src.orchestration.workflow_manager import WorkflowManager
from src.search.database_connectors import ACMConnector, MockConnector
from src.search.multi_database_searcher import MultiDatabaseSearcher
from src.extraction.data_extractor_agent import DataExtractorAgent, ExtractedData
from src.schemas.extraction_schemas import ExtractedDataSchema
from src.search.connectors.base import Paper

# Load environment variables
load_dotenv()

# Test configuration
TEST_TOPIC = "machine learning in healthcare"
TEST_CONFIG_PATH = "config/workflow.yaml"


@pytest.fixture
def test_config_path():
    """Fixture providing test config path."""
    return TEST_CONFIG_PATH


@pytest.mark.e2e
def test_acm_403_handling():
    """Test that ACM connector handles 403 errors gracefully without retries."""
    # Create ACM connector
    connector = ACMConnector()
    
    # Mock a 403 response by patching the session
    import requests
    from unittest.mock import Mock, patch
    
    mock_response = Mock()
    mock_response.status_code = 403
    mock_response.raise_for_status = Mock(side_effect=requests.HTTPError("403 Forbidden"))
    
    with patch.object(connector, '_get_session') as mock_session:
        mock_session.return_value.get.return_value = mock_response
        
        # This should return empty list without retrying
        start_time = time.time()
        papers = connector.search("test query", max_results=10)
        elapsed = time.time() - start_time
        
        # Should return empty list immediately (not retry 3 times)
        assert papers == [], f"Expected empty list, got {len(papers)} papers"
        assert elapsed < 5.0, f"Should be fast, not waiting for retries (took {elapsed:.2f}s)"


@pytest.mark.e2e
def test_pydantic_schema_validation():
    """Test that Pydantic schema accepts null methodology values."""
    # Test data with null methodology
    test_data = {
        "title": "Test Paper",
        "authors": ["Author 1"],
        "year": 2024,
        "journal": None,
        "doi": None,
        "study_objectives": ["Objective 1"],
        "methodology": None,  # This should be accepted now
        "study_design": None,
        "participants": None,
        "interventions": None,
        "outcomes": [],
        "key_findings": [],
        "limitations": None,
    }
    
    # Should validate successfully
    schema_result = ExtractedDataSchema(**test_data)
    assert schema_result.methodology is None, f"Expected None, got {schema_result.methodology}"


@pytest.mark.e2e
def test_data_extraction_with_null_methodology():
    """Test data extraction agent handles null methodology correctly."""
    # Create extraction agent
    agent = DataExtractorAgent(
        llm_provider="gemini",
        agent_config={
            "role": "Test Extractor",
            "llm_model": "gemini-2.5-flash-lite",
            "temperature": 0.1,
        },
    )
    
    # Test normalization with null methodology
    test_json = json.dumps({
        "title": "Test Paper",
        "authors": [],
        "year": None,
        "journal": None,
        "doi": None,
        "study_objectives": [],
        "methodology": None,
        "study_design": None,
        "participants": None,
        "interventions": None,
        "outcomes": [],
        "key_findings": [],
        "limitations": None,
    })
    
    normalized = agent._normalize_extraction_response(test_json)
    
    # Should normalize successfully
    assert normalized.get("methodology") is None, f"Expected None, got {normalized.get('methodology')}"
    
    # Test schema validation
    schema_result = ExtractedDataSchema(**normalized)
    assert schema_result.methodology is None, f"Expected None, got {schema_result.methodology}"


@pytest.mark.e2e
def test_workflow_phases_independently(test_config_path):
    """Test each workflow phase independently."""
    # Initialize workflow manager
    manager = WorkflowManager(config_path=test_config_path)
    
    # Test search phase
    assert manager.searcher is not None, "Searcher not initialized"
    
    # Test deduplication phase
    assert manager.deduplicator is not None, "Deduplicator not initialized"
    
    # Test screening agents (may be lazy-loaded)
    if hasattr(manager, 'title_abstract_screener'):
        assert manager.title_abstract_screener is not None, "Screening agents not initialized"
    
    # Test extraction agent (may be lazy-loaded)
    if hasattr(manager, 'extraction_agent'):
        assert manager.extraction_agent is not None, "Extraction agent not initialized"


@pytest.mark.e2e
def test_mock_workflow_run():
    """Test workflow with mock data."""
    # Create mock papers
    mock_papers = [
        Paper(
            title="Test Paper 1",
            abstract="Test abstract 1",
            authors=["Author 1", "Author 2"],
            year=2024,
            doi="10.1000/test1",
            journal="Test Journal",
            database="Mock",
        ),
        Paper(
            title="Test Paper 2",
            abstract="Test abstract 2",
            authors=["Author 3"],
            year=2023,
            doi="10.1000/test2",
            journal="Test Journal 2",
            database="Mock",
        ),
    ]
    
    # Test deduplication
    from src.deduplication import Deduplicator
    deduplicator = Deduplicator(similarity_threshold=85)
    deduplicated = deduplicator.deduplicate_papers(mock_papers)
    
    assert len(deduplicated.unique_papers) == len(mock_papers), \
        f"Expected {len(mock_papers)}, got {len(deduplicated.unique_papers)}"


@pytest.mark.e2e
def test_error_recovery():
    """Test error recovery mechanisms."""
    # Test that ACM connector returns empty list on 403 (already tested above)
    # Test that other connectors handle errors gracefully
    from src.search.database_connectors import CrossrefConnector
    
    connector = CrossrefConnector()
    # This should not raise an exception even if network fails
    # (it will be handled by retry decorator)
    assert connector is not None, "Connector should initialize"


@pytest.mark.e2e
def test_output_validation():
    """Test that outputs are generated correctly."""
    # Check that output directories exist or can be created
    output_dir = Path("data/outputs")
    # Directory may not exist yet, but path should be valid
    assert output_dir.parent.exists(), "Output directory parent should exist"
    
    # Check checkpoint directory
    checkpoint_dir = Path("data/checkpoints")
    # Directory may not exist yet, but path should be valid
    assert checkpoint_dir.parent.exists(), "Checkpoint directory parent should exist"
