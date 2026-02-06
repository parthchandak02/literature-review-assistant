"""
Journal Selector

Manages journal configurations and validation.
"""

import logging
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class JournalSelector:
    """Select and validate journals."""

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize journal selector.

        Args:
            config_path: Path to journals.yaml config file (default: config/journals.yaml)
        """
        if config_path is None:
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config" / "journals.yaml"

        self.config_path = Path(config_path)
        self.journals_config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load journal configurations."""
        if not self.config_path.exists():
            logger.warning(f"Journal config not found: {self.config_path}")
            return {}

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            return config.get("journals", {})
        except Exception as e:
            logger.error(f"Failed to load journal config: {e}")
            return {}

    def list_journals(self) -> List[str]:
        """
        List available journals.

        Returns:
            List of journal names
        """
        return sorted(self.journals_config.keys())

    def get_journal_config(self, journal: str) -> Optional[Dict[str, Any]]:
        """
        Get configuration for a journal.

        Args:
            journal: Journal name

        Returns:
            Journal configuration dictionary, or None if not found
        """
        journal_lower = journal.lower()
        return self.journals_config.get(journal_lower)

    def validate_for_journal(
        self, manuscript_path: Path, journal: str
    ) -> Dict[str, bool]:
        """
        Validate manuscript for journal requirements.

        Args:
            manuscript_path: Path to manuscript file
            journal: Journal name

        Returns:
            Dictionary with validation results
        """
        config = self.get_journal_config(journal)
        if not config:
            logger.warning(f"Journal config not found: {journal}")
            return {}

        results = {}

        if not manuscript_path.exists():
            logger.error(f"Manuscript not found: {manuscript_path}")
            return {}

        content = manuscript_path.read_text(encoding="utf-8").lower()

        # Check required sections
        required_sections = config.get("required_sections", [])
        for section in required_sections:
            results[f"has_{section}"] = section in content

        # Check page limit (if applicable)
        max_pages = config.get("max_pages")
        if max_pages:
            # Rough estimate: ~500 words per page
            word_count = len(content.split())
            estimated_pages = word_count / 500
            results["within_page_limit"] = estimated_pages <= max_pages

        return results
