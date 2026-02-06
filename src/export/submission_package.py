"""
Submission Package Builder

Builds complete submission packages for journal submission.
Collects all required files: manuscript, figures, tables, supplementary materials.
"""

import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any

from .pandoc_converter import PandocConverter
from .template_manager import TemplateManager
from .submission_checklist import SubmissionChecklistGenerator

logger = logging.getLogger(__name__)


class SubmissionPackageBuilder:
    """Build submission packages for journals."""

    def __init__(self, output_dir: Path):
        """
        Initialize submission package builder.

        Args:
            output_dir: Base output directory
        """
        self.output_dir = Path(output_dir)
        self.pandoc_converter = PandocConverter()
        self.template_manager = TemplateManager()
        self.checklist_generator = SubmissionChecklistGenerator()

    def build_package(
        self,
        workflow_outputs: Dict[str, Any],
        journal: str,
        manuscript_markdown: Optional[Path] = None,
        generate_pdf: bool = True,
        generate_docx: bool = True,
        generate_html: bool = True,
        include_supplementary: bool = True,
    ) -> Path:
        """
        Build complete submission package.

        Args:
            workflow_outputs: Dictionary with workflow output paths
            journal: Journal name (e.g., 'ieee', 'nature')
            manuscript_markdown: Path to main markdown manuscript (optional)
            generate_pdf: Whether to generate PDF
            generate_docx: Whether to generate DOCX
            generate_html: Whether to generate HTML
            include_supplementary: Whether to include supplementary materials

        Returns:
            Path to submission package directory
        """
        package_dir = self.output_dir / f"submission_package_{journal}"
        package_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Building submission package for {journal} in {package_dir}")

        # Step 1: Copy manuscript
        if manuscript_markdown:
            self._copy_manuscript(manuscript_markdown, package_dir, journal)

        # Step 2: Collect figures first and get path mapping
        figures_dir = package_dir / "figures"
        figures_dir.mkdir(exist_ok=True)
        path_mapping = self._collect_figures(workflow_outputs, figures_dir)

        # Step 3: Update manuscript paths to reference figures/ directory
        if manuscript_markdown and path_mapping:
            manuscript_in_package = package_dir / "manuscript.md"
            self._update_manuscript_paths(manuscript_in_package, path_mapping)

        # Step 4: Generate formatted outputs from updated manuscript
        manuscript_in_package = package_dir / "manuscript.md"
        if generate_pdf and manuscript_in_package.exists():
            self._generate_pdf(manuscript_in_package, package_dir, journal)
        
        if generate_docx and manuscript_in_package.exists():
            self._generate_docx(manuscript_in_package, package_dir, journal)
        
        if generate_html and manuscript_in_package.exists():
            self._generate_html(manuscript_in_package, package_dir, journal)

        # Collect tables
        tables_dir = package_dir / "tables"
        tables_dir.mkdir(exist_ok=True)
        self._collect_tables(workflow_outputs, tables_dir)

        # Collect supplementary materials
        if include_supplementary:
            supplementary_dir = package_dir / "supplementary"
            supplementary_dir.mkdir(exist_ok=True)
            self._collect_supplementary(workflow_outputs, supplementary_dir)

        # Copy references
        self._copy_references(workflow_outputs, package_dir)

        # Generate submission checklist
        checklist_path = package_dir / "submission_checklist.md"
        checklist = self.checklist_generator.generate_checklist(
            journal, package_dir
        )
        checklist_path.write_text(checklist, encoding="utf-8")

        logger.info(f"Submission package created: {package_dir}")
        return package_dir

    def build_for_multiple_journals(
        self,
        workflow_outputs: Dict[str, Any],
        journals: List[str],
        manuscript_markdown: Optional[Path] = None,
        generate_pdf: bool = True,
        generate_docx: bool = True,
        generate_html: bool = True,
        include_supplementary: bool = True,
    ) -> Dict[str, Path]:
        """
        Build submission packages for multiple journals.

        Args:
            workflow_outputs: Dictionary with workflow output paths
            journals: List of journal names
            manuscript_markdown: Path to main markdown manuscript (optional)
            generate_pdf: Whether to generate PDF
            generate_docx: Whether to generate DOCX
            generate_html: Whether to generate HTML
            include_supplementary: Whether to include supplementary materials

        Returns:
            Dictionary mapping journal names to package directory paths
        """
        packages = {}
        
        for journal in journals:
            try:
                package_dir = self.build_package(
                    workflow_outputs,
                    journal,
                    manuscript_markdown,
                    generate_pdf,
                    generate_docx,
                    generate_html,
                    include_supplementary,
                )
                packages[journal] = package_dir
                logger.info(f"Built package for {journal}: {package_dir}")
            except Exception as e:
                logger.error(f"Failed to build package for {journal}: {e}")
                packages[journal] = None

        return packages

    def _copy_manuscript(
        self, manuscript_path: Path, package_dir: Path, journal: str
    ):
        """Copy manuscript markdown to package."""
        target = package_dir / "manuscript.md"
        shutil.copy2(manuscript_path, target)
        logger.debug(f"Copied manuscript to {target}")

    def _update_manuscript_paths(
        self, manuscript_path: Path, path_mapping: Dict[str, str]
    ) -> None:
        """
        Update image paths in manuscript.md to reference figures/ directory.
        
        Args:
            manuscript_path: Path to the manuscript.md file
            path_mapping: Dictionary mapping original paths to new figure paths
        """
        import re
        
        if not manuscript_path.exists():
            logger.warning(f"Manuscript not found: {manuscript_path}")
            return
        
        content = manuscript_path.read_text(encoding="utf-8")
        
        # Replace each image path
        for original_path, new_path in path_mapping.items():
            # Escape special regex characters in the original path
            escaped_original = re.escape(original_path)
            
            # Match markdown image syntax: ![alt](path)
            pattern = r'!\[([^\]]*)\]\(' + escaped_original + r'\)'
            replacement = r'![\1](' + new_path + r')'
            
            # Replace all occurrences
            content = re.sub(pattern, replacement, content)
        
        # Write updated content back
        manuscript_path.write_text(content, encoding="utf-8")
        logger.debug(f"Updated manuscript paths: {len(path_mapping)} mappings applied")

    def _generate_pdf(
        self, markdown_path: Path, package_dir: Path, journal: str
    ):
        """Generate PDF from markdown."""
        try:
            output_path = package_dir / "manuscript.pdf"
            
            # Get CSL style
            from ..citations.csl_formatter import CSLFormatter
            csl_formatter = CSLFormatter()
            csl_style_path = csl_formatter.get_style_path(journal)
            
            # Get template if available
            template_path = self.template_manager.get_template(journal)
            
            self.pandoc_converter.markdown_to_pdf(
                markdown_path,
                output_path,
                csl_style=csl_style_path,
                template=template_path,
            )
            logger.info(f"Generated PDF: {output_path}")
        except Exception as e:
            logger.warning(f"Failed to generate PDF: {e}")

    def _generate_docx(
        self, markdown_path: Path, package_dir: Path, journal: str
    ):
        """Generate DOCX from markdown."""
        try:
            output_path = package_dir / "manuscript.docx"
            
            # Get CSL style
            from ..citations.csl_formatter import CSLFormatter
            csl_formatter = CSLFormatter()
            csl_style_path = csl_formatter.get_style_path(journal)
            
            self.pandoc_converter.markdown_to_docx(
                markdown_path,
                output_path,
                csl_style=csl_style_path,
            )
            logger.info(f"Generated DOCX: {output_path}")
        except Exception as e:
            logger.warning(f"Failed to generate DOCX: {e}")

    def _generate_html(
        self, markdown_path: Path, package_dir: Path, journal: str
    ):
        """Generate HTML from markdown."""
        try:
            output_path = package_dir / "manuscript.html"
            
            # Get CSL style
            from ..citations.csl_formatter import CSLFormatter
            csl_formatter = CSLFormatter()
            csl_style_path = csl_formatter.get_style_path(journal)
            
            self.pandoc_converter.markdown_to_html(
                markdown_path,
                output_path,
                csl_style=csl_style_path,
            )
            logger.info(f"Generated HTML: {output_path}")
        except Exception as e:
            logger.warning(f"Failed to generate HTML: {e}")

    def _collect_figures(
        self, workflow_outputs: Dict[str, Any], figures_dir: Path
    ) -> Dict[str, str]:
        """
        Collect figure files and return path mapping.
        
        Returns:
            Dictionary mapping original paths to new figure paths (relative to package dir)
        """
        figures = []
        
        # PRISMA diagram
        if "prisma_diagram" in workflow_outputs:
            prisma_path = Path(workflow_outputs["prisma_diagram"])
            if prisma_path.exists():
                figures.append(prisma_path)

        # Visualizations
        if "visualizations" in workflow_outputs:
            viz_paths = workflow_outputs["visualizations"]
            if isinstance(viz_paths, dict):
                for _, path in viz_paths.items():
                    if not str(path).endswith(".html"):
                        fig_path = Path(path)
                        if fig_path.exists():
                            figures.append(fig_path)

        # Copy figures and build path mapping
        path_mapping = {}
        for i, fig_path in enumerate(figures, 1):
            target = figures_dir / f"figure_{i}{fig_path.suffix}"
            shutil.copy2(fig_path, target)
            logger.debug(f"Copied figure: {target}")
            
            # Map original path (multiple formats) to new figure path
            # Handle both absolute paths and relative paths (filename only)
            original_absolute = str(fig_path)
            original_relative = fig_path.name
            new_path = f"figures/figure_{i}{fig_path.suffix}"
            
            path_mapping[original_absolute] = new_path
            path_mapping[original_relative] = new_path
        
        return path_mapping

    def _collect_tables(
        self, workflow_outputs: Dict[str, Any], tables_dir: Path
    ):
        """Collect table files."""
        # Tables would typically be in extracted data or supplementary materials
        # This is a placeholder for future table collection
        pass

    def _collect_supplementary(
        self, workflow_outputs: Dict[str, Any], supplementary_dir: Path
    ):
        """Collect supplementary materials."""
        # Search strategies
        if "search_strategies" in workflow_outputs:
            search_strategies_path = Path(workflow_outputs["search_strategies"])
            if search_strategies_path.exists():
                target = supplementary_dir / "search_strategies.md"
                shutil.copy2(search_strategies_path, target)

        # PRISMA checklist
        if "prisma_checklist" in workflow_outputs:
            checklist_path = Path(workflow_outputs["prisma_checklist"])
            if checklist_path.exists():
                target = supplementary_dir / "prisma_checklist.json"
                shutil.copy2(checklist_path, target)

        # Data extraction form
        if "extraction_form" in workflow_outputs:
            form_path = Path(workflow_outputs["extraction_form"])
            if form_path.exists():
                target = supplementary_dir / "data_extraction_form.md"
                shutil.copy2(form_path, target)

    def _copy_references(
        self, workflow_outputs: Dict[str, Any], package_dir: Path
    ):
        """Copy reference files."""
        # BibTeX
        bibtex_path = self.output_dir / "references.bib"
        if bibtex_path.exists():
            target = package_dir / "references.bib"
            shutil.copy2(bibtex_path, target)

        # RIS
        ris_path = self.output_dir / "references.ris"
        if ris_path.exists():
            target = package_dir / "references.ris"
            shutil.copy2(ris_path, target)
