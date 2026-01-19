"""
Distributed Tracing for Agent Calls

Provides tracing context for tracking agent execution across workflow phases.
"""

import uuid
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, field
from datetime import datetime
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)


@dataclass
class Span:
    """Represents a single span in a trace."""

    span_id: str
    trace_id: str
    parent_span_id: Optional[str]
    name: str
    start_time: datetime
    end_time: Optional[datetime] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "pending"  # "pending", "success", "error"
    error: Optional[str] = None


class TracingContext:
    """Context manager for distributed tracing."""

    def __init__(self, trace_id: Optional[str] = None):
        """
        Initialize tracing context.

        Args:
            trace_id: Optional trace ID (generated if None)
        """
        self.trace_id = trace_id or str(uuid.uuid4())
        self.spans: Dict[str, Span] = {}
        self.current_span_id: Optional[str] = None

    @contextmanager
    def span(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        """
        Create a new span context.

        Args:
            name: Span name
            attributes: Optional span attributes

        Yields:
            Span ID
        """
        span_id = str(uuid.uuid4())
        parent_span_id = self.current_span_id

        span = Span(
            span_id=span_id,
            trace_id=self.trace_id,
            parent_span_id=parent_span_id,
            name=name,
            start_time=datetime.now(),
            attributes=attributes or {},
        )

        self.spans[span_id] = span
        previous_span = self.current_span_id
        self.current_span_id = span_id

        try:
            yield span_id
            span.status = "success"
        except Exception as e:
            span.status = "error"
            span.error = str(e)
            raise
        finally:
            span.end_time = datetime.now()
            self.current_span_id = previous_span

    def add_event(self, span_id: str, name: str, attributes: Optional[Dict[str, Any]] = None):
        """
        Add an event to a span.

        Args:
            span_id: Span ID
            name: Event name
            attributes: Optional event attributes
        """
        if span_id in self.spans:
            self.spans[span_id].events.append(
                {
                    "name": name,
                    "timestamp": datetime.now().isoformat(),
                    "attributes": attributes or {},
                }
            )

    def get_trace(self) -> Dict[str, Any]:
        """
        Get complete trace data.

        Returns:
            Trace dictionary
        """
        return {
            "trace_id": self.trace_id,
            "spans": [
                {
                    "span_id": span.span_id,
                    "trace_id": span.trace_id,
                    "parent_span_id": span.parent_span_id,
                    "name": span.name,
                    "start_time": span.start_time.isoformat(),
                    "end_time": span.end_time.isoformat() if span.end_time else None,
                    "duration": (
                        (span.end_time - span.start_time).total_seconds() if span.end_time else None
                    ),
                    "attributes": span.attributes,
                    "events": span.events,
                    "status": span.status,
                    "error": span.error,
                }
                for span in self.spans.values()
            ],
        }


# Global tracing context (thread-local in production)
_global_tracing: Optional[TracingContext] = None


def get_tracing_context() -> Optional[TracingContext]:
    """Get the current tracing context."""
    return _global_tracing


def set_tracing_context(context: TracingContext):
    """Set the current tracing context."""
    global _global_tracing
    _global_tracing = context


@contextmanager
def trace_agent_call(agent_name: str, operation: str, attributes: Optional[Dict[str, Any]] = None):
    """
    Context manager for tracing agent calls.

    Args:
        agent_name: Agent name
        operation: Operation name
        attributes: Optional attributes

    Yields:
        Span ID
    """
    context = get_tracing_context()
    if not context:
        # No tracing context, create a temporary one
        context = TracingContext()
        set_tracing_context(context)

    span_name = f"{agent_name}.{operation}"
    with context.span(span_name, attributes) as span_id:
        yield span_id
