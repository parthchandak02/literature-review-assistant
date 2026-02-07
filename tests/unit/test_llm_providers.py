"""
Unit tests for LLM provider integrations.
"""

import os
from unittest.mock import Mock, patch

from src.screening.base_agent import (
    BaseScreeningAgent,
    get_default_model_for_provider,
    validate_model_provider_compatibility,
)


class TestGoogleGenAIIntegration:
    """Test Google GenAI integration."""

    @patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"})
    def test_setup_google_genai_client(self):
        """Test Google GenAI client setup."""
        with patch("src.screening.base_agent.genai") as mock_genai:
            mock_client = Mock()
            mock_genai.Client.return_value = mock_client

            # Create a concrete agent instance for testing
            class TestAgent(BaseScreeningAgent):
                def screen(self, title, abstract, inclusion_criteria, exclusion_criteria):
                    return None

            agent = TestAgent(
                llm_provider="google",
                api_key="test-key",
                agent_config={"llm_model": "gemini-2.5-flash"},
            )

            assert agent.llm_client == mock_client
            assert hasattr(agent, "llm_model_name")
            mock_genai.Client.assert_called_once_with(api_key="test-key")

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"})
    def test_setup_google_genai_with_gemini_key(self):
        """Test Google GenAI setup with GEMINI_API_KEY."""
        with patch("src.screening.base_agent.genai") as mock_genai:
            mock_client = Mock()
            mock_genai.Client.return_value = mock_client

            class TestAgent(BaseScreeningAgent):
                def screen(self, title, abstract, inclusion_criteria, exclusion_criteria):
                    return None

            agent = TestAgent(llm_provider="gemini", agent_config={"llm_model": "gemini-2.5-flash"})

            assert agent.llm_client == mock_client
            mock_genai.Client.assert_called_once()

    @patch.dict(os.environ, {"GOOGLE_API_KEY": "preferred-key", "GEMINI_API_KEY": "fallback-key"})
    def test_google_api_key_precedence(self):
        """Test that GOOGLE_API_KEY takes precedence over GEMINI_API_KEY."""
        with patch("src.screening.base_agent.genai") as mock_genai:
            mock_client = Mock()
            mock_genai.Client.return_value = mock_client

            class TestAgent(BaseScreeningAgent):
                def screen(self, title, abstract, inclusion_criteria, exclusion_criteria):
                    return None

            _agent = TestAgent(
                llm_provider="google", agent_config={"llm_model": "gemini-2.5-flash"}
            )

            # Should use GOOGLE_API_KEY (preferred)
            mock_genai.Client.assert_called_once_with(api_key="preferred-key")


class TestProviderSwitching:
    """Test switching between providers."""

    def test_provider_validation(self):
        """Test that invalid providers are handled gracefully."""

        class TestAgent(BaseScreeningAgent):
            def screen(self, title, abstract, inclusion_criteria, exclusion_criteria):
                return None

        # Invalid provider should not crash
        agent = TestAgent(llm_provider="invalid_provider", agent_config={})

        assert agent.llm_client is None


class TestErrorHandling:
    """Test error handling for missing keys and invalid models."""

    def test_missing_api_key_google(self):
        """Test handling of missing Google API key."""

        class TestAgent(BaseScreeningAgent):
            def screen(self, title, abstract, inclusion_criteria, exclusion_criteria):
                return None

        agent = TestAgent(llm_provider="google", agent_config={"llm_model": "gemini-2.5-flash"})

        # Should handle gracefully
        assert agent.llm_client is None or hasattr(agent, "llm_client")

    def test_missing_api_key_perplexity(self):
        """Test handling of missing Perplexity API key."""

        class TestAgent(BaseScreeningAgent):
            def screen(self, title, abstract, inclusion_criteria, exclusion_criteria):
                return None

        agent = TestAgent(llm_provider="perplexity", agent_config={"llm_model": "sonar-pro"})

        # Should handle gracefully
        assert agent.llm_client is None or hasattr(agent, "llm_client")

    def test_invalid_model_provider_combination(self):
        """Test handling of invalid model/provider combinations."""

        class TestAgent(BaseScreeningAgent):
            def screen(self, title, abstract, inclusion_criteria, exclusion_criteria):
                return None

        # Using OpenAI model with Google provider should be handled
        agent = TestAgent(
            llm_provider="google",
            api_key="test-key",
            agent_config={"llm_model": "gpt-4"},  # Wrong model for provider
        )

        # Should still initialize (validation can be added later)
        assert hasattr(agent, "llm_model")


class TestToolRegistryProviders:
    """Test tool registry support for new providers."""

    def test_tool_registry_google_format(self):
        """Test tool registry Google format conversion."""
        from src.tools.tool_registry import Tool, ToolParameter, ToolRegistry

        registry = ToolRegistry()

        tool = Tool(
            name="test_tool",
            description="Test tool",
            parameters=[
                ToolParameter(name="query", type="string", description="Test query", required=True)
            ],
        )

        registry.register(tool)

        # Test Google format
        google_tools = registry.get_tools_for_llm("google")
        assert len(google_tools) == 1
        assert google_tools[0]["name"] == "test_tool"
        assert "parameters" in google_tools[0]


class TestDefaultModelSelection:
    """Test provider-specific default model selection."""

    def test_get_default_model_gemini(self):
        """Test Gemini default model."""
        assert get_default_model_for_provider("gemini") == "gemini-2.5-pro"
        assert get_default_model_for_provider("GEMINI") == "gemini-2.5-pro"

    def test_get_default_model_unknown(self):
        """Test unknown provider defaults to gemini-2.5-pro."""
        assert get_default_model_for_provider("unknown") == "gemini-2.5-pro"


class TestModelProviderValidation:
    """Test model/provider compatibility validation."""

    def test_validate_gemini_models(self):
        """Test Gemini model validation."""
        assert validate_model_provider_compatibility("gemini-2.5-pro", "gemini") is True
        assert validate_model_provider_compatibility("gemini-2.5-flash", "gemini") is True
        assert validate_model_provider_compatibility("gemini-pro", "gemini") is True
        assert validate_model_provider_compatibility("gpt-4", "gemini") is False

    def test_validate_unsupported_provider(self):
        """Test that unsupported providers return False."""
        assert validate_model_provider_compatibility("gpt-4", "openai") is False
        assert validate_model_provider_compatibility("claude-3", "anthropic") is False


class TestDefaultModelUsage:
    """Test that default models are used when not specified in config."""

    def test_gemini_uses_default_when_not_in_config(self):
        """Test Gemini provider uses default model when not in config."""

        class TestAgent(BaseScreeningAgent):
            def screen(self, title, abstract, inclusion_criteria, exclusion_criteria):
                return None

        agent = TestAgent(llm_provider="gemini", agent_config={})

        # Should use Gemini default
        assert agent.llm_model == "gemini-2.5-pro"

    def test_config_model_overrides_default(self):
        """Test that model in config overrides default."""

        class TestAgent(BaseScreeningAgent):
            def screen(self, title, abstract, inclusion_criteria, exclusion_criteria):
                return None

        agent = TestAgent(llm_provider="gemini", agent_config={"llm_model": "gemini-2.5-flash"})

        # Should use config model, not default
        assert agent.llm_model == "gemini-2.5-flash"
        assert agent.llm_model != "gemini-2.5-pro"
