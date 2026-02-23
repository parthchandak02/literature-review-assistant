"""Export package: IEEE LaTeX, submission packager, validators."""

from src.export.bibtex_builder import build_bibtex
from src.export.docx_exporter import generate_docx
from src.export.ieee_latex import markdown_to_latex
from src.export.ieee_validator import ValidationResult as IEEEValidationResult
from src.export.ieee_validator import validate_ieee
from src.export.markdown_refs import (
    assemble_submission_manuscript,
    build_markdown_figures_section,
    build_markdown_references_section,
    strip_appended_sections,
)
from src.export.prisma_checklist import PrismaValidationResult, validate_prisma
from src.export.submission_packager import package_submission

__all__ = [
    "assemble_submission_manuscript",
    "build_bibtex",
    "build_markdown_figures_section",
    "build_markdown_references_section",
    "generate_docx",
    "markdown_to_latex",
    "package_submission",
    "strip_appended_sections",
    "validate_ieee",
    "validate_prisma",
    "IEEEValidationResult",
    "PrismaValidationResult",
]
