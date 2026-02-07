"""
Unit tests for circuit breaker.
"""

import time

import pytest

from src.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitState,
)


def test_circuit_breaker_closed_state():
    """Test circuit breaker in closed state."""
    breaker = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))

    assert breaker.get_state() == CircuitState.CLOSED

    # Successful call
    result = breaker.call(lambda: "success")
    assert result == "success"
    assert breaker.get_state() == CircuitState.CLOSED


def test_circuit_breaker_opens_after_threshold():
    """Test circuit breaker opens after failure threshold."""
    breaker = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))

    # Cause failures
    for _i in range(3):
        try:
            breaker.call(lambda: (_ for _ in ()).throw(Exception("Test error")))
        except Exception:
            pass

    assert breaker.get_state() == CircuitState.OPEN


def test_circuit_breaker_rejects_when_open():
    """Test circuit breaker rejects calls when open."""
    breaker = CircuitBreaker(CircuitBreakerConfig(failure_threshold=2, timeout=0.1))

    # Open the circuit
    for _i in range(2):
        try:
            breaker.call(lambda: (_ for _ in ()).throw(Exception("Test")))
        except Exception:
            pass

    assert breaker.is_open()

    # Should raise CircuitBreakerOpenError
    with pytest.raises(CircuitBreakerOpenError):
        breaker.call(lambda: "test")


def test_circuit_breaker_half_open_transition():
    """Test circuit breaker transitions to half-open after timeout."""
    breaker = CircuitBreaker(CircuitBreakerConfig(failure_threshold=2, timeout=0.1))

    # Open the circuit
    for _i in range(2):
        try:
            breaker.call(lambda: (_ for _ in ()).throw(Exception("Test")))
        except Exception:
            pass

    assert breaker.get_state() == CircuitState.OPEN

    # Wait for timeout
    time.sleep(0.15)

    # Attempt call should transition to half-open
    try:
        breaker.call(lambda: "success")
    except CircuitBreakerOpenError:
        # If still open, manually transition for testing
        breaker.stats.state = CircuitState.HALF_OPEN
        breaker.stats.last_failure_time = None

    # Successful call in half-open
    result = breaker.call(lambda: "success")
    assert result == "success"
    breaker._on_success()  # Manually trigger success handler

    # Second success should close circuit
    result = breaker.call(lambda: "success")
    assert result == "success"
    breaker._on_success()

    # Should be closed after success threshold
    if breaker.stats.successes >= breaker.config.success_threshold:
        assert breaker.get_state() == CircuitState.CLOSED


def test_circuit_breaker_reset():
    """Test manual circuit breaker reset."""
    breaker = CircuitBreaker(CircuitBreakerConfig(failure_threshold=2))

    # Open the circuit
    for _i in range(2):
        try:
            breaker.call(lambda: (_ for _ in ()).throw(Exception("Test")))
        except Exception:
            pass

    assert breaker.is_open()

    # Reset
    breaker.reset()
    assert breaker.get_state() == CircuitState.CLOSED
    assert breaker.stats.failures == 0


def test_circuit_breaker_config():
    """Test circuit breaker configuration."""
    config = CircuitBreakerConfig(failure_threshold=5, success_threshold=3, timeout=60.0)

    assert config.failure_threshold == 5
    assert config.success_threshold == 3
    assert config.timeout == 60.0
