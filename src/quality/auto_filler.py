"""
Auto-fill quality assessments using LLM.

This module provides functionality to automatically fill quality assessment
templates using LLM-based assessment.
"""

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config.debug_config import DebugLevel
from ..utils.rich_utils import (
    console,
    print_llm_request_panel,
    print_llm_response_panel,
)

logger = logging.getLogger(__name__)


class QualityAssessmentAutoFiller:
    """Uses LLM to automatically fill quality assessments."""

    def __init__(
        self,
        llm_provider: str = "gemini",
        llm_model: str = "gemini-2.5-pro",
        debug_config: Optional[Any] = None,
    ):
        """
        Initialize with LLM configuration.

        Args:
            llm_provider: LLM provider to use
            llm_model: LLM model to use
            debug_config: Optional debug configuration for verbose output
        """
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.temperature = 0.2
        self.debug_config = debug_config

        # Initialize LLM client
        if llm_provider == "gemini":
            from google import genai
            from google.genai import types

            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY not found in environment")
            # Use 120 second timeout for quality assessment LLM calls
            self.llm_client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(timeout=120_000),  # 120 seconds in milliseconds
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {llm_provider}")

    def _call_llm(self, prompt: str) -> str:
        """
        Call LLM with prompt and show verbose output if enabled.

        Args:
            prompt: Prompt to send to LLM

        Returns:
            LLM response text
        """
        # Enhanced logging with Rich console
        should_show_verbose = self.debug_config and (
            self.debug_config.show_llm_calls or self.debug_config.enabled
        )

        if should_show_verbose:
            prompt_preview = prompt[:200] + "..." if len(prompt) > 200 else prompt
            print_llm_request_panel(
                model=self.llm_model,
                provider=self.llm_provider,
                agent="Quality Assessment Auto-Filler",
                temperature=self.temperature,
                prompt_length=len(prompt),
                prompt_preview=prompt_preview,
            )

        if self.llm_provider == "gemini":
            from google.genai import types

            call_start_time = time.time()
            response = self.llm_client.models.generate_content(
                model=self.llm_model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=self.temperature),
            )
            duration = time.time() - call_start_time
            response_text = response.text if hasattr(response, "text") else ""

            # Track cost (always, not conditional on debug config)
            cost = 0.0
            from ..observability.cost_tracker import (
                LLMCostTracker,
                TokenUsage,
                get_cost_tracker,
            )

            cost_tracker = get_cost_tracker()
            llm_cost_tracker = LLMCostTracker(cost_tracker)

            # Extract usage_metadata from Gemini response
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                usage_metadata = response.usage_metadata
                prompt_tokens = getattr(usage_metadata, "prompt_token_count", 0)
                completion_tokens = getattr(usage_metadata, "candidates_token_count", 0)
                total_tokens = getattr(usage_metadata, "total_token_count", 0)

                # Track cost
                llm_cost_tracker.track_gemini_response(
                    response, self.llm_model, agent_name="Quality Assessment Auto-Filler"
                )

                # Calculate cost for display
                cost = cost_tracker._calculate_cost(
                    "gemini",
                    self.llm_model,
                    TokenUsage(
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens,
                    ),
                )

                # Log per-call cost details
                logger.debug(
                    f"[Quality Assessment Auto-Filler] LLM Call: ${cost:.4f} "
                    f"({total_tokens:,} tokens in {duration:.2f}s)"
                )

            # Enhanced logging with Rich console for response
            if should_show_verbose:
                response_preview = (
                    response_text[:200] + "..." if len(response_text) > 200 else response_text
                )
                print_llm_response_panel(
                    duration=duration,
                    response_preview=response_preview,
                    tokens=None,
                    cost=cost,
                )

            return response_text
        return ""

    def assess_with_casp(
        self, study_title: str, checklist_type: str, extracted_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Assess study quality using CASP checklist.

        Args:
            study_title: Title of the study
            checklist_type: CASP checklist to use ('casp_rct', 'casp_cohort', 'casp_qualitative')
            extracted_data: Extracted study data dictionary

        Returns:
            Dictionary with CASP assessment results including:
                - checklist_used: str
                - responses: Dict with q1, q2, etc.
                - score: Dict with yes_count, quality_rating
                - overall_summary: str
        """
        from .casp_prompts import (
            build_casp_cohort_prompt,
            build_casp_qualitative_prompt,
            build_casp_rct_prompt,
            get_checklist_info,
        )

        # Build appropriate prompt based on checklist type
        if checklist_type == "casp_rct":
            prompt = build_casp_rct_prompt(study_title, extracted_data)
        elif checklist_type == "casp_cohort":
            prompt = build_casp_cohort_prompt(study_title, extracted_data)
        elif checklist_type == "casp_qualitative":
            prompt = build_casp_qualitative_prompt(study_title, extracted_data)
        else:
            logger.error(f"Unknown checklist type: {checklist_type}. Using cohort as fallback.")
            prompt = build_casp_cohort_prompt(study_title, extracted_data)
            checklist_type = "casp_cohort"

        try:
            response = self._call_llm(prompt)

            # Extract JSON from response
            response_clean = re.sub(r"```json\s*|\s*```", "", response).strip()
            json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", response_clean, re.DOTALL)

            if json_match:
                assessment = json.loads(json_match.group())

                # Validate and structure response
                checklist_info = get_checklist_info(checklist_type)
                num_questions = checklist_info.get("num_questions", 10)

                # Extract responses (q1, q2, etc.)
                responses = {}
                yes_count = 0
                no_count = 0
                cant_tell_count = 0

                for i in range(1, num_questions + 1):
                    q_key = f"q{i}"
                    if q_key in assessment:
                        q_data = assessment[q_key]
                        responses[q_key] = q_data

                        # Count responses
                        answer = q_data.get("answer", "Can't Tell")
                        if answer == "Yes":
                            yes_count += 1
                        elif answer == "No":
                            no_count += 1
                        else:
                            cant_tell_count += 1
                    else:
                        # Question missing - use fallback
                        responses[q_key] = {
                            "answer": "Can't Tell",
                            "justification": "Assessment not completed for this question",
                        }
                        cant_tell_count += 1

                # Get or calculate summary
                if "summary" in assessment:
                    summary = assessment["summary"]
                    # Override counts with our calculated ones (more reliable)
                    summary["yes_count"] = yes_count
                    summary["no_count"] = no_count
                    summary["cant_tell_count"] = cant_tell_count
                else:
                    summary = {
                        "yes_count": yes_count,
                        "no_count": no_count,
                        "cant_tell_count": cant_tell_count,
                    }

                # Calculate quality rating based on yes_count
                yes_percentage = yes_count / num_questions
                if yes_percentage >= 0.8:
                    quality_rating = "High"
                elif yes_percentage >= 0.5:
                    quality_rating = "Moderate"
                else:
                    quality_rating = "Low"

                summary["quality_rating"] = summary.get("quality_rating", quality_rating)
                summary["total_questions"] = num_questions

                if "overall_notes" not in summary:
                    summary["overall_notes"] = (
                        f"Automated CASP assessment: {yes_count}/{num_questions} criteria met"
                    )

                return {
                    "checklist_used": checklist_type,
                    "responses": responses,
                    "score": summary,
                    "overall_summary": summary.get("overall_notes", ""),
                }
            else:
                # Fallback: return conservative assessment
                logger.warning(f"Could not parse CASP response for {study_title}, using fallback")
                return self._get_fallback_assessment(
                    checklist_type,
                    num_questions=get_checklist_info(checklist_type).get("num_questions", 10),
                )

        except Exception as e:
            logger.error(f"Error in CASP assessment for {study_title}: {e}")
            logger.debug(
                f"Response text: {response[:500] if 'response' in locals() else 'No response'}"
            )
            return self._get_fallback_assessment(
                checklist_type,
                num_questions=get_checklist_info(checklist_type).get("num_questions", 10),
            )

    def _get_fallback_assessment(self, checklist_type: str, num_questions: int) -> Dict[str, Any]:
        """Generate fallback assessment when parsing fails."""
        responses = {}
        for i in range(1, num_questions + 1):
            responses[f"q{i}"] = {
                "answer": "Can't Tell",
                "justification": "Automated assessment failed - manual review recommended",
            }

        return {
            "checklist_used": checklist_type,
            "responses": responses,
            "score": {
                "yes_count": 0,
                "no_count": 0,
                "cant_tell_count": num_questions,
                "total_questions": num_questions,
                "quality_rating": "Moderate",
                "overall_notes": "Automated assessment failed - manual review recommended",
            },
            "overall_summary": "Automated assessment encountered errors - manual review recommended",
        }

    def assess_grade(
        self, outcome: str, all_extracted_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Assess GRADE certainty for an outcome.

        Returns:
            Dictionary with GRADE assessment
        """
        # Count how many studies report this outcome
        studies_with_outcome = sum(
            1
            for data in all_extracted_data
            if outcome.lower() in " ".join(data.get("outcomes", [])).lower()
        )

        prompt = f"""Assess the GRADE certainty of evidence for this outcome based on the included studies.

Outcome: {outcome}
Number of studies reporting this outcome: {studies_with_outcome}
Total number of studies: {len(all_extracted_data)}

Provide a GRADE assessment. Consider:
- Risk of bias in studies
- Inconsistency of results
- Indirectness of evidence
- Imprecision of estimates
- Publication bias

Return a JSON object:
{{
  "certainty": "High/Moderate/Low/Very Low",
  "downgrade_reasons": ["reason1", "reason2"],
  "upgrade_reasons": [],
  "justification": "Brief explanation"
}}

Common downgrade reasons: "Risk of bias", "Inconsistency", "Indirectness", "Imprecision", "Publication bias"
Common upgrade reasons: "Large effect", "Dose-response", "All plausible confounding"
"""

        try:
            response = self._call_llm(prompt)
            json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", response, re.DOTALL)
            if json_match:
                assessment = json.loads(json_match.group())
                # Ensure required fields
                assessment.setdefault("downgrade_reasons", [])
                assessment.setdefault("upgrade_reasons", [])
                assessment.setdefault("justification", "Automated assessment")
                return assessment
            else:
                return {
                    "certainty": "Moderate",
                    "downgrade_reasons": ["Risk of bias"],
                    "upgrade_reasons": [],
                    "justification": "Automated assessment - review recommended",
                }
        except Exception as e:
            logger.error(f"Error assessing GRADE for {outcome}: {e}")
            return {
                "certainty": "Moderate",
                "downgrade_reasons": ["Risk of bias"],
                "upgrade_reasons": [],
                "justification": f"Automated assessment - error occurred: {e}",
            }


def auto_fill_assessments(
    template_path: str,
    extracted_data_list: List[Any],
    llm_provider: str = "gemini",
    llm_model: str = "gemini-2.5-pro",
    debug_config: Optional[Any] = None,
    framework: str = "CASP",
    detector_model: str = "gemini-2.5-flash",
) -> bool:
    """
    Fill out quality assessments automatically using CASP framework.

    Args:
        template_path: Path to quality assessment template JSON file
        extracted_data_list: List of ExtractedData objects
        llm_provider: LLM provider to use
        llm_model: LLM model to use for quality assessment
        debug_config: Optional debug configuration for verbose output
        framework: Assessment framework to use (default: "CASP")
        detector_model: LLM model to use for study type detection (default: "gemini-2.5-flash")

    Returns:
        True if successful, False otherwise
    """
    from rich.progress import (
        BarColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
    )

    from .study_type_detector import StudyTypeDetector

    template_path_obj = Path(template_path)

    if not template_path_obj.exists():
        logger.error(f"Template file not found: {template_path}")
        return False

    # Load template
    with open(template_path_obj) as f:
        template = json.load(f)

    # Convert ExtractedData to dicts
    extracted_data_dicts = []
    for data in extracted_data_list:
        extracted_data_dicts.append(data.to_dict() if hasattr(data, "to_dict") else data)

    logger.info(f"Found {len(extracted_data_dicts)} extracted studies")
    logger.info(f"Found {len(template.get('studies', []))} studies in template")

    # Check for grade_outcomes vs grade_assessments (handle both formats)
    grade_key = "grade_assessments" if "grade_assessments" in template else "grade_outcomes"
    logger.info(f"Found {len(template.get(grade_key, []))} outcomes to assess")

    # Determine verbose mode
    is_verbose = (
        debug_config
        and debug_config.enabled
        and debug_config.level in [DebugLevel.DETAILED, DebugLevel.FULL]
    )

    # Initialize filler
    try:
        filler = QualityAssessmentAutoFiller(
            llm_provider=llm_provider, llm_model=llm_model, debug_config=debug_config
        )
    except Exception as e:
        logger.error(f"Failed to initialize LLM client: {e}")
        return False

    # Initialize study type detector
    try:
        detector = StudyTypeDetector(
            llm_client=filler.llm_client,
            llm_model=detector_model,
            confidence_threshold=0.7,
            fallback_checklist="casp_cohort",
            debug_config=debug_config,
        )
    except Exception as e:
        logger.error(f"Failed to initialize study type detector: {e}")
        return False

    # Fill CASP assessments with Rich progress bar
    logger.info(f"Assessing study quality using {framework} framework...")
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed}/{task.total})"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            "[cyan]Assessing study quality...",
            total=len(template["studies"]),
        )

        for i, study in enumerate(template["studies"], 1):
            study_title = study["study_title"]

            # Find matching extracted data
            extracted_data = {}
            for data in extracted_data_dicts:
                if isinstance(data, dict):
                    if data.get("title", "").lower() == study_title.lower():
                        extracted_data = data
                        break
                elif hasattr(data, "title") and data.title.lower() == study_title.lower():
                    extracted_data = data.to_dict() if hasattr(data, "to_dict") else {}
                    break

            study_title_short = study_title[:50]
            progress.update(task, description=f"[cyan]Assessing: {study_title_short}...")

            # Detect study type if not already set
            if "detected_type" not in study or not study["detected_type"]:
                if is_verbose:
                    progress.log(
                        f"[bold cyan]Detecting study type {i}/{len(template['studies'])}:[/bold cyan] "
                        f"[cyan]{study_title_short}...[/cyan]"
                    )

                detection_result = detector.detect_study_type(extracted_data)
                study["detected_type"] = detection_result["checklist"]
                study["detection_confidence"] = detection_result["confidence"]
                study["detection_reasoning"] = detection_result["reasoning"]

                if is_verbose:
                    progress.log(
                        f"  [green]Detected:[/green] {detection_result['checklist']} "
                        f"(confidence: {detection_result['confidence']:.2f})"
                    )

            checklist_type = study.get("detected_type", "casp_cohort")

            # Verbose output for quality assessment
            if is_verbose:
                progress.log(
                    f"[bold cyan]Assessing quality {i}/{len(template['studies'])}:[/bold cyan] "
                    f"[cyan]{study_title_short}...[/cyan]"
                )
                progress.log(f"  [dim]-> Using checklist: {checklist_type}[/dim]")
                progress.log("  [dim]-> Building CASP assessment prompt...[/dim]")
                progress.log(f"  [dim]-> Calling LLM ({llm_model})...[/dim]")

            # Assess with CASP
            casp_assessment = filler.assess_with_casp(
                study_title=study_title,
                checklist_type=checklist_type,
                extracted_data=extracted_data,
            )

            # Update template with CASP assessment
            if "quality_assessment" not in study:
                study["quality_assessment"] = {}

            study["quality_assessment"]["checklist_used"] = casp_assessment["checklist_used"]
            study["quality_assessment"]["questions"] = casp_assessment["responses"]
            study["quality_assessment"]["score"] = casp_assessment["score"]
            study["quality_assessment"]["overall_notes"] = casp_assessment["overall_summary"]

            # Verbose output for completion
            if is_verbose:
                quality_rating = casp_assessment["score"].get("quality_rating", "Unknown")
                yes_count = casp_assessment["score"].get("yes_count", 0)
                total = casp_assessment["score"].get("total_questions", 10)
                progress.log(
                    f"  [green]Assessment complete[/green] - Quality: {quality_rating} "
                    f"({yes_count}/{total} Yes)"
                )

            progress.advance(task)

    # Fill GRADE assessments with Rich progress bar (if enabled)
    grade_assessments = template.get("grade_assessments", [])
    if grade_assessments:
        logger.info("Assessing GRADE certainty for outcomes...")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                "[cyan]Assessing GRADE certainty...",
                total=len(grade_assessments),
            )

            for i, grade_assessment in enumerate(grade_assessments, 1):
                outcome = grade_assessment["outcome"]
                outcome_short = outcome[:50]
                progress.update(task, description=f"[cyan]Assessing: {outcome_short}...")

                # Verbose output for GRADE assessment
                if is_verbose:
                    progress.log(
                        f"[bold cyan]Assessing GRADE {i}/{len(grade_assessments)}:[/bold cyan] "
                        f"[cyan]{outcome_short}...[/cyan]"
                    )
                    progress.log("  [dim]-> Building GRADE assessment prompt...[/dim]")
                    progress.log(f"  [dim]-> Calling LLM ({llm_model})...[/dim]")

                # Assess GRADE
                grade_result = filler.assess_grade(outcome, extracted_data_dicts)

                # Update template
                grade_assessment["certainty"] = grade_result.get("certainty", "Moderate")
                grade_assessment["downgrade_reasons"] = grade_result.get("downgrade_reasons", [])
                grade_assessment["upgrade_reasons"] = grade_result.get("upgrade_reasons", [])
                grade_assessment["justification"] = grade_result.get(
                    "justification", "Automated assessment"
                )

                # Verbose output for completion
                if is_verbose:
                    certainty = grade_result.get("certainty", "Moderate")
                    downgrade_count = len(grade_result.get("downgrade_reasons", []))
                    progress.log(
                        f"  [green]Assessment complete[/green] - Certainty: {certainty}, "
                        f"Downgrades: {downgrade_count}"
                    )

                progress.advance(task)
    else:
        logger.info("No GRADE outcomes to assess (skipping GRADE assessment)")

    # Save filled template
    with open(template_path_obj, "w") as f:
        json.dump(template, f, indent=2)

    logger.info(f"Successfully filled assessments! Saved to: {template_path_obj}")
    return True
