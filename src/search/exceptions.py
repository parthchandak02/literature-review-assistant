"""
Custom exceptions for database search operations.
"""


class DatabaseSearchError(Exception):
    """Base exception for database search errors."""

    pass


class RateLimitError(DatabaseSearchError):
    """Raised when rate limit is exceeded."""

    pass


class APIKeyError(DatabaseSearchError):
    """Raised when API key is missing or invalid."""

    pass


class NetworkError(DatabaseSearchError):
    """Raised when network request fails."""

    pass


class ParsingError(DatabaseSearchError):
    """Raised when response parsing fails."""

    pass


class DatabaseUnavailableError(DatabaseSearchError):
    """Raised when database is temporarily unavailable."""

    pass


class InvalidQueryError(DatabaseSearchError):
    """Raised when query is invalid."""

    pass


class ForbiddenError(DatabaseSearchError):
    """Raised when access is forbidden (403). Does not trigger retries."""

    pass
