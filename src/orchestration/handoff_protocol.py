"""
Structured Handoff Protocol

JSON Schema-based protocol for reliable agent-to-agent communication
with topic context included in every handoff.
"""

from typing import Dict, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import json
from ..orchestration.topic_propagator import TopicContext


@dataclass
class ErrorContext:
    """Error context for propagation through handoffs."""

    error_type: str
    error_message: str
    error_timestamp: str
    retry_count: int = 0
    recovery_action: Optional[str] = None
    additional_context: Optional[Dict[str, Any]] = None


@dataclass
class HandoffData:
    """Structured handoff data between agents."""

    from_agent: str
    to_agent: str
    stage: str  # e.g., "search", "screening", "extraction", "writing"
    topic_context: Dict[str, Any]
    data: Dict[str, Any]
    metadata: Dict[str, Any]
    timestamp: str
    error_context: Optional[ErrorContext] = None  # Error context if handoff due to error

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HandoffData":
        """Create from dictionary."""
        return cls(**data)


class HandoffProtocol:
    """Manages structured handoffs between agents."""

    @staticmethod
    def create_handoff(
        from_agent: str,
        to_agent: str,
        stage: str,
        topic_context: TopicContext,
        data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
        error_context: Optional[ErrorContext] = None,
    ) -> HandoffData:
        """
        Create a structured handoff between agents.

        Args:
            from_agent: Source agent name
            to_agent: Target agent name
            stage: Workflow stage
            topic_context: TopicContext instance
            data: Data payload
            metadata: Optional metadata
            error_context: Optional error context if handoff is due to error

        Returns:
            HandoffData instance
        """
        return HandoffData(
            from_agent=from_agent,
            to_agent=to_agent,
            stage=stage,
            topic_context=topic_context.get_for_agent(to_agent),
            data=data,
            metadata=metadata or {},
            timestamp=datetime.now().isoformat(),
            error_context=error_context,
        )

    @staticmethod
    def create_error_handoff(
        from_agent: str,
        to_agent: str,
        stage: str,
        topic_context: TopicContext,
        error: Exception,
        retry_count: int = 0,
        recovery_action: Optional[str] = None,
        additional_context: Optional[Dict[str, Any]] = None,
    ) -> HandoffData:
        """
        Create a handoff with error context for error recovery scenarios.

        Args:
            from_agent: Source agent name
            to_agent: Target agent name (e.g., error handler agent)
            stage: Workflow stage
            topic_context: TopicContext instance
            error: Exception that occurred
            retry_count: Number of retries attempted
            recovery_action: Suggested recovery action
            additional_context: Additional error context

        Returns:
            HandoffData instance with error context
        """
        error_context = ErrorContext(
            error_type=type(error).__name__,
            error_message=str(error),
            error_timestamp=datetime.now().isoformat(),
            retry_count=retry_count,
            recovery_action=recovery_action,
            additional_context=additional_context,
        )

        return HandoffData(
            from_agent=from_agent,
            to_agent=to_agent,
            stage=stage,
            topic_context=topic_context.get_for_agent(to_agent),
            data={"error": str(error)},
            metadata={"error_handoff": True},
            timestamp=datetime.now().isoformat(),
            error_context=error_context,
        )

    @staticmethod
    def validate_handoff(handoff: HandoffData) -> bool:
        """
        Validate handoff structure.

        Args:
            handoff: HandoffData instance

        Returns:
            True if valid

        Raises:
            ValueError: If invalid
        """
        if not handoff.from_agent:
            raise ValueError("Handoff must have from_agent")

        if not handoff.to_agent:
            raise ValueError("Handoff must have to_agent")

        if not handoff.stage:
            raise ValueError("Handoff must have stage")

        if not handoff.topic_context:
            raise ValueError("Handoff must include topic_context")

        if "topic" not in handoff.topic_context:
            raise ValueError("Topic context must include 'topic' field")

        return True

    @staticmethod
    def extract_topic_from_handoff(handoff: HandoffData) -> Dict[str, Any]:
        """
        Extract topic context from handoff.

        Args:
            handoff: HandoffData instance

        Returns:
            Topic context dictionary
        """
        return handoff.topic_context

    @staticmethod
    def extract_data_from_handoff(handoff: HandoffData) -> Dict[str, Any]:
        """
        Extract data payload from handoff.

        Args:
            handoff: HandoffData instance

        Returns:
            Data dictionary
        """
        return handoff.data


# JSON Schema for validation (optional, for strict validation)
HANDOFF_SCHEMA = {
    "type": "object",
    "required": [
        "from_agent",
        "to_agent",
        "stage",
        "topic_context",
        "data",
        "metadata",
        "timestamp",
    ],
    "properties": {
        "from_agent": {"type": "string"},
        "to_agent": {"type": "string"},
        "stage": {"type": "string"},
        "topic_context": {
            "type": "object",
            "required": ["topic"],
            "properties": {
                "topic": {"type": "string"},
                "domain": {"type": "string"},
                "research_question": {"type": "string"},
                "keywords": {"type": "array", "items": {"type": "string"}},
            },
        },
        "data": {"type": "object"},
        "metadata": {"type": "object"},
        "timestamp": {"type": "string"},
    },
}
