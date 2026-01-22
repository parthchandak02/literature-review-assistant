"""
Test script to verify humanization integration.

This script verifies that all components are properly integrated
and can be instantiated without errors.
"""

import yaml
from pathlib import Path

import pytest

from src.writing.style_reference import StylePatterns


@pytest.mark.integration
def test_imports():
    """Test that all new modules can be imported."""
    # Test that StylePatterns can be imported
    assert StylePatterns is not None


@pytest.mark.integration
def test_initialization():
    """Test that components can be initialized."""
    # Test StylePatterns
    patterns = StylePatterns()
    patterns.add_pattern("introduction", "sentence_openings", "The proliferation of...")
    patterns_dict = patterns.to_dict()
    assert "introduction" in patterns_dict
    
    # Test that patterns can be loaded from dict
    patterns2 = StylePatterns.from_dict(patterns_dict)
    assert patterns2.get_patterns("introduction", "sentence_openings") == ["The proliferation of..."]


@pytest.mark.integration
def test_config_loading():
    """Test that workflow config includes writing section."""
    project_root = Path(__file__).parent.parent.parent
    config_path = project_root / "config" / "workflow.yaml"
    
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    
    assert "writing" in config, "Writing section missing from config"
    assert "style_extraction" in config["writing"], "style_extraction missing"
    assert "humanization" in config["writing"], "humanization missing"
