"""
Stage Validators

Validate prerequisites and outputs for workflow stages.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of validation."""

    is_valid: bool
    errors: List[str]
    warnings: List[str]

    def __str__(self) -> str:
        if self.is_valid:
            return "Validation passed"
        return f"Validation failed: {', '.join(self.errors)}"


class StageValidator:
    """Base validator for workflow stages."""

    def validate_prerequisites(
        self,
        stage: str,
        state: Dict[str, Any],
    ) -> ValidationResult:
        """
        Validate that required data exists for a stage.

        Args:
            stage: Stage name
            state: State dictionary

        Returns:
            ValidationResult
        """
        errors = []
        warnings = []

        prerequisites = self._get_prerequisites(stage)
        data = state.get("data", {})

        for req in prerequisites:
            if req not in data:
                errors.append(f"Missing prerequisite: {req}")
            elif not data[req]:
                warnings.append(f"Empty prerequisite: {req}")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def validate_outputs(
        self,
        stage: str,
        outputs: Dict[str, Any],
    ) -> ValidationResult:
        """
        Validate stage outputs.

        Args:
            stage: Stage name
            outputs: Output dictionary

        Returns:
            ValidationResult
        """
        errors = []
        warnings = []

        expected_outputs = self._get_expected_outputs(stage)

        for expected in expected_outputs:
            if expected not in outputs:
                errors.append(f"Missing output: {expected}")
            elif not outputs[expected]:
                warnings.append(f"Empty output: {expected}")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def _get_prerequisites(self, stage: str) -> List[str]:
        """Get list of required prerequisites for a stage."""
        prerequisites_map = {
            "search_databases": ["all_papers"],
            "deduplication": ["all_papers"],
            "title_abstract_screening": ["unique_papers"],
            "fulltext_screening": ["screened_papers", "title_abstract_results"],
            "data_extraction": ["eligible_papers", "fulltext_results"],
            "prisma_generation": ["final_papers"],
            "visualization_generation": ["final_papers", "extracted_data"],
            "article_writing": ["extracted_data"],
            "report_generation": ["article_sections"],
        }
        return prerequisites_map.get(stage, [])

    def _get_expected_outputs(self, stage: str) -> List[str]:
        """Get list of expected outputs for a stage."""
        outputs_map = {
            "search_databases": ["all_papers"],
            "deduplication": ["unique_papers"],
            "title_abstract_screening": ["screened_papers", "title_abstract_results"],
            "fulltext_screening": ["eligible_papers", "fulltext_results"],
            "data_extraction": ["extracted_data"],
            "prisma_generation": ["prisma_diagram"],
            "visualization_generation": ["visualizations"],
            "article_writing": ["article_sections"],
            "report_generation": ["final_report"],
        }
        return outputs_map.get(stage, [])


class CitationValidator(StageValidator):
    """Validate citation processing."""

    def validate_citations(
        self,
        article_sections: Dict[str, str],
        papers: List[Dict[str, Any]],
    ) -> ValidationResult:
        """
        Validate citation extraction and formatting.

        Args:
            article_sections: Dictionary of article sections
            papers: List of paper dictionaries

        Returns:
            ValidationResult
        """
        errors = []
        warnings = []

        # Check for citation markers in text
        citation_patterns = ["[Citation", "[citation", "Citation"]
        found_citations = False

        for _section_name, section_text in article_sections.items():
            for pattern in citation_patterns:
                if pattern in section_text:
                    found_citations = True
                    break

        if not found_citations:
            warnings.append("No citation markers found in article sections")

        # Validate citation format (should be [Citation N] or [N])
        import re

        citation_regex = r"\[Citation\s+\d+\]|\[\d+\]"

        for _section_name, section_text in article_sections.items():
            citations = re.findall(citation_regex, section_text)
            if citations:
                # Check if citation numbers are valid
                for citation in citations:
                    # Extract number
                    num_match = re.search(r"\d+", citation)
                    if num_match:
                        num = int(num_match.group())
                        if num > len(papers):
                            errors.append(
                                f"Citation [{num}] exceeds number of papers ({len(papers)})"
                            )

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )


class ChartValidator(StageValidator):
    """Validate chart generation."""

    def validate_charts(
        self,
        chart_paths: Dict[str, str],
        papers: List[Dict[str, Any]],
    ) -> ValidationResult:
        """
        Validate chart generation.

        Args:
            chart_paths: Dictionary mapping chart names to file paths
            papers: List of paper dictionaries

        Returns:
            ValidationResult
        """
        errors = []
        warnings = []

        expected_charts = ["papers_by_country", "papers_by_subject", "network_graph"]

        for chart_name in expected_charts:
            if chart_name not in chart_paths:
                warnings.append(f"Missing chart: {chart_name}")
            else:
                chart_path = Path(chart_paths[chart_name])
                if not chart_path.exists():
                    errors.append(f"Chart file not found: {chart_path}")
                elif chart_path.stat().st_size == 0:
                    errors.append(f"Chart file is empty: {chart_path}")

        # Validate data availability for charts
        if papers:
            countries = sum(1 for p in papers if p.get("country"))
            subjects = sum(1 for p in papers if p.get("subjects"))

            if countries == 0:
                warnings.append("No country data available for country chart")
            if subjects == 0:
                warnings.append("No subject data available for subject chart")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )


class ScreeningValidator(StageValidator):
    """Validate screening decisions."""

    def validate_screening(
        self,
        papers: List[Dict[str, Any]],
        results: List[Dict[str, Any]],
    ) -> ValidationResult:
        """
        Validate screening results.

        Args:
            papers: List of paper dictionaries
            results: List of screening result dictionaries

        Returns:
            ValidationResult
        """
        errors = []
        warnings = []

        if len(papers) != len(results):
            errors.append(f"Mismatch: {len(papers)} papers but {len(results)} screening results")

        # Check for valid decisions
        valid_decisions = ["include", "exclude", "uncertain"]
        for i, result in enumerate(results):
            decision = result.get("decision")
            if decision not in valid_decisions:
                errors.append(f"Invalid decision '{decision}' in result {i}")

            confidence = result.get("confidence", 0.0)
            if not (0.0 <= confidence <= 1.0):
                errors.append(f"Invalid confidence {confidence} in result {i}")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )


class StageValidatorFactory:
    """Factory for creating stage validators."""

    @staticmethod
    def create(stage: str) -> StageValidator:
        """
        Create appropriate validator for stage.

        Args:
            stage: Stage name

        Returns:
            StageValidator instance
        """
        if "citation" in stage.lower() or "report" in stage.lower():
            return CitationValidator()
        elif "visualization" in stage.lower() or "chart" in stage.lower():
            return ChartValidator()
        elif "screening" in stage.lower():
            return ScreeningValidator()
        else:
            return StageValidator()
