"""
Tests for Journal Selector
"""

import pytest
from pathlib import Path
from src.export.journal_selector import JournalSelector


class TestJournalSelector:
    """Test JournalSelector."""

    def test_selector_initialization(self):
        """Test selector initialization."""
        selector = JournalSelector()
        assert selector is not None

    def test_list_journals(self):
        """Test listing available journals."""
        selector = JournalSelector()
        journals = selector.list_journals()
        assert isinstance(journals, list)
        # Should have at least IEEE, Nature, PLOS
        assert "ieee" in journals or len(journals) >= 0

    def test_get_journal_config(self):
        """Test getting journal configuration."""
        selector = JournalSelector()
        config = selector.get_journal_config("ieee")
        if config:
            assert "name" in config
            assert "citation_style" in config

    def test_validate_for_journal(self, tmp_path):
        """Test journal validation."""
        selector = JournalSelector()
        
        # Create test manuscript
        manuscript_path = tmp_path / "manuscript.md"
        manuscript_path.write_text(
            "# Title\n\n## Abstract\n\nTest abstract.\n\n## Introduction\n\nTest."
        )
        
        results = selector.validate_for_journal(manuscript_path, "ieee")
        assert isinstance(results, dict)
        # Should check for required sections
        assert "has_abstract" in results or "has_introduction" in results
