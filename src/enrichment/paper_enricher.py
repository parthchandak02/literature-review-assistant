"""
Paper Enricher

Enriches Paper objects with missing metadata by fetching from Crossref API using DOI.
"""

import logging
import os
import requests
from typing import List, Optional
from pathlib import Path

from ..search.connectors.base import Paper
from ..search.database_connectors import CrossrefConnector
from ..search.exceptions import RateLimitError, NetworkError, DatabaseSearchError
from ..search.rate_limiter import retry_with_backoff, get_rate_limiter

logger = logging.getLogger(__name__)


class PaperEnricher:
    """Enriches papers with missing affiliation data from Crossref API."""

    def __init__(self, crossref_connector: Optional[CrossrefConnector] = None):
        """
        Initialize paper enricher.

        Args:
            crossref_connector: Optional CrossrefConnector instance (creates one if not provided)
        """
        self.crossref = crossref_connector or CrossrefConnector(
            email=os.getenv("CROSSREF_EMAIL", "user@example.com")
        )

    def enrich_papers(self, papers: List[Paper]) -> List[Paper]:
        """
        Enrich papers with missing affiliation data from Crossref.

        Args:
            papers: List of Paper objects to enrich

        Returns:
            List of enriched Paper objects
        """
        enriched = []
        enriched_count = 0
        skipped_count = 0

        logger.info(f"Starting enrichment of {len(papers)} papers...")

        for i, paper in enumerate(papers, 1):
            # Skip if already has affiliations
            if paper.affiliations:
                enriched.append(paper)
                skipped_count += 1
                continue

            # Skip if no DOI
            if not paper.doi:
                enriched.append(paper)
                skipped_count += 1
                continue

            # Try to fetch enriched data
            try:
                enriched_paper = self._fetch_by_doi(paper.doi)
                if enriched_paper and enriched_paper.affiliations:
                    # Update paper with enriched affiliations
                    paper.affiliations = enriched_paper.affiliations
                    enriched_count += 1
                    logger.debug(
                        f"Enriched paper {i}/{len(papers)}: {paper.title[:50]}... "
                        f"(found {len(enriched_paper.affiliations)} affiliations)"
                    )
                else:
                    logger.debug(
                        f"No affiliations found for paper {i}/{len(papers)}: {paper.doi}"
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to enrich paper {i}/{len(papers)} (DOI: {paper.doi}): {e}"
                )

            enriched.append(paper)

            # Log progress every 10 papers
            if i % 10 == 0:
                logger.info(
                    f"Enrichment progress: {i}/{len(papers)} processed, "
                    f"{enriched_count} enriched, {skipped_count} skipped"
                )

        logger.info(
            f"Enrichment complete: {enriched_count} papers enriched, "
            f"{skipped_count} skipped (already had affiliations or no DOI)"
        )

        return enriched

    @retry_with_backoff(max_attempts=3)
    def _fetch_by_doi(self, doi: str) -> Optional[Paper]:
        """
        Fetch paper metadata by DOI from Crossref API.

        Args:
            doi: DOI string (with or without https://doi.org/ prefix)

        Returns:
            Paper object with enriched data, or None if not found
        """
        # Normalize DOI (remove https://doi.org/ prefix if present)
        normalized_doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()

        if not normalized_doi:
            return None

        try:
            # Use rate limiter to respect Crossref's rate limits (10 req/sec)
            rate_limiter = get_rate_limiter("Crossref")
            rate_limiter.acquire()
            
            # Use Crossref API to get full record by DOI
            url = f"https://api.crossref.org/works/{normalized_doi}"
            params = {"mailto": self.crossref.email}

            response = requests.get(url, params=params, timeout=30)

            if response.status_code == 404:
                logger.debug(f"DOI not found in Crossref: {normalized_doi}")
                return None

            if response.status_code == 429:
                raise RateLimitError("Crossref rate limit exceeded")

            response.raise_for_status()
            data = response.json()

            if "message" not in data:
                return None

            item = data["message"]

            # Extract affiliations from author data
            affiliations = []
            authors = []

            if "author" in item and isinstance(item["author"], list):
                for author in item["author"]:
                    if isinstance(author, dict):
                        # Extract author name
                        given = author.get("given", "")
                        family = author.get("family", "")
                        if family:
                            name = f"{given} {family}".strip()
                            if name:
                                authors.append(name)

                        # Extract affiliations from author objects
                        if "affiliation" in author:
                            aff_list = (
                                author["affiliation"]
                                if isinstance(author["affiliation"], list)
                                else [author["affiliation"]]
                            )
                            for aff in aff_list:
                                if isinstance(aff, dict):
                                    # Try different possible fields
                                    aff_name = (
                                        aff.get("name")
                                        or aff.get("affiliation")
                                        or aff.get("institution")
                                    )
                                    if aff_name and aff_name.strip():
                                        affiliations.append(aff_name.strip())
                                elif isinstance(aff, str) and aff.strip():
                                    affiliations.append(aff.strip())

            # Remove duplicates while preserving order
            seen = set()
            unique_affiliations = []
            for aff in affiliations:
                if aff not in seen:
                    seen.add(aff)
                    unique_affiliations.append(aff)

            # Create Paper object with enriched data
            if unique_affiliations:
                enriched_paper = Paper(
                    title=item.get("title", [""])[0] if isinstance(item.get("title"), list) else item.get("title", ""),
                    abstract="",  # Not needed for enrichment
                    authors=authors,
                    year=None,
                    doi=normalized_doi,
                    journal=None,
                    database="Crossref",
                    url=f"https://doi.org/{normalized_doi}",
                    keywords=None,
                    affiliations=unique_affiliations,
                    subjects=None,
                )
                return enriched_paper

        except requests.RequestException as e:
            logger.error(f"Network error fetching DOI {normalized_doi}: {e}")
            raise NetworkError(f"Crossref fetch failed: {e}") from e
        except Exception as e:
            logger.error(f"Error fetching DOI {normalized_doi}: {e}")
            raise DatabaseSearchError(f"Crossref fetch error: {e}") from e

        return None
