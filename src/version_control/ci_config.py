"""
CI/CD Configuration

Configuration for continuous integration and deployment of manuscripts.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class CIConfig:
    """CI/CD configuration manager."""

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize CI/CD configuration.

        Args:
            config_path: Path to CI config file (optional)
        """
        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load CI/CD configuration."""
        default_config = {
            "build_on_push": True,
            "build_on_pr": True,
            "generate_pdf": True,
            "generate_docx": True,
            "generate_html": True,
            "journals": ["ieee"],
            "artifact_retention_days": 30,
        }
        
        if self.config_path and self.config_path.exists():
            try:
                import yaml
                with open(self.config_path, "r") as f:
                    user_config = yaml.safe_load(f) or {}
                default_config.update(user_config)
            except Exception as e:
                logger.warning(f"Failed to load CI config: {e}")

        return default_config

    def get_build_journals(self) -> List[str]:
        """Get list of journals to build."""
        return self.config.get("journals", ["ieee"])

    def should_generate_pdf(self) -> bool:
        """Check if PDF should be generated."""
        return self.config.get("generate_pdf", True)

    def should_generate_docx(self) -> bool:
        """Check if DOCX should be generated."""
        return self.config.get("generate_docx", True)

    def should_generate_html(self) -> bool:
        """Check if HTML should be generated."""
        return self.config.get("generate_html", True)
