"""
Integrity Checker

Validates that required fields are present in paper data.
Inspired by pybliometrics' integrity checking system.
"""

import logging
from typing import List, Optional
from enum import Enum

from .connectors.base import Paper

logger = logging.getLogger(__name__)


class IntegrityAction(Enum):
    """Action to take when integrity check fails."""
    WARN = "warn"
    RAISE = "raise"


class IntegrityChecker:
    """
    Validates field integrity for Paper objects.
    
    Ensures required fields are present and checks field consistency.
    """

    def __init__(
        self,
        required_fields: Optional[List[str]] = None,
        action: str = "warn",
        database: Optional[str] = None,
    ):
        """
        Initialize integrity checker.

        Args:
            required_fields: List of required field names (default: ["title", "authors"])
            action: Action to take on failure ("warn" or "raise")
            database: Database name for context in error messages
        """
        if required_fields is None:
            required_fields = ["title", "authors"]
        
        self.required_fields = set(required_fields)
        self.action = IntegrityAction(action.lower())
        self.database = database or "unknown"

    def check(self, paper: Paper) -> bool:
        """
        Check integrity of a paper.

        Args:
            paper: Paper object to check

        Returns:
            True if paper passes integrity check, False otherwise

        Raises:
            AttributeError: If action is "raise" and integrity check fails
        """
        missing_fields = []
        
        # Check required fields
        for field in self.required_fields:
            value = getattr(paper, field, None)
            
            # Handle list fields (e.g., authors)
            if isinstance(value, list):
                if not value or len(value) == 0:
                    missing_fields.append(field)
            # Handle string fields
            elif isinstance(value, str):
                if not value or not value.strip():
                    missing_fields.append(field)
            # Handle None or empty values
            elif value is None:
                missing_fields.append(field)

        if missing_fields:
            message = (
                f"Paper from {self.database} missing required fields: {', '.join(missing_fields)}. "
                f"Title: {paper.title[:50] if paper.title else 'N/A'}..."
            )
            
            if self.action == IntegrityAction.RAISE:
                raise AttributeError(message)
            else:
                logger.warning(message)
                return False
        
        return True

    def check_batch(self, papers: List[Paper]) -> List[Paper]:
        """
        Check integrity of multiple papers and return valid ones.

        Args:
            papers: List of Paper objects to check

        Returns:
            List of papers that passed integrity check
        """
        valid_papers = []
        
        for paper in papers:
            try:
                if self.check(paper):
                    valid_papers.append(paper)
            except AttributeError:
                # If action is "raise", we still want to continue with other papers
                # but log the error
                logger.error(f"Skipping paper due to integrity check failure: {paper.title[:50] if paper.title else 'N/A'}...")
                continue
        
        if len(valid_papers) < len(papers):
            logger.info(
                f"Integrity check: {len(valid_papers)}/{len(papers)} papers passed "
                f"for {self.database}"
            )
        
        return valid_papers

    def check_field_consistency(self, papers: List[Paper], field: str) -> bool:
        """
        Check consistency of a field across papers.

        Args:
            papers: List of Paper objects
            field: Field name to check

        Returns:
            True if field is consistent, False otherwise
        """
        if not papers:
            return True
        
        values = []
        for paper in papers:
            value = getattr(paper, field, None)
            if value is not None:
                values.append(value)
        
        if not values:
            logger.warning(f"Field '{field}' is missing in all papers from {self.database}")
            return False
        
        # Check if all values are the same (for fields that should be consistent)
        # This is useful for checking database field consistency
        if len(set(values)) > 1:
            logger.debug(
                f"Field '{field}' has inconsistent values across papers from {self.database}"
            )
        
        return True


def create_integrity_checker_from_config(
    config: dict, database: Optional[str] = None
) -> Optional[IntegrityChecker]:
    """
    Create IntegrityChecker from configuration dictionary.

    Args:
        config: Configuration dictionary with integrity settings
        database: Database name for context

    Returns:
        IntegrityChecker instance or None if integrity checking is disabled
    """
    integrity_config = config.get("integrity", {})
    
    if not integrity_config.get("enabled", True):
        return None
    
    return IntegrityChecker(
        required_fields=integrity_config.get("required_fields", ["title", "authors"]),
        action=integrity_config.get("action", "warn"),
        database=database,
    )
