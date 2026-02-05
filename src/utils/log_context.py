"""
Log context management for adding context to logs.
"""

import logging
from contextlib import contextmanager
import time
from rich.rule import Rule
from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()


class LogContext:
    """Context manager for adding context to logs."""

    def __init__(self, **context):
        """
        Initialize log context.

        Args:
            **context: Context key-value pairs
        """
        self.context = context
        self.start_time = None

    def __enter__(self):
        """Enter context."""
        self.start_time = time.time()
        # Add context to logger
        old_factory = logging.getLogRecordFactory()

        def record_factory(*args, **kwargs):
            record = old_factory(*args, **kwargs)
            for key, value in self.context.items():
                setattr(record, key, value)
            return record

        logging.setLogRecordFactory(record_factory)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context."""
        # Restore original factory
        logging.setLogRecordFactory(logging.getLogRecordFactory())

        if self.start_time:
            duration = time.time() - self.start_time
            if duration > 0.1:  # Log if operation took significant time
                logger.debug(f"Operation completed in {duration:.2f}s")

        return False

    def add_event(self, event_name: str, **attributes):
        """
        Add an event to the log context.

        Args:
            event_name: Event name
            **attributes: Event attributes
        """
        logger.debug(f"Event: {event_name}", extra=attributes)


@contextmanager
def agent_log_context(agent_name: str, operation: str, **extra_context):
    """
    Context manager for agent operations.

    Args:
        agent_name: Agent name
        operation: Operation name
        **extra_context: Additional context
    """
    context = {"agent": agent_name, "operation": operation, **extra_context}

    with LogContext(**context):
        logger.info(f"[{agent_name}] Starting {operation}")
        try:
            yield
            logger.info(f"[{agent_name}] Completed {operation}")
        except Exception as e:
            logger.error(f"[{agent_name}] Failed {operation}: {e}", exc_info=True)
            raise


@contextmanager
def workflow_phase_context(phase: str, **extra_context):
    """
    Context manager for workflow phases.

    Args:
        phase: Phase name
        **extra_context: Additional context
    """
    context = {"phase": phase, **extra_context}

    with LogContext(**context):
        console.print(Rule(f"[dim]Phase: {phase}[/dim]", style="dim"))
        logger.info(f"=== Phase: {phase} ===")
        try:
            yield
            console.print(Rule(f"[dim]Phase {phase} completed[/dim]", style="dim"))
            logger.info(f"=== Phase {phase} completed ===")
        except Exception as e:
            logger.error(f"=== Phase {phase} failed: {e} ===", exc_info=True)
            raise
