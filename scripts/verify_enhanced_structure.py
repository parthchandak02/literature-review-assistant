#!/usr/bin/env python3
"""
[Utility Script] Enhanced Structure Verification

Tests that the enhanced code produces the expected structure without running full workflow.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EnhancedStructureVerifier:
    """Verifies enhanced output structure matches expected plan."""

    def __init__(self):
        """Initialize verifier."""
        self.checks = []

    def verify_report_structure(self, report_path: str) -> Dict[str, any]:
        """
        Verify report structure matches enhanced plan.

        Args:
            report_path: Path to markdown report file

        Returns:
            Verification results dictionary
        """
        report_path_obj = Path(report_path)
        if not report_path_obj.exists():
            raise FileNotFoundError(f"Report file not found: {report_path}")

        with open(report_path_obj, "r", encoding="utf-8") as f:
            content = f.read()

        results = {
            "report_path": str(report_path),
            "checks": {},
            "structure": {},
            "all_passed": True,
        }

        # Check 1: Topic-specific title (not generic "Systematic Review Report")
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if title_match:
            title = title_match.group(1)
            has_topic_specific = not title.lower().startswith("systematic review report")
            has_systematic_review = "systematic review" in title.lower()
            results["checks"]["topic_specific_title"] = {
                "passed": has_topic_specific and has_systematic_review,
                "title": title,
                "expected": "Topic-specific title with 'Systematic Review'",
            }
        else:
            results["checks"]["topic_specific_title"] = {
                "passed": False,
                "title": None,
                "expected": "Topic-specific title with 'Systematic Review'",
            }

        # Check 2: Abstract section present
        abstract_present = bool(re.search(r"##\s+Abstract", content, re.IGNORECASE))
        results["checks"]["abstract_section"] = {
            "passed": abstract_present,
            "expected": "Abstract section present",
        }

        # Check 3: Keywords section present
        keywords_present = bool(re.search(r"##\s+Keywords", content, re.IGNORECASE))
        results["checks"]["keywords_section"] = {
            "passed": keywords_present,
            "expected": "Keywords section present",
        }

        # Check 4: Introduction section present
        intro_present = bool(re.search(r"##\s+Introduction", content, re.IGNORECASE))
        results["checks"]["introduction_section"] = {
            "passed": intro_present,
            "expected": "Introduction section present",
        }

        # Check 5: Methods section present
        methods_present = bool(re.search(r"##\s+Methods", content, re.IGNORECASE))
        results["checks"]["methods_section"] = {
            "passed": methods_present,
            "expected": "Methods section present",
        }

        # Check 6: Results section present
        results_present = bool(re.search(r"##\s+Results", content, re.IGNORECASE))
        results["checks"]["results_section"] = {
            "passed": results_present,
            "expected": "Results section present",
        }

        # Check 7: PRISMA diagram in Results section (not separate section)
        if results_present:
            results_section_match = re.search(
                r"##\s+Results\s+(.*?)(?=##\s+|\Z)", content, re.DOTALL | re.IGNORECASE
            )
            if results_section_match:
                results_section = results_section_match.group(1)
                prisma_in_results = bool(
                    re.search(
                        r"PRISMA|prisma.*diagram|Figure\s+1.*PRISMA",
                        results_section,
                        re.IGNORECASE,
                    )
                )
                results["checks"]["prisma_in_results"] = {
                    "passed": prisma_in_results,
                    "expected": "PRISMA diagram referenced in Results section",
                }
            else:
                results["checks"]["prisma_in_results"] = {
                    "passed": False,
                    "expected": "PRISMA diagram referenced in Results section",
                }
        else:
            results["checks"]["prisma_in_results"] = {
                "passed": False,
                "expected": "PRISMA diagram referenced in Results section",
            }

        # Check 8: Visualizations in Results section (not separate section)
        # Visualizations must appear BEFORE the --- separator that marks end of Results section
        if results_present:
            results_section_match = re.search(
                r"##\s+Results\s+(.*?)(?=##\s+|\Z)", content, re.DOTALL | re.IGNORECASE
            )
            if results_section_match:
                results_section = results_section_match.group(1)
                # Check for figure references (Figure 2, Figure 3, etc.)
                has_figures = bool(
                    re.search(r"Figure\s+[2-9]|Figure\s+\d{2,}", results_section, re.IGNORECASE)
                )
                # Verify visualizations appear before separator (if separator exists in Results section)
                separator_pos = results_section.find("\n---\n")
                if separator_pos != -1:
                    # Check if figures appear before separator
                    figures_before_separator = bool(
                        re.search(r"Figure\s+[2-9]|Figure\s+\d{2,}", results_section[:separator_pos], re.IGNORECASE)
                    )
                    results["checks"]["visualizations_in_results"] = {
                        "passed": has_figures and figures_before_separator,
                        "expected": "Visualizations (figures) referenced in Results section before separator",
                    }
                else:
                    # No separator found in Results section, just check for figures
                    results["checks"]["visualizations_in_results"] = {
                        "passed": has_figures,
                        "expected": "Visualizations (figures) referenced in Results section",
                    }
            else:
                results["checks"]["visualizations_in_results"] = {
                    "passed": False,
                    "expected": "Visualizations (figures) referenced in Results section",
                }
        else:
            results["checks"]["visualizations_in_results"] = {
                "passed": False,
                "expected": "Visualizations (figures) referenced in Results section",
            }

        # Check 9: Discussion section present
        discussion_present = bool(re.search(r"##\s+Discussion", content, re.IGNORECASE))
        results["checks"]["discussion_section"] = {
            "passed": discussion_present,
            "expected": "Discussion section present",
        }

        # Check 10: References section present
        references_present = bool(
            re.search(r"##\s+References|##\s+Reference", content, re.IGNORECASE)
        )
        results["checks"]["references_section"] = {
            "passed": references_present,
            "expected": "References section present",
        }

        # Check 11: Registration section present (in Other Information)
        registration_present = bool(re.search(r"##\s+Registration", content, re.IGNORECASE))
        results["checks"]["registration_section"] = {
            "passed": registration_present,
            "expected": "Registration section present",
        }

        # Check 12: Funding section present
        funding_present = bool(re.search(r"##\s+Funding", content, re.IGNORECASE))
        results["checks"]["funding_section"] = {
            "passed": funding_present,
            "expected": "Funding section present",
        }

        # Check 13: Conflicts of Interest section present
        coi_present = bool(
            re.search(r"##\s+Conflicts\s+of\s+Interest|##\s+Conflict", content, re.IGNORECASE)
        )
        results["checks"]["conflicts_section"] = {
            "passed": coi_present,
            "expected": "Conflicts of Interest section present",
        }

        # Check 14: NO Summary section (should be removed)
        summary_present = bool(re.search(r"##\s+Summary", content, re.IGNORECASE))
        results["checks"]["no_summary_section"] = {
            "passed": not summary_present,
            "expected": "No Summary section (should be removed)",
            "found": summary_present,
        }

        # Check 15: Methods subsections
        if methods_present:
            methods_section_match = re.search(
                r"##\s+Methods\s+(.*?)(?=##\s+|\Z)", content, re.DOTALL | re.IGNORECASE
            )
            if methods_section_match:
                methods_section = methods_section_match.group(1)
                # Check for Reporting Bias Assessment
                reporting_bias_methods = bool(
                    re.search(
                        r"reporting\s+bias|publication\s+bias|selective\s+outcome",
                        methods_section,
                        re.IGNORECASE,
                    )
                )
                results["checks"]["reporting_bias_methods"] = {
                    "passed": reporting_bias_methods,
                    "expected": "Reporting Bias Assessment in Methods section",
                }
            else:
                results["checks"]["reporting_bias_methods"] = {
                    "passed": False,
                    "expected": "Reporting Bias Assessment in Methods section",
                }
        else:
            results["checks"]["reporting_bias_methods"] = {
                "passed": False,
                "expected": "Reporting Bias Assessment in Methods section",
            }

        # Check 16: Results subsections - Reporting Biases
        # Handle both 3-level (###) and 4-level (####) headers
        if results_present:
            results_section_match = re.search(
                r"##\s+Results\s+(.*?)(?=##\s+|\Z)", content, re.DOTALL | re.IGNORECASE
            )
            if results_section_match:
                results_section = results_section_match.group(1)
                # Check for Reporting Biases subsection at both header levels
                reporting_biases_results = bool(
                    re.search(
                        r"(?:###|####)\s+Reporting\s+Biases|reporting\s+biases|publication\s+bias",
                        results_section,
                        re.IGNORECASE,
                    )
                )
                results["checks"]["reporting_biases_results"] = {
                    "passed": reporting_biases_results,
                    "expected": "Reporting Biases subsection in Results section (3-level or 4-level header)",
                }
            else:
                results["checks"]["reporting_biases_results"] = {
                    "passed": False,
                    "expected": "Reporting Biases subsection in Results section (3-level or 4-level header)",
                }
        else:
            results["checks"]["reporting_biases_results"] = {
                "passed": False,
                "expected": "Reporting Biases subsection in Results section (3-level or 4-level header)",
            }

        # Extract section order
        section_headers = re.findall(r"^##\s+(.+)$", content, re.MULTILINE)
        results["structure"]["section_order"] = section_headers

        # Calculate overall pass rate
        passed_checks = sum(1 for check in results["checks"].values() if check["passed"])
        total_checks = len(results["checks"])
        results["structure"]["pass_rate"] = passed_checks / total_checks if total_checks > 0 else 0.0
        results["all_passed"] = all(check["passed"] for check in results["checks"].values())

        return results

    def generate_verification_report(
        self, verification_results: Dict[str, any], output_path: Optional[str] = None
    ) -> str:
        """
        Generate verification report.

        Args:
            verification_results: Results from verify_report_structure()
            output_path: Optional output path for report file

        Returns:
            Path to saved report
        """
        if not output_path:
            report_path = verification_results["report_path"]
            output_path = str(Path(report_path).parent / "enhanced_structure_verification.txt")

        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path_obj, "w") as f:
            f.write("=" * 70 + "\n")
            f.write("Enhanced Structure Verification Report\n")
            f.write("=" * 70 + "\n\n")
            f.write(f"Report: {verification_results['report_path']}\n")
            f.write(f"Pass Rate: {verification_results['structure']['pass_rate']:.1%}\n")
            f.write(f"All Checks Passed: {verification_results['all_passed']}\n\n")

            f.write("Section Order:\n")
            for i, section in enumerate(verification_results["structure"]["section_order"], 1):
                f.write(f"  {i}. {section}\n")
            f.write("\n")

            f.write("Detailed Checks:\n")
            f.write("-" * 70 + "\n")
            for check_name, check_result in verification_results["checks"].items():
                status = "PASS" if check_result["passed"] else "FAIL"
                f.write(f"{status}: {check_name}\n")
                f.write(f"  Expected: {check_result['expected']}\n")
                if "title" in check_result:
                    f.write(f"  Found: {check_result['title']}\n")
                if "found" in check_result:
                    f.write(f"  Found Summary Section: {check_result['found']}\n")
                f.write("\n")

        logger.info(f"Verification report saved to {output_path_obj}")
        return str(output_path_obj)


def main():
    """CLI entry point for verification."""
    import argparse

    parser = argparse.ArgumentParser(description="Verify enhanced output structure")
    parser.add_argument(
        "--report", type=str, required=True, help="Path to markdown report file"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output path for verification report",
    )

    args = parser.parse_args()

    verifier = EnhancedStructureVerifier()
    results = verifier.verify_report_structure(args.report)

    print("=" * 70)
    print("Enhanced Structure Verification")
    print("=" * 70)
    print(f"\nReport: {results['report_path']}")
    print(f"Pass Rate: {results['structure']['pass_rate']:.1%}")
    print(f"All Checks Passed: {results['all_passed']}\n")

    print("Section Order:")
    for i, section in enumerate(results["structure"]["section_order"], 1):
        print(f"  {i}. {section}")
    print()

    print("Check Results:")
    print("-" * 70)
    for check_name, check_result in results["checks"].items():
        status = "[PASS]" if check_result["passed"] else "[FAIL]"
        print(f"{status} {check_name}: {check_result['expected']}")

    # Generate report
    report_path = verifier.generate_verification_report(results, args.output)
    print(f"\nVerification report saved to: {report_path}")


if __name__ == "__main__":
    main()
