"""
Unit tests for rate limiter.
"""

import time

from src.search.rate_limiter import RateLimiter, get_rate_limiter


class TestRateLimiter:
    """Test RateLimiter class."""

    def test_rate_limiting(self):
        """Test that rate limiter enforces limits."""
        limiter = RateLimiter(max_requests=2, time_window=1.0)

        start_time = time.time()
        limiter.acquire()
        limiter.acquire()
        limiter.acquire()  # Should wait
        end_time = time.time()

        # Should have waited at least a bit
        assert end_time - start_time >= 0.5

    def test_database_specific_limiter(self):
        """Test getting database-specific rate limiters."""
        pubmed_limiter = get_rate_limiter("PubMed")
        assert pubmed_limiter.max_requests == 3.0

        arxiv_limiter = get_rate_limiter("arXiv")
        assert arxiv_limiter.max_requests == 3.0

        semantic_limiter = get_rate_limiter("Semantic Scholar")
        assert semantic_limiter.max_requests == 1.0

    def test_default_limiter(self):
        """Test default limiter for unknown database."""
        limiter = get_rate_limiter("UnknownDB")
        assert limiter.max_requests == 5.0
