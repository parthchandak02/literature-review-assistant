#!/usr/bin/env python3
"""
Test script to verify humanization integration.

This script verifies that all components are properly integrated
and can be instantiated without errors.
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_imports():
    """Test that all new modules can be imported."""
    print("Testing imports...")
    try:
        from src.writing.style_pattern_extractor import StylePatternExtractor
        from src.writing.humanization_agent import HumanizationAgent
        from src.writing.naturalness_scorer import NaturalnessScorer
        from src.writing.style_reference import StylePatterns
        print("  [OK] All imports successful")
        return True
    except Exception as e:
        print(f"  [FAIL] Import error: {e}")
        return False

def test_initialization():
    """Test that components can be initialized."""
    print("\nTesting initialization...")
    try:
        from src.writing.style_reference import StylePatterns
        
        # Test StylePatterns
        patterns = StylePatterns()
        patterns.add_pattern("introduction", "sentence_openings", "The proliferation of...")
        patterns_dict = patterns.to_dict()
        assert "introduction" in patterns_dict
        print("  [OK] StylePatterns initialization successful")
        
        # Test that patterns can be loaded from dict
        patterns2 = StylePatterns.from_dict(patterns_dict)
        assert patterns2.get_patterns("introduction", "sentence_openings") == ["The proliferation of..."]
        print("  [OK] StylePatterns serialization successful")
        
        return True
    except Exception as e:
        print(f"  [FAIL] Initialization error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_config_loading():
    """Test that workflow config includes writing section."""
    print("\nTesting configuration...")
    try:
        import yaml
        config_path = project_root / "config" / "workflow.yaml"
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        
        assert "writing" in config, "Writing section missing from config"
        assert "style_extraction" in config["writing"], "style_extraction missing"
        assert "humanization" in config["writing"], "humanization missing"
        print("  [OK] Configuration structure correct")
        return True
    except Exception as e:
        print(f"  [FAIL] Configuration error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests."""
    print("=" * 60)
    print("Humanization Integration Test")
    print("=" * 60)
    
    results = []
    results.append(test_imports())
    results.append(test_initialization())
    results.append(test_config_loading())
    
    print("\n" + "=" * 60)
    if all(results):
        print("All tests passed! Humanization integration is ready.")
        print("\nTo test the full workflow:")
        print("1. Ensure dependencies are installed: pip install -r requirements.txt")
        print("2. Set up .env file with API keys")
        print("3. Run: python main.py")
        return 0
    else:
        print("Some tests failed. Please check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
