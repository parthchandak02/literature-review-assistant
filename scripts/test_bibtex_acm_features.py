#!/usr/bin/env python3
"""
[Temporary Testing Script] BibTeX and ACM Features Test

Manual test script for BibTeX and ACM features.
Run this to verify the implementations work correctly.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_bibtex_formatter():
    """Test BibTeX formatter."""
    print("Testing BibTeX Formatter...")
    try:
        from src.citations.bibtex_formatter import BibTeXFormatter
        from src.search.connectors.base import Paper
        
        formatter = BibTeXFormatter()
        
        # Test paper
        paper = Paper(
            title="Machine Learning for Health",
            authors=["Smith, John", "Doe, Jane"],
            year=2023,
            journal="Test Journal",
            doi="10.1000/test",
            abstract="Test abstract"
        )
        
        # Generate citation key
        key = formatter.generate_citation_key(paper, 1)
        print(f"  Citation key: {key}")
        assert key.startswith("Smith2023"), f"Key should start with Smith2023, got {key}"
        
        # Format citation
        entry = formatter.format_citation(paper, key)
        print(f"  Entry type: {formatter.determine_entry_type(paper)}")
        assert "@article" in entry, "Should be @article"
        assert "title = {Machine Learning for Health}" in entry
        assert "year = {2023}" in entry
        assert "doi = {10.1000/test}" in entry
        
        print("  BibTeX Formatter: PASSED")
        return True
    except Exception as e:
        print(f"  BibTeX Formatter: FAILED - {e}")
        import traceback
        traceback.print_exc()
        return False

def test_citation_manager_bibtex():
    """Test CitationManager BibTeX methods."""
    print("\nTesting CitationManager BibTeX Export...")
    try:
        from src.citations.citation_manager import CitationManager
        from src.search.connectors.base import Paper
        
        papers = [
            Paper(
                title="Test Paper 1",
                authors=["Author A"],
                year=2023,
                journal="Test Journal"
            )
        ]
        
        manager = CitationManager(papers)
        manager.extract_and_map_citations("See [Citation 1].")
        
        # Generate BibTeX
        bibtex = manager.generate_bibtex_references()
        assert "@article" in bibtex or "@inproceedings" in bibtex or "@misc" in bibtex
        assert "Test Paper 1" in bibtex
        
        # Export BibTeX
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.bib', delete=False) as f:
            output_path = f.name
        
        result_path = manager.export_bibtex(output_path)
        assert Path(result_path).exists()
        
        # Read and verify
        content = Path(result_path).read_text()
        assert "@article" in content or "@inproceedings" in content or "@misc" in content
        
        # Cleanup
        Path(result_path).unlink()
        
        print("  CitationManager BibTeX: PASSED")
        return True
    except Exception as e:
        print(f"  CitationManager BibTeX: FAILED - {e}")
        import traceback
        traceback.print_exc()
        return False

def test_acm_connector():
    """Test ACM connector initialization and basic methods."""
    print("\nTesting ACM Connector...")
    try:
        from src.search.database_connectors import ACMConnector
        
        connector = ACMConnector()
        assert connector.get_database_name() == "ACM"
        assert connector.base_url == "https://dl.acm.org"
        assert connector.search_url == "https://dl.acm.org/action/doSearch"
        
        print("  ACM Connector initialization: PASSED")
        return True
    except Exception as e:
        print(f"  ACM Connector: FAILED - {e}")
        import traceback
        traceback.print_exc()
        return False

def test_acm_connector_parsing():
    """Test ACM connector HTML parsing."""
    print("\nTesting ACM Connector HTML Parsing...")
    try:
        from src.search.database_connectors import ACMConnector
        from bs4 import BeautifulSoup
        
        connector = ACMConnector()
        
        # Test HTML parsing
        html = """
        <div class="search__item">
            <h5 class="hlFld-Title"><a href="/doi/10.1145/test">Test Paper</a></h5>
            <div class="authors">
                <a class="author-name">John Smith</a>
                <a class="author-name">Jane Doe</a>
            </div>
            <div class="abstract">This is a test abstract.</div>
            <span class="year">2023</span>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        item = soup.find("div", class_="search__item")
        
        paper = connector._extract_paper_from_item(item)
        assert paper is not None
        assert paper.title == "Test Paper"
        assert len(paper.authors) >= 1
        assert paper.year == 2023
        
        print("  ACM Connector HTML Parsing: PASSED")
        return True
    except Exception as e:
        print(f"  ACM Connector HTML Parsing: FAILED - {e}")
        import traceback
        traceback.print_exc()
        return False

def test_integration():
    """Test integration with workflow components."""
    print("\nTesting Integration...")
    try:
        # Test that ACM is registered
        from src.search import ACMConnector
        from src.search.database_connectors import ACMConnector as ACMConnector2
        assert ACMConnector == ACMConnector2
        
        # Test that BibTeXFormatter is accessible
        from src.citations import BibTeXFormatter
        from src.citations.bibtex_formatter import BibTeXFormatter as BibTeXFormatter2
        assert BibTeXFormatter == BibTeXFormatter2
        
        # Test factory can create ACM connector
        from src.orchestration.database_connector_factory import DatabaseConnectorFactory
        connector = DatabaseConnectorFactory.create_connector("ACM")
        assert connector is not None
        assert connector.get_database_name() == "ACM"
        
        print("  Integration: PASSED")
        return True
    except Exception as e:
        print(f"  Integration: FAILED - {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Manual Test Suite for BibTeX and ACM Features")
    print("=" * 60)
    
    results = []
    results.append(test_bibtex_formatter())
    results.append(test_citation_manager_bibtex())
    results.append(test_acm_connector())
    results.append(test_acm_connector_parsing())
    results.append(test_integration())
    
    print("\n" + "=" * 60)
    print(f"Results: {sum(results)}/{len(results)} tests passed")
    print("=" * 60)
    
    if all(results):
        print("All tests PASSED!")
        sys.exit(0)
    else:
        print("Some tests FAILED!")
        sys.exit(1)
