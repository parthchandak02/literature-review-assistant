"""
Risk of Bias Assessor

Processes risk of bias assessments and generates summary tables and narratives.
"""

import json
import logging
from pathlib import Path
from typing import List

from .quality_assessment_schemas import RiskOfBiasAssessment

logger = logging.getLogger(__name__)


class RiskOfBiasAssessor:
    """Processes risk of bias assessments."""

    def load_assessments(self, template_path: str) -> List[RiskOfBiasAssessment]:
        """
        Load risk of bias assessments from template file.

        Args:
            template_path: Path to assessment template file

        Returns:
            List of risk of bias assessments
        """
        template_path_obj = Path(template_path)
        if not template_path_obj.exists():
            raise FileNotFoundError(f"Assessment file not found: {template_path}")

        with open(template_path_obj) as f:
            data = json.load(f)

        assessments = []
        for study_data in data.get("studies", []):
            rob_data = study_data.get("risk_of_bias", {})
            if rob_data.get("overall"):  # Only include if assessment is complete
                assessment = RiskOfBiasAssessment(
                    study_id=study_data["study_id"],
                    study_title=study_data["study_title"],
                    tool=rob_data.get("tool", "RoB 2"),
                    domains=rob_data.get("domains", {}),
                    overall=rob_data.get("overall", ""),
                    notes=rob_data.get("notes"),
                )
                assessments.append(assessment)

        logger.info(f"Loaded {len(assessments)} risk of bias assessments")
        return assessments

    def generate_summary_table(self, assessments: List[RiskOfBiasAssessment]) -> str:
        """
        Generate markdown summary table of risk of bias assessments.

        Args:
            assessments: List of risk of bias assessments

        Returns:
            Markdown table string
        """
        if not assessments:
            return "No risk of bias assessments available."

        # Get all unique domains across assessments
        all_domains = set()
        for assessment in assessments:
            all_domains.update(assessment.domains.keys())

        domains = sorted(all_domains)

        # Build table header
        header = "| Study ID | Study Title"
        for domain in domains:
            # Shorten domain names for table
            short_domain = domain.split(" ")[:3]  # First 3 words
            header += f" | {' '.join(short_domain)}"
        header += " | Overall |\n"

        # Build separator
        separator = "|" + "|".join(["---"] * (len(domains) + 3)) + "|\n"

        # Build rows
        rows = []
        for assessment in assessments:
            row = f"| {assessment.study_id} | {assessment.study_title[:50]}"
            for domain in domains:
                rating = assessment.domains.get(domain, "N/A")
                # Add color coding symbols
                if rating == "Low":
                    symbol = "Low"
                elif rating == "Some concerns":
                    symbol = "Some concerns"
                elif rating == "High":
                    symbol = "High"
                elif rating == "Critical":
                    symbol = "Critical"
                else:
                    symbol = "N/A"
                row += f" | {symbol}"
            row += f" | {assessment.overall} |\n"
            rows.append(row)

        table = header + separator + "".join(rows)
        return table

    def generate_narrative_summary(
        self, assessments: List[RiskOfBiasAssessment], word_target: int = 200
    ) -> str:
        """
        Generate narrative summary of risk of bias assessments.

        Args:
            assessments: List of risk of bias assessments
            word_target: Target word count for summary

        Returns:
            Narrative summary text
        """
        if not assessments:
            return "No risk of bias assessments were conducted."

        # Count ratings
        overall_counts = {"Low": 0, "Some concerns": 0, "High": 0, "Critical": 0}
        for assessment in assessments:
            overall = assessment.overall
            if overall in overall_counts:
                overall_counts[overall] += 1

        total_studies = len(assessments)
        tool = assessments[0].tool if assessments else "RoB 2"

        # Build narrative
        narrative = f"Risk of bias was assessed using the {tool} tool for {total_studies} included studies. "

        # Describe overall ratings
        rating_descriptions = []
        if overall_counts["Low"] > 0:
            rating_descriptions.append(
                f"{overall_counts['Low']} study{'ies' if overall_counts['Low'] > 1 else ''} "
                f"had low risk of bias"
            )
        if overall_counts["Some concerns"] > 0:
            rating_descriptions.append(
                f"{overall_counts['Some concerns']} study{'ies' if overall_counts['Some concerns'] > 1 else ''} "
                f"had some concerns"
            )
        if overall_counts["High"] > 0:
            rating_descriptions.append(
                f"{overall_counts['High']} study{'ies' if overall_counts['High'] > 1 else ''} "
                f"had high risk of bias"
            )
        if overall_counts["Critical"] > 0:
            rating_descriptions.append(
                f"{overall_counts['Critical']} study{'ies' if overall_counts['Critical'] > 1 else ''} "
                f"had critical risk of bias"
            )

        if rating_descriptions:
            narrative += "Overall, " + ", ".join(rating_descriptions) + ". "

        # Describe domain-specific concerns
        domain_concerns = {}
        for assessment in assessments:
            for domain, rating in assessment.domains.items():
                if rating in ["Some concerns", "High", "Critical"]:
                    if domain not in domain_concerns:
                        domain_concerns[domain] = []
                    domain_concerns[domain].append(assessment.study_id)

        if domain_concerns:
            narrative += "Common concerns were identified in the following domains: "
            concern_descriptions = []
            for domain, study_ids in list(domain_concerns.items())[:3]:  # Limit to 3 domains
                short_domain = domain.split(" ")[:3]  # First 3 words
                concern_descriptions.append(f"{' '.join(short_domain)} ({len(study_ids)} studies)")
            narrative += ", ".join(concern_descriptions) + ". "

        # Ensure word count is approximately correct
        words = narrative.split()
        if len(words) > word_target:
            # Truncate if too long
            narrative = " ".join(words[:word_target]) + "..."
        elif len(words) < word_target * 0.7:
            # Add more detail if too short
            narrative += "Further details are provided in the risk of bias table above."

        return narrative
