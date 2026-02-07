"""
Template generator for quality assessments using CASP framework.

Generates assessment templates with CASP checklist structure that can be
filled manually or automatically.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..extraction.data_extractor_agent import ExtractedData

logger = logging.getLogger(__name__)


class QualityAssessmentTemplateGenerator:
    """Generates quality assessment templates using CASP framework."""

    def __init__(self, framework: str = "CASP"):
        """
        Initialize template generator.

        Args:
            framework: Assessment framework to use (default: "CASP")
        """
        self.framework = framework

    def generate_template(
        self,
        extracted_data: List[ExtractedData],
        output_path: str,
        grade_outcomes: Optional[List[str]] = None,
        detected_types: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> str:
        """
        Generate quality assessment template file with CASP structure.

        Args:
            extracted_data: List of extracted study data
            output_path: Path to save the template JSON file
            grade_outcomes: List of outcomes to assess with GRADE (if None, will be inferred)
            detected_types: Optional dict mapping study titles to detection results

        Returns:
            Path to the generated template file
        """
        from .casp_prompts import get_checklist_info

        template = {
            "framework": self.framework,
            "studies": [],
            "grade_outcomes": grade_outcomes or [],
        }

        # Generate CASP assessment template for each study
        for i, study in enumerate(extracted_data, 1):
            study_id = f"Study_{i}"

            # Get detected type if available
            detected_type = None
            detection_confidence = None
            detection_reasoning = None

            if detected_types and study.title in detected_types:
                detection = detected_types[study.title]
                detected_type = detection.get("checklist", "casp_cohort")
                detection_confidence = detection.get("confidence", 0.0)
                detection_reasoning = detection.get("reasoning", "")

            # Get checklist info for the detected or default type
            checklist_type = detected_type or "casp_cohort"
            checklist_info = get_checklist_info(checklist_type)
            num_questions = checklist_info.get("num_questions", 10)

            # Build questions template
            questions = {}
            for q_num in range(1, num_questions + 1):
                questions[f"q{q_num}"] = {
                    "answer": "",  # Will be filled with Yes/No/Can't Tell
                    "justification": "",
                }

            study_template = {
                "study_id": study_id,
                "study_title": study.title,
                "study_design": study.study_design or "Not specified",
                "detected_type": detected_type,
                "detection_confidence": detection_confidence,
                "detection_reasoning": detection_reasoning,
                "quality_assessment": {
                    "checklist_used": checklist_type,
                    "questions": questions,
                    "score": {
                        "yes_count": None,
                        "no_count": None,
                        "cant_tell_count": None,
                        "total_questions": num_questions,
                        "quality_rating": "",  # High/Moderate/Low
                    },
                    "overall_notes": "",
                },
            }
            template["studies"].append(study_template)

        # Generate GRADE template for outcomes
        if not grade_outcomes:
            # Infer outcomes from extracted data
            all_outcomes = set()
            for study in extracted_data:
                all_outcomes.update(study.outcomes)
            grade_outcomes = sorted(all_outcomes)[:10]  # Limit to 10 outcomes

        template["grade_outcomes"] = grade_outcomes
        template["grade_assessments"] = [
            {
                "outcome": outcome,
                "certainty": "",  # High/Moderate/Low/Very Low
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
            f"Generated CASP quality assessment template with {len(extracted_data)} studies "
            f"and {len(grade_outcomes)} GRADE outcomes at {output_path}"
        )

        return str(output_path_obj)

    def get_checklist_question_text(self, checklist_type: str, question_num: int) -> str:
        """
        Get the question text for a specific CASP checklist question.

        Args:
            checklist_type: Type of CASP checklist
            question_num: Question number (1-indexed)

        Returns:
            Question text string
        """
        questions_map = {
            "casp_rct": {
                1: "Did the trial address a clearly focused issue?",
                2: "Was the assignment of patients to treatments randomized?",
                3: "Were all patients who entered the trial properly accounted for at its conclusion?",
                4: "Were patients, health workers and study personnel blinded to treatment?",
                5: "Were the groups similar at the start of the trial?",
                6: "Aside from the experimental intervention, were the groups treated equally?",
                7: "How large was the treatment effect?",
                8: "How precise was the estimate of the treatment effect?",
                9: "Can the results be applied to your local population or in your context?",
                10: "Were all clinically important outcomes considered?",
                11: "Are the benefits worth the harms and costs?",
            },
            "casp_cohort": {
                1: "Did the study address a clearly focused issue?",
                2: "Was the cohort recruited in an acceptable way?",
                3: "Was the exposure accurately measured to minimize bias?",
                4: "Was the outcome accurately measured to minimize bias?",
                5: "Have the authors identified all important confounding factors?",
                6: "Have the authors taken account of confounding factors in the design and/or analysis?",
                7: "Was the follow-up of subjects complete enough?",
                8: "Was the follow-up of subjects long enough?",
                9: "What are the results of this study?",
                10: "How precise are the results?",
                11: "Do you believe the results?",
                12: "Can the results be applied to the local population?",
            },
            "casp_qualitative": {
                1: "Was there a clear statement of the aims of the research?",
                2: "Is a qualitative methodology appropriate?",
                3: "Was the research design appropriate to address the aims of the research?",
                4: "Was the recruitment strategy appropriate to the aims of the research?",
                5: "Was the data collected in a way that addressed the research issue?",
                6: "Has the relationship between researcher and participants been adequately considered?",
                7: "Have ethical issues been taken into consideration?",
                8: "Was the data analysis sufficiently rigorous?",
                9: "Is there a clear statement of findings?",
                10: "How valuable is the research?",
            },
        }

        checklist_questions = questions_map.get(checklist_type, {})
        return checklist_questions.get(question_num, f"Question {question_num}")
