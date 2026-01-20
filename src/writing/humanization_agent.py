"""
Humanization Agent

Post-processes generated text to enhance naturalness and human-like quality.
Uses style patterns extracted from eligible papers.
"""

import logging
from typing import Dict, Optional, Any
from ..screening.base_agent import BaseScreeningAgent
from .naturalness_scorer import NaturalnessScorer

logger = logging.getLogger(__name__)


class HumanizationAgent(BaseScreeningAgent):
    """Post-processes text to enhance naturalness."""

    def screen(
        self,
        title: str,
        abstract: str,
        inclusion_criteria: List[str],
        exclusion_criteria: List[str],
    ):
        """Stub implementation - humanization agent doesn't screen papers."""
        from ..screening.base_agent import ScreeningResult, InclusionDecision
        return ScreeningResult(
            decision=InclusionDecision.UNCERTAIN,
            confidence=0.0,
            reasoning="Humanization agent - screening not applicable",
        )

    def __init__(
        self,
        llm_provider: str = "gemini",
        api_key: Optional[str] = None,
        agent_config: Optional[Dict[str, Any]] = None,
        naturalness_scorer: Optional[NaturalnessScorer] = None,
    ):
        """
        Initialize humanization agent.

        Args:
            llm_provider: LLM provider name
            api_key: API key for LLM provider
            agent_config: Agent configuration
            naturalness_scorer: NaturalnessScorer instance (optional, creates one if not provided)
        """
        super().__init__(
            llm_provider=llm_provider,
            api_key=api_key,
            agent_config=agent_config or {},
        )
        self.naturalness_scorer = naturalness_scorer or NaturalnessScorer(
            llm_provider=llm_provider,
            api_key=api_key,
            agent_config=agent_config,
        )
        self.max_iterations = agent_config.get("max_iterations", 2) if agent_config else 2
        self.naturalness_threshold = (
            agent_config.get("naturalness_threshold", 0.75) if agent_config else 0.75
        )

    def humanize_section(
        self,
        text: str,
        section_type: str,
        style_patterns: Optional[Dict[str, Dict[str, list]]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Humanize a section of text.

        Args:
            text: Original text to humanize
            section_type: Type of section (introduction, methods, results, discussion)
            style_patterns: Style patterns extracted from eligible papers
            context: Additional context (domain, topic, etc.)

        Returns:
            Humanized text
        """
        if not text or len(text.strip()) < 50:
            logger.warning(f"Text too short to humanize: {len(text)} chars")
            return text

        # Get initial naturalness score
        initial_scores = self.naturalness_scorer.score_naturalness(text, section_type)
        initial_naturalness = initial_scores.get("overall_naturalness", 0.5)

        logger.debug(
            f"Humanizing {section_type} section: "
            f"initial naturalness = {initial_naturalness:.2f}"
        )

        # If already acceptable, return as-is
        if initial_naturalness >= self.naturalness_threshold:
            logger.debug(f"Text already meets naturalness threshold ({initial_naturalness:.2f} >= {self.naturalness_threshold})")
            return text

        # Humanize iteratively
        current_text = text
        for iteration in range(self.max_iterations):
            logger.debug(f"Humanization iteration {iteration + 1}/{self.max_iterations}")

            # Build humanization prompt
            prompt = self._build_humanization_prompt(
                current_text, section_type, style_patterns, context
            )

            try:
                # Call LLM for humanization
                humanized_text = self._call_llm(prompt)

                # Clean up the response (remove any meta-commentary)
                humanized_text = self._clean_humanized_text(humanized_text)

                # Score the humanized text
                new_scores = self.naturalness_scorer.score_naturalness(
                    humanized_text, section_type
                )
                new_naturalness = new_scores.get("overall_naturalness", 0.5)

                logger.debug(
                    f"Iteration {iteration + 1}: "
                    f"naturalness = {new_naturalness:.2f} "
                    f"(improvement: {new_naturalness - initial_naturalness:+.2f})"
                )

                # If improved and meets threshold, use it
                if new_naturalness >= self.naturalness_threshold:
                    logger.info(
                        f"Humanization complete: "
                        f"naturalness improved from {initial_naturalness:.2f} to {new_naturalness:.2f}"
                    )
                    return humanized_text

                # If improved but not enough, continue iterating
                if new_naturalness > initial_naturalness:
                    current_text = humanized_text
                    initial_naturalness = new_naturalness
                else:
                    # No improvement, stop
                    logger.debug(
                        f"No improvement in iteration {iteration + 1}, stopping"
                    )
                    break

            except Exception as e:
                logger.warning(f"Error in humanization iteration {iteration + 1}: {e}")
                break

        # Return best version (current_text or original)
        return current_text if current_text != text else text

    def _build_humanization_prompt(
        self,
        text: str,
        section_type: str,
        style_patterns: Optional[Dict[str, Dict[str, list]]],
        context: Optional[Dict[str, Any]],
    ) -> str:
        """Build prompt for humanization."""
        # Truncate if too long
        max_length = 4000
        if len(text) > max_length:
            text = text[:max_length] + "... [truncated]"

        domain = context.get("domain", "") if context else ""
        topic = context.get("topic", "") if context else ""

        # Extract relevant style patterns for this section
        style_examples = ""
        if style_patterns and section_type in style_patterns:
            section_patterns = style_patterns[section_type]
            
            # Build examples from patterns
            examples_parts = []
            
            if section_patterns.get("sentence_openings"):
                openings = section_patterns["sentence_openings"][:3]  # First 3 examples
                examples_parts.append(f"Sentence opening examples: {', '.join(openings)}")
            
            if section_patterns.get("citation_patterns"):
                citations = section_patterns["citation_patterns"][:3]
                examples_parts.append(f"Citation pattern examples: {', '.join(citations)}")
            
            if section_patterns.get("transitions"):
                transitions = section_patterns["transitions"][:2]
                examples_parts.append(f"Transition examples: {', '.join(transitions)}")
            
            if section_patterns.get("vocabulary"):
                vocab = section_patterns["vocabulary"][:5]
                examples_parts.append(f"Domain vocabulary: {', '.join(vocab)}")
            
            if examples_parts:
                style_examples = "\n".join(examples_parts)

        prompt = f"""You are an expert academic editor. Refine the following text to make it sound more natural and human-written while maintaining technical accuracy.

ORIGINAL TEXT:
{text}

SECTION TYPE: {section_type}
DOMAIN: {domain}
TOPIC: {topic}

STYLE PATTERNS (from included papers in this review):
{style_examples if style_examples else "No specific patterns available - use general academic writing best practices."}

REFINEMENT GUIDELINES:
1. Vary sentence structures - avoid repetitive patterns (use examples from style patterns if provided)
2. Enrich vocabulary - use domain-specific academic terms naturally
3. Improve citation integration - make citations feel organic (follow patterns from included papers if provided)
4. Enhance transitions - use natural connectors (avoid formulaic phrases like "Furthermore," "Moreover," at sentence start)
5. Maintain technical accuracy - do not change meaning, facts, or data
6. Preserve structure - keep section organization intact (headings, paragraphs, lists)
7. Match writing style of included papers - use similar vocabulary and phrasing patterns if provided
8. Create natural flow - ensure sentences connect logically without forced transitions

CRITICAL CONSTRAINTS:
- Do NOT add meta-commentary, explanations, or notes
- Do NOT change the meaning or facts
- Do NOT add new content that wasn't in the original
- Output ONLY the refined text, ready for direct use
- Begin immediately with the content (no preamble)

Provide the refined text that sounds more natural and human-written."""

        return prompt

    def _clean_humanized_text(self, text: str) -> str:
        """Clean humanized text to remove any meta-commentary."""
        # Remove common LLM preambles
        preambles = [
            "Here is the refined text:",
            "Refined text:",
            "Here's the refined version:",
            "The refined text is:",
        ]

        for preamble in preambles:
            if text.startswith(preamble):
                text = text[len(preamble) :].strip()

        # Remove separator lines
        import re

        text = re.sub(r"^[-=*]{3,}\s*$", "", text, flags=re.MULTILINE)

        return text.strip()
