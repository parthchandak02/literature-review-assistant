"""Literature Search Module."""

from .connectors.base import DatabaseConnector, Paper
from .database_connectors import (
    ACMConnector,
    ArxivConnector,
    CrossrefConnector,
    IEEEXploreConnector,
    MockConnector,
    PubMedConnector,
    ScopusConnector,
    SemanticScholarConnector,
    SpringerConnector,
)
from .multi_database_searcher import MultiDatabaseSearcher

try:
    from .connectors.google_scholar_connector import GoogleScholarConnector
except ImportError:
    GoogleScholarConnector = None

try:
    from .author_service import AuthorService
    from .citation_network import CitationEdge, CitationNetworkBuilder
    from .models import Affiliation, Author
except ImportError:
    # Models may not be available
    Author = None
    Affiliation = None
    AuthorService = None
    CitationNetworkBuilder = None
    CitationEdge = None
from ..deduplication import DeduplicationResult, Deduplicator
from .cache import SearchCache
from .exceptions import (
    APIKeyError,
    DatabaseSearchError,
    DatabaseUnavailableError,
    InvalidQueryError,
    NetworkError,
    ParsingError,
    RateLimitError,
)
from .rate_limiter import RateLimiter, get_rate_limiter, retry_with_backoff
from .search_logger import SearchLogger
from .search_strategy import SearchStrategyBuilder, SearchTerm

__all__ = [
    "ACMConnector",
    "APIKeyError",
    "Affiliation",
    "ArxivConnector",
    "Author",
    "AuthorService",
    "CitationEdge",
    "CitationNetworkBuilder",
    "CrossrefConnector",
    "DatabaseConnector",
    "DatabaseSearchError",
    "DatabaseUnavailableError",
    "DeduplicationResult",
    "Deduplicator",
    "GoogleScholarConnector",
    "IEEEXploreConnector",
    "InvalidQueryError",
    "MockConnector",
    "MultiDatabaseSearcher",
    "NetworkError",
    "Paper",
    "ParsingError",
    "PubMedConnector",
    "RateLimitError",
    "RateLimiter",
    "ScopusConnector",
    "SearchCache",
    "SearchLogger",
    "SearchStrategyBuilder",
    "SearchTerm",
    "SemanticScholarConnector",
    "SpringerConnector",
    "get_rate_limiter",
    "retry_with_backoff",
]
