"""
Unit tests for config loader.
"""

import pytest
import yaml
from src.config.config_loader import ConfigLoader
from src.orchestration.topic_propagator import TopicContext


class TestConfigLoader:
    """Test ConfigLoader class."""

    def test_config_loader_initialization(self, tmp_path):
        """Test ConfigLoader initialization."""
        config_file = tmp_path / "test_config.yaml"
        config_file.write_text("topic:\n  topic: Test Topic\n")

        loader = ConfigLoader(config_path=str(config_file))

        assert loader.config_path == config_file
        assert loader.config is None

    def test_load_config(self, tmp_path):
        """Test loading configuration."""
        config_file = tmp_path / "test_config.yaml"
        config_data = {"topic": {"topic": "Test Topic"}, "workflow": {"databases": ["PubMed"]}}
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader(config_path=str(config_file))
        config = loader.load()

        assert config["topic"]["topic"] == "Test Topic"
        assert config["workflow"]["databases"] == ["PubMed"]

    def test_load_nonexistent_config(self, tmp_path):
        """Test loading nonexistent config."""
        loader = ConfigLoader(config_path=str(tmp_path / "nonexistent.yaml"))

        with pytest.raises(FileNotFoundError):
            loader.load()

    def test_substitute_env_vars_string(self, tmp_path):
        """Test environment variable substitution in string."""
        import os

        os.environ["TEST_VAR"] = "test_value"

        config_file = tmp_path / "test_config.yaml"
        config_file.write_text("topic:\n  topic: Test\n")

        loader = ConfigLoader(config_path=str(config_file))

        result = loader.substitute_env_vars("${TEST_VAR}")
        assert result == "test_value"

        result = loader.substitute_env_vars("prefix_${TEST_VAR}_suffix")
        assert result == "prefix_test_value_suffix"

    def test_substitute_env_vars_dict(self, tmp_path):
        """Test environment variable substitution in dict."""
        import os

        os.environ["TEST_VAR"] = "test_value"

        config_file = tmp_path / "test_config.yaml"
        config_file.write_text("topic:\n  topic: Test\n")

        loader = ConfigLoader(config_path=str(config_file))

        data = {"key": "${TEST_VAR}", "nested": {"key2": "prefix_${TEST_VAR}_suffix"}}
        result = loader.substitute_env_vars(data)

        assert result["key"] == "test_value"
        assert result["nested"]["key2"] == "prefix_test_value_suffix"

    def test_substitute_env_vars_list(self, tmp_path):
        """Test environment variable substitution in list."""
        import os

        os.environ["TEST_VAR"] = "test_value"

        config_file = tmp_path / "test_config.yaml"
        config_file.write_text("topic:\n  topic: Test\n")

        loader = ConfigLoader(config_path=str(config_file))

        data = ["${TEST_VAR}", "static_value"]
        result = loader.substitute_env_vars(data)

        assert result[0] == "test_value"
        assert result[1] == "static_value"

    def test_apply_template_replacement(self, tmp_path):
        """Test template replacement."""
        config_file = tmp_path / "test_config.yaml"
        config_file.write_text("topic:\n  topic: Test\n")

        loader = ConfigLoader(config_path=str(config_file))

        topic_context = TopicContext(
            topic="Test Topic",
            domain="healthcare",
            research_question="Test question",
            keywords=["keyword1", "keyword2"],
        )

        config = {
            "agents": {
                "screening_agent": {
                    "role": "Screener for {topic}",
                    "goal": "Screen papers about {domain}",
                }
            }
        }

        result = loader.apply_template_replacement(config, topic_context)

        assert "{topic}" not in result["agents"]["screening_agent"]["role"]
        assert "{domain}" not in result["agents"]["screening_agent"]["goal"]
        assert "Test Topic" in result["agents"]["screening_agent"]["role"]
        assert "healthcare" in result["agents"]["screening_agent"]["goal"]
