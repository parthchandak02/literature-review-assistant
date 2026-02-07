"""
Study type detector for CASP checklist selection.

Analyzes extracted study data and determines the most appropriate CASP checklist
using LLM-powered classification.
"""

import json
import re
import time
from typing import Dict, Any, Optional
import logging

from ..utils.rich_utils import (
    console,
    print_llm_request_panel,
    print_llm_response_panel,
)

logger = logging.getLogger(__name__)


class StudyTypeDetector:
    """LLM-powered detector to classify studies and select appropriate CASP checklist."""
    
    def __init__(
        self,
        llm_client: Any,
        llm_model: str = "gemini-2.5-flash",
        confidence_threshold: float = 0.7,
        fallback_checklist: str = "casp_cohort",
        debug_config: Optional[Any] = None
    ):
        """
        Initialize study type detector.
        
        Args:
            llm_client: LLM client for making API calls
            llm_model: Model to use (gemini-2.5-flash for fast classification)
            confidence_threshold: Minimum confidence to use detected type (default: 0.7)
            fallback_checklist: Checklist to use if confidence is low (default: casp_cohort)
            debug_config: Optional debug configuration for verbose output
        """
        self.llm_client = llm_client
        self.llm_model = llm_model
        self.confidence_threshold = confidence_threshold
        self.fallback_checklist = fallback_checklist
        self.debug_config = debug_config
        
    def detect_study_type(self, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Detect study type and recommend CASP checklist.
        
        Args:
            extracted_data: Dictionary with study information (title, design, methodology, etc.)
            
        Returns:
            Dictionary with:
                - checklist: Recommended CASP checklist ('casp_rct', 'casp_cohort', 'casp_qualitative')
                - confidence: Confidence score (0-1)
                - reasoning: Explanation for the selection
                - fallback_used: Boolean indicating if fallback was triggered
        """
        title = extracted_data.get('title', 'Unknown title')
        study_design = extracted_data.get('study_design', 'Not specified')
        methodology = extracted_data.get('methodology', 'Not specified')
        participants = extracted_data.get('participants', 'Not specified')
        interventions = extracted_data.get('interventions', [])
        outcomes = extracted_data.get('outcomes', [])
        
        # Build detection prompt
        prompt = self._build_detection_prompt(
            title=title,
            study_design=study_design,
            methodology=methodology,
            participants=participants,
            interventions=interventions,
            outcomes=outcomes
        )
        
        try:
            # Call LLM for classification
            response = self._call_llm(prompt)
            
            # Parse response
            result = self._parse_detection_response(response)
            
            # Apply confidence threshold
            if result['confidence'] < self.confidence_threshold:
                logger.warning(
                    f"Low confidence ({result['confidence']:.2f}) for study '{title[:50]}...'. "
                    f"Using fallback checklist: {self.fallback_checklist}"
                )
                result['checklist'] = self.fallback_checklist
                result['fallback_used'] = True
                result['original_detection'] = result.get('checklist', 'unknown')
            else:
                result['fallback_used'] = False
                
            logger.info(
                f"Detected study type for '{title[:50]}...': {result['checklist']} "
                f"(confidence: {result['confidence']:.2f})"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error detecting study type for '{title[:50]}...': {e}")
            # Return fallback on error
            return {
                'checklist': self.fallback_checklist,
                'confidence': 0.0,
                'reasoning': f"Error during detection: {str(e)}. Using fallback checklist.",
                'fallback_used': True,
                'error': str(e)
            }
    
    def _build_detection_prompt(
        self,
        title: str,
        study_design: str,
        methodology: str,
        participants: str,
        interventions: list,
        outcomes: list
    ) -> str:
        """Build comprehensive detection prompt."""
        interventions_str = ', '.join(interventions) if interventions else 'Not specified'
        outcomes_str = ', '.join(outcomes) if outcomes else 'Not specified'
        
        prompt = f"""Analyze this study and determine the most appropriate quality assessment checklist.

Study Information:
- Title: {title}
- Study Design: {study_design}
- Methodology: {methodology}
- Participants: {participants}
- Interventions: {interventions_str}
- Outcomes: {outcomes_str}

Choose ONE checklist from the following options:

1. CASP RCT Checklist (casp_rct)
   - Use for: Randomized controlled trials, experimental studies with random assignment
   - Key indicators: 
     * Explicit mention of randomization or random allocation
     * Control group or comparison group
     * Intervention assignment by chance
     * Terms: "randomized", "RCT", "controlled trial", "random assignment", "double-blind"
   - Examples: Drug trials, educational intervention trials, technology comparison studies with randomization

2. CASP Cohort Study Checklist (casp_cohort)
   - Use for: Observational studies, longitudinal studies, prospective/retrospective cohorts
   - Key indicators:
     * Follow-up of groups over time
     * No random assignment to interventions
     * Comparison of exposed vs unexposed groups
     * Terms: "cohort", "longitudinal", "prospective", "retrospective", "observational", "follow-up"
   - Examples: Tracking patients using new technology, implementation studies, registry studies

3. CASP Qualitative Research Checklist (casp_qualitative)
   - Use for: Qualitative studies, interviews, focus groups, ethnography, case studies
   - Key indicators:
     * Emphasis on experiences, perceptions, meanings
     * Interviews, focus groups, observations as data collection
     * Thematic analysis, content analysis, grounded theory
     * Terms: "qualitative", "interview", "focus group", "thematic analysis", "phenomenology", "lived experience"
   - Examples: User experience studies, satisfaction surveys with open-ended responses, ethnographic studies

Decision Guidelines:
- Look for EXPLICIT RANDOMIZATION for RCT (not just "trial" or "study")
- If NO randomization but compares groups over time -> COHORT
- If focus is on EXPERIENCES, MEANINGS, or uses INTERVIEWS -> QUALITATIVE
- When unsure between RCT and Cohort, check for random assignment language
- Technology/prototype studies without randomization -> usually COHORT
- User experience or acceptability studies -> usually QUALITATIVE

Return your response as valid JSON only (no markdown, no code blocks) with this exact structure:
{{
  "checklist": "casp_rct" | "casp_cohort" | "casp_qualitative",
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation (2-3 sentences) citing specific evidence from the study information"
}}

Respond with JSON only:"""
        
        return prompt
    
    def _call_llm(self, prompt: str) -> str:
        """Call LLM for study type classification with rich console output."""
        from google.genai import types
        
        # Enhanced logging with Rich console
        should_show_verbose = self.debug_config and (
            self.debug_config.show_llm_calls or self.debug_config.enabled
        )
        
        if should_show_verbose:
            prompt_preview = prompt[:200] + "..." if len(prompt) > 200 else prompt
            print_llm_request_panel(
                model=self.llm_model,
                provider="gemini",
                agent="Study Type Detector",
                temperature=0.2,
                prompt_length=len(prompt),
                prompt_preview=prompt_preview,
            )
        
        call_start_time = time.time()
        response = self.llm_client.models.generate_content(
            model=self.llm_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,  # Low temperature for consistent classification
                response_mime_type="application/json"  # Request JSON response
            )
        )
        duration = time.time() - call_start_time
        
        response_text = response.text if hasattr(response, 'text') else str(response)
        
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
    
    def _parse_detection_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response and extract detection result."""
        # Try to extract JSON from response
        try:
            # Remove markdown code blocks if present
            response = re.sub(r'```json\s*|\s*```', '', response)
            response = response.strip()
            
            # Parse JSON
            result = json.loads(response)
            
            # Validate required fields
            if 'checklist' not in result:
                raise ValueError("Missing 'checklist' field in response")
            if 'confidence' not in result:
                raise ValueError("Missing 'confidence' field in response")
            if 'reasoning' not in result:
                result['reasoning'] = "No reasoning provided"
            
            # Validate checklist value
            valid_checklists = ['casp_rct', 'casp_cohort', 'casp_qualitative']
            if result['checklist'] not in valid_checklists:
                raise ValueError(
                    f"Invalid checklist '{result['checklist']}'. "
                    f"Must be one of: {valid_checklists}"
                )
            
            # Ensure confidence is float between 0 and 1
            result['confidence'] = float(result['confidence'])
            if not 0 <= result['confidence'] <= 1:
                logger.warning(
                    f"Confidence {result['confidence']} out of range [0,1]. Clipping."
                )
                result['confidence'] = max(0.0, min(1.0, result['confidence']))
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Response text: {response[:200]}...")
            raise ValueError(f"Invalid JSON response from LLM: {e}")
        except Exception as e:
            logger.error(f"Error parsing detection response: {e}")
            raise
