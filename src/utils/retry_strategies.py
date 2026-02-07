"""
Retry Strategies for LLM Calls and Agent Operations

Implements exponential backoff with jitter for robust error handling.
"""

import logging
import random
import time
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

from tenacity import (
    after_log,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryConfig:
    """Configuration for retry strategies."""

    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retryable_exceptions: tuple = (Exception,),
    ):
        """
        Initialize retry configuration.

        Args:
            max_attempts: Maximum number of retry attempts
            initial_delay: Initial delay in seconds
            max_delay: Maximum delay in seconds
            exponential_base: Base for exponential backoff
            jitter: Whether to add random jitter to delays
            retryable_exceptions: Tuple of exceptions that should trigger retry
        """
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions


def exponential_backoff_with_jitter(
    base_delay: float, attempt: int, max_delay: float = 60.0, jitter: bool = True
) -> float:
    """
    Calculate delay with exponential backoff and optional jitter.

    Args:
        base_delay: Base delay in seconds
        attempt: Current attempt number (0-indexed)
        max_delay: Maximum delay in seconds
        jitter: Whether to add jitter

    Returns:
        Delay in seconds
    """
    delay = min(base_delay * (2**attempt), max_delay)

    if jitter:
        # Add random jitter: ±20% of delay
        jitter_amount = delay * 0.2 * random.uniform(-1, 1)
        delay = max(0.1, delay + jitter_amount)

    return delay


def retry_with_exponential_backoff(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    retryable_exceptions: tuple = (Exception,),
):
    """
    Decorator for retrying functions with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        jitter: Whether to add jitter
        retryable_exceptions: Exceptions that should trigger retry

    Returns:
        Decorated function
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e

                    if attempt == max_attempts - 1:
                        # Last attempt, re-raise
                        raise

                    delay = exponential_backoff_with_jitter(
                        initial_delay, attempt, max_delay, jitter
                    )

                    logger.warning(
                        f"Attempt {attempt + 1}/{max_attempts} failed for {func.__name__}: {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )
                    time.sleep(delay)
                except Exception:
                    # Non-retryable exception, re-raise immediately
                    raise

            # Should never reach here, but just in case
            if last_exception:
                raise last_exception
            raise RuntimeError(f"Function {func.__name__} failed after {max_attempts} attempts")

        return wrapper

    return decorator


def create_llm_retry_decorator(config: Optional[RetryConfig] = None):
    """
    Create a retry decorator specifically for LLM calls using tenacity.

    Args:
        config: Retry configuration (uses defaults if None)

    Returns:
        Retry decorator
    """
    if config is None:
        config = RetryConfig()

    return retry(
        stop=stop_after_attempt(config.max_attempts),
        wait=wait_exponential(
            multiplier=config.initial_delay,
            min=config.initial_delay,
            max=config.max_delay,
        ),
        retry=retry_if_exception_type(config.retryable_exceptions),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        after=after_log(logger, logging.INFO),
        reraise=True,
    )


# Common retry configurations
LLM_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    initial_delay=1.0,
    max_delay=60.0,
    jitter=True,
    retryable_exceptions=(Exception,),
)

API_RETRY_CONFIG = RetryConfig(
    max_attempts=5,
    initial_delay=0.5,
    max_delay=30.0,
    jitter=True,
    retryable_exceptions=(ConnectionError, TimeoutError, Exception),
)
