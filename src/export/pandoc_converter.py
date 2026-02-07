"""
Pandoc Converter

Converts markdown to PDF, DOCX, and HTML using Pandoc.
Supports CSL citation styles.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    import pypandoc

    PYPANDOC_AVAILABLE = True
except ImportError:
    PYPANDOC_AVAILABLE = False
    pypandoc = None


class PandocConverter:
    """Convert markdown to various formats using Pandoc."""

    def __init__(self):
        """Initialize Pandoc converter."""
        if not PYPANDOC_AVAILABLE:
            logger.warning("pypandoc not available. Install with: pip install pypandoc")
            logger.warning("Pandoc must be installed separately on your system")

    def markdown_to_pdf(
        self,
        markdown_path: Path,
        output_path: Path,
        csl_style: Optional[Path] = None,
        template: Optional[Path] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """
        Convert markdown to PDF using Pandoc.

        Args:
            markdown_path: Path to input markdown file
            output_path: Path to output PDF file
            csl_style: Optional path to CSL style file
            template: Optional path to LaTeX template
            metadata: Optional metadata dictionary

        Returns:
            Path to generated PDF file

        Raises:
            ImportError: If pypandoc is not installed
            RuntimeError: If Pandoc conversion fails
        """
        if not PYPANDOC_AVAILABLE:
            raise ImportError("pypandoc required. Install with: pip install pypandoc")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        extra_args = []

        # Add CSL style if provided
        if csl_style and csl_style.exists():
            extra_args.extend(["--csl", str(csl_style)])

        # Add template if provided
        if template and template.exists():
            extra_args.extend(["--template", str(template)])

        # Add metadata if provided
        if metadata:
            for key, value in metadata.items():
                extra_args.extend(["-M", f"{key}={value}"])

        # Enable citation processing
        extra_args.append("--citeproc")

        # Set resource path to the directory containing the markdown file
        # This allows Pandoc to find images referenced with relative paths
        extra_args.extend(["--resource-path", str(markdown_path.parent)])

        try:
            pypandoc.convert_file(
                str(markdown_path),
                "pdf",
                outputfile=str(output_path),
                extra_args=extra_args,
            )
            logger.info(f"Converted markdown to PDF: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Failed to convert to PDF: {e}")
            raise RuntimeError(f"PDF conversion failed: {e}") from e

    def markdown_to_docx(
        self,
        markdown_path: Path,
        output_path: Path,
        csl_style: Optional[Path] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """
        Convert markdown to DOCX using Pandoc.

        Args:
            markdown_path: Path to input markdown file
            output_path: Path to output DOCX file
            csl_style: Optional path to CSL style file
            metadata: Optional metadata dictionary

        Returns:
            Path to generated DOCX file

        Raises:
            ImportError: If pypandoc is not installed
            RuntimeError: If Pandoc conversion fails
        """
        if not PYPANDOC_AVAILABLE:
            raise ImportError("pypandoc required. Install with: pip install pypandoc")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        extra_args = []

        # Add CSL style if provided
        if csl_style and csl_style.exists():
            extra_args.extend(["--csl", str(csl_style)])

        # Add metadata if provided
        if metadata:
            for key, value in metadata.items():
                extra_args.extend(["-M", f"{key}={value}"])

        # Enable citation processing
        extra_args.append("--citeproc")

        # Set resource path to the directory containing the markdown file
        # This allows Pandoc to find images referenced with relative paths
        extra_args.extend(["--resource-path", str(markdown_path.parent)])

        try:
            pypandoc.convert_file(
                str(markdown_path),
                "docx",
                outputfile=str(output_path),
                extra_args=extra_args,
            )
            logger.info(f"Converted markdown to DOCX: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Failed to convert to DOCX: {e}")
            raise RuntimeError(f"DOCX conversion failed: {e}") from e

    def markdown_to_html(
        self,
        markdown_path: Path,
        output_path: Path,
        csl_style: Optional[Path] = None,
        metadata: Optional[Dict[str, Any]] = None,
        standalone: bool = True,
    ) -> Path:
        """
        Convert markdown to HTML using Pandoc.

        Args:
            markdown_path: Path to input markdown file
            output_path: Path to output HTML file
            csl_style: Optional path to CSL style file
            metadata: Optional metadata dictionary
            standalone: Whether to generate standalone HTML (default: True)

        Returns:
            Path to generated HTML file

        Raises:
            ImportError: If pypandoc is not installed
            RuntimeError: If Pandoc conversion fails
        """
        if not PYPANDOC_AVAILABLE:
            raise ImportError("pypandoc required. Install with: pip install pypandoc")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        extra_args = []

        # Add CSL style if provided
        if csl_style and csl_style.exists():
            extra_args.extend(["--csl", str(csl_style)])

        # Add metadata if provided
        if metadata:
            for key, value in metadata.items():
                extra_args.extend(["-M", f"{key}={value}"])

        # Enable citation processing
        extra_args.append("--citeproc")

        # Standalone HTML
        if standalone:
            extra_args.append("--standalone")

        # Set resource path to the directory containing the markdown file
        # This allows Pandoc to find images referenced with relative paths
        extra_args.extend(["--resource-path", str(markdown_path.parent)])

        try:
            pypandoc.convert_file(
                str(markdown_path),
                "html",
                outputfile=str(output_path),
                extra_args=extra_args,
            )
            logger.info(f"Converted markdown to HTML: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Failed to convert to HTML: {e}")
            raise RuntimeError(f"HTML conversion failed: {e}") from e

    def check_pandoc_available(self) -> bool:
        """
        Check if Pandoc is available on the system.

        Returns:
            True if Pandoc is available, False otherwise
        """
        if not PYPANDOC_AVAILABLE:
            return False

        try:
            # Try to get Pandoc version
            version = pypandoc.get_pandoc_version()
            logger.debug(f"Pandoc version: {version}")
            return True
        except Exception:
            return False
