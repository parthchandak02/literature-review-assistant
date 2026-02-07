"""
Google Scholar Connector

Connector for Google Scholar using the scholarly library.
Provides author search, publication search, citation tracking, and related articles.
"""

import logging
import os
from typing import Any, List, Optional

from ..cache import SearchCache
from ..proxy_manager import ProxyManager
from .base import DatabaseConnector, Paper

logger = logging.getLogger(__name__)

try:
    from scholarly import ProxyGenerator, scholarly

    SCHOLARLY_AVAILABLE = True
except ImportError:
    SCHOLARLY_AVAILABLE = False
    scholarly = None
    ProxyGenerator = None
    # Don't log warning here - will be logged when connector is instantiated


class GoogleScholarConnector(DatabaseConnector):
    """Google Scholar connector using scholarly library."""

    def __init__(
        self,
        cache: Optional[SearchCache] = None,
        proxy_manager: Optional[ProxyManager] = None,
        integrity_checker: Optional[Any] = None,
        persistent_session: bool = True,
        cookie_jar: Optional[str] = None,
        use_proxy: bool = True,
    ):
        """
        Initialize Google Scholar connector.

        Args:
            cache: Optional SearchCache instance
            proxy_manager: Optional ProxyManager for proxy support
            integrity_checker: Optional IntegrityChecker
            persistent_session: Whether to use persistent sessions
            cookie_jar: Path to cookie jar file
            use_proxy: Whether to use proxy (recommended for Google Scholar)
        """
        super().__init__(
            api_key=None,  # Google Scholar doesn't use API keys
            cache=cache,
            proxy_manager=proxy_manager,
            integrity_checker=integrity_checker,
            persistent_session=persistent_session,
            cookie_jar=cookie_jar,
        )

        if not SCHOLARLY_AVAILABLE:
            raise ImportError(
                "scholarly library is required for Google Scholar connector. "
                "Install with: pip install scholarly or pip install -e '.[bibliometrics]'"
            )

        self.use_proxy = use_proxy
        self._setup_proxy()

    def _setup_proxy(self):
        """Setup proxy for scholarly if available."""
        if not self.use_proxy:
            return

        try:
            pg = ProxyGenerator()

            # Try ScraperAPI first if available
            scraperapi_key = os.getenv("SCRAPERAPI_KEY")
            if scraperapi_key and self.proxy_manager:
                try:
                    success = pg.ScraperAPI(scraperapi_key)
                    if success:
                        scholarly.use_proxy(pg)
                        logger.info("Using ScraperAPI proxy for Google Scholar")
                        return
                except Exception as e:
                    logger.debug(f"ScraperAPI setup failed: {e}")

            # Try free proxies as fallback
            try:
                success = pg.FreeProxies()
                if success:
                    scholarly.use_proxy(pg)
                    logger.info("Using free proxies for Google Scholar")
                    return
            except Exception as e:
                logger.debug(f"Free proxy setup failed: {e}")

            logger.warning(
                "No proxy configured for Google Scholar. "
                "You may encounter CAPTCHAs or rate limiting. "
                "Consider setting SCRAPERAPI_KEY or enabling proxy support."
            )
        except Exception as e:
            logger.warning(f"Failed to setup proxy for Google Scholar: {e}")

    def search(self, query: str, max_results: int = 100) -> List[Paper]:
        """
        Search Google Scholar for publications.

        Args:
            query: Search query string
            max_results: Maximum number of results to return

        Returns:
            List of Paper objects
        """
        if not SCHOLARLY_AVAILABLE:
            logger.error("scholarly library not available")
            return []

        # Check cache first
        if self.cache:
            cached = self.cache.get(query, "Google Scholar")
            if cached:
                return cached[:max_results]

        papers = []

        try:
            # Search for publications
            search_query = scholarly.search_pubs(query)

            count = 0
            for pub in search_query:
                if count >= max_results:
                    break

                try:
                    # Fill publication data if needed
                    if not pub.get("filled", False):
                        pub = scholarly.fill(pub)

                    # Extract paper data
                    bib = pub.get("bib", {})

                    # Extract authors
                    authors = []
                    if "author" in bib:
                        if isinstance(bib["author"], list):
                            authors = bib["author"]
                        else:
                            authors = [bib["author"]]

                    # Extract year
                    year = None
                    if "pub_year" in bib:
                        try:
                            year = int(bib["pub_year"])
                        except (ValueError, TypeError):
                            pass
                    elif "year" in bib:
                        try:
                            year = int(bib["year"])
                        except (ValueError, TypeError):
                            pass

                    # Extract citation count
                    citation_count = None
                    if "cites" in pub:
                        try:
                            citation_count = int(pub["cites"])
                        except (ValueError, TypeError):
                            pass

                    # Extract URL
                    url = None
                    if "pub_url" in pub:
                        url = pub["pub_url"]
                    elif "eprint_url" in bib:
                        url = bib["eprint_url"]
                    elif "url" in bib:
                        url = bib["url"]

                    # Extract related/citing papers
                    related_papers = []
                    if "citedby" in pub:
                        # This would require additional API calls
                        pass

                    paper = Paper(
                        title=bib.get("title", ""),
                        abstract=bib.get("abstract", ""),
                        authors=authors,
                        year=year,
                        doi=bib.get("doi"),
                        journal=bib.get("venue", "") or bib.get("journal", ""),
                        database="Google Scholar",
                        url=url,
                        keywords=bib.get("keywords", []),
                        citation_count=citation_count,
                        cited_by_count=None,  # Would need to call citedby() separately
                        scholar_id=pub.get("author_id"),  # Store author ID if available
                        related_papers=related_papers if related_papers else None,
                    )

                    papers.append(paper)
                    count += 1

                except Exception as e:
                    logger.warning(f"Error processing Google Scholar result: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error searching Google Scholar: {e}")
            # Don't raise - return partial results

        # Validate papers
        papers = self._validate_papers(papers)

        # Cache results
        if self.cache and papers:
            self.cache.set(query, "Google Scholar", papers)

        return papers

    def search_author(self, author_name: str, max_results: int = 10) -> List[dict]:
        """
        Search for authors by name.

        Args:
            author_name: Author name to search for
            max_results: Maximum number of results

        Returns:
            List of author dictionaries
        """
        if not SCHOLARLY_AVAILABLE:
            return []

        authors = []
        try:
            search_query = scholarly.search_author(author_name)

            count = 0
            for author in search_query:
                if count >= max_results:
                    break
                authors.append(author)
                count += 1
        except Exception as e:
            logger.error(f"Error searching authors: {e}")

        return authors

    def get_cited_by(self, paper: Paper, max_results: int = 100) -> List[Paper]:
        """
        Find papers that cite the given paper.

        Args:
            paper: Paper object to find citations for
            max_results: Maximum number of citing papers to return

        Returns:
            List of Paper objects that cite the given paper
        """
        if not SCHOLARLY_AVAILABLE:
            return []

        # This requires the paper to have been retrieved from Google Scholar
        # with proper citation link information
        # For now, return empty list - would need paper's Google Scholar ID
        logger.warning("citedby functionality requires paper's Google Scholar metadata")
        return []

    def get_related_articles(self, paper: Paper, max_results: int = 100) -> List[Paper]:
        """
        Find articles related to the given paper.

        Args:
            paper: Paper object
            max_results: Maximum number of related articles

        Returns:
            List of related Paper objects
        """
        if not SCHOLARLY_AVAILABLE:
            return []

        # This would require the paper to have been retrieved from Google Scholar
        logger.warning("Related articles functionality requires paper's Google Scholar metadata")
        return []

    def get_database_name(self) -> str:
        """Return the name of the database."""
        return "Google Scholar"
