"""
Circuit Breaker Pattern Implementation

Prevents cascading failures by stopping requests to failing services.
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5  # Failures before opening circuit
    success_threshold: int = 2  # Successes in half-open to close
    timeout: float = 60.0  # Seconds before attempting half-open
    expected_exception: type = Exception  # Exception type to count as failure


@dataclass
class CircuitBreakerStats:
    """Statistics for circuit breaker."""

    failures: int = 0
    successes: int = 0
    last_failure_time: Optional[float] = None
    state: CircuitState = CircuitState.CLOSED
    _lock: Lock = field(default_factory=Lock)


class CircuitBreaker:
    """
    Circuit breaker implementation to prevent cascading failures.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, reject requests immediately
    - HALF_OPEN: Testing if service recovered, allow limited requests
    """

    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        """
        Initialize circuit breaker.

        Args:
            config: Circuit breaker configuration
        """
        self.config = config or CircuitBreakerConfig()
        self.stats = CircuitBreakerStats()

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """
        Execute function with circuit breaker protection.

        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerOpenError: If circuit is open
            Exception: If function call fails
        """
        with self.stats._lock:
            # Check if circuit should transition from OPEN to HALF_OPEN
            if self.stats.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    logger.info("Circuit breaker transitioning to HALF_OPEN state")
                    self.stats.state = CircuitState.HALF_OPEN
                    self.stats.successes = 0
                else:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker is OPEN. Last failure: {self.stats.last_failure_time}"
                    )

        # Attempt the call
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.config.expected_exception:
            self._on_failure()
            raise

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self.stats.last_failure_time is None:
            return True

        elapsed = time.time() - self.stats.last_failure_time
        return elapsed >= self.config.timeout

    def _on_success(self):
        """Handle successful call."""
        with self.stats._lock:
            if self.stats.state == CircuitState.HALF_OPEN:
                self.stats.successes += 1
                if self.stats.successes >= self.config.success_threshold:
                    logger.info("Circuit breaker transitioning to CLOSED state")
                    self.stats.state = CircuitState.CLOSED
                    self.stats.failures = 0
                    self.stats.successes = 0
            elif self.stats.state == CircuitState.CLOSED:
                # Reset failure count on success
                self.stats.failures = 0

    def _on_failure(self):
        """Handle failed call."""
        with self.stats._lock:
            self.stats.failures += 1
            self.stats.last_failure_time = time.time()

            if self.stats.state == CircuitState.HALF_OPEN:
                # Failure in half-open, go back to open
                logger.warning("Circuit breaker transitioning back to OPEN state")
                self.stats.state = CircuitState.OPEN
                self.stats.successes = 0
            elif self.stats.state == CircuitState.CLOSED:
                if self.stats.failures >= self.config.failure_threshold:
                    logger.error(f"Circuit breaker opening after {self.stats.failures} failures")
                    self.stats.state = CircuitState.OPEN

    def reset(self):
        """Manually reset circuit breaker to CLOSED state."""
        with self.stats._lock:
            logger.info("Circuit breaker manually reset")
            self.stats.state = CircuitState.CLOSED
            self.stats.failures = 0
            self.stats.successes = 0
            self.stats.last_failure_time = None

    def get_state(self) -> CircuitState:
        """Get current circuit breaker state."""
        return self.stats.state

    def is_open(self) -> bool:
        """Check if circuit breaker is open."""
        return self.stats.state == CircuitState.OPEN


class CircuitBreakerOpenError(Exception):
    """Exception raised when circuit breaker is open."""

    pass


def circuit_breaker_decorator(
    config: Optional[CircuitBreakerConfig] = None,
) -> Callable:
    """
    Decorator to add circuit breaker to a function.

    Args:
        config: Circuit breaker configuration

    Returns:
        Decorator function
    """
    breaker = CircuitBreaker(config)

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args: Any, **kwargs: Any) -> T:
            return breaker.call(func, *args, **kwargs)

        wrapper.circuit_breaker = breaker
        return wrapper

    return decorator
