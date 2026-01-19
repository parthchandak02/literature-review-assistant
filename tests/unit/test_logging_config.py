"""
Unit tests for logging config.
"""

import logging
from src.utils.logging_config import setup_logging, LogLevel, get_logger, ColoredFormatter


class TestLogLevel:
    """Test LogLevel enum."""

    def test_log_level_values(self):
        """Test LogLevel enum values."""
        assert LogLevel.MINIMAL == "minimal"
        assert LogLevel.NORMAL == "normal"
        assert LogLevel.DETAILED == "detailed"
        assert LogLevel.FULL == "full"


class TestSetupLogging:
    """Test setup_logging function."""

    def test_setup_logging_normal(self):
        """Test setting up logging in normal mode."""
        logger = setup_logging(level=LogLevel.NORMAL)

        assert logger is not None
        assert logger.level <= logging.INFO

    def test_setup_logging_debug(self):
        """Test setting up logging in debug mode."""
        logger = setup_logging(level=LogLevel.DETAILED, debug=True)

        assert logger is not None
        assert logger.level <= logging.DEBUG

    def test_setup_logging_to_file(self, tmp_path):
        """Test setting up logging to file."""
        log_file = tmp_path / "test.log"

        logger = setup_logging(level=LogLevel.NORMAL, log_to_file=True, log_file=str(log_file))

        assert logger is not None
        # Check if file handler was added
        assert any(isinstance(h, logging.FileHandler) for h in logger.handlers)

    def test_setup_logging_minimal(self):
        """Test setting up logging in minimal mode."""
        logger = setup_logging(level=LogLevel.MINIMAL)

        assert logger is not None
        assert logger.level >= logging.WARNING


class TestGetLogger:
    """Test get_logger function."""

    def test_get_logger(self):
        """Test getting logger."""
        logger = get_logger("test_module")

        assert logger is not None
        assert isinstance(logger, logging.Logger)
        # get_logger prefixes with 'research_article_writer.'
        assert "test_module" in logger.name


class TestColoredFormatter:
    """Test ColoredFormatter class."""

    def test_colored_formatter_format(self):
        """Test colored formatter formatting."""
        formatter = ColoredFormatter("%(levelname)s | %(message)s")

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        formatted = formatter.format(record)
        assert "Test message" in formatted
        assert "INFO" in formatted
