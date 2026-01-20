"""
Base Database Connector

Base classes and Paper dataclass for database connectors.
"""

from typing import List, Optional, Dict, TYPE_CHECKING
from dataclasses import dataclass
from abc import ABC, abstractmethod
import logging
import requests
from pathlib import Path
import os

from ..cache import SearchCache
from ..rate_limiter import get_rate_limiter
from ..proxy_manager import ProxyManager

if TYPE_CHECKING:
    from ..integrity_checker import IntegrityChecker

logger = logging.getLogger(__name__)


@dataclass
class Paper:
    """Represents a research paper."""

    title: str
    abstract: str
    authors: List[str]
    year: Optional[int] = None
    doi: Optional[str] = None
    journal: Optional[str] = None
    database: Optional[str] = None
    url: Optional[str] = None
    keywords: Optional[List[str]] = None
    affiliations: Optional[List[str]] = None
    subjects: Optional[List[str]] = None
    country: Optional[str] = None
    
    # Bibliometric fields (enhanced from pybliometrics and scholarly)
    citation_count: Optional[int] = None  # Total citations
    cited_by_count: Optional[int] = None  # Number of papers citing this paper
    h_index: Optional[int] = None  # Author h-index (if available from author profile)
    coauthors: Optional[List[str]] = None  # List of coauthor names
    subject_areas: Optional[List[str]] = None  # Subject area classifications
    related_papers: Optional[List[str]] = None  # Related paper IDs/DOIs
    eid: Optional[str] = None  # Scopus EID
    pubmed_id: Optional[str] = None  # PubMed ID
    scopus_id: Optional[str] = None  # Scopus author/document ID
    scholar_id: Optional[str] = None  # Google Scholar ID


class DatabaseConnector(ABC):
    """Base class for database connectors."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        cache: Optional[SearchCache] = None,
        proxy_manager: Optional[ProxyManager] = None,
        integrity_checker: Optional["IntegrityChecker"] = None,
        persistent_session: bool = True,
        cookie_jar: Optional[str] = None,
    ):
        self.api_key = api_key
        self.base_url = ""
        self.cache = cache
        self.rate_limiter = None
        self.proxy_manager = proxy_manager
        self.integrity_checker = integrity_checker
        self.persistent_session = persistent_session
        self.cookie_jar = cookie_jar
        self._session: Optional[requests.Session] = None

    def _get_rate_limiter(self):
        """Get rate limiter for this database."""
        if self.rate_limiter is None:
            self.rate_limiter = get_rate_limiter(self.get_database_name())
        return self.rate_limiter

    def _get_session(self) -> requests.Session:
        """
        Get or create HTTP session with proxy support and cookie persistence.

        Returns:
            requests.Session instance
        """
        if self._session is None:
            self._session = requests.Session()
            
            # Configure proxies if available
            if self.proxy_manager and self.proxy_manager.has_proxy():
                proxies = self.proxy_manager.get_proxies()
                if proxies:
                    self._session.proxies = proxies
                    logger.debug(f"Using proxy for {self.get_database_name()}: {proxies.get('http', 'N/A')}")
            
            # Configure cookie persistence if enabled
            if self.persistent_session and self.cookie_jar:
                try:
                    from http.cookiejar import LWPCookieJar
                    cookie_path = Path(self.cookie_jar)
                    cookie_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    jar = LWPCookieJar(str(cookie_path))
                    if cookie_path.exists():
                        jar.load(ignore_discard=True, ignore_expires=True)
                    self._session.cookies = jar
                    logger.debug(f"Using persistent cookie jar: {cookie_path}")
                except Exception as e:
                    logger.warning(f"Failed to setup cookie persistence: {e}")
        
        return self._session
    
    def _save_session_cookies(self):
        """Save session cookies if persistent session is enabled."""
        if self._session and self.persistent_session and self.cookie_jar:
            try:
                if hasattr(self._session.cookies, 'save'):
                    self._session.cookies.save(ignore_discard=True)
                    logger.debug(f"Saved cookies to {self.cookie_jar}")
            except Exception as e:
                logger.debug(f"Failed to save cookies: {e}")

    def _get_request_kwargs(self) -> Dict:
        """
        Get keyword arguments for requests (proxies, timeout, etc.).

        Returns:
            Dictionary with request parameters
        """
        kwargs = {}
        
        if self.proxy_manager and self.proxy_manager.has_proxy():
            proxies = self.proxy_manager.get_proxies()
            if proxies:
                kwargs["proxies"] = proxies
                kwargs["timeout"] = self.proxy_manager.get_timeout()
        
        return kwargs

    def _validate_paper(self, paper: Paper) -> bool:
        """
        Validate paper integrity if integrity checker is configured.

        Args:
            paper: Paper object to validate

        Returns:
            True if paper is valid, False otherwise
        """
        if self.integrity_checker:
            try:
                return self.integrity_checker.check(paper)
            except AttributeError:
                # If action is "raise", integrity_checker.check will raise
                # but we want to handle it gracefully
                return False
        return True

    def _validate_papers(self, papers: List[Paper]) -> List[Paper]:
        """
        Validate multiple papers and return valid ones.

        Args:
            papers: List of Paper objects to validate

        Returns:
            List of valid papers
        """
        if self.integrity_checker:
            return self.integrity_checker.check_batch(papers)
        return papers

    @abstractmethod
    def search(self, query: str, max_results: int = 100) -> List[Paper]:
        """Search the database and return list of papers."""
        pass

    @abstractmethod
    def get_database_name(self) -> str:
        """Return the name of the database."""
        pass
