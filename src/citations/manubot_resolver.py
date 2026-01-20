"""
Manubot Citation Resolver

Resolves citations from identifiers (DOI, PubMed ID, arXiv ID, etc.) using Manubot.
"""

import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

try:
    from manubot.cite.citekey import citekey_to_csl_item
    MANUBOT_AVAILABLE = True
except ImportError:
    MANUBOT_AVAILABLE = False
    
    def citekey_to_csl_item(*args, **kwargs):
        """Placeholder function when Manubot is not available."""
        raise ImportError("Manubot package required. Install with: pip install manubot")

from ..search.connectors.base import Paper

logger = logging.getLogger(__name__)


class ManubotCitationResolver:
    """Resolve citations using Manubot's citation resolution."""

    def __init__(self):
        """Initialize Manubot citation resolver."""
        self._manubot_available = MANUBOT_AVAILABLE
        if not self._manubot_available:
            logger.warning(
                "Manubot not available. Install with: pip install manubot"
            )

    def resolve_from_doi(self, doi: str) -> Dict[str, Any]:
        """
        Resolve citation from DOI.

        Args:
            doi: DOI string (e.g., "10.1038/nbt.3780")

        Returns:
            CSL JSON item as dictionary

        Raises:
            ImportError: If Manubot is not installed
            ValueError: If DOI resolution fails
        """
        if not self._manubot_available:
            raise ImportError("Manubot package required. Install with: pip install manubot")

        citekey = f"doi:{doi}"
        try:
            csl_item = citekey_to_csl_item(citekey)
            logger.debug(f"Resolved DOI {doi} to CSL item")
            return csl_item
        except Exception as e:
            logger.error(f"Failed to resolve DOI {doi}: {e}")
            raise ValueError(f"Failed to resolve DOI {doi}: {e}") from e

    def resolve_from_pmid(self, pmid: str) -> Dict[str, Any]:
        """
        Resolve citation from PubMed ID.

        Args:
            pmid: PubMed ID string (e.g., "29424689")

        Returns:
            CSL JSON item as dictionary

        Raises:
            ImportError: If Manubot is not installed
            ValueError: If PMID resolution fails
        """
        if not self._manubot_available:
            raise ImportError("Manubot package required. Install with: pip install manubot")

        citekey = f"pmid:{pmid}"
        try:
            csl_item = citekey_to_csl_item(citekey)
            logger.debug(f"Resolved PMID {pmid} to CSL item")
            return csl_item
        except Exception as e:
            logger.error(f"Failed to resolve PMID {pmid}: {e}")
            raise ValueError(f"Failed to resolve PMID {pmid}: {e}") from e

    def resolve_from_arxiv(self, arxiv_id: str) -> Dict[str, Any]:
        """
        Resolve citation from arXiv ID.

        Args:
            arxiv_id: arXiv ID string (e.g., "1407.3561" or "arXiv:1407.3561")

        Returns:
            CSL JSON item as dictionary

        Raises:
            ImportError: If Manubot is not installed
            ValueError: If arXiv ID resolution fails
        """
        if not self._manubot_available:
            raise ImportError("Manubot package required. Install with: pip install manubot")

        # Handle both formats: "1407.3561" and "arXiv:1407.3561"
        if not arxiv_id.startswith("arXiv:") and not arxiv_id.startswith("arxiv:"):
            citekey = f"arxiv:{arxiv_id}"
        else:
            citekey = arxiv_id

        try:
            csl_item = citekey_to_csl_item(citekey)
            logger.debug(f"Resolved arXiv ID {arxiv_id} to CSL item")
            return csl_item
        except Exception as e:
            logger.error(f"Failed to resolve arXiv ID {arxiv_id}: {e}")
            raise ValueError(f"Failed to resolve arXiv ID {arxiv_id}: {e}") from e

    def resolve_from_identifier(self, identifier: str) -> Dict[str, Any]:
        """
        Resolve citation from identifier (auto-detect type).

        Args:
            identifier: Identifier string (DOI, PMID, arXiv ID, or citekey)

        Returns:
            CSL JSON item as dictionary

        Raises:
            ImportError: If Manubot is not installed
            ValueError: If identifier resolution fails
        """
        if not self._manubot_available:
            raise ImportError("Manubot package required. Install with: pip install manubot")

        # Auto-detect identifier type
        identifier_lower = identifier.lower().strip()

        if identifier_lower.startswith("doi:") or (
            identifier_lower.startswith("10.") and "/" in identifier
        ):
            # DOI
            if identifier_lower.startswith("doi:"):
                doi = identifier[4:].strip()
            else:
                doi = identifier.strip()
            return self.resolve_from_doi(doi)

        elif identifier_lower.startswith("pmid:") or (
            identifier_lower.isdigit() and len(identifier_lower) >= 6
        ):
            # PubMed ID
            if identifier_lower.startswith("pmid:"):
                pmid = identifier[5:].strip()
            else:
                pmid = identifier.strip()
            return self.resolve_from_pmid(pmid)

        elif identifier_lower.startswith("arxiv:") or (
            "." in identifier and any(c.isdigit() for c in identifier)
        ):
            # arXiv ID
            if identifier_lower.startswith("arxiv:"):
                arxiv_id = identifier[6:].strip()
            else:
                arxiv_id = identifier.strip()
            return self.resolve_from_arxiv(arxiv_id)

        else:
            # Try as generic citekey
            try:
                csl_item = citekey_to_csl_item(identifier)
                logger.debug(f"Resolved citekey {identifier} to CSL item")
                return csl_item
            except Exception as e:
                raise ValueError(
                    f"Could not resolve identifier {identifier}: {e}"
                ) from e

    def csl_to_paper(self, csl_item: Dict[str, Any]) -> Paper:
        """
        Convert CSL JSON item to Paper object.

        Args:
            csl_item: CSL JSON item dictionary

        Returns:
            Paper object
        """
        # Extract authors
        authors = []
        if "author" in csl_item:
            for author in csl_item["author"]:
                if "family" in author and "given" in author:
                    authors.append(f"{author['family']}, {author['given']}")
                elif "family" in author:
                    authors.append(author["family"])
                elif "literal" in author:
                    authors.append(author["literal"])

        # Extract title
        title = csl_item.get("title", "")

        # Extract abstract
        abstract = csl_item.get("abstract", "")

        # Extract year
        year = None
        if "issued" in csl_item and "date-parts" in csl_item["issued"]:
            date_parts = csl_item["issued"]["date-parts"]
            if date_parts and len(date_parts[0]) > 0:
                year = int(date_parts[0][0])

        # Extract DOI
        doi = csl_item.get("DOI") or csl_item.get("doi")

        # Extract journal
        journal = (
            csl_item.get("container-title")
            or csl_item.get("journal")
            or csl_item.get("publisher")
        )

        # Extract URL
        url = csl_item.get("URL") or csl_item.get("url")

        # Extract keywords (if available)
        keywords = None
        if "keyword" in csl_item:
            keywords = (
                csl_item["keyword"]
                if isinstance(csl_item["keyword"], list)
                else [csl_item["keyword"]]
            )

        return Paper(
            title=title,
            abstract=abstract,
            authors=authors,
            year=year,
            doi=doi,
            journal=journal,
            url=url,
            keywords=keywords,
            database="Manubot",
        )
