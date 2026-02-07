"""
Integration tests for LLM provider integrations with agents.
"""

import os
from unittest.mock import Mock, patch

from src.screening.base_agent import BaseScreeningAgent
from src.tools.exa_tool import create_exa_search_tool
from src.tools.tavily_tool import create_tavily_search_tool
from src.tools.tool_registry import ToolRegistry


class TestAgentWithGoogleGenAI:
    """Test agents with Google GenAI provider."""

    @patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"})
    @patch("src.screening.base_agent.genai")
    def test_agent_with_google_genai(self, mock_genai):
        """Test agent initialization with Google GenAI."""
        mock_client = Mock()
        mock_genai.Client.return_value = mock_client

        class TestAgent(BaseScreeningAgent):
            def screen(self, title, abstract, inclusion_criteria, exclusion_criteria):
                return None

        agent = TestAgent(
            llm_provider="google",
            api_key="test-key",
            agent_config={"llm_model": "gemini-2.5-flash", "role": "Test Agent", "tools": []},
        )

        assert agent.llm_provider == "google"
        assert agent.llm_client == mock_client
        assert hasattr(agent, "llm_model_name")

    @patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"})
    @patch("src.screening.base_agent.genai")
    def test_google_genai_tool_calling(self, mock_genai):
        """Test tool calling with Google GenAI."""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.text = "Final response"
        mock_response.function_calls = None
        mock_client.models.generate_content.return_value = mock_response
        mock_genai.Client.return_value = mock_client

        class TestAgent(BaseScreeningAgent):
            def screen(self, title, abstract, inclusion_criteria, exclusion_criteria):
                return None

        agent = TestAgent(
            llm_provider="google",
            api_key="test-key",
            agent_config={"llm_model": "gemini-2.5-flash", "tools": ["exa_search"]},
        )

        # Register a test tool
        from src.tools.tool_registry import Tool, ToolParameter

        test_tool = Tool(
            name="test_tool",
            description="Test",
            parameters=[ToolParameter(name="x", type="string", description="x", required=True)],
        )
        agent.register_tool(test_tool)

        # Test tool calling
        result = agent._call_llm_with_tools("Test prompt", max_iterations=1)
        assert result == "Final response"


class TestExaToolIntegration:
    """Test Exa tool integration."""

    @patch.dict(os.environ, {"EXA_API_KEY": "test-key"})
    @patch("src.tools.exa_tool.Exa")
    def test_exa_search_tool_creation(self, mock_exa):
        """Test Exa search tool creation."""
        mock_client = Mock()
        mock_exa.return_value = mock_client

        tool = create_exa_search_tool(api_key="test-key")

        assert tool.name == "exa_search"
        assert len(tool.parameters) == 2
        assert tool.parameters[0].name == "query"

    @patch.dict(os.environ, {"EXA_API_KEY": "test-key"})
    @patch("src.tools.exa_tool.Exa")
    def test_exa_tool_registration(self, mock_exa):
        """Test Exa tool registration in agent."""
        mock_client = Mock()
        mock_exa.return_value = mock_client

        class TestAgent(BaseScreeningAgent):
            def screen(self, title, abstract, inclusion_criteria, exclusion_criteria):
                return None

        agent = TestAgent(llm_provider="openai", agent_config={"tools": ["exa_search"]})

        # Check if tool was registered
        assert "exa_search" in agent.tool_registry.list_tools()


class TestTavilyToolIntegration:
    """Test Tavily tool integration."""

    @patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"})
    @patch("src.tools.tavily_tool.TavilyClient")
    def test_tavily_search_tool_creation(self, mock_tavily):
        """Test Tavily search tool creation."""
        mock_client = Mock()
        mock_tavily.return_value = mock_client

        tool = create_tavily_search_tool(api_key="test-key")

        assert tool.name == "tavily_search"
        assert len(tool.parameters) == 2
        assert tool.parameters[0].name == "query"

    @patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"})
    @patch("src.tools.tavily_tool.TavilyClient")
    def test_tavily_tool_registration(self, mock_tavily):
        """Test Tavily tool registration in agent."""
        mock_client = Mock()
        mock_tavily.return_value = mock_client

        class TestAgent(BaseScreeningAgent):
            def screen(self, title, abstract, inclusion_criteria, exclusion_criteria):
                return None

        agent = TestAgent(llm_provider="openai", agent_config={"tools": ["tavily_search"]})

        # Check if tool was registered
        assert "tavily_search" in agent.tool_registry.list_tools()


class TestProviderToolCompatibility:
    """Test tool compatibility across providers."""

    def test_tools_work_with_all_providers(self):
        """Test that tools can be used with all LLM providers."""
        from src.tools.tool_registry import Tool, ToolParameter

        registry = ToolRegistry()

        tool = Tool(
            name="test_tool",
            description="Test tool",
            parameters=[
                ToolParameter(name="query", type="string", description="Test query", required=True)
            ],
        )

        registry.register(tool)

        # Test all providers
        providers = ["openai", "anthropic", "google", "gemini", "perplexity"]
        for provider in providers:
            tools = registry.get_tools_for_llm(provider)
            assert len(tools) == 1
            assert (
                tools[0]["name"] == "test_tool"
                or tools[0].get("function", {}).get("name") == "test_tool"
            )


class TestSearchWorkflowIntegration:
    """Test Exa and Tavily tools in search workflow."""

    @patch.dict(os.environ, {"EXA_API_KEY": "test-key", "TAVILY_API_KEY": "test-key"})
    @patch("src.tools.exa_tool.Exa")
    @patch("src.tools.tavily_tool.TavilyClient")
    def test_search_agent_with_research_tools(self, mock_tavily, mock_exa):
        """Test search agent with Exa and Tavily tools."""
        mock_exa_client = Mock()
        mock_tavily_client = Mock()
        mock_exa.return_value = mock_exa_client
        mock_tavily.return_value = mock_tavily_client

        class TestAgent(BaseScreeningAgent):
            def screen(self, title, abstract, inclusion_criteria, exclusion_criteria):
                return None

        agent = TestAgent(
            llm_provider="openai",
            agent_config={"tools": ["exa_search", "tavily_search", "exa_answer", "tavily_extract"]},
        )

        # Verify tools are registered
        registered_tools = agent.tool_registry.list_tools()
        assert "exa_search" in registered_tools
        assert "tavily_search" in registered_tools
        assert "exa_answer" in registered_tools
        assert "tavily_extract" in registered_tools
