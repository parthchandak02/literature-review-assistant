"""Literature Search Module."""

from .connectors.base import Paper, DatabaseConnector
from .multi_database_searcher import MultiDatabaseSearcher
from .database_connectors import (
    PubMedConnector,
    ArxivConnector,
    SemanticScholarConnector,
    CrossrefConnector,
    ScopusConnector,
    ACMConnector,
    MockConnector,
)
from .search_strategy import SearchStrategyBuilder, SearchTerm
from ..deduplication import Deduplicator, DeduplicationResult
from .cache import SearchCache
from .rate_limiter import RateLimiter, get_rate_limiter, retry_with_backoff
from .exceptions import (
    DatabaseSearchError,
    RateLimitError,
    APIKeyError,
    NetworkError,
    ParsingError,
    DatabaseUnavailableError,
    InvalidQueryError,
)
from .search_logger import SearchLogger

__all__ = [
    "Paper",
    "DatabaseConnector",
    "PubMedConnector",
    "ArxivConnector",
    "SemanticScholarConnector",
    "CrossrefConnector",
    "ScopusConnector",
    "ACMConnector",
    "MockConnector",
    "MultiDatabaseSearcher",
    "SearchStrategyBuilder",
    "SearchTerm",
    "Deduplicator",
    "DeduplicationResult",
    "SearchCache",
    "RateLimiter",
    "get_rate_limiter",
    "retry_with_backoff",
    "DatabaseSearchError",
    "RateLimitError",
    "APIKeyError",
    "NetworkError",
    "ParsingError",
    "DatabaseUnavailableError",
    "InvalidQueryError",
    "SearchLogger",
]
