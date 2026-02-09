"""
Naturalness Scorer

LLM-based evaluation system to measure text naturalness.
"""

import logging
from typing import Dict, List, Optional

from ..screening.base_agent import BaseScreeningAgent

logger = logging.getLogger(__name__)


class NaturalnessScorer(BaseScreeningAgent):
    """Scores text naturalness using LLM evaluation."""

    def screen(
        self,
        title: str,
        abstract: str,
        inclusion_criteria: List[str],
        exclusion_criteria: List[str],
    ):
        """Stub implementation - naturalness scorer doesn't screen papers."""
        from ..screening.base_agent import InclusionDecision, ScreeningResult

        return ScreeningResult(
            decision=InclusionDecision.UNCERTAIN,
            confidence=0.0,
            reasoning="Naturalness scorer - screening not applicable",
        )

    def __init__(
        self,
        llm_provider: str = "gemini",
        api_key: Optional[str] = None,
        agent_config: Optional[Dict] = None,
    ):
        """
        Initialize naturalness scorer.

        Args:
            llm_provider: LLM provider name
            api_key: API key for LLM provider
            agent_config: Agent configuration
        """
        super().__init__(
            llm_provider=llm_provider,
            api_key=api_key,
            agent_config=agent_config or {},
        )
        # Cache for scoring results
        self._score_cache: Dict[str, Dict[str, float]] = {}

    def score_naturalness(
        self, text: str, section_type: str, use_cache: bool = True
    ) -> Dict[str, float]:
        """
        Score text naturalness across multiple dimensions.

        Args:
            text: Text to score
            section_type: Type of section (introduction, methods, etc.)
            use_cache: Whether to use cached scores

        Returns:
            Dictionary with scores for each dimension and overall score
        """
        from ..utils.rich_utils import print_naturalness_panel

        # Check cache
        cache_key = f"{section_type}:{hash(text[:500])}"
        if use_cache and cache_key in self._score_cache:
            logger.debug(f"Using cached naturalness score for {section_type}")
            return self._score_cache[cache_key]

        # Show evaluating panel
        print_naturalness_panel(section_name=section_type.title(), status="evaluating", scores=None)

        prompt = self._build_scoring_prompt(text, section_type)

        try:
            response = self._call_llm(prompt)
            scores = self._parse_scoring_response(response)

            # Calculate overall naturalness (weighted average)
            weights = {
                "sentence_structure_diversity": 0.25,
                "vocabulary_richness": 0.25,
                "citation_naturalness": 0.20,
                "transition_quality": 0.15,
                "overall_human_like": 0.15,
            }

            overall = sum(
                scores.get(key, 0.5) * weight for key, weight in weights.items() if key in scores
            )
            scores["overall_naturalness"] = overall

            # Cache result
            if use_cache:
                self._score_cache[cache_key] = scores

            # Show complete panel with scores
            print_naturalness_panel(
                section_name=section_type.title(), status="complete", scores=scores
            )

            return scores

        except Exception as e:
            logger.warning(f"Error scoring naturalness: {e}", exc_info=True)
            # Return default scores on error
            default_scores = {
                "sentence_structure_diversity": 0.5,
                "vocabulary_richness": 0.5,
                "citation_naturalness": 0.5,
                "transition_quality": 0.5,
                "overall_human_like": 0.5,
                "overall_naturalness": 0.5,
            }

            # Show complete panel with default scores
            print_naturalness_panel(
                section_name=section_type.title(), status="complete", scores=default_scores
            )

            return default_scores

    def _build_scoring_prompt(self, text: str, section_type: str) -> str:
        """Build prompt for naturalness scoring."""
        # Truncate if too long
        max_length = 3000
        if len(text) > max_length:
            text = text[:max_length] + "... [truncated]"

        prompt = f"""Evaluate the naturalness of this academic text on a scale of 0.0 to 1.0 for each dimension:

SECTION TYPE: {section_type}

TEXT TO EVALUATE:
{text}

Evaluate the following dimensions (provide scores as numbers between 0.0 and 1.0):

1. Sentence structure diversity (0.0-1.0): How varied are the sentence structures?
   - 1.0 = Excellent variety (simple, compound, complex sentences mixed naturally)
   - 0.5 = Some variety but repetitive patterns
   - 0.0 = Highly repetitive, formulaic structures

2. Vocabulary richness (0.0-1.0): How rich and varied is the vocabulary?
   - 1.0 = Excellent use of synonyms, domain-specific terms, natural academic language
   - 0.5 = Adequate vocabulary but some repetition
   - 0.0 = Limited vocabulary, repetitive word choices

3. Citation naturalness (0.0-1.0): How naturally are citations integrated?
   - 1.0 = Citations feel organic, varied placement and phrasing
   - 0.5 = Citations present but feel inserted
   - 0.0 = Citations feel systematic and formulaic

4. Transition quality (0.0-1.0): How natural are the transitions?
   - 1.0 = Natural flow, varied connectors, no formulaic phrases
   - 0.5 = Some natural transitions but some formulaic connectors
   - 0.0 = Formulaic transitions, repetitive connectors

5. Overall human-like quality (0.0-1.0): How human-written does this text sound?
   - 1.0 = Sounds completely natural and human-written
   - 0.5 = Mostly natural but some AI-like patterns detectable
   - 0.0 = Clearly AI-generated, robotic patterns

Provide your response in this exact format:
SENTENCE_STRUCTURE_DIVERSITY: [0.0-1.0]
VOCABULARY_RICHNESS: [0.0-1.0]
CITATION_NATURALNESS: [0.0-1.0]
TRANSITION_QUALITY: [0.0-1.0]
OVERALL_HUMAN_LIKE: [0.0-1.0]

Do not include any other text or explanations."""

        return prompt

    def _parse_scoring_response(self, response: str) -> Dict[str, float]:
        """Parse LLM response to extract scores."""
        import re

        scores = {}

        patterns = {
            "sentence_structure_diversity": r"SENTENCE_STRUCTURE_DIVERSITY:\s*([0-9.]+)",
            "vocabulary_richness": r"VOCABULARY_RICHNESS:\s*([0-9.]+)",
            "citation_naturalness": r"CITATION_NATURALNESS:\s*([0-9.]+)",
            "transition_quality": r"TRANSITION_QUALITY:\s*([0-9.]+)",
            "overall_human_like": r"OVERALL_HUMAN_LIKE:\s*([0-9.]+)",
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, response, re.IGNORECASE)
            if match:
                try:
                    score = float(match.group(1))
                    # Clamp to 0-1 range
                    score = max(0.0, min(1.0, score))
                    scores[key] = score
                except ValueError:
                    logger.warning(f"Could not parse score for {key}")

        return scores

    def is_acceptable(self, text: str, section_type: str, threshold: float = 0.75) -> bool:
        """
        Check if text meets naturalness threshold.

        Args:
            text: Text to evaluate
            section_type: Type of section
            threshold: Minimum overall naturalness score (default: 0.75)

        Returns:
            True if text meets threshold, False otherwise
        """
        scores = self.score_naturalness(text, section_type)
        overall = scores.get("overall_naturalness", 0.0)
        return overall >= threshold

    def score_dimension(self, text: str, dimension: str, section_type: str = "general") -> float:
        """
        Score a specific dimension.

        Args:
            text: Text to score
            dimension: Dimension to score (sentence_structure_diversity, etc.)
            section_type: Type of section

        Returns:
            Score for the dimension (0.0-1.0)
        """
        scores = self.score_naturalness(text, section_type)
        return scores.get(dimension, 0.5)
