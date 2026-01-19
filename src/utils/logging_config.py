"""
Logging configuration for debug and verbose modes.
"""

import logging
import sys
from pathlib import Path
from typing import Optional
from enum import Enum
import colorama
from colorama import Fore, Style

colorama.init(autoreset=True)


class LogLevel(str, Enum):
    """Log level enumeration."""

    MINIMAL = "minimal"  # Only errors and critical info
    NORMAL = "normal"  # INFO, WARNING, ERROR
    DETAILED = "detailed"  # DEBUG, INFO, WARNING, ERROR
    FULL = "full"  # All logs with full context


class ColoredFormatter(logging.Formatter):
    """Colored log formatter."""

    COLORS = {
        "DEBUG": Fore.CYAN,
        "INFO": Fore.GREEN,
        "WARNING": Fore.YELLOW,
        "ERROR": Fore.RED,
        "CRITICAL": Fore.RED + Style.BRIGHT,
    }

    def format(self, record):
        """Format log record with colors."""
        log_color = self.COLORS.get(record.levelname, "")
        record.levelname = f"{log_color}{record.levelname}{Style.RESET_ALL}"
        return super().format(record)


def setup_logging(
    level: LogLevel = LogLevel.NORMAL,
    log_to_file: bool = False,
    log_file: Optional[str] = None,
    verbose: bool = False,
    debug: bool = False,
) -> logging.Logger:
    """
    Setup logging configuration.

    Args:
        level: Log level
        log_to_file: Whether to log to file
        log_file: Log file path
        verbose: Verbose mode flag
        debug: Debug mode flag

    Returns:
        Configured logger
    """
    # Determine actual log level
    if debug:
        log_level = logging.DEBUG
    elif verbose or level == LogLevel.DETAILED or level == LogLevel.FULL:
        log_level = logging.DEBUG
    elif level == LogLevel.NORMAL:
        log_level = logging.INFO
    else:  # MINIMAL
        log_level = logging.WARNING

    # Create logger
    logger = logging.getLogger("research_article_writer")
    logger.setLevel(log_level)
    logger.handlers.clear()  # Clear existing handlers

    # Console handler with colored output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    if debug or verbose:
        # Detailed format for debug/verbose
        console_format = ColoredFormatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", datefmt="%H:%M:%S"
        )
    else:
        # Simple format for normal mode
        console_format = ColoredFormatter("%(levelname)-8s | %(message)s")

    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # File handler if requested
    if log_to_file:
        if log_file is None:
            log_file = "logs/workflow.log"

        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)  # Always log everything to file

        file_format = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get logger for a module.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(f"research_article_writer.{name}")
