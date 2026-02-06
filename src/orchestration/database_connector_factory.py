"""
Database Connector Factory

Factory for creating database connectors based on configuration and API keys.
"""

import os
import logging
from typing import Optional

from ..search.connectors.base import DatabaseConnector
from ..search.database_connectors import (
    PubMedConnector,
    ArxivConnector,
    SemanticScholarConnector,
    CrossrefConnector,
    ScopusConnector,
    ACMConnector,
    SpringerConnector,
    IEEEXploreConnector,
    PerplexityConnector,
    MockConnector,
)
try:
    from ..search.connectors.google_scholar_connector import GoogleScholarConnector
    GOOGLE_SCHOLAR_AVAILABLE = True
except ImportError:
    GOOGLE_SCHOLAR_AVAILABLE = False
    GoogleScholarConnector = None
from ..search.cache import SearchCache
from ..search.proxy_manager import ProxyManager
from ..search.integrity_checker import IntegrityChecker

logger = logging.getLogger(__name__)


class DatabaseConnectorFactory:
    """Factory for creating database connectors."""

    @staticmethod
    def create_connector(
        db_name: str,
        cache: Optional[SearchCache] = None,
        proxy_manager: Optional[ProxyManager] = None,
        integrity_checker: Optional[IntegrityChecker] = None,
        persistent_session: bool = True,
        cookie_jar: Optional[str] = None,
    ) -> Optional[DatabaseConnector]:
        """
        Create appropriate connector based on database name and available API keys.

        Args:
            db_name: Name of the database
            cache: Optional search cache instance
            proxy_manager: Optional proxy manager instance
            integrity_checker: Optional integrity checker instance
            persistent_session: Whether to use persistent HTTP sessions
            cookie_jar: Path to cookie jar directory

        Returns:
            DatabaseConnector instance or None if database should be skipped
        """
        db_lower = db_name.lower()

        if db_lower == "pubmed":
            api_key = os.getenv("PUBMED_API_KEY")
            email = os.getenv("PUBMED_EMAIL")
            if api_key or email:
                logger.info(
                    f"PubMed: Using real connector (API key: {'SET' if api_key else 'NOT SET'}, "
                    f"Email: {'SET' if email else 'NOT SET'})"
                )
                return PubMedConnector(
                    api_key=api_key,
                    email=email,
                    cache=cache,
                    proxy_manager=proxy_manager,
                    integrity_checker=integrity_checker,
                    persistent_session=persistent_session,
                    cookie_jar=cookie_jar,
                )
            else:
                logger.warning("PubMed: No API key or email set, using mock connector")
                return MockConnector("PubMed")

        elif db_lower == "arxiv":
            logger.info("arXiv: Using real connector (no API key needed)")
            return ArxivConnector(
                cache=cache,
                proxy_manager=proxy_manager,
                integrity_checker=integrity_checker,
                persistent_session=persistent_session,
                cookie_jar=cookie_jar,
            )

        elif db_lower == "semantic scholar":
            api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
            if api_key:
                logger.info("Semantic Scholar: Using real connector (API key: SET)")
            else:
                logger.info("Semantic Scholar: Using real connector (no API key, lower rate limits)")
            return SemanticScholarConnector(
                api_key=api_key,
                cache=cache,
                proxy_manager=proxy_manager,
                integrity_checker=integrity_checker,
                persistent_session=persistent_session,
                cookie_jar=cookie_jar,
            )

        elif db_lower == "crossref":
            email = os.getenv("CROSSREF_EMAIL")
            if email:
                logger.info("Crossref: Using real connector (Email: SET)")
            else:
                logger.info("Crossref: Using real connector (no email, lower rate limits)")
            return CrossrefConnector(
                email=email,
                cache=cache,
                proxy_manager=proxy_manager,
                integrity_checker=integrity_checker,
                persistent_session=persistent_session,
                cookie_jar=cookie_jar,
            )

        elif db_lower == "scopus":
            api_key = os.getenv("SCOPUS_API_KEY")
            if api_key:
                logger.info("Scopus: Using real connector (API key: SET)")
                # Check for view configuration (COMPLETE for subscribers, STANDARD otherwise)
                view = os.getenv("SCOPUS_VIEW")  # None = auto-detect based on subscriber
                # Check for subscriber setting (default to False for free tier)
                subscriber_env = os.getenv("SCOPUS_SUBSCRIBER", "false").lower()
                subscriber = subscriber_env in ("true", "1", "yes")
                logger.info(f"Scopus: subscriber={subscriber}, view={view or 'auto'}")
                return ScopusConnector(
                    api_key=api_key,
                    cache=cache,
                    proxy_manager=proxy_manager,
                    integrity_checker=integrity_checker,
                    view=view,
                    subscriber=subscriber,
                    persistent_session=persistent_session,
                    cookie_jar=cookie_jar,
                )
            else:
                logger.warning("Scopus: API key required but not set, skipping")
                return None  # Skip Scopus if no key

        elif db_lower == "acm":
            logger.info("ACM: Using real connector (web scraping, no API key needed)")
            return ACMConnector(
                cache=cache,
                proxy_manager=proxy_manager,
                integrity_checker=integrity_checker,
                persistent_session=persistent_session,
                cookie_jar=cookie_jar,
            )

        elif db_lower == "springer":
            logger.info("Springer: Using real connector (web scraping, no API key needed)")
            return SpringerConnector(
                cache=cache,
                proxy_manager=proxy_manager,
                integrity_checker=integrity_checker,
                persistent_session=persistent_session,
                cookie_jar=cookie_jar,
            )

        elif db_lower in ["ieee", "ieee xplore"]:
            api_key = os.getenv("IEEE_API_KEY")
            if api_key:
                logger.info("IEEE Xplore: Using real connector (API key: SET)")
            else:
                logger.info("IEEE Xplore: Using real connector (web scraping, no API key)")
            return IEEEXploreConnector(
                api_key=api_key,
                cache=cache,
                proxy_manager=proxy_manager,
                integrity_checker=integrity_checker,
                persistent_session=persistent_session,
                cookie_jar=cookie_jar,
            )

        elif db_lower == "google scholar":
            if not GOOGLE_SCHOLAR_AVAILABLE:
                logger.warning(
                    "Google Scholar: scholarly library not available. "
                    "Install with: pip install scholarly or pip install -e '.[bibliometrics]'"
                )
                return None

            # Google Scholar requires proxy for reliable operation
            use_proxy = proxy_manager is not None and proxy_manager.has_proxy()
            if not use_proxy:
                logger.warning(
                    "Google Scholar: Proxy highly recommended to avoid CAPTCHAs. "
                    "Consider enabling proxy in configuration."
                )

            logger.info(f"Google Scholar: Using real connector (proxy: {'ENABLED' if use_proxy else 'DISABLED'})")
            return GoogleScholarConnector(
                cache=cache,
                proxy_manager=proxy_manager,
                integrity_checker=integrity_checker,
                persistent_session=persistent_session,
                cookie_jar=cookie_jar,
                use_proxy=use_proxy,
            )

        elif db_lower == "perplexity":
            # Use PERPLEXITY_SEARCH_API_KEY for search (separate from LLM API key)
            api_key = os.getenv("PERPLEXITY_SEARCH_API_KEY") or os.getenv("PERPLEXITY_API_KEY")
            if api_key:
                logger.info("Perplexity: Using real connector for search (API key: SET)")
                return PerplexityConnector(
                    api_key=api_key,
                    cache=cache,
                    proxy_manager=proxy_manager,
                    integrity_checker=integrity_checker,
                    persistent_session=persistent_session,
                    cookie_jar=cookie_jar,
                )
            else:
                logger.warning("Perplexity: Search API key required but not set (PERPLEXITY_SEARCH_API_KEY), skipping")
                return None  # Skip Perplexity if no key

        else:
            logger.warning(f"Unknown database: {db_name}, using mock connector")
            return MockConnector(db_name)

    @staticmethod
    def validate_database_config(databases: list) -> dict:
        """
        Validate which databases can be used based on API keys.

        Args:
            databases: List of database names

        Returns:
            Dictionary mapping database names to whether they can be used
        """
        validation = {}

        for db_name in databases:
            db_lower = db_name.lower()
            can_use = False
            reason = ""

            if db_lower == "pubmed":
                can_use = True  # Works without API key
                reason = "Works without API key"
            elif db_lower == "arxiv":
                can_use = True  # No API key needed
                reason = "No API key needed"
            elif db_lower == "semantic scholar":
                can_use = True  # Works without API key (lower limits)
                reason = "Works without API key (lower rate limits)"
            elif db_lower == "crossref":
                can_use = True  # Works without email (lower limits)
                reason = "Works without email (lower rate limits)"
            elif db_lower == "scopus":
                can_use = bool(os.getenv("SCOPUS_API_KEY"))
                reason = "API key required" if not can_use else "API key available"
            elif db_lower == "acm":
                can_use = True  # Works without API key (web scraping)
                reason = "Works without API key (web scraping)"
            elif db_lower == "springer":
                can_use = True  # Works without API key (web scraping)
                reason = "Works without API key (web scraping)"
            elif db_lower in ["ieee", "ieee xplore"]:
                can_use = True  # Works without API key (web scraping)
                reason = "Works without API key (web scraping)"
            elif db_lower == "google scholar":
                can_use = GOOGLE_SCHOLAR_AVAILABLE
                reason = "scholarly library required" if not can_use else "Works without API key (proxy recommended)"
            elif db_lower == "perplexity":
                can_use = bool(os.getenv("PERPLEXITY_SEARCH_API_KEY") or os.getenv("PERPLEXITY_API_KEY"))
                reason = "Search API key required (PERPLEXITY_SEARCH_API_KEY)" if not can_use else "Search API key available"
            else:
                can_use = False
                reason = "Unknown database"

            validation[db_name] = can_use

            if not can_use:
                logger.warning(f"{db_name}: Cannot use - {reason}")
            else:
                logger.debug(f"{db_name}: Can use - {reason}")

        return validation
