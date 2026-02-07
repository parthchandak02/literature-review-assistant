"""
Rate limiting and retry logic for database API calls.
"""

import time
import random
from typing import Callable
from threading import Lock
from collections import deque
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
import logging

from .exceptions import NetworkError, DatabaseUnavailableError

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Token bucket rate limiter for API calls.

    Implements a sliding window rate limiter to respect API rate limits.
    """

    def __init__(self, max_requests: float, time_window: float = 1.0):
        """
        Initialize rate limiter.

        Args:
            max_requests: Maximum number of requests allowed
            time_window: Time window in seconds (default: 1.0 second)
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = deque()
        self.lock = Lock()

    def acquire(self):
        """
        Acquire permission to make a request.
        Blocks if necessary to respect rate limits.
        """
        with self.lock:
            now = time.time()

            # Remove requests outside the time window
            while self.requests and self.requests[0] < now - self.time_window:
                self.requests.popleft()

            # If we're at the limit, wait until the oldest request expires
            if len(self.requests) >= self.max_requests:
                sleep_time = self.time_window - (now - self.requests[0])
                if sleep_time > 0:
                    logger.debug(f"Rate limit reached, sleeping for {sleep_time:.2f}s")
                    time.sleep(sleep_time)
                    # Clean up again after sleep
                    now = time.time()
                    while self.requests and self.requests[0] < now - self.time_window:
                        self.requests.popleft()

            # Record this request
            self.requests.append(time.time())

    def __call__(self, func: Callable) -> Callable:
        """Decorator to rate limit a function."""

        def wrapper(*args, **kwargs):
            self.acquire()
            return func(*args, **kwargs)

        return wrapper


# Database-specific rate limiters
RATE_LIMITERS = {
    "PubMed": RateLimiter(max_requests=3.0, time_window=1.0),
    "arXiv": RateLimiter(max_requests=3.0, time_window=1.0),
    "Semantic Scholar": RateLimiter(max_requests=1.0, time_window=1.0),
    "Crossref": RateLimiter(max_requests=10.0, time_window=1.0),  # Conservative limit
    "Scopus": RateLimiter(max_requests=9.0, time_window=1.0),  # 9 req/sec typical
    "IEEE": RateLimiter(max_requests=5.0, time_window=1.0),
    "IEEE Xplore": RateLimiter(max_requests=2.0, time_window=1.0),  # Conservative for web scraping
    "ACM": RateLimiter(max_requests=2.0, time_window=1.0),  # Conservative for web scraping
    "Springer": RateLimiter(max_requests=2.0, time_window=1.0),  # Conservative for web scraping
    "Perplexity": RateLimiter(
        max_requests=5.0, time_window=1.0
    ),  # Conservative limit for Search API
}


def get_rate_limiter(database_name: str) -> RateLimiter:
    """
    Get rate limiter for a specific database.

    Args:
        database_name: Name of the database

    Returns:
        RateLimiter instance
    """
    return RATE_LIMITERS.get(database_name, RateLimiter(max_requests=5.0, time_window=1.0))


def retry_with_backoff(
    max_attempts: int = 3,
    initial_wait: float = 1.0,
    max_wait: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
):
    """
    Decorator for retrying API calls with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        initial_wait: Initial wait time in seconds
        max_wait: Maximum wait time in seconds
        exponential_base: Base for exponential backoff
        jitter: Whether to add random jitter to wait times
    """

    def decorator(func: Callable) -> Callable:
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=initial_wait, max=max_wait, exp_base=exponential_base)
            + (lambda retry_state: random.uniform(0, 0.1) if jitter else 0),
            retry=retry_if_exception_type((NetworkError, DatabaseUnavailableError)),
            before_sleep=before_sleep_log(logger, logging.WARNING),
        )
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Convert certain exceptions to our custom exceptions
                if isinstance(e, (ConnectionError, TimeoutError)):
                    raise NetworkError(f"Network error: {e}") from e
                raise

        return wrapper

    return decorator
