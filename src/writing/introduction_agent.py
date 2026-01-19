"""
Introduction Writer Agent

Generates introduction section for research articles.
"""

from typing import List, Dict, Optional, Any
from ..screening.base_agent import BaseScreeningAgent
from ..utils.text_cleaner import clean_writing_output


class IntroductionWriter(BaseScreeningAgent):
    """Writes introduction sections for research articles."""

    def _get_system_instruction(self):
        """Return academic writing system instruction for introduction writing."""
        return self._get_academic_writing_system_instruction()

    def screen(
        self,
        title: str,
        abstract: str,
        inclusion_criteria: List[str],
        exclusion_criteria: List[str],
    ):
        """Stub implementation - writing agents don't screen papers."""
        from ..screening.base_agent import ScreeningResult, InclusionDecision

        return ScreeningResult(
            decision=InclusionDecision.UNCERTAIN,
            confidence=0.0,
            reasoning="Writing agent - screening not applicable",
        )

    def write(
        self,
        research_question: str,
        justification: str,
        background_context: Optional[str] = None,
        gap_description: Optional[str] = None,
        topic_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Write introduction section.

        Args:
            research_question: The research question
            justification: Justification for the research
            background_context: Background context (optional)
            gap_description: Description of research gap (optional)
            topic_context: Optional topic context

        Returns:
            Introduction text
        """
        # Use provided topic_context or instance topic_context
        if topic_context:
            original_context = self.topic_context
            self.topic_context = topic_context

        prompt = self._build_introduction_prompt(
            research_question, justification, background_context, gap_description
        )

        if not self.llm_client:
            result = self._fallback_introduction(research_question, justification)
        else:
            response = self._call_llm(prompt)
            result = response

        # Restore original context
        if topic_context:
            self.topic_context = original_context

        # Apply text cleaning to remove meta-commentary
        result = clean_writing_output(result)
        return result

    def _build_introduction_prompt(
        self,
        research_question: str,
        justification: str,
        background_context: Optional[str],
        gap_description: Optional[str],
    ) -> str:
        """Build prompt for introduction writing."""
        prompt = f"""Write a comprehensive introduction section for a systematic review research article.

Research Question: {research_question}

Justification: {justification}
"""

        if background_context:
            prompt += f"\nBackground Context: {background_context}"

        if gap_description:
            prompt += f"\nResearch Gap: {gap_description}"

        prompt += """

CRITICAL OUTPUT CONSTRAINTS:
- Begin IMMEDIATELY with substantive content - do NOT start with phrases like "Here is an introduction for..." or "Of course. Here is..."
- NO conversational preamble, acknowledgments, or meta-commentary whatsoever
- NO separator lines (***, ---) or decorative elements
- NO self-referential statements like "In this section" or "As mentioned above"
- Output ONLY the section content suitable for direct insertion into an academic document

PROHIBITED PHRASES (DO NOT USE):
- "Of course"
- "Here is" / "Here's"
- "As an expert"
- "Certainly"
- "Let me provide"
- "Below is"
- "I'll provide"
- "Allow me to"
- Any separator lines (***, ---, ===)

EXAMPLE OF CORRECT OUTPUT FORMAT:
[DIRECT CONTENT STARTS HERE - NO PREAMBLE]
Health literacy disparities disproportionately affect low-income communities...
[END - NO CLOSING REMARKS]

Please write a well-structured introduction that includes:
1. Background and context of the research area
2. Importance and relevance of the topic
3. Identification of research gaps
4. Clear statement of the research question
5. Justification for conducting this systematic review
6. Overview of the review's contribution

Write in academic style, use appropriate citations (use [Citation X] format), and ensure the introduction flows logically. Begin immediately with the background content - do not include any introductory phrases."""

        return prompt

    def _fallback_introduction(self, research_question: str, justification: str) -> str:
        """Fallback introduction."""
        return f"""## Introduction

{research_question}

{justification}

This systematic review aims to address this research question through a comprehensive analysis of the existing literature."""
