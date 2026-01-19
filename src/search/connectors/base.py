"""
Base Database Connector

Base classes and Paper dataclass for database connectors.
"""

from typing import List, Optional
from dataclasses import dataclass
from abc import ABC, abstractmethod
import logging

from ..cache import SearchCache
from ..rate_limiter import get_rate_limiter

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


class DatabaseConnector(ABC):
    """Base class for database connectors."""

    def __init__(self, api_key: Optional[str] = None, cache: Optional[SearchCache] = None):
        self.api_key = api_key
        self.base_url = ""
        self.cache = cache
        self.rate_limiter = None

    def _get_rate_limiter(self):
        """Get rate limiter for this database."""
        if self.rate_limiter is None:
            self.rate_limiter = get_rate_limiter(self.get_database_name())
        return self.rate_limiter

    @abstractmethod
    def search(self, query: str, max_results: int = 100) -> List[Paper]:
        """Search the database and return list of papers."""
        pass

    @abstractmethod
    def get_database_name(self) -> str:
        """Return the name of the database."""
        pass
