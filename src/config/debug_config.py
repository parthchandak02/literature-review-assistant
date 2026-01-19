"""
Debug configuration and settings.
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import yaml


class DebugLevel(str, Enum):
    """Debug level enumeration."""

    MINIMAL = "minimal"
    NORMAL = "normal"
    DETAILED = "detailed"
    FULL = "full"


@dataclass
class DebugConfig:
    """Debug configuration."""

    enabled: bool = False
    level: DebugLevel = DebugLevel.NORMAL
    log_to_file: bool = False
    log_file: str = "logs/workflow.log"
    show_metrics: bool = True
    show_costs: bool = True
    show_traces: bool = False
    show_tool_calls: bool = True
    show_llm_calls: bool = False  # Can be verbose
    show_handoffs: bool = True
    show_state_transitions: bool = True
    performance_profiling: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DebugConfig":
        """Create from dictionary."""
        if isinstance(data.get("level"), str):
            data["level"] = DebugLevel(data["level"])
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "level": self.level.value,
            "log_to_file": self.log_to_file,
            "log_file": self.log_file,
            "show_metrics": self.show_metrics,
            "show_costs": self.show_costs,
            "show_traces": self.show_traces,
            "show_tool_calls": self.show_tool_calls,
            "show_llm_calls": self.show_llm_calls,
            "show_handoffs": self.show_handoffs,
            "show_state_transitions": self.show_state_transitions,
            "performance_profiling": self.performance_profiling,
        }


def load_debug_config(config_path: Optional[str] = None) -> DebugConfig:
    """
    Load debug configuration from YAML file.

    Args:
        config_path: Path to config file (default: config/workflow.yaml)

    Returns:
        DebugConfig instance
    """
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "config" / "workflow.yaml"

    config_path = Path(config_path)

    if not config_path.exists():
        return DebugConfig()

    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        debug_section = config.get("debug", {})
        return DebugConfig.from_dict(debug_section)
    except Exception:
        return DebugConfig()


def get_debug_config_from_env() -> DebugConfig:
    """
    Get debug configuration from environment variables.

    Returns:
        DebugConfig instance
    """
    import os

    config = DebugConfig()

    if os.getenv("DEBUG", "").lower() == "true":
        config.enabled = True
        config.level = DebugLevel.FULL

    if os.getenv("VERBOSE", "").lower() == "true":
        config.enabled = True
        config.level = DebugLevel.DETAILED

    level_str = os.getenv("DEBUG_LEVEL", "").lower()
    if level_str:
        try:
            config.level = DebugLevel(level_str)
            config.enabled = True
        except ValueError:
            pass

    if os.getenv("LOG_TO_FILE", "").lower() == "true":
        config.log_to_file = True
        config.log_file = os.getenv("LOG_FILE", config.log_file)

    return config
