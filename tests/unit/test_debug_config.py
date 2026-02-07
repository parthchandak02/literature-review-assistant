"""
Unit tests for debug config.
"""

import yaml

from src.config.debug_config import (
    DebugConfig,
    DebugLevel,
    get_debug_config_from_env,
    load_debug_config,
)


class TestDebugConfig:
    """Test DebugConfig class."""

    def test_debug_config_defaults(self):
        """Test DebugConfig default values."""
        config = DebugConfig()

        assert config.enabled is False
        assert config.level == DebugLevel.NORMAL
        assert config.log_to_file is False
        assert config.show_metrics is True
        assert config.show_costs is True

    def test_debug_config_from_dict(self):
        """Test creating DebugConfig from dict."""
        data = {"enabled": True, "level": "full", "log_to_file": True, "show_metrics": False}

        config = DebugConfig.from_dict(data)

        assert config.enabled is True
        assert config.level == DebugLevel.FULL
        assert config.log_to_file is True
        assert config.show_metrics is False

    def test_debug_config_to_dict(self):
        """Test converting DebugConfig to dict."""
        config = DebugConfig(enabled=True, level=DebugLevel.DETAILED)

        data = config.to_dict()

        assert data["enabled"] is True
        assert data["level"] == "detailed"
        assert isinstance(data, dict)


class TestLoadDebugConfig:
    """Test loading debug config."""

    def test_load_debug_config_from_file(self, tmp_path):
        """Test loading debug config from YAML file."""
        config_file = tmp_path / "test_config.yaml"
        config_data = {"debug": {"enabled": True, "level": "detailed", "log_to_file": True}}
        config_file.write_text(yaml.dump(config_data))

        config = load_debug_config(str(config_file))

        assert config.enabled is True
        assert config.level == DebugLevel.DETAILED
        assert config.log_to_file is True

    def test_load_debug_config_nonexistent_file(self, tmp_path):
        """Test loading debug config from nonexistent file."""
        config = load_debug_config(str(tmp_path / "nonexistent.yaml"))

        # Should return default config
        assert config.enabled is False
        assert config.level == DebugLevel.NORMAL

    def test_get_debug_config_from_env(self, monkeypatch):
        """Test getting debug config from environment."""
        monkeypatch.setenv("DEBUG", "true")
        monkeypatch.setenv("DEBUG_LEVEL", "full")
        monkeypatch.setenv("LOG_TO_FILE", "true")

        config = get_debug_config_from_env()

        assert config.enabled is True
        assert config.level == DebugLevel.FULL
        assert config.log_to_file is True

    def test_get_debug_config_from_env_defaults(self, monkeypatch):
        """Test getting debug config with defaults."""
        # Clear env vars
        monkeypatch.delenv("DEBUG", raising=False)
        monkeypatch.delenv("DEBUG_LEVEL", raising=False)

        config = get_debug_config_from_env()

        assert config.enabled is False
        assert config.level == DebugLevel.NORMAL
