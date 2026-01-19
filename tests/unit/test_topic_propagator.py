"""
Unit tests for topic propagator.
"""

from src.orchestration.topic_propagator import TopicContext


def test_topic_context_from_config_string():
    """Test TopicContext creation from string config."""
    config = {"topic": "Test Topic"}

    context = TopicContext.from_config(config)
    assert context.topic == "Test Topic"
    assert context.keywords == []
    assert context.domain is None


def test_topic_context_from_config_dict():
    """Test TopicContext creation from dict config."""
    config = {
        "topic": {
            "topic": "Test Topic",
            "keywords": ["keyword1", "keyword2"],
            "domain": "healthcare",
            "research_question": "Test question",
            "context": "Test context",
        }
    }

    context = TopicContext.from_config(config)
    assert context.topic == "Test Topic"
    assert len(context.keywords) == 2
    assert context.domain == "healthcare"
    assert context.research_question == "Test question"


def test_topic_context_enrich():
    """Test context enrichment."""
    context = TopicContext(topic="Test Topic")

    context.enrich(["Insight 1", "Insight 2"])
    assert len(context.insights) == 2
    assert "Insight 1" in context.insights


def test_topic_context_accumulate_findings():
    """Test findings accumulation."""
    context = TopicContext(topic="Test Topic")

    findings = [
        {"title": "Paper 1", "key_findings": ["Finding 1", "Finding 2"]},
        {"title": "Paper 2", "key_findings": ["Finding 3"]},
    ]

    context.accumulate_findings(findings)
    assert len(context.findings) == 2
    assert context.extracted_data_summary is not None


def test_topic_context_get_for_agent():
    """Test agent-specific context formatting."""
    context = TopicContext(
        topic="Test Topic",
        domain="healthcare",
        research_question="Test question",
        keywords=["keyword1"],
    )

    agent_context = context.get_for_agent("screening_agent")
    assert agent_context["topic"] == "Test Topic"
    assert agent_context["domain"] == "healthcare"
    assert agent_context["research_question"] == "Test question"

    # Writer agents should get insights
    writer_context = context.get_for_agent("introduction_writer")
    assert "insights" in writer_context or "findings_summary" in writer_context


def test_topic_context_inject_into_prompt():
    """Test prompt template injection."""
    context = TopicContext(
        topic="Telemedicine",
        domain="healthcare",
        research_question="How can UX be improved?",
        keywords=["telemedicine", "UX"],
    )

    template = "Research topic: {topic}, Domain: {domain}, Question: {research_question}"
    result = context.inject_into_prompt(template)

    assert "Telemedicine" in result
    assert "healthcare" in result
    assert "How can UX be improved?" in result


def test_topic_context_to_dict():
    """Test context serialization."""
    context = TopicContext(
        topic="Test Topic", keywords=["keyword1"], domain="test", research_question="Test question"
    )

    context.enrich(["Insight 1"])

    data = context.to_dict()
    assert data["topic"] == "Test Topic"
    assert len(data["keywords"]) == 1
    assert data["domain"] == "test"
    assert len(data["insights"]) == 1
