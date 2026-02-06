"""
Multi-Database Searcher

Searches across multiple databases with caching and error handling.
"""

from typing import List, Dict, Optional
import logging

from .connectors.base import DatabaseConnector, Paper
from .cache import SearchCache

logger = logging.getLogger(__name__)


class MultiDatabaseSearcher:
    """Searches across multiple databases with caching and error handling."""

    def __init__(self, cache: Optional[SearchCache] = None):
        """
        Initialize multi-database searcher.

        Args:
            cache: Optional SearchCache instance for caching results
        """
        self.connectors: List[DatabaseConnector] = []
        self.cache = cache

    def add_connector(self, connector: DatabaseConnector):
        """Add a database connector."""
        # Set cache on connector if available
        if self.cache and not connector.cache:
            connector.cache = self.cache
        self.connectors.append(connector)

    def search_all(self, query: str, max_results_per_db: int = 100) -> Dict[str, List[Paper]]:
        """
        Search all databases and return results by database.

        Continues searching even if some databases fail.
        """
        results = {}

        for connector in self.connectors:
            db_name = connector.get_database_name()
            logger.info(f"Searching {db_name}...")

            try:
                papers = connector.search(query, max_results_per_db)
                results[db_name] = papers
                logger.info(f"Found {len(papers)} papers in {db_name}")
            except Exception as e:
                logger.error(f"Error searching {db_name}: {e}")
                results[db_name] = []  # Continue with other databases

        return results

    def search_all_combined(self, query: str, max_results_per_db: int = 100) -> List[Paper]:
        """Search all databases and return combined results."""
        all_results = []
        results_by_db = self.search_all(query, max_results_per_db)

        for _db_name, papers in results_by_db.items():
            all_results.extend(papers)

        return all_results
