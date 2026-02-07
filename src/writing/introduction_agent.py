"""
Introduction Writer Agent

Generates introduction section for research articles.
"""

from typing import Any, Dict, List, Optional

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
        from ..screening.base_agent import InclusionDecision, ScreeningResult

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
        style_patterns: Optional[Dict[str, Dict[str, List[str]]]] = None,
    ) -> str:
        """
        Write introduction section.

        Args:
            research_question: The research question
            justification: Justification for the research
            background_context: Background context (optional)
            gap_description: Description of research gap (optional)
            topic_context: Optional topic context
            style_patterns: Optional style patterns extracted from eligible papers

        Returns:
            Introduction text
        """
        # Use provided topic_context or instance topic_context
        if topic_context:
            original_context = self.topic_context
            self.topic_context = topic_context

        prompt = self._build_introduction_prompt(
            research_question, justification, background_context, gap_description, style_patterns
        )

        if not self.llm_client:
            raise RuntimeError("LLM client is required for introduction generation")

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
        style_patterns: Optional[Dict[str, Dict[str, List[str]]]] = None,
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

        # Add style guidelines if patterns available
        style_guidelines = ""
        if style_patterns and "introduction" in style_patterns:
            intro_patterns = style_patterns["introduction"]
            style_guidelines = (
                "\n\nSTYLE GUIDELINES (based on analysis of included papers in this review):\n"
            )
            style_guidelines += (
                "- Vary sentence structures: mix simple, compound, and complex sentences\n"
            )
            style_guidelines += (
                "- Use natural academic vocabulary with domain-specific terms from the field\n"
            )
            style_guidelines += "- Integrate citations naturally: vary placement and phrasing\n"
            style_guidelines += "- Create natural flow: avoid formulaic transitions\n"
            style_guidelines += "- Maintain scholarly tone: precise but not robotic\n"

            if intro_patterns.get("sentence_openings"):
                examples = intro_patterns["sentence_openings"][:3]
                style_guidelines += "\nWRITING PATTERNS FROM INCLUDED PAPERS:\n"
                style_guidelines += f"Sentence opening examples: {', '.join(examples[:3])}\n"

            if intro_patterns.get("vocabulary"):
                vocab = intro_patterns["vocabulary"][:5]
                style_guidelines += f"Domain vocabulary examples: {', '.join(vocab)}\n"

        prompt += (
            style_guidelines
            + """

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
5. Explicit Objectives section with bullet points listing the specific objectives of this systematic review (e.g., "The objectives of this systematic review are: (1) to identify..., (2) to assess..., (3) to synthesize...")
6. Justification for conducting this systematic review
7. Overview of the review's contribution

CRITICAL REQUIREMENT: You MUST include an explicit "Objectives" paragraph or subsection with bullet points listing the specific objectives. This is required by PRISMA 2020 (Item #4).

Write in academic style, use appropriate citations (use [Citation X] format), and ensure the introduction flows logically. Begin immediately with the background content - do not include any introductory phrases."""
        )

        return prompt
