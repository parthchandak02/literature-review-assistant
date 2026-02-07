"""
Submission Checklist Generator

Generates and validates submission checklists for journal submissions.
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class SubmissionChecklistGenerator:
    """Generate submission checklists."""

    def __init__(self):
        """Initialize checklist generator."""

    def generate_checklist(self, journal: str, package_dir: Path) -> str:
        """
        Generate submission checklist markdown.

        Args:
            journal: Journal name
            package_dir: Path to submission package directory

        Returns:
            Checklist as markdown string
        """
        checks = self.validate_submission(package_dir, journal)

        lines = [
            f"# Submission Checklist for {journal.upper()}",
            "",
            "## Required Files",
            "",
        ]

        # Check required files
        required_files = [
            ("manuscript.pdf", "PDF manuscript"),
            ("manuscript.docx", "Word manuscript"),
            ("manuscript.html", "HTML manuscript (optional)"),
            ("references.bib", "BibTeX references"),
            ("figures/", "Figures directory"),
            ("supplementary/", "Supplementary materials"),
        ]

        for filename, description in required_files:
            file_path = package_dir / filename
            exists = file_path.exists()
            status = "[x]" if exists else "[ ]"
            lines.append(f"{status} {description} ({filename})")

        lines.append("")
        lines.append("## Content Checks")
        lines.append("")

        # Content validation
        content_checks = [
            ("Abstract present", checks.get("has_abstract", False)),
            ("Introduction present", checks.get("has_introduction", False)),
            ("Methods present", checks.get("has_methods", False)),
            ("Results present", checks.get("has_results", False)),
            ("Discussion present", checks.get("has_discussion", False)),
            ("References present", checks.get("has_references", False)),
            ("Figures included", checks.get("has_figures", False)),
        ]

        for check_name, passed in content_checks:
            status = "[x]" if passed else "[ ]"
            lines.append(f"{status} {check_name}")

        lines.append("")
        lines.append("## Formatting Checks")
        lines.append("")

        formatting_checks = [
            ("Citation format correct", checks.get("citations_valid", False)),
            ("Figure captions present", checks.get("figure_captions", False)),
            ("Table formatting correct", checks.get("tables_valid", False)),
        ]

        for check_name, passed in formatting_checks:
            status = "[x]" if passed else "[ ]"
            lines.append(f"{status} {check_name}")

        lines.append("")
        lines.append("## Summary")
        lines.append("")

        total_checks = len(required_files) + len(content_checks) + len(formatting_checks)
        passed_checks = sum(
            [
                checks.get("has_abstract", False),
                checks.get("has_introduction", False),
                checks.get("has_methods", False),
                checks.get("has_results", False),
                checks.get("has_discussion", False),
                checks.get("has_references", False),
                checks.get("has_figures", False),
            ]
        ) + sum(
            [
                v
                for k, v in checks.items()
                if k in ["citations_valid", "figure_captions", "tables_valid"]
            ]
        )

        lines.append(f"**Total checks:** {total_checks}")
        lines.append(f"**Passed:** {passed_checks}")
        lines.append(f"**Failed:** {total_checks - passed_checks}")
        lines.append("")

        if passed_checks == total_checks:
            lines.append("**Status:** READY FOR SUBMISSION")
        else:
            lines.append("**Status:** REVIEW REQUIRED")

        return "\n".join(lines)

    def validate_submission(
        self, package_dir: Path, journal: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate submission package.

        Args:
            package_dir: Path to submission package directory
            journal: Optional journal name for journal-specific validation

        Returns:
            Dictionary with validation results
        """
        results = {
            "has_abstract": False,
            "has_introduction": False,
            "has_methods": False,
            "has_results": False,
            "has_discussion": False,
            "has_references": False,
            "has_figures": False,
            "citations_valid": False,
            "figure_captions": False,
            "tables_valid": False,
        }

        # Check manuscript files
        manuscript_md = package_dir / "manuscript.md"
        if manuscript_md.exists():
            content = manuscript_md.read_text(encoding="utf-8")
            results["has_abstract"] = "abstract" in content.lower()
            results["has_introduction"] = "introduction" in content.lower()
            results["has_methods"] = "methods" in content.lower()
            results["has_results"] = "results" in content.lower()
            results["has_discussion"] = "discussion" in content.lower()
            results["has_references"] = (
                "references" in content.lower() or "reference" in content.lower()
            )
            results["citations_valid"] = "[" in content and "]" in content  # Basic citation check

        # Check figures
        figures_dir = package_dir / "figures"
        if figures_dir.exists() and any(figures_dir.iterdir()):
            results["has_figures"] = True
            # Check for figure captions in manuscript
            if manuscript_md.exists():
                content = manuscript_md.read_text(encoding="utf-8")
                results["figure_captions"] = (
                    "figure" in content.lower() and "caption" in content.lower()
                )

        # Check references
        bibtex_path = package_dir / "references.bib"
        if bibtex_path.exists():
            results["has_references"] = True

        return results
