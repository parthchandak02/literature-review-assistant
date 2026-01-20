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
try:
    from .connectors.google_scholar_connector import GoogleScholarConnector
except ImportError:
    GoogleScholarConnector = None

try:
    from .models import Author, Affiliation
    from .author_service import AuthorService
    from .citation_network import CitationNetworkBuilder, CitationEdge
except ImportError:
    # Models may not be available
    Author = None
    Affiliation = None
    AuthorService = None
    CitationNetworkBuilder = None
    CitationEdge = None
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
    "GoogleScholarConnector",
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
    "Author",
    "Affiliation",
    "AuthorService",
    "CitationNetworkBuilder",
    "CitationEdge",
]
