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
    MockConnector,
)
from ..search.cache import SearchCache

logger = logging.getLogger(__name__)


class DatabaseConnectorFactory:
    """Factory for creating database connectors."""

    @staticmethod
    def create_connector(
        db_name: str, cache: Optional[SearchCache] = None
    ) -> Optional[DatabaseConnector]:
        """
        Create appropriate connector based on database name and available API keys.

        Args:
            db_name: Name of the database
            cache: Optional search cache instance

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
                return PubMedConnector(api_key=api_key, email=email, cache=cache)
            else:
                logger.warning("PubMed: No API key or email set, using mock connector")
                return MockConnector("PubMed")

        elif db_lower == "arxiv":
            logger.info("arXiv: Using real connector (no API key needed)")
            return ArxivConnector(cache=cache)

        elif db_lower == "semantic scholar":
            api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
            if api_key:
                logger.info("Semantic Scholar: Using real connector (API key: SET)")
            else:
                logger.info("Semantic Scholar: Using real connector (no API key, lower rate limits)")
            return SemanticScholarConnector(api_key=api_key, cache=cache)

        elif db_lower == "crossref":
            email = os.getenv("CROSSREF_EMAIL")
            if email:
                logger.info("Crossref: Using real connector (Email: SET)")
            else:
                logger.info("Crossref: Using real connector (no email, lower rate limits)")
            return CrossrefConnector(email=email, cache=cache)

        elif db_lower == "scopus":
            api_key = os.getenv("SCOPUS_API_KEY")
            if api_key:
                logger.info("Scopus: Using real connector (API key: SET)")
                return ScopusConnector(api_key=api_key, cache=cache)
            else:
                logger.warning("Scopus: API key required but not set, skipping")
                return None  # Skip Scopus if no key

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
            else:
                can_use = False
                reason = "Unknown database"

            validation[db_name] = can_use

            if not can_use:
                logger.warning(f"{db_name}: Cannot use - {reason}")
            else:
                logger.debug(f"{db_name}: Can use - {reason}")

        return validation
