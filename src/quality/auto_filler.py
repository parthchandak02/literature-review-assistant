"""
Auto-fill quality assessments using LLM.

This module provides functionality to automatically fill quality assessment
templates using LLM-based assessment.
"""

import json
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
import os
import logging

from ..utils.rich_utils import (
    console,
    print_llm_request_panel,
    print_llm_response_panel,
)
from ..config.debug_config import DebugLevel

logger = logging.getLogger(__name__)


class QualityAssessmentAutoFiller:
    """Uses LLM to automatically fill quality assessments."""
    
    def __init__(
        self, 
        llm_provider: str = "gemini", 
        llm_model: str = "gemini-2.5-pro",
        debug_config: Optional[Any] = None
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
                http_options=types.HttpOptions(timeout=120_000)  # 120 seconds in milliseconds
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
        should_show_verbose = (
            self.debug_config and 
            (self.debug_config.show_llm_calls or self.debug_config.enabled)
        )
        
        if should_show_verbose:
            prompt_preview = (
                prompt[:200] + "..." if len(prompt) > 200 else prompt
            )
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
            
            # Enhanced logging with Rich console for response
            if should_show_verbose:
                response_preview = (
                    response_text[:200] + "..." if len(response_text) > 200 else response_text
                )
                print_llm_response_panel(
                    duration=duration,
                    response_preview=response_preview,
                    tokens=None,
                    cost=None,
                )
            
            return response_text
        return ""
    
    def assess_risk_of_bias(self, study_title: str, study_design: str, extracted_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Assess risk of bias for a study using LLM.
        
        Returns:
            Dictionary with domain assessments and overall rating
        """
        # Build prompt for risk of bias assessment
        prompt = f"""Assess the risk of bias for this study using RoB 2 (Risk of Bias 2) tool.

Study Title: {study_title}
Study Design: {study_design}

Extracted Data:
- Methodology: {extracted_data.get('methodology', 'Not specified')}
- Study Design: {extracted_data.get('study_design', 'Not specified')}
- Participants: {extracted_data.get('participants', 'Not specified')}
- Outcomes: {', '.join(extracted_data.get('outcomes', []))}

For each RoB 2 domain, provide one of: "Low", "Some concerns", "High", or "Not applicable" (if the study design doesn't apply).

Note: Many studies in this systematic review are simulation studies, computational models, or system designs rather than randomized controlled trials. For non-RCT studies, use "Not applicable" for randomization-related domains and assess other domains appropriately.

Return a JSON object with this structure:
{{
  "Bias arising from the randomization process": "Low/Some concerns/High/Not applicable",
  "Bias due to deviations from intended interventions": "Low/Some concerns/High/Not applicable",
  "Bias due to missing outcome data": "Low/Some concerns/High/Not applicable",
  "Bias in measurement of the outcome": "Low/Some concerns/High/Not applicable",
  "Bias in selection of the reported result": "Low/Some concerns/High/Not applicable",
  "overall": "Low/Some concerns/High",
  "notes": "Brief explanation of the assessment"
}}
"""
        
        try:
            response = self._call_llm(prompt)
            # Extract JSON from response
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, re.DOTALL)
            if json_match:
                assessment = json.loads(json_match.group())
                return assessment
            else:
                # Fallback: return conservative assessment
                logger.warning(f"Could not parse LLM response for {study_title}, using conservative assessment")
                return {
                    "Bias arising from the randomization process": "Not applicable",
                    "Bias due to deviations from intended interventions": "Some concerns",
                    "Bias due to missing outcome data": "Some concerns",
                    "Bias in measurement of the outcome": "Some concerns",
                    "Bias in selection of the reported result": "Some concerns",
                    "overall": "Some concerns",
                    "notes": "Automated assessment - review recommended"
                }
        except Exception as e:
            logger.error(f"Error assessing {study_title}: {e}")
            # Return conservative assessment
            return {
                "Bias arising from the randomization process": "Not applicable",
                "Bias due to deviations from intended interventions": "Some concerns",
                "Bias due to missing outcome data": "Some concerns",
                "Bias in measurement of the outcome": "Some concerns",
                "Bias in selection of the reported result": "Some concerns",
                "overall": "Some concerns",
                "notes": f"Automated assessment - error occurred: {e}"
            }
    
    def assess_grade(self, outcome: str, all_extracted_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Assess GRADE certainty for an outcome.
        
        Returns:
            Dictionary with GRADE assessment
        """
        # Count how many studies report this outcome
        studies_with_outcome = sum(1 for data in all_extracted_data if outcome.lower() in ' '.join(data.get('outcomes', [])).lower())
        
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
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, re.DOTALL)
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
                    "justification": "Automated assessment - review recommended"
                }
        except Exception as e:
            logger.error(f"Error assessing GRADE for {outcome}: {e}")
            return {
                "certainty": "Moderate",
                "downgrade_reasons": ["Risk of bias"],
                "upgrade_reasons": [],
                "justification": f"Automated assessment - error occurred: {e}"
            }


def auto_fill_assessments(
    template_path: str,
    extracted_data_list: List[Any],
    llm_provider: str = "gemini",
    llm_model: str = "gemini-2.5-pro",
    debug_config: Optional[Any] = None
) -> bool:
    """
    Fill out quality assessments automatically.
    
    Args:
        template_path: Path to quality assessment template JSON file
        extracted_data_list: List of ExtractedData objects
        llm_provider: LLM provider to use
        llm_model: LLM model to use
        debug_config: Optional debug configuration for verbose output
    
    Returns:
        True if successful, False otherwise
    """
    from rich.progress import (
        Progress,
        BarColumn,
        TextColumn,
        TimeElapsedColumn,
        SpinnerColumn,
    )
    
    template_path_obj = Path(template_path)
    
    if not template_path_obj.exists():
        logger.error(f"Template file not found: {template_path}")
        return False
    
    # Load template
    with open(template_path_obj, 'r') as f:
        template = json.load(f)
    
    # Convert ExtractedData to dicts
    extracted_data_dicts = []
    for data in extracted_data_list:
        extracted_data_dicts.append(data.to_dict() if hasattr(data, 'to_dict') else data)
    
    logger.info(f"Found {len(extracted_data_dicts)} extracted studies")
    logger.info(f"Found {len(template['studies'])} studies in template")
    logger.info(f"Found {len(template['grade_outcomes'])} outcomes to assess")
    
    # Determine verbose mode
    is_verbose = (
        debug_config and 
        debug_config.enabled and 
        debug_config.level in [DebugLevel.DETAILED, DebugLevel.FULL]
    )
    
    # Initialize filler
    try:
        filler = QualityAssessmentAutoFiller(
            llm_provider=llm_provider, 
            llm_model=llm_model,
            debug_config=debug_config
        )
    except Exception as e:
        logger.error(f"Failed to initialize LLM client: {e}")
        return False
    
    # Fill risk of bias assessments with Rich progress bar
    logger.info("Assessing risk of bias for each study...")
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
            "[cyan]Assessing risk of bias...",
            total=len(template['studies']),
        )
        
        for i, study in enumerate(template['studies'], 1):
            study_title = study['study_title']
            study_design = study.get('study_design', 'Not specified')
            
            # Find matching extracted data
            extracted_data = {}
            for data in extracted_data_dicts:
                if isinstance(data, dict):
                    if data.get('title', '').lower() == study_title.lower():
                        extracted_data = data
                        break
                elif hasattr(data, 'title') and data.title.lower() == study_title.lower():
                    extracted_data = data.to_dict() if hasattr(data, 'to_dict') else {}
                    break
            
            study_title_short = study_title[:50]
            progress.update(task, description=f"[cyan]Assessing: {study_title_short}...")
            
            # Verbose output for risk of bias assessment
            if is_verbose:
                progress.log(
                    f"[bold cyan]Assessing risk of bias {i}/{len(template['studies'])}:[/bold cyan] "
                    f"[cyan]{study_title_short}...[/cyan]"
                )
                progress.log(
                    f"  [dim]-> Building RoB 2 assessment prompt...[/dim]"
                )
                progress.log(
                    f"  [dim]-> Calling LLM ({llm_model})...[/dim]"
                )
            
            # Assess risk of bias
            rob_assessment = filler.assess_risk_of_bias(study_title, study_design, extracted_data)
            
            # Update template
            study['risk_of_bias']['domains'] = {
                "Bias arising from the randomization process": rob_assessment.get("Bias arising from the randomization process", "Not applicable"),
                "Bias due to deviations from intended interventions": rob_assessment.get("Bias due to deviations from intended interventions", "Some concerns"),
                "Bias due to missing outcome data": rob_assessment.get("Bias due to missing outcome data", "Some concerns"),
                "Bias in measurement of the outcome": rob_assessment.get("Bias in measurement of the outcome", "Some concerns"),
                "Bias in selection of the reported result": rob_assessment.get("Bias in selection of the reported result", "Some concerns"),
            }
            study['risk_of_bias']['overall'] = rob_assessment.get('overall', 'Some concerns')
            study['risk_of_bias']['notes'] = rob_assessment.get('notes', 'Automated assessment')
            
            # Verbose output for completion
            if is_verbose:
                overall_rating = rob_assessment.get('overall', 'Some concerns')
                progress.log(
                    f"  [green]Assessment complete[/green] - Overall: {overall_rating}"
                )
            
            progress.advance(task)
    
    # Fill GRADE assessments with Rich progress bar
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
            total=len(template['grade_assessments']),
        )
        
        for i, grade_assessment in enumerate(template['grade_assessments'], 1):
            outcome = grade_assessment['outcome']
            outcome_short = outcome[:50]
            progress.update(task, description=f"[cyan]Assessing: {outcome_short}...")
            
            # Verbose output for GRADE assessment
            if is_verbose:
                progress.log(
                    f"[bold cyan]Assessing GRADE {i}/{len(template['grade_assessments'])}:[/bold cyan] "
                    f"[cyan]{outcome_short}...[/cyan]"
                )
                progress.log(
                    f"  [dim]-> Building GRADE assessment prompt...[/dim]"
                )
                progress.log(
                    f"  [dim]-> Calling LLM ({llm_model})...[/dim]"
                )
            
            # Assess GRADE
            grade_result = filler.assess_grade(outcome, extracted_data_dicts)
            
            # Update template
            grade_assessment['certainty'] = grade_result.get('certainty', 'Moderate')
            grade_assessment['downgrade_reasons'] = grade_result.get('downgrade_reasons', [])
            grade_assessment['upgrade_reasons'] = grade_result.get('upgrade_reasons', [])
            grade_assessment['justification'] = grade_result.get('justification', 'Automated assessment')
            
            # Verbose output for completion
            if is_verbose:
                certainty = grade_result.get('certainty', 'Moderate')
                downgrade_count = len(grade_result.get('downgrade_reasons', []))
                progress.log(
                    f"  [green]Assessment complete[/green] - Certainty: {certainty}, "
                    f"Downgrades: {downgrade_count}"
                )
            
            progress.advance(task)
    
    # Save filled template
    with open(template_path_obj, 'w') as f:
        json.dump(template, f, indent=2)
    
    logger.info(f"Successfully filled assessments! Saved to: {template_path_obj}")
    return True
