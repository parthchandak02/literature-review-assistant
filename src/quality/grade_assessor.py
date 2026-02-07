"""
GRADE Assessor

Processes GRADE assessments and generates evidence profile tables and narratives.
"""

import json
from pathlib import Path
from typing import List
import logging

from .quality_assessment_schemas import GRADEAssessment

logger = logging.getLogger(__name__)


class GRADEAssessor:
    """Processes GRADE assessments."""

    def load_assessments(self, template_path: str) -> List[GRADEAssessment]:
        """
        Load GRADE assessments from template file.

        Args:
            template_path: Path to assessment template file

        Returns:
            List of GRADE assessments
        """
        template_path_obj = Path(template_path)
        if not template_path_obj.exists():
            raise FileNotFoundError(f"Assessment file not found: {template_path}")

        with open(template_path_obj, "r") as f:
            data = json.load(f)

        assessments = []
        for grade_data in data.get("grade_assessments", []):
            if grade_data.get("certainty"):  # Only include if assessment is complete
                assessment = GRADEAssessment(
                    outcome=grade_data["outcome"],
                    certainty=grade_data.get("certainty", ""),
                    downgrade_reasons=grade_data.get("downgrade_reasons", []),
                    upgrade_reasons=grade_data.get("upgrade_reasons", []),
                    justification=grade_data.get("justification"),
                )
                assessments.append(assessment)

        logger.info(f"Loaded {len(assessments)} GRADE assessments")
        return assessments

    def generate_evidence_profile_table(self, assessments: List[GRADEAssessment]) -> str:
        """
        Generate markdown evidence profile table for GRADE assessments.

        Args:
            assessments: List of GRADE assessments

        Returns:
            Markdown table string
        """
        if not assessments:
            return "No GRADE assessments available."

        # Build table
        header = "| Outcome | Certainty | Downgrade Reasons | Upgrade Reasons |\n"
        separator = "|" + "|".join(["---"] * 4) + "|\n"

        rows = []
        for assessment in assessments:
            downgrade_str = "; ".join(assessment.downgrade_reasons[:3])  # Limit to 3
            if len(assessment.downgrade_reasons) > 3:
                downgrade_str += "..."
            if not downgrade_str:
                downgrade_str = "None"

            upgrade_str = "; ".join(assessment.upgrade_reasons[:3])  # Limit to 3
            if len(assessment.upgrade_reasons) > 3:
                upgrade_str += "..."
            if not upgrade_str:
                upgrade_str = "None"

            row = (
                f"| {assessment.outcome} | {assessment.certainty} | "
                f"{downgrade_str} | {upgrade_str} |\n"
            )
            rows.append(row)

        table = header + separator + "".join(rows)
        return table

    def generate_narrative_summary(self, assessments: List[GRADEAssessment]) -> str:
        """
        Generate narrative summary of GRADE assessments.

        Args:
            assessments: List of GRADE assessments

        Returns:
            Narrative summary text
        """
        if not assessments:
            return "No GRADE assessments were conducted."

        # Count certainty levels
        certainty_counts = {
            "High": 0,
            "Moderate": 0,
            "Low": 0,
            "Very Low": 0,
        }
        for assessment in assessments:
            certainty = assessment.certainty
            if certainty in certainty_counts:
                certainty_counts[certainty] += 1

        total_outcomes = len(assessments)

        # Build narrative
        narrative = f"GRADE assessment was conducted for {total_outcomes} critical outcomes. "

        # Describe certainty distribution
        certainty_descriptions = []
        if certainty_counts["High"] > 0:
            certainty_descriptions.append(
                f"{certainty_counts['High']} outcome{'s' if certainty_counts['High'] > 1 else ''} "
                f"had high certainty"
            )
        if certainty_counts["Moderate"] > 0:
            certainty_descriptions.append(
                f"{certainty_counts['Moderate']} outcome{'s' if certainty_counts['Moderate'] > 1 else ''} "
                f"had moderate certainty"
            )
        if certainty_counts["Low"] > 0:
            certainty_descriptions.append(
                f"{certainty_counts['Low']} outcome{'s' if certainty_counts['Low'] > 1 else ''} "
                f"had low certainty"
            )
        if certainty_counts["Very Low"] > 0:
            certainty_descriptions.append(
                f"{certainty_counts['Very Low']} outcome{'s' if certainty_counts['Very Low'] > 1 else ''} "
                f"had very low certainty"
            )

        if certainty_descriptions:
            narrative += "Overall, " + ", ".join(certainty_descriptions) + ". "

        # Describe common downgrade reasons
        downgrade_reasons = {}
        for assessment in assessments:
            for reason in assessment.downgrade_reasons:
                if reason not in downgrade_reasons:
                    downgrade_reasons[reason] = 0
                downgrade_reasons[reason] += 1

        if downgrade_reasons:
            top_reasons = sorted(downgrade_reasons.items(), key=lambda x: x[1], reverse=True)[:3]
            narrative += (
                "Common reasons for downgrading certainty included: "
                + ", ".join([f"{reason} ({count} outcomes)" for reason, count in top_reasons])
                + ". "
            )

        return narrative
