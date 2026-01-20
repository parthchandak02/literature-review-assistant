"""
Template generator for quality assessments.

Generates assessment templates that users can fill out manually.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging

from ..extraction.data_extractor_agent import ExtractedData

logger = logging.getLogger(__name__)


class QualityAssessmentTemplateGenerator:
    """Generates quality assessment templates from extracted study data."""

    def __init__(self, risk_of_bias_tool: str = "RoB 2"):
        """
        Initialize template generator.

        Args:
            risk_of_bias_tool: Tool to use for risk of bias assessment
                Options: "RoB 2", "ROBINS-I", "CASP"
        """
        self.risk_of_bias_tool = risk_of_bias_tool

    def generate_template(
        self,
        extracted_data: List[ExtractedData],
        output_path: str,
        grade_outcomes: Optional[List[str]] = None,
    ) -> str:
        """
        Generate quality assessment template file.

        Args:
            extracted_data: List of extracted study data
            output_path: Path to save the template JSON file
            grade_outcomes: List of outcomes to assess with GRADE (if None, will be inferred)

        Returns:
            Path to the generated template file
        """
        template = {
            "risk_of_bias_tool": self.risk_of_bias_tool,
            "studies": [],
            "grade_outcomes": grade_outcomes or [],
        }

        # Generate risk of bias template for each study
        for i, study in enumerate(extracted_data, 1):
            study_id = f"Study_{i}"
            domains = self._get_domains_for_tool(self.risk_of_bias_tool)

            study_template = {
                "study_id": study_id,
                "study_title": study.title,
                "study_design": study.study_design or "Not specified",
                "risk_of_bias": {
                    "tool": self.risk_of_bias_tool,
                    "domains": {domain: "" for domain in domains},
                    "overall": "",
                    "notes": "",
                },
            }
            template["studies"].append(study_template)

        # Generate GRADE template for outcomes
        if not grade_outcomes:
            # Infer outcomes from extracted data
            all_outcomes = set()
            for study in extracted_data:
                all_outcomes.update(study.outcomes)
            grade_outcomes = sorted(list(all_outcomes))[:10]  # Limit to 10 outcomes

        template["grade_outcomes"] = grade_outcomes
        template["grade_assessments"] = [
            {
                "outcome": outcome,
                "certainty": "",
                "downgrade_reasons": [],
                "upgrade_reasons": [],
                "justification": "",
            }
            for outcome in grade_outcomes
        ]

        # Save template
        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path_obj, "w") as f:
            json.dump(template, f, indent=2)

        logger.info(
            f"Generated quality assessment template with {len(extracted_data)} studies "
            f"and {len(grade_outcomes)} GRADE outcomes at {output_path}"
        )

        return str(output_path_obj)

    def _get_domains_for_tool(self, tool: str) -> List[str]:
        """Get domain names for a specific risk of bias tool."""
        domains_map = {
            "RoB 2": [
                "Bias arising from the randomization process",
                "Bias due to deviations from intended interventions",
                "Bias due to missing outcome data",
                "Bias in measurement of the outcome",
                "Bias in selection of the reported result",
            ],
            "ROBINS-I": [
                "Bias due to confounding",
                "Bias due to selection of participants",
                "Bias in classification of interventions",
                "Bias due to deviations from intended interventions",
                "Bias due to missing data",
                "Bias in measurement of outcomes",
                "Bias in selection of the reported result",
            ],
            "CASP": [
                "Clear statement of aims",
                "Appropriate methodology",
                "Appropriate research design",
                "Recruitment strategy",
                "Data collection",
                "Relationship between researcher and participants",
                "Ethical considerations",
                "Data analysis",
                "Clear statement of findings",
                "Value of research",
            ],
        }
        return domains_map.get(tool, domains_map["RoB 2"])
