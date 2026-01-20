"""
Template Manager

Manages journal-specific LaTeX templates for manuscript formatting.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class TemplateManager:
    """Manage journal templates."""

    def __init__(self, templates_dir: Optional[Path] = None):
        """
        Initialize template manager.

        Args:
            templates_dir: Directory containing journal templates (default: templates/journals/)
        """
        if templates_dir is None:
            # Default to project templates directory
            project_root = Path(__file__).parent.parent.parent
            templates_dir = project_root / "templates" / "journals"
        
        self.templates_dir = Path(templates_dir)
        self.templates_dir.mkdir(parents=True, exist_ok=True)

    def get_template(self, journal: str) -> Optional[Path]:
        """
        Get path to journal template.

        Args:
            journal: Journal name (e.g., 'ieee', 'nature', 'plos')

        Returns:
            Path to template file, or None if not found
        """
        journal_lower = journal.lower()
        
        # Try different possible template file names
        possible_names = [
            f"{journal_lower}.latex",
            f"{journal_lower}.tex",
            f"{journal_lower}.lua",  # Pandoc template
        ]

        for name in possible_names:
            template_path = self.templates_dir / name
            if template_path.exists():
                logger.debug(f"Found template for {journal}: {template_path}")
                return template_path

        logger.warning(f"Template not found for journal: {journal}")
        return None

    def list_available_journals(self) -> List[str]:
        """
        List available journal templates.

        Returns:
            List of journal names with available templates
        """
        journals = []
        for template_file in self.templates_dir.glob("*.latex"):
            journal_name = template_file.stem
            journals.append(journal_name)
        for template_file in self.templates_dir.glob("*.tex"):
            journal_name = template_file.stem
            if journal_name not in journals:
                journals.append(journal_name)
        
        return sorted(journals)

    def validate_template(self, template_path: Path) -> bool:
        """
        Validate template file exists and is readable.

        Args:
            template_path: Path to template file

        Returns:
            True if template is valid, False otherwise
        """
        if not template_path.exists():
            logger.error(f"Template file not found: {template_path}")
            return False

        if not template_path.is_file():
            logger.error(f"Template path is not a file: {template_path}")
            return False

        try:
            # Try to read the template
            content = template_path.read_text(encoding="utf-8")
            if len(content) == 0:
                logger.warning(f"Template file is empty: {template_path}")
                return False
            return True
        except Exception as e:
            logger.error(f"Error reading template {template_path}: {e}")
            return False

    def create_custom_template(
        self, journal: str, template_content: str
    ) -> Path:
        """
        Create a custom template for a journal.

        Args:
            journal: Journal name
            template_content: Template content as string

        Returns:
            Path to created template file
        """
        template_path = self.templates_dir / f"{journal.lower()}.latex"
        template_path.write_text(template_content, encoding="utf-8")
        logger.info(f"Created custom template: {template_path}")
        return template_path
