#!/usr/bin/env python3
"""
Database Health Check Script

Tests all configured database connectors and reports their status.
"""

import os
import sys
import time
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path to import src modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.search.database_connectors import (
    PubMedConnector,
    ArxivConnector,
    SemanticScholarConnector,
    CrossrefConnector,
    ScopusConnector,
    Paper,
)
from src.search.exceptions import DatabaseSearchError, APIKeyError, RateLimitError, NetworkError

# Load environment variables
load_dotenv()

# Test query
TEST_QUERY = "health literacy"


class DatabaseHealthChecker:
    """Check health of database connectors."""

    def __init__(self):
        self.results: Dict[str, Dict] = {}

    def check_api_keys(self) -> Dict[str, bool]:
        """Check which API keys are configured."""
        return {
            "PUBMED_API_KEY": bool(os.getenv("PUBMED_API_KEY")),
            "PUBMED_EMAIL": bool(os.getenv("PUBMED_EMAIL")),
            "SEMANTIC_SCHOLAR_API_KEY": bool(os.getenv("SEMANTIC_SCHOLAR_API_KEY")),
            "CROSSREF_EMAIL": bool(os.getenv("CROSSREF_EMAIL")),
            "SCOPUS_API_KEY": bool(os.getenv("SCOPUS_API_KEY")),
        }

    def test_pubmed(self) -> Tuple[bool, str, List[Paper], Optional[str]]:
        """Test PubMed connector."""
        try:
            api_key = os.getenv("PUBMED_API_KEY")
            email = os.getenv("PUBMED_EMAIL")
            
            connector = PubMedConnector(api_key=api_key, email=email)
            start_time = time.time()
            results = connector.search(TEST_QUERY, max_results=10)
            duration = time.time() - start_time
            
            if len(results) > 0:
                sample = results[0].title[:60] + "..." if len(results[0].title) > 60 else results[0].title
                status = "WORKING"
                if api_key:
                    status += " (API key: SET"
                    if email:
                        status += ", Email: SET"
                    status += ")"
                elif email:
                    status += " (Email: SET)"
                else:
                    status += " (No API key needed)"
                
                return True, status, results, sample
            else:
                return False, "No results returned", [], None
        except Exception as e:
            return False, f"Error: {str(e)}", [], None

    def test_arxiv(self) -> Tuple[bool, str, List[Paper], Optional[str]]:
        """Test arXiv connector."""
        try:
            connector = ArxivConnector()
            start_time = time.time()
            results = connector.search(TEST_QUERY, max_results=10)
            duration = time.time() - start_time
            
            if len(results) > 0:
                sample = results[0].title[:60] + "..." if len(results[0].title) > 60 else results[0].title
                return True, "WORKING (No API key needed)", results, sample
            else:
                return False, "No results returned", [], None
        except Exception as e:
            return False, f"Error: {str(e)}", [], None

    def test_semantic_scholar(self) -> Tuple[bool, str, List[Paper], Optional[str]]:
        """Test Semantic Scholar connector."""
        try:
            api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
            connector = SemanticScholarConnector(api_key=api_key)
            start_time = time.time()
            results = connector.search(TEST_QUERY, max_results=10)
            duration = time.time() - start_time
            
            if len(results) > 0:
                sample = results[0].title[:60] + "..." if len(results[0].title) > 60 else results[0].title
                status = "WORKING"
                if api_key:
                    status += " (API key: SET)"
                else:
                    status += " (No API key, lower rate limits)"
                return True, status, results, sample
            else:
                return False, "No results returned", [], None
        except Exception as e:
            return False, f"Error: {str(e)}", [], None

    def test_crossref(self) -> Tuple[bool, str, List[Paper], Optional[str]]:
        """Test Crossref connector."""
        try:
            email = os.getenv("CROSSREF_EMAIL")
            connector = CrossrefConnector(email=email)
            start_time = time.time()
            results = connector.search(TEST_QUERY, max_results=10)
            duration = time.time() - start_time
            
            if len(results) > 0:
                sample = results[0].title[:60] + "..." if len(results[0].title) > 60 else results[0].title
                status = "WORKING"
                if email:
                    status += f" (Email: SET)"
                else:
                    status += " (No email, lower rate limits)"
                return True, status, results, sample
            else:
                return False, "No results returned", [], None
        except Exception as e:
            return False, f"Error: {str(e)}", [], None

    def test_scopus(self) -> Tuple[bool, str, List[Paper], Optional[str]]:
        """Test Scopus connector."""
        api_key = os.getenv("SCOPUS_API_KEY")
        if not api_key:
            return False, "NOT WORKING (API key: NOT SET)", [], None
        
        try:
            connector = ScopusConnector(api_key=api_key)
            start_time = time.time()
            results = connector.search(TEST_QUERY, max_results=10)
            duration = time.time() - start_time
            
            if len(results) > 0:
                sample = results[0].title[:60] + "..." if len(results[0].title) > 60 else results[0].title
                return True, "WORKING (API key: SET)", results, sample
            else:
                return False, "No results returned", [], None
        except Exception as e:
            return False, f"Error: {str(e)}", [], None

    def run_all_checks(self):
        """Run health checks for all databases."""
        print("Database Health Check Report")
        print("=" * 60)
        print()
        
        # Check API keys
        print("API Key Configuration:")
        api_keys = self.check_api_keys()
        for key, is_set in api_keys.items():
            status = "SET" if is_set else "NOT SET"
            print(f"  {key}: {status}")
        print()
        
        # Test each database
        databases = [
            ("PubMed", self.test_pubmed),
            ("arXiv", self.test_arxiv),
            ("Semantic Scholar", self.test_semantic_scholar),
            ("Crossref", self.test_crossref),
            ("Scopus", self.test_scopus),
        ]
        
        working_count = 0
        total_count = len(databases)
        
        for db_name, test_func in databases:
            success, status, results, sample = test_func()
            
            symbol = "✓" if success else "✗"
            print(f"{db_name}: {symbol} {status}")
            
            if success:
                working_count += 1
                print(f"  - Test query: \"{TEST_QUERY}\"")
                print(f"  - Results: {len(results)} papers found")
                if sample:
                    print(f"  - Sample: \"{sample}\"")
                
                # Show paper quality metrics
                papers_with_abstracts = sum(1 for p in results if p.abstract)
                papers_with_authors = sum(1 for p in results if p.authors)
                papers_with_doi = sum(1 for p in results if p.doi)
                
                print(f"  - Quality: {papers_with_abstracts}/{len(results)} with abstracts, "
                      f"{papers_with_authors}/{len(results)} with authors, "
                      f"{papers_with_doi}/{len(results)} with DOI")
            else:
                print(f"  - Error: {status}")
            
            print()
        
        # Summary
        print("=" * 60)
        print(f"Summary: {working_count}/{total_count} databases working")
        print()
        
        if working_count < total_count:
            print("Recommendations:")
            missing = total_count - working_count
            if "Scopus" in [db for db, _ in databases if not self.results.get(db, {}).get("success", False)]:
                print("  - Set SCOPUS_API_KEY to enable Scopus (requires institutional access)")
            if not api_keys["PUBMED_API_KEY"] and not api_keys["PUBMED_EMAIL"]:
                print("  - Set PUBMED_API_KEY and PUBMED_EMAIL for better PubMed rate limits")
            if not api_keys["SEMANTIC_SCHOLAR_API_KEY"]:
                print("  - Set SEMANTIC_SCHOLAR_API_KEY for higher Semantic Scholar rate limits")
            if not api_keys["CROSSREF_EMAIL"]:
                print("  - Set CROSSREF_EMAIL for better Crossref service")
        
        return working_count == total_count


def main():
    """Main entry point."""
    checker = DatabaseHealthChecker()
    all_working = checker.run_all_checks()
    
    # Exit with appropriate code
    sys.exit(0 if all_working else 1)


if __name__ == "__main__":
    main()
