"""
Configuration Loader

Loads and processes unified YAML configuration file.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()


class ConfigLoader:
    """Loads and processes unified YAML configuration."""

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize config loader.

        Args:
            config_path: Path to YAML config file (default: config/workflow.yaml)
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config" / "workflow.yaml"

        self.config_path = Path(config_path)
        self.config: Optional[Dict[str, Any]] = None

    def load(self) -> Dict[str, Any]:
        """
        Load YAML configuration file.

        Returns:
            Configuration dictionary
        """
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")

        with open(self.config_path, "r") as f:
            self.config = yaml.safe_load(f)

        if not self.config:
            raise ValueError("Configuration file is empty or invalid")

        return self.config

    def substitute_env_vars(self, value: Any) -> Any:
        """
        Recursively substitute environment variables in config values.

        Args:
            value: Config value (may contain ${VAR_NAME} placeholders)

        Returns:
            Value with environment variables substituted
        """
        if isinstance(value, str):
            # Replace ${VAR_NAME} with environment variable
            import re

            pattern = r"\$\{([^}]+)\}"

            def replace_env(match):
                var_name = match.group(1)
                return os.getenv(var_name, match.group(0))

            return re.sub(pattern, replace_env, value)
        elif isinstance(value, dict):
            return {k: self.substitute_env_vars(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self.substitute_env_vars(item) for item in value]
        else:
            return value

    def apply_template_replacement(
        self, config: Dict[str, Any], topic_context: Any
    ) -> Dict[str, Any]:
        """
        Apply template replacement for {topic}, {domain}, etc.

        Args:
            config: Configuration dictionary
            topic_context: TopicContext instance

        Returns:
            Configuration with templates replaced
        """
        replacements = {
            "{topic}": topic_context.topic,
            "{domain}": topic_context.domain or "general",
            "{research_question}": topic_context.research_question or topic_context.topic,
            "{scope}": topic_context.scope or "",
            "{keywords}": ", ".join(topic_context.keywords) if topic_context.keywords else "",
            "{context}": topic_context.context or "",
        }

        def replace_templates(obj: Any) -> Any:
            """Recursively replace templates in object."""
            if isinstance(obj, str):
                result = obj
                for placeholder, value in replacements.items():
                    result = result.replace(placeholder, str(value))
                return result
            elif isinstance(obj, dict):
                return {k: replace_templates(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [replace_templates(item) for item in obj]
            else:
                return obj

        return replace_templates(config)

    def validate(self, config: Dict[str, Any]) -> None:
        """
        Validate configuration structure.

        Args:
            config: Configuration dictionary

        Raises:
            ValueError: If configuration is invalid
        """
        required_sections = ["topic", "agents", "workflow", "criteria", "output"]

        for section in required_sections:
            if section not in config:
                raise ValueError(f"Missing required configuration section: {section}")

        # Validate topic
        topic_config = config["topic"]
        if isinstance(topic_config, dict):
            if "topic" not in topic_config:
                raise ValueError("Topic configuration must include 'topic' field")
        elif not isinstance(topic_config, str):
            raise ValueError("Topic must be a string or dictionary")

        # Validate agents
        if not isinstance(config["agents"], dict):
            raise ValueError("Agents configuration must be a dictionary")

        # Validate workflow
        workflow = config["workflow"]
        if "databases" not in workflow:
            raise ValueError("Workflow must include 'databases' list")

        # Validate criteria
        criteria = config["criteria"]
        if "inclusion" not in criteria or "exclusion" not in criteria:
            raise ValueError("Criteria must include 'inclusion' and 'exclusion' lists")

    def get_config(self) -> Dict[str, Any]:
        """
        Get loaded configuration.

        Returns:
            Configuration dictionary

        Raises:
            ValueError: If config not loaded
        """
        if self.config is None:
            raise ValueError("Configuration not loaded. Call load() first.")
        return self.config


def load_workflow_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Convenience function to load workflow configuration.

    Args:
        config_path: Optional path to config file

    Returns:
        Configuration dictionary
    """
    loader = ConfigLoader(config_path)
    config = loader.load()
    config = loader.substitute_env_vars(config)
    loader.validate(config)
    return config
