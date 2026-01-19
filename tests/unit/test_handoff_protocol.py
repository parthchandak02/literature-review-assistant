"""
Unit tests for handoff protocol.
"""

import pytest
from src.orchestration.handoff_protocol import HandoffProtocol, HandoffData
from src.orchestration.topic_propagator import TopicContext


def test_create_handoff():
    """Test handoff creation."""
    topic_context = TopicContext(topic="Test Topic")

    handoff = HandoffProtocol.create_handoff(
        from_agent="agent1",
        to_agent="agent2",
        stage="screening",
        topic_context=topic_context,
        data={"papers_count": 10},
        metadata={"phase": "title_abstract"},
    )

    assert handoff.from_agent == "agent1"
    assert handoff.to_agent == "agent2"
    assert handoff.stage == "screening"
    assert handoff.data["papers_count"] == 10
    assert handoff.topic_context is not None


def test_validate_handoff():
    """Test handoff validation."""
    topic_context = TopicContext(topic="Test Topic")

    handoff = HandoffProtocol.create_handoff(
        from_agent="agent1",
        to_agent="agent2",
        stage="screening",
        topic_context=topic_context,
        data={},
    )

    assert HandoffProtocol.validate_handoff(handoff) is True


def test_validate_handoff_missing_fields():
    """Test handoff validation with missing fields."""
    topic_context = TopicContext(topic="Test Topic")

    # Missing from_agent
    handoff = HandoffData(
        from_agent="",
        to_agent="agent2",
        stage="screening",
        topic_context=topic_context.get_for_agent("agent2"),
        data={},
        metadata={},
        timestamp="2024-01-01T00:00:00",
    )

    with pytest.raises(ValueError, match="from_agent"):
        HandoffProtocol.validate_handoff(handoff)


def test_create_error_handoff():
    """Test error handoff creation."""
    topic_context = TopicContext(topic="Test Topic")
    error = ValueError("Test error")

    handoff = HandoffProtocol.create_error_handoff(
        from_agent="agent1",
        to_agent="error_handler",
        stage="screening",
        topic_context=topic_context,
        error=error,
        retry_count=2,
        recovery_action="retry_with_fallback",
    )

    assert handoff.error_context is not None
    assert handoff.error_context.error_type == "ValueError"
    assert handoff.error_context.error_message == "Test error"
    assert handoff.error_context.retry_count == 2
    assert handoff.error_context.recovery_action == "retry_with_fallback"


def test_handoff_serialization():
    """Test handoff serialization."""
    topic_context = TopicContext(topic="Test Topic")

    handoff = HandoffProtocol.create_handoff(
        from_agent="agent1",
        to_agent="agent2",
        stage="screening",
        topic_context=topic_context,
        data={"test": "data"},
    )

    # Test to_dict
    handoff_dict = handoff.to_dict()
    assert handoff_dict["from_agent"] == "agent1"
    assert handoff_dict["to_agent"] == "agent2"

    # Test to_json
    json_str = handoff.to_json()
    assert "agent1" in json_str
    assert "agent2" in json_str

    # Test from_dict
    restored = HandoffData.from_dict(handoff_dict)
    assert restored.from_agent == "agent1"
    assert restored.to_agent == "agent2"


def test_extract_topic_from_handoff():
    """Test topic extraction from handoff."""
    topic_context = TopicContext(topic="Test Topic", domain="test")

    handoff = HandoffProtocol.create_handoff(
        from_agent="agent1",
        to_agent="agent2",
        stage="screening",
        topic_context=topic_context,
        data={},
    )

    extracted = HandoffProtocol.extract_topic_from_handoff(handoff)
    assert extracted["topic"] == "Test Topic"
    assert extracted["domain"] == "test"


def test_extract_data_from_handoff():
    """Test data extraction from handoff."""
    topic_context = TopicContext(topic="Test Topic")

    handoff = HandoffProtocol.create_handoff(
        from_agent="agent1",
        to_agent="agent2",
        stage="screening",
        topic_context=topic_context,
        data={"papers": [1, 2, 3], "count": 3},
    )

    extracted = HandoffProtocol.extract_data_from_handoff(handoff)
    assert extracted["count"] == 3
    assert len(extracted["papers"]) == 3
