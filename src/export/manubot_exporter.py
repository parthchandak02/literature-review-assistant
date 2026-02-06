"""
Manubot Exporter

Exports systematic review reports to Manubot-compatible structure.
Generates structured markdown files in content/ directory with manubot.yaml config.
"""

import logging
from pathlib import Path
from typing import Dict, Optional, Any
from datetime import datetime
import yaml

from ..citations import CitationManager

logger = logging.getLogger(__name__)


class ManubotExporter:
    """Export reports to Manubot structure."""

    def __init__(self, output_dir: Path, citation_manager: Optional[CitationManager] = None):
        """
        Initialize Manubot exporter.

        Args:
            output_dir: Base output directory for manuscript
            citation_manager: CitationManager instance (optional)
        """
        self.output_dir = Path(output_dir)
        self.citation_manager = citation_manager
        self.content_dir = self.output_dir / "content"
        self.output_build_dir = self.output_dir / "output"
        self.build_dir = self.output_dir / "build"

    def export(
        self,
        article_sections: Dict[str, str],
        metadata: Optional[Dict[str, Any]] = None,
        citation_style: str = "ieee",
        auto_resolve_citations: bool = True,
    ) -> Path:
        """
        Export article sections to Manubot structure.

        Args:
            article_sections: Dictionary with section names and content
            metadata: Optional metadata (title, authors, etc.)
            citation_style: Citation style name (default: 'ieee')
            auto_resolve_citations: Whether to auto-resolve Manubot citations

        Returns:
            Path to manuscript directory
        """
        # Create directory structure
        self.content_dir.mkdir(parents=True, exist_ok=True)
        self.output_build_dir.mkdir(parents=True, exist_ok=True)
        self.build_dir.mkdir(parents=True, exist_ok=True)

        # Generate front matter
        front_matter = self._generate_front_matter(metadata or {})
        front_matter_path = self.content_dir / "00.front-matter.md"
        front_matter_path.write_text(front_matter, encoding="utf-8")

        # Export sections
        section_order = [
            ("abstract", "01.abstract.md"),
            ("introduction", "02.introduction.md"),
            ("methods", "03.methods.md"),
            ("results", "04.results.md"),
            ("discussion", "05.discussion.md"),
        ]

        for section_name, filename in section_order:
            if section_name in article_sections:
                content = article_sections[section_name]

                # Process citations if citation manager available
                if self.citation_manager:
                    content = self.citation_manager.extract_and_map_citations(
                        content, auto_resolve=auto_resolve_citations
                    )

                section_path = self.content_dir / filename
                section_content = self._format_section(section_name, content)
                section_path.write_text(section_content, encoding="utf-8")
                logger.debug(f"Exported section {section_name} to {section_path}")

        # Generate references section
        if self.citation_manager:
            references_content = self._generate_references_section()
            references_path = self.content_dir / "06.references.md"
            references_path.write_text(references_content, encoding="utf-8")

        # Generate manubot.yaml
        manubot_config = self._generate_manubot_config(citation_style)
        config_path = self.output_dir / "manubot.yaml"
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(manubot_config, f, default_flow_style=False, sort_keys=False)

        logger.info(f"Manubot structure exported to {self.output_dir}")
        return self.output_dir

    def _generate_front_matter(self, metadata: Dict[str, Any]) -> str:
        """Generate front matter markdown file."""
        title = metadata.get("title", "Systematic Review")
        authors = metadata.get("authors", [])
        date = metadata.get("date", datetime.now().strftime("%Y-%m-%d"))
        keywords = metadata.get("keywords", [])

        lines = [
            "---",
            f"title: {title}",
            f"date: {date}",
        ]

        if authors:
            lines.append("authors:")
            for author in authors:
                if isinstance(author, dict):
                    name = author.get("name", "")
                    affiliation = author.get("affiliation", "")
                    if affiliation:
                        lines.append(f'  - name: "{name}"')
                        lines.append(f'    affiliation: "{affiliation}"')
                    else:
                        lines.append(f'  - "{name}"')
                else:
                    lines.append(f'  - "{author}"')

        if keywords:
            keywords_str = ", ".join(keywords)
            lines.append(f'keywords: [{keywords_str}]')

        lines.append("---")
        lines.append("")

        return "\n".join(lines)

    def _format_section(self, section_name: str, content: str) -> str:
        """Format section content with YAML frontmatter."""
        lines = [
            "---",
            f"title: {section_name.title()}",
            "---",
            "",
            content,
        ]
        return "\n".join(lines)

    def _generate_references_section(self) -> str:
        """Generate references section."""
        if not self.citation_manager:
            return "## References\n\nNo references available.\n"

        references = self.citation_manager.generate_references_section()
        lines = [
            "---",
            "title: References",
            "---",
            "",
            references,
        ]
        return "\n".join(lines)

    def _generate_manubot_config(self, citation_style: str) -> Dict[str, Any]:
        """Generate manubot.yaml configuration."""
        config = {
            "manubot": {
                "version": "0.5.0",
            },
            "csl": {
                "style": citation_style,
            },
            "output": {
                "format": ["html", "pdf", "docx"],
            },
            "authors": [],
            "keywords": [],
        }

        return config
