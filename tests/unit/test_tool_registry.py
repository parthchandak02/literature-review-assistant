"""
Unit tests for tool registry.
"""

from src.tools.tool_registry import ToolRegistry, Tool, ToolParameter, ToolResultStatus


def test_tool_registry_register():
    """Test tool registration."""
    registry = ToolRegistry()

    tool = Tool(
        name="test_tool", description="Test tool", parameters=[], execute_fn=lambda: "result"
    )

    registry.register(tool)
    assert "test_tool" in registry.list_tools()


def test_tool_registry_get_tool():
    """Test tool retrieval."""
    registry = ToolRegistry()

    tool = Tool(
        name="test_tool", description="Test tool", parameters=[], execute_fn=lambda: "result"
    )

    registry.register(tool)
    retrieved = registry.get_tool("test_tool")

    assert retrieved is not None
    assert retrieved.name == "test_tool"


def test_tool_parameter_validation():
    """Test tool parameter validation."""
    tool = Tool(
        name="test_tool",
        description="Test tool",
        parameters=[
            ToolParameter(name="query", type="string", description="Test query", required=True),
            ToolParameter(name="limit", type="number", description="Limit", required=False),
        ],
        execute_fn=lambda query, limit=10: f"Result: {query}, Limit: {limit}",
    )

    # Valid arguments
    assert tool.validate_arguments({"query": "test"}) is True
    assert tool.validate_arguments({"query": "test", "limit": 5}) is True

    # Missing required parameter
    assert tool.validate_arguments({"limit": 5}) is False

    # Invalid type
    assert tool.validate_arguments({"query": 123}) is False


def test_tool_execution():
    """Test tool execution."""

    def test_fn(query: str, limit: int = 10) -> str:
        return f"Query: {query}, Limit: {limit}"

    tool = Tool(
        name="test_tool",
        description="Test tool",
        parameters=[
            ToolParameter(name="query", type="string", description="Query", required=True),
            ToolParameter(name="limit", type="number", description="Limit", required=False),
        ],
        execute_fn=test_fn,
    )

    # Successful execution
    result = tool.execute({"query": "test", "limit": 5})
    assert result.status == ToolResultStatus.SUCCESS
    assert "Query: test" in result.result
    assert result.execution_time is not None

    # Invalid arguments
    result = tool.execute({"limit": 5})  # Missing required 'query'
    assert result.status == ToolResultStatus.ERROR
    assert "Invalid arguments" in result.error


def test_tool_openai_format():
    """Test tool OpenAI format conversion."""
    tool = Tool(
        name="test_tool",
        description="Test tool",
        parameters=[
            ToolParameter(name="query", type="string", description="Query", required=True),
            ToolParameter(name="limit", type="number", description="Limit", required=False),
        ],
        execute_fn=lambda query, limit=10: "result",
    )

    openai_format = tool.to_openai_format()

    assert openai_format["type"] == "function"
    assert openai_format["function"]["name"] == "test_tool"
    assert "query" in openai_format["function"]["parameters"]["properties"]
    assert "query" in openai_format["function"]["parameters"]["required"]


def test_tool_registry_execute():
    """Test tool execution through registry."""
    registry = ToolRegistry()

    def test_fn(query: str) -> str:
        return f"Result: {query}"

    tool = Tool(
        name="test_tool",
        description="Test tool",
        parameters=[ToolParameter(name="query", type="string", description="Query", required=True)],
        execute_fn=test_fn,
    )

    registry.register(tool)

    result = registry.execute_tool("test_tool", {"query": "test"})
    assert result.status == ToolResultStatus.SUCCESS
    assert "Result: test" in result.result

    # Non-existent tool
    result = registry.execute_tool("nonexistent", {})
    assert result.status == ToolResultStatus.ERROR


def test_tool_registry_get_tools_for_llm():
    """Test getting tools in LLM format."""
    registry = ToolRegistry()

    tool1 = Tool(name="tool1", description="Tool 1", parameters=[], execute_fn=lambda: "result1")

    tool2 = Tool(name="tool2", description="Tool 2", parameters=[], execute_fn=lambda: "result2")

    registry.register(tool1)
    registry.register(tool2)

    tools = registry.get_tools_for_llm("openai")
    assert len(tools) == 2
    assert all(t["type"] == "function" for t in tools)
