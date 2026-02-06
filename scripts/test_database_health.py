#!/usr/bin/env python3
"""
[Recurring Usage Script] Database Health Check

Tests all configured database connectors and reports their status.
Used by: python main.py --test-databases
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
    ACMConnector,
    SpringerConnector,
    IEEEXploreConnector,
    PerplexityConnector,
    Paper,
)

# Try to import Google Scholar connector (optional dependency)
try:
    from src.search.connectors.google_scholar_connector import GoogleScholarConnector
    GOOGLE_SCHOLAR_AVAILABLE = True
except ImportError:
    GOOGLE_SCHOLAR_AVAILABLE = False
    GoogleScholarConnector = None

# Load environment variables
load_dotenv()

# Test query
TEST_QUERY = "health literacy"


class DatabaseHealthChecker:
    """Check health of database connectors."""

    def __init__(self):
        self.results: Dict[str, Dict] = {}

    def _extract_error_message(self, e: Exception) -> str:
        """Extract a clean, user-friendly error message from an exception."""
        error_str = str(e)
        error_type = type(e).__name__
        
        # Handle RetryError - extract the underlying error
        if "RetryError" in error_str or "RetryError" in error_type:
            if hasattr(e, "last_attempt") and e.last_attempt:
                underlying = e.last_attempt.exception()
                if underlying:
                    error_str = str(underlying)
            elif hasattr(e, "args") and e.args:
                error_str = str(e.args[0])
        
        # Handle SSL certificate errors
        if "SSL" in error_str or "CERTIFICATE_VERIFY_FAILED" in error_str:
            if "self-signed certificate" in error_str:
                return "SSL certificate verification failed (corporate proxy/certificate issue)"
            return "SSL/TLS connection error"
        
        # Handle network errors
        if "ConnectionPool" in error_str or "Max retries exceeded" in error_str:
            if "SSL" in error_str or "CERTIFICATE" in error_str:
                return "Network connection failed (SSL certificate issue)"
            if "Read timed out" in error_str or "timeout" in error_str.lower():
                return "Connection timeout"
            return "Network connection failed"
        
        # Handle API limit errors
        if "limit" in error_str.lower() or "rate limit" in error_str.lower() or "exceeds the maximum" in error_str.lower():
            return "API rate limit reached"
        
        # Handle 403 Forbidden (anti-scraping)
        if "403" in error_str or "Forbidden" in error_str:
            return "Access forbidden (anti-scraping protection)"
        
        # Handle AttributeError (like Google Scholar library issues)
        if "AttributeError" in error_str or "has no attribute" in error_str:
            attr_name = error_str.split("'")[1] if "'" in error_str else "unknown"
            return f"Library compatibility issue (missing attribute: {attr_name})"
        
        # Truncate very long error messages
        if len(error_str) > 200:
            error_str = error_str[:197] + "..."
        
        return error_str

    def check_api_keys(self) -> Dict[str, bool]:
        """Check which API keys are configured."""
        # Check for pybliometrics installation
        import importlib.util
        pybliometrics_available = importlib.util.find_spec("pybliometrics") is not None
        
        return {
            "PUBMED_API_KEY": bool(os.getenv("PUBMED_API_KEY")),
            "PUBMED_EMAIL": bool(os.getenv("PUBMED_EMAIL")),
            "SEMANTIC_SCHOLAR_API_KEY": bool(os.getenv("SEMANTIC_SCHOLAR_API_KEY")),
            "CROSSREF_EMAIL": bool(os.getenv("CROSSREF_EMAIL")),
            "SCOPUS_API_KEY": bool(os.getenv("SCOPUS_API_KEY")),
            "PERPLEXITY_SEARCH_API_KEY": bool(os.getenv("PERPLEXITY_SEARCH_API_KEY")),
            "PERPLEXITY_API_KEY": bool(os.getenv("PERPLEXITY_API_KEY")),
            "WOS_API_KEY": bool(os.getenv("WOS_API_KEY")),
            "IEEE_API_KEY": bool(os.getenv("IEEE_API_KEY")),
            "PYBLIOMETRICS_INSTALLED": pybliometrics_available,
        }

    def test_pubmed(self) -> Tuple[bool, str, List[Paper], Optional[str]]:
        """Test PubMed connector."""
        try:
            api_key = os.getenv("PUBMED_API_KEY")
            email = os.getenv("PUBMED_EMAIL")
            
            connector = PubMedConnector(api_key=api_key, email=email)
            start_time = time.time()
            results = connector.search(TEST_QUERY, max_results=10)
            time.time() - start_time
            
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
                return False, "NOT WORKING (No results returned)", [], None
        except Exception as e:
            error_msg = self._extract_error_message(e)
            return False, f"ERROR: {error_msg}", [], None

    def test_arxiv(self) -> Tuple[bool, str, List[Paper], Optional[str]]:
        """Test arXiv connector."""
        try:
            connector = ArxivConnector()
            start_time = time.time()
            results = connector.search(TEST_QUERY, max_results=10)
            time.time() - start_time
            
            if len(results) > 0:
                sample = results[0].title[:60] + "..." if len(results[0].title) > 60 else results[0].title
                return True, "WORKING (No API key needed)", results, sample
            else:
                return False, "NOT WORKING (No results returned)", [], None
        except Exception as e:
            error_msg = self._extract_error_message(e)
            return False, f"ERROR: {error_msg}", [], None

    def test_semantic_scholar(self) -> Tuple[bool, str, List[Paper], Optional[str]]:
        """Test Semantic Scholar connector."""
        try:
            api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
            connector = SemanticScholarConnector(api_key=api_key)
            start_time = time.time()
            results = connector.search(TEST_QUERY, max_results=10)
            time.time() - start_time
            
            if len(results) > 0:
                sample = results[0].title[:60] + "..." if len(results[0].title) > 60 else results[0].title
                status = "WORKING"
                if api_key:
                    status += " (API key: SET)"
                else:
                    status += " (No API key, lower rate limits)"
                return True, status, results, sample
            else:
                return False, "NOT WORKING (No results returned)", [], None
        except Exception as e:
            error_msg = self._extract_error_message(e)
            return False, f"ERROR: {error_msg}", [], None

    def test_crossref(self) -> Tuple[bool, str, List[Paper], Optional[str]]:
        """Test Crossref connector."""
        try:
            email = os.getenv("CROSSREF_EMAIL")
            connector = CrossrefConnector(email=email)
            start_time = time.time()
            results = connector.search(TEST_QUERY, max_results=10)
            time.time() - start_time
            
            if len(results) > 0:
                sample = results[0].title[:60] + "..." if len(results[0].title) > 60 else results[0].title
                status = "WORKING"
                if email and email != "your_email@example.com":
                    status += " (Email: SET)"
                else:
                    status += " (No email, lower rate limits)"
                return True, status, results, sample
            else:
                return False, "NOT WORKING (No results returned)", [], None
        except Exception as e:
            error_msg = self._extract_error_message(e)
            return False, f"ERROR: {error_msg}", [], None

    def test_scopus(self) -> Tuple[bool, str, List[Paper], Optional[str]]:
        """Test Scopus connector."""
        api_key = os.getenv("SCOPUS_API_KEY")
        if not api_key:
            return False, "SKIPPED (API key: NOT SET)", [], None
        
        try:
            connector = ScopusConnector(api_key=api_key)
            start_time = time.time()
            results = connector.search(TEST_QUERY, max_results=10)
            time.time() - start_time
            
            if len(results) > 0:
                sample = results[0].title[:60] + "..." if len(results[0].title) > 60 else results[0].title
                return True, "WORKING (API key: SET)", results, sample
            else:
                return False, "NOT WORKING (No results returned)", [], None
        except Exception as e:
            error_msg = self._extract_error_message(e)
            return False, f"ERROR: {error_msg}", [], None

    def test_acm(self) -> Tuple[bool, str, List[Paper], Optional[str]]:
        """Test ACM connector."""
        try:
            connector = ACMConnector()
            start_time = time.time()
            results = connector.search(TEST_QUERY, max_results=10)
            time.time() - start_time
            
            if len(results) > 0:
                sample = results[0].title[:60] + "..." if len(results[0].title) > 60 else results[0].title
                return True, "WORKING (Web scraping, no API key needed)", results, sample
            else:
                return False, "NOT WORKING (No results returned)", [], None
        except Exception as e:
            error_msg = self._extract_error_message(e)
            return False, f"ERROR: {error_msg}", [], None

    def test_springer(self) -> Tuple[bool, str, List[Paper], Optional[str]]:
        """Test Springer connector."""
        try:
            connector = SpringerConnector()
            start_time = time.time()
            results = connector.search(TEST_QUERY, max_results=10)
            time.time() - start_time
            
            if len(results) > 0:
                sample = results[0].title[:60] + "..." if len(results[0].title) > 60 else results[0].title
                return True, "WORKING (Web scraping, no API key needed)", results, sample
            else:
                return False, "NOT WORKING (No results returned)", [], None
        except Exception as e:
            error_msg = self._extract_error_message(e)
            return False, f"ERROR: {error_msg}", [], None

    def test_ieee_xplore(self) -> Tuple[bool, str, List[Paper], Optional[str]]:
        """Test IEEE Xplore connector."""
        try:
            connector = IEEEXploreConnector()
            start_time = time.time()
            results = connector.search(TEST_QUERY, max_results=10)
            time.time() - start_time
            
            if len(results) > 0:
                sample = results[0].title[:60] + "..." if len(results[0].title) > 60 else results[0].title
                return True, "WORKING (Web scraping, no API key needed)", results, sample
            else:
                return False, "NOT WORKING (No results returned)", [], None
        except Exception as e:
            error_msg = self._extract_error_message(e)
            return False, f"ERROR: {error_msg}", [], None

    def test_perplexity(self) -> Tuple[bool, str, List[Paper], Optional[str]]:
        """Test Perplexity connector."""
        api_key = os.getenv("PERPLEXITY_SEARCH_API_KEY") or os.getenv("PERPLEXITY_API_KEY")
        if not api_key:
            return False, "SKIPPED (API key: NOT SET)", [], None
        
        try:
            connector = PerplexityConnector(api_key=api_key)
            start_time = time.time()
            results = connector.search(TEST_QUERY, max_results=10)
            time.time() - start_time
            
            if len(results) > 0:
                sample = results[0].title[:60] + "..." if len(results[0].title) > 60 else results[0].title
                return True, "WORKING (API key: SET)", results, sample
            else:
                return False, "NOT WORKING (No results returned)", [], None
        except Exception as e:
            error_msg = self._extract_error_message(e)
            return False, f"ERROR: {error_msg}", [], None

    def test_google_scholar(self) -> Tuple[bool, str, List[Paper], Optional[str]]:
        """Test Google Scholar connector."""
        if not GOOGLE_SCHOLAR_AVAILABLE:
            return False, "SKIPPED (scholarly library not available)", [], None
        
        try:
            connector = GoogleScholarConnector()
            start_time = time.time()
            results = connector.search(TEST_QUERY, max_results=10)
            time.time() - start_time
            
            if len(results) > 0:
                sample = results[0].title[:60] + "..." if len(results[0].title) > 60 else results[0].title
                return True, "WORKING (No API key needed, proxy recommended)", results, sample
            else:
                return False, "NOT WORKING (No results returned)", [], None
        except Exception as e:
            error_msg = self._extract_error_message(e)
            return False, f"ERROR: {error_msg}", [], None

    def run_all_checks(self):
        """Run health checks for all databases."""
        print("Database Health Check Report")
        print("=" * 60)
        print()
        
        # Check API keys and dependencies
        print("API Key Configuration:")
        api_keys = self.check_api_keys()
        for key, is_set in api_keys.items():
            if key == "PYBLIOMETRICS_INSTALLED":
                status = "INSTALLED" if is_set else "NOT INSTALLED"
            else:
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
            ("ACM", self.test_acm),
            ("Springer", self.test_springer),
            ("IEEE Xplore", self.test_ieee_xplore),
            ("Perplexity", self.test_perplexity),
            ("Google Scholar", self.test_google_scholar),
        ]
        
        working_count = 0
        skipped_count = 0
        error_count = 0
        total_count = len(databases)
        
        for db_name, test_func in databases:
            success, status, results, sample = test_func()
            
            # Determine status type
            if success:
                symbol = "[OK]"
                working_count += 1
            elif "SKIPPED" in status:
                symbol = "[SKIP]"
                skipped_count += 1
            else:
                symbol = "[FAIL]"
                error_count += 1
            
            print(f"{db_name}: {symbol} {status}")
            
            if success:
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
            elif "SKIPPED" in status:
                print(f"  - Reason: {status}")
            else:
                print(f"  - Details: {status}")
            
            print()
        
        # Summary
        print("=" * 60)
        print("Summary:")
        print(f"  Working: {working_count}/{total_count}")
        print(f"  Skipped: {skipped_count}/{total_count}")
        print(f"  Errors: {error_count}/{total_count}")
        print()
        
        # Recommendations
        recommendations = []
        
        if not api_keys["SCOPUS_API_KEY"]:
            recommendations.append("  - Set SCOPUS_API_KEY to enable Scopus (requires institutional access)")
        
        if not api_keys["PUBMED_API_KEY"] and not api_keys["PUBMED_EMAIL"]:
            recommendations.append("  - Set PUBMED_API_KEY and PUBMED_EMAIL for better PubMed rate limits")
        elif not api_keys["PUBMED_API_KEY"]:
            recommendations.append("  - Set PUBMED_API_KEY for better PubMed rate limits")
        
        if not api_keys["SEMANTIC_SCHOLAR_API_KEY"]:
            recommendations.append("  - Set SEMANTIC_SCHOLAR_API_KEY for higher Semantic Scholar rate limits")
        
        email = os.getenv("CROSSREF_EMAIL")
        if not email or email == "your_email@example.com":
            recommendations.append("  - Set CROSSREF_EMAIL (not placeholder) for better Crossref service")
        
        if not api_keys["PERPLEXITY_SEARCH_API_KEY"] and not api_keys["PERPLEXITY_API_KEY"]:
            recommendations.append("  - Set PERPLEXITY_SEARCH_API_KEY to enable Perplexity search")
        
        if not GOOGLE_SCHOLAR_AVAILABLE:
            recommendations.append("  - Install scholarly library for Google Scholar: pip install scholarly")
        
        if not api_keys.get("PYBLIOMETRICS_INSTALLED", False):
            recommendations.append("  - Install pybliometrics for Scopus: pip install pybliometrics or pip install -e '.[bibliometrics]'")
        
        if recommendations:
            print("Recommendations:")
            for rec in recommendations:
                print(rec)
            print()
        
        # Return True if all testable databases are working
        testable_count = total_count - skipped_count
        return testable_count > 0 and working_count == testable_count


def main():
    """Main entry point."""
    checker = DatabaseHealthChecker()
    all_working = checker.run_all_checks()
    
    # Exit with appropriate code
    sys.exit(0 if all_working else 1)


if __name__ == "__main__":
    main()
