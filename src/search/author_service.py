"""
Author Service

Unified interface for author retrieval across multiple databases.
Aggregates author profiles and bibliometric data from different sources.
"""

import logging
from typing import Any, Dict, List, Optional

from .connectors.base import DatabaseConnector
from .models import Affiliation, Author

logger = logging.getLogger(__name__)


class AuthorService:
    """
    Unified service for author retrieval across databases.

    Aggregates author profiles from multiple sources and provides
    a consistent interface for bibliometric data.
    """

    def __init__(self, connectors: Dict[str, DatabaseConnector]):
        """
        Initialize author service.

        Args:
            connectors: Dictionary mapping database names to connector instances
        """
        self.connectors = connectors

    def get_author(
        self,
        author_id: str,
        database: Optional[str] = None,
        author_name: Optional[str] = None,
    ) -> Optional[Author]:
        """
        Retrieve author by ID or name.

        Args:
            author_id: Database-specific author ID
            database: Database name (e.g., "Scopus", "Google Scholar")
            author_name: Author name (used for search if ID not available)

        Returns:
            Author object or None if not found
        """
        # If database specified, use that connector
        if database and database in self.connectors:
            connector = self.connectors[database]
            if hasattr(connector, "get_author_by_id"):
                return connector.get_author_by_id(author_id)

        # Try all connectors that support author retrieval
        for db_name, connector in self.connectors.items():
            if hasattr(connector, "get_author_by_id"):
                try:
                    author = connector.get_author_by_id(author_id)
                    if author:
                        return author
                except Exception as e:
                    logger.debug(f"Error retrieving author from {db_name}: {e}")
                    continue

        # If ID lookup failed and name provided, try search
        if author_name:
            return (
                self.search_author(author_name, max_results=1)[0]
                if self.search_author(author_name, max_results=1)
                else None
            )

        return None

    def search_author(
        self,
        query: str,
        database: Optional[str] = None,
        max_results: int = 10,
    ) -> List[Author]:
        """
        Search for authors by name or query.

        Args:
            query: Search query (author name or database-specific query)
            database: Database name to search (None = search all)
            max_results: Maximum number of results per database

        Returns:
            List of Author objects
        """
        authors = []

        # If database specified, use that connector
        if database and database in self.connectors:
            connector = self.connectors[database]
            if hasattr(connector, "search_authors"):
                try:
                    results = connector.search_authors(query, max_results)
                    authors.extend(results)
                except Exception as e:
                    logger.debug(f"Error searching authors in {database}: {e}")
            elif hasattr(connector, "search_author"):
                # Google Scholar uses search_author
                try:
                    results = connector.search_author(query, max_results)
                    # Convert to Author objects if needed
                    for result in results:
                        author = self._convert_scholar_author(result)
                        if author:
                            authors.append(author)
                except Exception as e:
                    logger.debug(f"Error searching authors in {database}: {e}")
            return authors

        # Search all databases
        for db_name, connector in self.connectors.items():
            try:
                if hasattr(connector, "search_authors"):
                    results = connector.search_authors(query, max_results)
                    authors.extend(results)
                elif hasattr(connector, "search_author"):
                    # Google Scholar
                    results = connector.search_author(query, max_results)
                    for result in results:
                        author = self._convert_scholar_author(result)
                        if author:
                            authors.append(author)
            except Exception as e:
                logger.debug(f"Error searching authors in {db_name}: {e}")
                continue

        return authors

    def get_author_metrics(
        self,
        author_id: str,
        database: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get bibliometric metrics for an author.

        Args:
            author_id: Author ID
            database: Database name

        Returns:
            Dictionary with metrics (h_index, citation_count, etc.)
        """
        author = self.get_author(author_id, database)
        if not author:
            return {}

        return {
            "h_index": author.h_index,
            "i10_index": author.i10_index,
            "h_index_5y": author.h_index_5y,
            "i10_index_5y": author.i10_index_5y,
            "citation_count": author.citation_count,
            "cited_by_count": author.cited_by_count,
            "document_count": author.document_count,
            "coauthor_count": author.coauthor_count,
        }

    def get_coauthors(
        self,
        author_id: str,
        database: Optional[str] = None,
        max_results: int = 50,
    ) -> List[Author]:
        """
        Get coauthors for an author.

        Args:
            author_id: Author ID
            database: Database name
            max_results: Maximum number of coauthors

        Returns:
            List of Author objects (coauthors)
        """
        author = self.get_author(author_id, database)
        if not author:
            return []

        # Return coauthors if already loaded
        if author.coauthors:
            return author.coauthors[:max_results]

        # Try to fetch coauthors if connector supports it
        if database and database in self.connectors:
            self.connectors[database]
            # This would require additional connector methods
            # For now, return empty list
            pass

        return []

    def aggregate_author_profiles(
        self,
        author_name: str,
        databases: Optional[List[str]] = None,
    ) -> Optional[Author]:
        """
        Aggregate author profiles from multiple databases.

        Combines data from different sources to create a comprehensive profile.

        Args:
            author_name: Author name to search for
            databases: List of databases to search (None = all)

        Returns:
            Aggregated Author object
        """
        if databases is None:
            databases = list(self.connectors.keys())

        profiles = []
        for db_name in databases:
            if db_name not in self.connectors:
                continue

            authors = self.search_author(author_name, database=db_name, max_results=1)
            if authors:
                profiles.append(authors[0])

        if not profiles:
            return None

        # Merge profiles (use first as base, enrich with data from others)
        base = profiles[0]

        for profile in profiles[1:]:
            # Merge metrics (take maximum or average)
            if profile.h_index and (not base.h_index or profile.h_index > base.h_index):
                base.h_index = profile.h_index
            if profile.citation_count and (
                not base.citation_count or profile.citation_count > base.citation_count
            ):
                base.citation_count = profile.citation_count

            # Merge affiliations
            for aff in profile.current_affiliations:
                if aff not in base.current_affiliations:
                    base.current_affiliations.append(aff)

            # Merge subject areas
            for area in profile.subject_areas:
                if area not in base.subject_areas:
                    base.subject_areas.append(area)

        return base

    def _convert_scholar_author(self, scholar_data: dict) -> Optional[Author]:
        """
        Convert Google Scholar author data to Author model.

        Args:
            scholar_data: Dictionary from scholarly library

        Returns:
            Author object or None
        """
        try:
            # scholarly returns dictionaries, need to fill for full data
            # For now, create basic author from available data
            author = Author(
                name=scholar_data.get("name", ""),
                id=scholar_data.get("id"),
                email=scholar_data.get("email"),
                h_index=scholar_data.get("hindex"),
                i10_index=scholar_data.get("i10index"),
                citation_count=scholar_data.get("citedby"),
                database="Google Scholar",
                url=scholar_data.get("url_picture"),
            )

            # Add affiliation if available
            if scholar_data.get("affiliation"):
                author.current_affiliations.append(Affiliation(name=scholar_data["affiliation"]))

            # Add research interests
            if scholar_data.get("interests"):
                author.research_interests = scholar_data["interests"]

            return author
        except Exception as e:
            logger.debug(f"Error converting scholar author: {e}")
            return None
