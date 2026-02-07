"""
Bibliometric Enricher

Enriches papers with bibliometric data from pybliometrics and scholarly.
"""

import logging
from typing import Any, Dict, List, Optional

from .author_service import AuthorService
from .citation_network import CitationNetworkBuilder
from .connectors.base import Paper

logger = logging.getLogger(__name__)


class BibliometricEnricher:
    """
    Enriches papers with bibliometric data.

    Uses AuthorService and CitationNetworkBuilder to add:
    - Author metrics (h-index, citation counts)
    - Citation networks
    - Subject areas
    - Coauthor information
    """

    def __init__(
        self,
        author_service: Optional[AuthorService] = None,
        citation_network_builder: Optional[CitationNetworkBuilder] = None,
        enabled: bool = True,
        include_author_metrics: bool = True,
        include_citation_networks: bool = True,
        include_subject_areas: bool = True,
    ):
        """
        Initialize bibliometric enricher.

        Args:
            author_service: Optional AuthorService instance
            citation_network_builder: Optional CitationNetworkBuilder instance
            enabled: Whether bibliometric enrichment is enabled
            include_author_metrics: Whether to include author metrics
            include_citation_networks: Whether to build citation networks
            include_subject_areas: Whether to include subject areas
        """
        self.author_service = author_service
        self.citation_network_builder = citation_network_builder
        self.enabled = enabled
        self.include_author_metrics = include_author_metrics
        self.include_citation_networks = include_citation_networks
        self.include_subject_areas = include_subject_areas

    def enrich_papers(
        self,
        papers: List[Paper],
        max_authors_per_paper: int = 5,
    ) -> List[Paper]:
        """
        Enrich papers with bibliometric data.

        Args:
            papers: List of Paper objects to enrich
            max_authors_per_paper: Maximum number of authors to look up per paper

        Returns:
            List of enriched Paper objects
        """
        if not self.enabled:
            logger.debug("Bibliometric enrichment disabled, skipping")
            return papers

        if not self.author_service:
            logger.warning("AuthorService not available, skipping bibliometric enrichment")
            return papers

        enriched_count = 0

        logger.info(f"Enriching {len(papers)} papers with bibliometric data...")

        for i, paper in enumerate(papers, 1):
            try:
                # Enrich with author metrics if enabled
                if self.include_author_metrics and paper.authors:
                    self._enrich_author_metrics(paper, max_authors_per_paper)

                # Subject areas are already extracted in search if available
                # This is a placeholder for additional enrichment if needed

                if paper.citation_count or paper.subject_areas:
                    enriched_count += 1

            except Exception as e:
                logger.debug(f"Error enriching paper {i} with bibliometric data: {e}")
                continue

            # Log progress every 10 papers
            if i % 10 == 0:
                logger.debug(f"Bibliometric enrichment progress: {i}/{len(papers)}")

        logger.info(f"Bibliometric enrichment complete: {enriched_count} papers enriched")

        return papers

    def _enrich_author_metrics(self, paper: Paper, max_authors: int = 5):
        """
        Enrich paper with author metrics.

        Args:
            paper: Paper object to enrich
            max_authors: Maximum number of authors to look up
        """
        if not self.author_service:
            return

        # Try to get author metrics for first few authors
        authors_to_lookup = paper.authors[:max_authors]

        h_indices = []
        citation_counts = []

        for author_name in authors_to_lookup:
            try:
                # Search for author
                authors = self.author_service.search_author(author_name, max_results=1)
                if authors:
                    author = authors[0]
                    if author.h_index:
                        h_indices.append(author.h_index)
                    if author.citation_count:
                        citation_counts.append(author.citation_count)
            except Exception as e:
                logger.debug(f"Error looking up author {author_name}: {e}")
                continue

        # Set paper-level metrics (use max or average)
        if h_indices:
            paper.h_index = max(h_indices)  # Use max h-index

        # Citation count is already set from search results
        # This would add author-level citation counts if needed

    def build_citation_network(self, papers: List[Paper]) -> Optional[Dict[str, Any]]:
        """
        Build citation network from papers.

        Args:
            papers: List of Paper objects

        Returns:
            Network data dictionary or None
        """
        if not self.include_citation_networks:
            return None

        if not self.citation_network_builder:
            logger.warning("CitationNetworkBuilder not available")
            return None

        try:
            network_data = self.citation_network_builder.build_network_from_papers(papers)
            stats = self.citation_network_builder.get_citation_statistics()

            logger.info(
                f"Citation network built: {stats.get('total_papers', 0)} papers, {stats.get('citation_edges', 0)} edges"
            )

            return {
                "network": network_data,
                "statistics": stats,
            }
        except Exception as e:
            logger.error(f"Error building citation network: {e}")
            return None
