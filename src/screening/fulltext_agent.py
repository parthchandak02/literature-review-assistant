"""
Full-text Screening Agent

Screens papers based on full-text content using LLM.
"""

from typing import List, Optional, Dict, Any
import logging
from .base_agent import BaseScreeningAgent, ScreeningResult, InclusionDecision
from ..config.debug_config import DebugLevel

logger = logging.getLogger(__name__)


class FullTextScreener(BaseScreeningAgent):
    """Screens papers based on full-text content."""

    def screen(
        self,
        title: str,
        abstract: str,
        full_text: Optional[str],
        inclusion_criteria: List[str],
        exclusion_criteria: List[str],
        topic_context: Optional[Dict[str, Any]] = None,
    ) -> ScreeningResult:
        """
        Screen a paper based on full-text content.

        Args:
            title: Paper title
            abstract: Paper abstract
            full_text: Full text content (if available)
            inclusion_criteria: List of inclusion criteria
            exclusion_criteria: List of exclusion criteria

        Returns:
            ScreeningResult with decision and reasoning
        """
        # Handle edge cases
        title = title or ""
        abstract = abstract or ""
        full_text = full_text or None
        
        # If both title and abstract are missing/empty, return uncertain
        if not title.strip() and not abstract.strip() and not full_text:
            logger.warning(f"[{self.role}] Paper has no title, abstract, or full-text, returning UNCERTAIN")
            return ScreeningResult(
                decision=InclusionDecision.UNCERTAIN,
                confidence=0.3,
                reasoning="Paper has no title, abstract, or full-text available for screening",
            )
        
        # Validate criteria
        if not inclusion_criteria:
            logger.warning(f"[{self.role}] No inclusion criteria provided")
        if not exclusion_criteria:
            logger.warning(f"[{self.role}] No exclusion criteria provided")
        
        # If full-text is very short, log warning
        if full_text and len(full_text.strip()) < 100:
            logger.warning(f"[{self.role}] Full-text is very short ({len(full_text)} chars), may be incomplete")

        # Check if verbose mode is enabled
        is_verbose = self.debug_config.enabled and self.debug_config.level in [
            DebugLevel.DETAILED,
            DebugLevel.FULL,
        ]

        # Use provided topic_context or instance topic_context
        if topic_context:
            original_context = self.topic_context
            self.topic_context = topic_context

        if is_verbose:
            logger.debug(
                f"[{self.role}] Screening paper \"{title[:60]}...\" - "
                f"Full-text available: {full_text is not None}"
            )

        if not full_text:
            # Fall back to title/abstract screening
            if is_verbose:
                logger.debug(
                    f"[{self.role}] Full-text not available, falling back to title/abstract screening"
                )
            result = self._screen_title_abstract(
                title, abstract, inclusion_criteria, exclusion_criteria
            )
        else:
            if is_verbose:
                logger.debug(
                    f"[{self.role}] Analyzing full-text ({len(full_text)} chars), "
                    f"title ({len(title)} chars), abstract ({len(abstract)} chars)"
                )
                logger.debug(
                    f"[{self.role}] Building prompt with {len(inclusion_criteria)} inclusion criteria, "
                    f"{len(exclusion_criteria)} exclusion criteria"
                )

            prompt = self._build_fulltext_prompt(
                title, abstract, full_text, inclusion_criteria, exclusion_criteria
            )

            if not self.llm_client:
                if is_verbose:
                    logger.debug(f"[{self.role}] No LLM client, using fallback keyword matching")
                result = self._fallback_screen(
                    title, abstract, full_text, inclusion_criteria, exclusion_criteria
                )
            else:
                if is_verbose:
                    logger.debug(
                        f"[{self.role}] Calling LLM ({self.llm_model}) for full-text screening..."
                    )
                response = self._call_llm(prompt)
                result = self._parse_llm_response(response)
                
                if is_verbose:
                    logger.debug(
                        f"[{self.role}] Decision: {result.decision.value.upper()}, "
                        f"Confidence: {result.confidence:.2f}"
                    )
                    logger.debug(f"[{self.role}] Reasoning: {result.reasoning[:100]}...")
                    if result.exclusion_reason:
                        logger.debug(f"[{self.role}] Exclusion reason: {result.exclusion_reason}")

        # Restore original context
        if topic_context:
            self.topic_context = original_context

        return result

    def _screen_title_abstract(
        self,
        title: str,
        abstract: str,
        inclusion_criteria: List[str],
        exclusion_criteria: List[str],
    ) -> ScreeningResult:
        """Screen using only title and abstract."""
        from ..screening.title_abstract_agent import TitleAbstractScreener

        # Pass agent_config to use the correct model from config
        screener = TitleAbstractScreener(
            self.llm_provider, 
            self.api_key, 
            self.topic_context, 
            self.agent_config
        )
        return screener.screen(title, abstract, inclusion_criteria, exclusion_criteria)

    def _build_fulltext_prompt(
        self,
        title: str,
        abstract: str,
        full_text: str,
        inclusion_criteria: List[str],
        exclusion_criteria: List[str],
    ) -> str:
        """Build prompt for full-text screening."""
        # Truncate full text if too long (LLM context limits)
        max_text_length = 8000
        if len(full_text) > max_text_length:
            full_text = full_text[:max_text_length] + "... [truncated]"

        prompt = f"""You are screening research papers for a systematic review. Evaluate the following paper based on its FULL TEXT:

Title: {title}

Abstract: {abstract}

Full Text (excerpt): {full_text}

Inclusion Criteria:
{chr(10).join(f"- {criterion}" for criterion in inclusion_criteria)}

Exclusion Criteria:
{chr(10).join(f"- {criterion}" for criterion in exclusion_criteria)}

IMPORTANT SCREENING GUIDELINES:
- A paper should be INCLUDED if it meets SUFFICIENT inclusion criteria (not necessarily all criteria)
- For full-text screening, apply stricter criteria than title/abstract screening, but still be INCLUSIVE if paper is borderline relevant
- When in doubt, err on the side of INCLUSION
- Exclusion requires CLEAR violation of exclusion criteria
- Only exclude papers that definitively do not meet inclusion criteria or clearly violate exclusion criteria

Please provide:
1. Decision: INCLUDE, EXCLUDE, or UNCERTAIN
2. Confidence: A number between 0.0 and 1.0
3. Reasoning: Brief explanation of your decision
4. Exclusion Reason: If excluding, specify which exclusion criterion applies

Format your response as:
DECISION: [INCLUDE/EXCLUDE/UNCERTAIN]
CONFIDENCE: [0.0-1.0]
REASONING: [your reasoning]
EXCLUSION_REASON: [if excluding, which criterion]"""
        return prompt

    def _parse_llm_response(self, response: str) -> ScreeningResult:
        """Parse LLM response into ScreeningResult."""
        decision = InclusionDecision.UNCERTAIN
        confidence = 0.5
        reasoning = response
        exclusion_reason = None

        lines = response.split("\n")
        for line in lines:
            line_upper = line.upper().strip()
            if line_upper.startswith("DECISION:"):
                decision_str = line.split(":", 1)[1].strip().upper()
                if "INCLUDE" in decision_str:
                    decision = InclusionDecision.INCLUDE
                elif "EXCLUDE" in decision_str:
                    decision = InclusionDecision.EXCLUDE
                else:
                    decision = InclusionDecision.UNCERTAIN
            elif line_upper.startswith("CONFIDENCE:"):
                try:
                    confidence = float(line.split(":", 1)[1].strip())
                    confidence = max(0.0, min(1.0, confidence))
                except ValueError:
                    pass
            elif line_upper.startswith("REASONING:"):
                reasoning = line.split(":", 1)[1].strip()
            elif line_upper.startswith("EXCLUSION_REASON:"):
                exclusion_reason = line.split(":", 1)[1].strip()

        return ScreeningResult(
            decision=decision,
            confidence=confidence,
            reasoning=reasoning,
            exclusion_reason=exclusion_reason,
        )

    def _fallback_screen(
        self,
        title: str,
        abstract: str,
        full_text: Optional[str],
        inclusion_criteria: List[str],
        exclusion_criteria: List[str],
    ) -> ScreeningResult:
        """Fallback screening using keyword matching."""
        text = (title + " " + abstract + " " + (full_text or "")).lower()

        # Check exclusion criteria first
        for criterion in exclusion_criteria:
            keywords = criterion.lower().split()
            if any(keyword in text for keyword in keywords if len(keyword) > 3):
                return ScreeningResult(
                    decision=InclusionDecision.EXCLUDE,
                    confidence=0.6,
                    reasoning=f"Matched exclusion criterion: {criterion}",
                    exclusion_reason=criterion,
                )

        # Check inclusion criteria
        inclusion_matches = 0
        for criterion in inclusion_criteria:
            keywords = criterion.lower().split()
            if any(keyword in text for keyword in keywords if len(keyword) > 3):
                inclusion_matches += 1

        if inclusion_matches >= len(inclusion_criteria) * 0.5:
            return ScreeningResult(
                decision=InclusionDecision.INCLUDE,
                confidence=0.7,
                reasoning=f"Matched {inclusion_matches} inclusion criteria",
            )
        else:
            return ScreeningResult(
                decision=InclusionDecision.EXCLUDE,
                confidence=0.6,
                reasoning="Did not meet inclusion criteria",
                exclusion_reason="Insufficient match to inclusion criteria",
            )
