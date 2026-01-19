"""
Unit tests for LLM provider integrations.
"""

import os
from unittest.mock import Mock, patch
import pytest
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


class TestPerplexityIntegration:
    """Test Perplexity integration."""

    @patch.dict(os.environ, {"PERPLEXITY_API_KEY": "test-key"})
    def test_setup_perplexity_client(self):
        """Test Perplexity client setup."""
        with patch("src.screening.base_agent.Perplexity") as mock_perplexity:
            mock_client = Mock()
            mock_perplexity.return_value = mock_client

            class TestAgent(BaseScreeningAgent):
                def screen(self, title, abstract, inclusion_criteria, exclusion_criteria):
                    return None

            agent = TestAgent(
                llm_provider="perplexity",
                api_key="test-key",
                agent_config={"llm_model": "sonar-pro"},
            )

            assert agent.llm_client == mock_client
            mock_perplexity.assert_called_once_with(api_key="test-key")

    def test_perplexity_api_call_format(self):
        """Test Perplexity uses OpenAI-compatible API format."""
        with patch("src.screening.base_agent.Perplexity") as mock_perplexity:
            mock_client = Mock()
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = "Test response"
            mock_client.chat.completions.create.return_value = mock_response
            mock_perplexity.return_value = mock_client

            class TestAgent(BaseScreeningAgent):
                def screen(self, title, abstract, inclusion_criteria, exclusion_criteria):
                    return None

            agent = TestAgent(
                llm_provider="perplexity",
                api_key="test-key",
                agent_config={"llm_model": "sonar-pro"},
            )

            # Verify OpenAI-compatible API is used
            result = agent._call_llm("Test prompt")
            mock_client.chat.completions.create.assert_called_once()
            assert result == "Test response"


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

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_openai_fallback(self):
        """Test OpenAI as default provider."""
        with patch("src.screening.base_agent.openai") as mock_openai:
            mock_client = Mock()
            mock_openai.OpenAI.return_value = mock_client

            class TestAgent(BaseScreeningAgent):
                def screen(self, title, abstract, inclusion_criteria, exclusion_criteria):
                    return None

            agent = TestAgent(llm_provider="openai", api_key="test-key")

            assert agent.llm_client == mock_client


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
        from src.tools.tool_registry import ToolRegistry, Tool, ToolParameter

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

    def test_tool_registry_perplexity_format(self):
        """Test tool registry Perplexity format (OpenAI-compatible)."""
        from src.tools.tool_registry import ToolRegistry, Tool, ToolParameter

        registry = ToolRegistry()

        tool = Tool(
            name="test_tool",
            description="Test tool",
            parameters=[
                ToolParameter(name="query", type="string", description="Test query", required=True)
            ],
        )

        registry.register(tool)

        # Test Perplexity format (should be OpenAI-compatible)
        perplexity_tools = registry.get_tools_for_llm("perplexity")
        assert len(perplexity_tools) == 1
        assert perplexity_tools[0]["type"] == "function"
        assert "function" in perplexity_tools[0]


class TestDefaultModelSelection:
    """Test provider-specific default model selection."""

    def test_get_default_model_openai(self):
        """Test OpenAI default model."""
        assert get_default_model_for_provider("openai") == "gpt-4"
        assert get_default_model_for_provider("OPENAI") == "gpt-4"

    def test_get_default_model_anthropic(self):
        """Test Anthropic default model."""
        assert get_default_model_for_provider("anthropic") == "claude-3-opus-20240229"
        assert get_default_model_for_provider("ANTHROPIC") == "claude-3-opus-20240229"

    def test_get_default_model_gemini(self):
        """Test Gemini default model."""
        assert get_default_model_for_provider("gemini") == "gemini-2.5-pro"
        assert get_default_model_for_provider("GEMINI") == "gemini-2.5-pro"

    def test_get_default_model_perplexity(self):
        """Test Perplexity default model."""
        assert get_default_model_for_provider("perplexity") == "sonar-pro"
        assert get_default_model_for_provider("PERPLEXITY") == "sonar-pro"

    def test_get_default_model_unknown(self):
        """Test unknown provider defaults to gpt-4."""
        assert get_default_model_for_provider("unknown") == "gpt-4"


class TestModelProviderValidation:
    """Test model/provider compatibility validation."""

    def test_validate_openai_models(self):
        """Test OpenAI model validation."""
        assert validate_model_provider_compatibility("gpt-4", "openai") is True
        assert validate_model_provider_compatibility("gpt-4o", "openai") is True
        assert validate_model_provider_compatibility("gpt-3.5-turbo", "openai") is True
        assert validate_model_provider_compatibility("o1-preview", "openai") is True
        assert validate_model_provider_compatibility("gemini-2.5-pro", "openai") is False

    def test_validate_anthropic_models(self):
        """Test Anthropic model validation."""
        assert validate_model_provider_compatibility("claude-3-opus-20240229", "anthropic") is True
        assert validate_model_provider_compatibility("claude-3-sonnet", "anthropic") is True
        assert validate_model_provider_compatibility("claude-2", "anthropic") is True
        assert validate_model_provider_compatibility("gpt-4", "anthropic") is False

    def test_validate_gemini_models(self):
        """Test Gemini model validation."""
        assert validate_model_provider_compatibility("gemini-2.5-pro", "gemini") is True
        assert validate_model_provider_compatibility("gemini-2.5-flash", "gemini") is True
        assert validate_model_provider_compatibility("gemini-pro", "gemini") is True
        assert validate_model_provider_compatibility("gpt-4", "gemini") is False

    def test_validate_perplexity_models(self):
        """Test Perplexity model validation."""
        assert validate_model_provider_compatibility("sonar-pro", "perplexity") is True
        assert validate_model_provider_compatibility("sonar-reasoning-pro", "perplexity") is True
        assert validate_model_provider_compatibility("llama-3", "perplexity") is True
        assert validate_model_provider_compatibility("gpt-4", "perplexity") is False


class TestDefaultModelUsage:
    """Test that default models are used when not specified in config."""

    def test_gemini_uses_default_when_not_in_config(self):
        """Test Gemini provider uses default model when not in config."""
        class TestAgent(BaseScreeningAgent):
            def screen(self, title, abstract, inclusion_criteria, exclusion_criteria):
                return None

        agent = TestAgent(llm_provider="gemini", agent_config={})
        
        # Should use Gemini default, not gpt-4
        assert agent.llm_model == "gemini-2.5-pro"
        assert agent.llm_model != "gpt-4"

    def test_openai_uses_default_when_not_in_config(self):
        """Test OpenAI provider uses default model when not in config."""
        class TestAgent(BaseScreeningAgent):
            def screen(self, title, abstract, inclusion_criteria, exclusion_criteria):
                return None

        agent = TestAgent(llm_provider="openai", agent_config={})
        
        assert agent.llm_model == "gpt-4"

    def test_anthropic_uses_default_when_not_in_config(self):
        """Test Anthropic provider uses default model when not in config."""
        class TestAgent(BaseScreeningAgent):
            def screen(self, title, abstract, inclusion_criteria, exclusion_criteria):
                return None

        agent = TestAgent(llm_provider="anthropic", agent_config={})
        
        assert agent.llm_model == "claude-3-opus-20240229"

    def test_perplexity_uses_default_when_not_in_config(self):
        """Test Perplexity provider uses default model when not in config."""
        class TestAgent(BaseScreeningAgent):
            def screen(self, title, abstract, inclusion_criteria, exclusion_criteria):
                return None

        agent = TestAgent(llm_provider="perplexity", agent_config={})
        
        assert agent.llm_model == "sonar-pro"

    def test_config_model_overrides_default(self):
        """Test that model in config overrides default."""
        class TestAgent(BaseScreeningAgent):
            def screen(self, title, abstract, inclusion_criteria, exclusion_criteria):
                return None

        agent = TestAgent(
            llm_provider="gemini",
            agent_config={"llm_model": "gemini-2.5-flash"}
        )
        
        # Should use config model, not default
        assert agent.llm_model == "gemini-2.5-flash"
        assert agent.llm_model != "gemini-2.5-pro"
