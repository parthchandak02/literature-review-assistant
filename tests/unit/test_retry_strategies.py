"""
Unit tests for retry strategies.
"""

import pytest

from src.utils.retry_strategies import (
    LLM_RETRY_CONFIG,
    RetryConfig,
    create_llm_retry_decorator,
    exponential_backoff_with_jitter,
    retry_with_exponential_backoff,
)


def test_exponential_backoff_calculation():
    """Test exponential backoff calculation."""
    delay1 = exponential_backoff_with_jitter(1.0, 0, max_delay=60.0, jitter=False)
    assert delay1 == 1.0

    delay2 = exponential_backoff_with_jitter(1.0, 1, max_delay=60.0, jitter=False)
    assert delay2 == 2.0

    delay3 = exponential_backoff_with_jitter(1.0, 2, max_delay=60.0, jitter=False)
    assert delay3 == 4.0

    # Test max delay cap
    delay_large = exponential_backoff_with_jitter(1.0, 10, max_delay=60.0, jitter=False)
    assert delay_large == 60.0


def test_exponential_backoff_with_jitter():
    """Test exponential backoff with jitter."""
    delay = exponential_backoff_with_jitter(1.0, 0, max_delay=60.0, jitter=True)
    # With jitter, should be within ±20% of base delay
    assert 0.8 <= delay <= 1.2


def test_retry_config():
    """Test RetryConfig creation."""
    config = RetryConfig(max_attempts=5, initial_delay=0.5, max_delay=30.0, jitter=True)

    assert config.max_attempts == 5
    assert config.initial_delay == 0.5
    assert config.max_delay == 30.0
    assert config.jitter is True


def test_retry_decorator_success():
    """Test retry decorator with successful call."""
    call_count = [0]

    @retry_with_exponential_backoff(max_attempts=3, initial_delay=0.01, jitter=False)
    def successful_function():
        call_count[0] += 1
        return "success"

    result = successful_function()
    assert result == "success"
    assert call_count[0] == 1


def test_retry_decorator_retries():
    """Test retry decorator with retries."""
    call_count = [0]

    @retry_with_exponential_backoff(
        max_attempts=3, initial_delay=0.01, jitter=False, retryable_exceptions=(ValueError,)
    )
    def failing_function():
        call_count[0] += 1
        if call_count[0] < 2:
            raise ValueError("Test error")
        return "success"

    result = failing_function()
    assert result == "success"
    assert call_count[0] == 2


def test_retry_decorator_max_attempts():
    """Test retry decorator respects max attempts."""
    call_count = [0]

    @retry_with_exponential_backoff(
        max_attempts=3, initial_delay=0.01, jitter=False, retryable_exceptions=(ValueError,)
    )
    def always_failing_function():
        call_count[0] += 1
        raise ValueError("Always fails")

    with pytest.raises(ValueError):
        always_failing_function()

    assert call_count[0] == 3


def test_retry_decorator_non_retryable_exception():
    """Test retry decorator doesn't retry non-retryable exceptions."""
    call_count = [0]

    @retry_with_exponential_backoff(
        max_attempts=3, initial_delay=0.01, jitter=False, retryable_exceptions=(ValueError,)
    )
    def raises_different_exception():
        call_count[0] += 1
        raise TypeError("Different error")

    with pytest.raises(TypeError):
        raises_different_exception()

    assert call_count[0] == 1  # Should not retry


def test_create_llm_retry_decorator():
    """Test LLM retry decorator creation."""
    config = RetryConfig(max_attempts=2, initial_delay=0.01)
    decorator = create_llm_retry_decorator(config)

    assert decorator is not None
    assert callable(decorator)


def test_llm_retry_config_defaults():
    """Test LLM retry config defaults."""
    assert LLM_RETRY_CONFIG.max_attempts == 3
    assert LLM_RETRY_CONFIG.initial_delay == 1.0
    assert LLM_RETRY_CONFIG.max_delay == 60.0
