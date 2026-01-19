"""
Integration tests for tool execution.
"""

from src.tools.tool_registry import ToolRegistry
from src.tools.database_search_tool import DatabaseSearchTool
from src.tools.query_builder_tool import QueryBuilderTool
from src.search.database_connectors import MultiDatabaseSearcher


def test_database_search_tool_execution():
    """Test database search tool execution."""
    searcher = MultiDatabaseSearcher()
    tool_wrapper = DatabaseSearchTool(searcher)
    tool = tool_wrapper.get_tool()

    result = tool.execute({"query": "telemedicine", "databases": ["PubMed"], "max_results": 5})

    assert result.status.value == "success"
    assert "total_results" in result.result
    assert "papers" in result.result


def test_query_builder_tool_execution():
    """Test query builder tool execution."""
    tool_wrapper = QueryBuilderTool()
    tool = tool_wrapper.get_tool()

    result = tool.execute(
        {
            "term_groups": [
                {"main_term": "telemedicine", "synonyms": ["telehealth", "remote healthcare"]}
            ],
            "database": "pubmed",
        }
    )

    assert result.status.value == "success"
    assert "query" in result.result
    assert "telemedicine" in result.result["query"]


def test_tool_registry_integration():
    """Test tool registry with real tools."""
    registry = ToolRegistry()

    searcher = MultiDatabaseSearcher()
    search_tool = DatabaseSearchTool(searcher)
    registry.register(search_tool.get_tool())

    query_tool = QueryBuilderTool()
    registry.register(query_tool.get_tool())

    assert len(registry.list_tools()) == 2

    # Execute search tool
    result = registry.execute_tool(
        "database_search", {"query": "test", "databases": ["PubMed"], "max_results": 3}
    )

    assert result.status.value == "success"


def test_tool_validation_in_execution():
    """Test tool argument validation during execution."""
    registry = ToolRegistry()

    search_tool = DatabaseSearchTool(MultiDatabaseSearcher())
    registry.register(search_tool.get_tool())

    # Missing required parameter
    result = registry.execute_tool(
        "database_search",
        {
            "databases": ["PubMed"]
            # Missing "query"
        },
    )

    assert result.status.value == "error"
    assert "Invalid arguments" in result.error or "Missing required" in result.error
