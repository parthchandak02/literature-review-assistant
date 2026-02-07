"""
PRISMA 2020 Compliance Validator

Validates generated reports against PRISMA 2020 checklist (27 items + 12 abstract elements).
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class PRISMAValidator:
    """Validates systematic review reports against PRISMA 2020 checklist."""

    def __init__(self):
        """Initialize PRISMA validator."""
        self.prisma_2020_items = self._load_prisma_checklist()
        self.abstract_items = self._load_abstract_checklist()

    def _load_prisma_checklist(self) -> Dict[str, Dict[str, Any]]:
        """Load PRISMA 2020 checklist items."""
        return {
            "title": {
                "item": 1,
                "description": "Identify the report as a systematic review",
                "section": "Title",
            },
            "abstract": {
                "item": 2,
                "description": "See PRISMA 2020 for Abstracts checklist",
                "section": "Abstract",
            },
            "rationale": {
                "item": 3,
                "description": "Describe the rationale for the review",
                "section": "Introduction",
            },
            "objectives": {
                "item": 4,
                "description": "Provide explicit statement of objectives",
                "section": "Introduction",
            },
            "eligibility_criteria": {
                "item": 5,
                "description": "Specify inclusion and exclusion criteria",
                "section": "Methods",
            },
            "information_sources": {
                "item": 6,
                "description": "Specify all databases and sources searched",
                "section": "Methods",
            },
            "search_strategy": {
                "item": 7,
                "description": "Present full search strategies",
                "section": "Methods",
            },
            "selection_process": {
                "item": 8,
                "description": "Specify methods for study selection",
                "section": "Methods",
            },
            "data_collection": {
                "item": 9,
                "description": "Specify methods for data collection",
                "section": "Methods",
            },
            "data_items": {
                "item": 10,
                "description": "List and define outcomes and variables",
                "section": "Methods",
            },
            "risk_of_bias_methods": {
                "item": 11,
                "description": "Specify methods for risk of bias assessment",
                "section": "Methods",
            },
            "effect_measures": {
                "item": 12,
                "description": "Specify effect measures",
                "section": "Methods",
            },
            "synthesis_methods": {
                "item": 13,
                "description": "Describe synthesis methods",
                "section": "Methods",
            },
            "reporting_bias": {
                "item": 14,
                "description": "Describe methods for assessing reporting bias",
                "section": "Methods",
            },
            "certainty_assessment": {
                "item": 15,
                "description": "Describe methods for assessing certainty",
                "section": "Methods",
            },
            "study_selection": {
                "item": 16,
                "description": "Describe results of search and selection",
                "section": "Results",
            },
            "study_characteristics": {
                "item": 17,
                "description": "Cite each included study and present characteristics",
                "section": "Results",
            },
            "risk_of_bias_results": {
                "item": 18,
                "description": "Present risk of bias assessments",
                "section": "Results",
            },
            "results_individual": {
                "item": 19,
                "description": "Present results for each study",
                "section": "Results",
            },
            "results_synthesis": {
                "item": 20,
                "description": "Present results of syntheses",
                "section": "Results",
            },
            "reporting_biases": {
                "item": 21,
                "description": "Present assessments of reporting biases",
                "section": "Results",
            },
            "certainty_evidence": {
                "item": 22,
                "description": "Present assessments of certainty",
                "section": "Results",
            },
            "discussion_summary": {
                "item": 23,
                "description": "Provide general interpretation",
                "section": "Discussion",
            },
            "protocol_registration": {
                "item": 24,
                "description": "Provide registration information",
                "section": "Other",
            },
            "funding": {
                "item": 25,
                "description": "Describe sources of support",
                "section": "Other",
            },
            "competing_interests": {
                "item": 26,
                "description": "Declare competing interests",
                "section": "Other",
            },
            "data_availability": {
                "item": 27,
                "description": "Report data availability",
                "section": "Other",
            },
        }

    def _load_abstract_checklist(self) -> Dict[str, Dict[str, Any]]:
        """Load PRISMA 2020 for Abstracts checklist items."""
        return {
            "title": {
                "item": 1,
                "description": "Identify as systematic review",
                "section": "Title",
            },
            "background": {
                "item": 2,
                "description": "Background",
                "section": "Abstract",
            },
            "objectives": {
                "item": 2,
                "description": "Objectives",
                "section": "Abstract",
            },
            "eligibility": {
                "item": 2,
                "description": "Eligibility criteria",
                "section": "Abstract",
            },
            "sources": {
                "item": 2,
                "description": "Information sources",
                "section": "Abstract",
            },
            "risk_of_bias": {
                "item": 2,
                "description": "Risk of bias",
                "section": "Abstract",
            },
            "synthesis": {
                "item": 2,
                "description": "Synthesis methods",
                "section": "Abstract",
            },
            "results": {
                "item": 2,
                "description": "Results",
                "section": "Abstract",
            },
            "limitations": {
                "item": 2,
                "description": "Limitations",
                "section": "Abstract",
            },
            "interpretation": {
                "item": 2,
                "description": "Interpretation",
                "section": "Abstract",
            },
            "funding": {
                "item": 2,
                "description": "Funding",
                "section": "Abstract",
            },
            "registration": {
                "item": 2,
                "description": "Registration",
                "section": "Abstract",
            },
        }

    def validate_report(self, report_path: str) -> Dict[str, Any]:
        """
        Validate report against PRISMA 2020 checklist.

        Args:
            report_path: Path to markdown report file

        Returns:
            Validation results dictionary
        """
        report_path_obj = Path(report_path)
        if not report_path_obj.exists():
            raise FileNotFoundError(f"Report file not found: {report_path}")

        with open(report_path_obj, encoding="utf-8") as f:
            report_content = f.read()

        results = {
            "report_path": str(report_path),
            "prisma_items": {},
            "abstract_items": {},
            "missing_items": [],
            "compliance_score": 0.0,
        }

        # Validate PRISMA 2020 items
        for key, item_info in self.prisma_2020_items.items():
            item_num = item_info["item"]
            description = item_info["description"]
            section = item_info["section"]

            is_present = self._check_item_presence(report_content, key, description, section)
            results["prisma_items"][f"Item_{item_num}"] = {
                "present": is_present,
                "description": description,
                "section": section,
            }

            if not is_present:
                results["missing_items"].append(f"Item {item_num}: {description} ({section})")

        # Validate abstract items
        abstract_section = self._extract_abstract(report_content)
        if abstract_section:
            for key, item_info in self.abstract_items.items():
                description = item_info["description"]
                is_present = self._check_abstract_element(abstract_section, key, description)
                results["abstract_items"][key] = {
                    "present": is_present,
                    "description": description,
                }

                if not is_present:
                    results["missing_items"].append(f"Abstract {key}: {description}")
        else:
            results["missing_items"].append("Abstract section not found")

        # Calculate compliance score
        total_items = len(self.prisma_2020_items) + len(self.abstract_items)
        present_items = sum(
            1 for item in results["prisma_items"].values() if item["present"]
        ) + sum(1 for item in results["abstract_items"].values() if item["present"])
        results["compliance_score"] = present_items / total_items if total_items > 0 else 0.0

        return results

    def _check_item_presence(self, content: str, key: str, description: str, section: str) -> bool:
        """Check if a PRISMA item is present in the report."""
        # Check for section presence
        section_patterns = {
            "Title": [r"#\s+.*[Ss]ystematic\s+[Rr]eview"],
            "Abstract": [r"##\s+Abstract", r"#\s+Abstract"],
            "Introduction": [r"##\s+Introduction", r"#\s+Introduction"],
            "Methods": [r"##\s+Methods", r"#\s+Methods"],
            "Results": [r"##\s+Results", r"#\s+Results"],
            "Discussion": [r"##\s+Discussion", r"#\s+Discussion"],
            "Other": [r"##\s+(Funding|Conflicts|Data Availability|Registration)"],
        }

        # Check section-specific content
        if key == "title":
            # Check for topic-specific title format: "[Topic]: A Systematic Review"
            # Should NOT be generic "Systematic Review Report"
            title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            if title_match:
                title = title_match.group(1)
                has_systematic_review = bool(
                    re.search(r"systematic\s+review", title, re.IGNORECASE)
                )
                is_not_generic = not title.lower().startswith("systematic review report")
                return has_systematic_review and is_not_generic
            return bool(re.search(r"systematic\s+review", content, re.IGNORECASE))
        elif key == "abstract":
            return bool(re.search(r"##\s+Abstract", content, re.IGNORECASE))
        elif key == "objectives":
            return bool(
                re.search(r"objectives?|objectives?\s+of\s+this\s+review", content, re.IGNORECASE)
            )
        elif key == "eligibility_criteria":
            return bool(
                re.search(
                    r"inclusion|exclusion|eligibility\s+criteria|PICOS", content, re.IGNORECASE
                )
            )
        elif key == "information_sources":
            return bool(
                re.search(r"database|PubMed|Scopus|search\s+sources?", content, re.IGNORECASE)
            )
        elif key == "search_strategy":
            return bool(re.search(r"search\s+strategy|search\s+query", content, re.IGNORECASE))
        elif key == "study_characteristics":
            return bool(
                re.search(
                    r"study\s+characteristics|characteristics\s+of\s+included\s+studies|table",
                    content,
                    re.IGNORECASE,
                )
            )
        elif key == "study_selection":
            # Check for Study Selection subsection in Results section
            # Also verify PRISMA diagram is in Results (not separate section)
            results_match = re.search(
                r"##\s+Results\s+(.*?)(?=##\s+|\Z)", content, re.DOTALL | re.IGNORECASE
            )
            if results_match:
                results_section = results_match.group(1)
                has_study_selection = bool(
                    re.search(
                        r"###\s+Study\s+Selection|study\s+selection", results_section, re.IGNORECASE
                    )
                )
                # Check PRISMA diagram is in Results (not separate section)
                prisma_in_results = bool(
                    re.search(
                        r"PRISMA|prisma.*diagram|Figure\s+1.*PRISMA",
                        results_section,
                        re.IGNORECASE,
                    )
                )
                # Check that PRISMA is NOT a separate section
                separate_prisma_section = bool(
                    re.search(r"##\s+PRISMA|##\s+.*Flow\s+Diagram", content, re.IGNORECASE)
                )
                return has_study_selection and prisma_in_results and not separate_prisma_section
            # Fallback to general check
            return bool(
                re.search(
                    r"study\s+selection|prisma\s+flow|flow\s+diagram",
                    content,
                    re.IGNORECASE,
                )
            )
        elif key == "results_synthesis":
            # Check for Results of Syntheses subsection in Results section
            # Also verify visualizations are in Results (not separate section)
            # Handle both 3-level (###) and 4-level (####) headers
            results_match = re.search(
                r"##\s+Results\s+(.*?)(?=##\s+|\Z)", content, re.DOTALL | re.IGNORECASE
            )
            if results_match:
                results_section = results_match.group(1)
                has_synthesis = bool(
                    re.search(
                        r"(?:###|####)\s+(Results\s+of\s+)?Synthesis|synthesis\s+of\s+(?:findings|results)",
                        results_section,
                        re.IGNORECASE,
                    )
                )
                # Check visualizations are in Results (not separate section)
                # Look for Figure 2+ references
                has_visualizations = bool(
                    re.search(r"Figure\s+[2-9]|Figure\s+\d{2,}", results_section, re.IGNORECASE)
                )
                # Check that Visualizations is NOT a separate section
                separate_viz_section = bool(
                    re.search(r"##\s+Visualizations|##\s+.*Visualization", content, re.IGNORECASE)
                )
                return has_synthesis and (has_visualizations or not separate_viz_section)
            # Fallback to general check
            return bool(
                re.search(
                    r"synthesis|meta-analysis|results\s+of\s+syntheses",
                    content,
                    re.IGNORECASE,
                )
            )
        elif key == "risk_of_bias_results":
            return bool(
                re.search(
                    r"risk\s+of\s+bias|quality\s+assessment|methodological\s+quality",
                    content,
                    re.IGNORECASE,
                )
            )
        elif key == "certainty_evidence":
            return bool(
                re.search(r"GRADE|certainty|confidence\s+in\s+evidence", content, re.IGNORECASE)
            )
        elif key == "reporting_bias":
            # Check for Reporting Bias Assessment in Methods section
            methods_match = re.search(
                r"##\s+Methods\s+(.*?)(?=##\s+|\Z)", content, re.DOTALL | re.IGNORECASE
            )
            if methods_match:
                methods_section = methods_match.group(1)
                return bool(
                    re.search(
                        r"reporting\s+bias|publication\s+bias|selective\s+outcome\s+reporting",
                        methods_section,
                        re.IGNORECASE,
                    )
                )
            return False
        elif key == "reporting_biases":
            # Check for Reporting Biases subsection in Results section
            # Handle both 3-level (###) and 4-level (####) headers
            results_match = re.search(
                r"##\s+Results\s+(.*?)(?=##\s+|\Z)", content, re.DOTALL | re.IGNORECASE
            )
            if results_match:
                results_section = results_match.group(1)
                # Check for subsection header at both 3-level and 4-level
                has_subsection = bool(
                    re.search(r"(?:###|####)\s+Reporting\s+Biases", results_section, re.IGNORECASE)
                )
                has_content = bool(
                    re.search(
                        r"reporting\s+biases|publication\s+bias|selective\s+outcome",
                        results_section,
                        re.IGNORECASE,
                    )
                )
                return has_subsection or has_content
            return False
        elif key == "protocol_registration":
            # Check for Registration section (enhanced structure)
            registration_section = bool(re.search(r"##\s+Registration", content, re.IGNORECASE))
            if registration_section:
                return True
            # Fallback to general registration check
            return bool(
                re.search(r"PROSPERO|registration|protocol\s+registered", content, re.IGNORECASE)
            )
        elif key == "funding":
            return bool(re.search(r"funding|financial\s+support", content, re.IGNORECASE))
        elif key == "data_availability":
            return bool(
                re.search(r"data\s+availability|supplementary\s+materials", content, re.IGNORECASE)
            )

        # Generic check for section presence
        if section in section_patterns:
            for pattern in section_patterns[section]:
                if re.search(pattern, content, re.IGNORECASE):
                    return True

        return False

    def _extract_abstract(self, content: str) -> Optional[str]:
        """Extract abstract section from report."""
        abstract_match = re.search(
            r"##\s+Abstract\s+(.*?)(?=##\s+|\Z)", content, re.DOTALL | re.IGNORECASE
        )
        if abstract_match:
            return abstract_match.group(1)
        return None

    def _check_abstract_element(self, abstract: str, key: str, description: str) -> bool:
        """Check if abstract element is present."""
        key_patterns = {
            "background": [r"background", r"context", r"rationale"],
            "objectives": [r"objectives?", r"aims?"],
            "eligibility": [r"eligibility|inclusion|exclusion"],
            "sources": [r"sources?|databases?", r"searched"],
            "risk_of_bias": [r"risk\s+of\s+bias", r"quality"],
            "synthesis": [r"synthesis|meta-analysis"],
            "results": [r"results?|findings?"],
            "limitations": [r"limitations?"],
            "interpretation": [r"interpretation|conclusions?"],
            "funding": [r"funding"],
            "registration": [r"registration|PROSPERO"],
        }

        if key in key_patterns:
            for pattern in key_patterns[key]:
                if re.search(pattern, abstract, re.IGNORECASE):
                    return True

        return False

    def generate_validation_report(
        self, validation_results: Dict[str, Any], output_path: Optional[str] = None
    ) -> str:
        """
        Generate JSON validation report.

        Args:
            validation_results: Results from validate_report()
            output_path: Optional output path for JSON file

        Returns:
            Path to saved validation report
        """
        if not output_path:
            report_path = validation_results["report_path"]
            output_path = str(Path(report_path).parent / "prisma_validation_report.json")

        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path_obj, "w") as f:
            json.dump(validation_results, f, indent=2)

        logger.info(f"Validation report saved to {output_path_obj}")
        return str(output_path_obj)


def main():
    """CLI entry point for validation."""
    import argparse

    parser = argparse.ArgumentParser(description="Validate PRISMA 2020 compliance")
    parser.add_argument("--report", type=str, required=True, help="Path to markdown report file")
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output path for validation report JSON",
    )

    args = parser.parse_args()

    validator = PRISMAValidator()
    results = validator.validate_report(args.report)

    print("=" * 60)
    print("PRISMA 2020 Compliance Validation")
    print("=" * 60)
    print(f"\nReport: {results['report_path']}")
    print(f"Compliance Score: {results['compliance_score']:.1%}")
    print(f"\nMissing Items: {len(results['missing_items'])}")

    if results["missing_items"]:
        print("\nMissing PRISMA Items:")
        for item in results["missing_items"]:
            print(f"  - {item}")
    else:
        print("\nAll PRISMA 2020 items are present!")

    # Generate validation report
    report_path = validator.generate_validation_report(results, args.output)
    print(f"\nValidation report saved to: {report_path}")


if __name__ == "__main__":
    main()
