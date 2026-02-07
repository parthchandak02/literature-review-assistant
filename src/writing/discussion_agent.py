"""
Discussion Writer Agent

Generates discussion section for research articles.
"""

from typing import Any, Dict, List, Optional

from ..extraction.data_extractor_agent import ExtractedData
from ..screening.base_agent import BaseScreeningAgent
from ..utils.text_cleaner import clean_writing_output


class DiscussionWriter(BaseScreeningAgent):
    """Writes discussion sections for research articles."""

    def _get_system_instruction(self):
        """Return academic writing system instruction for discussion writing."""
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
        key_findings: List[str],
        extracted_data: List[ExtractedData],
        limitations: Optional[List[str]] = None,
        implications: Optional[List[str]] = None,
        topic_context: Optional[Dict[str, Any]] = None,
        style_patterns: Optional[Dict[str, Dict[str, List[str]]]] = None,
    ) -> str:
        """
        Write discussion section.

        Args:
            research_question: The research question
            key_findings: List of key findings
            extracted_data: List of extracted data from studies
            limitations: Study limitations (optional)
            implications: Implications for practice/research (optional)

        Returns:
            Discussion text
        """
        # Use provided topic_context or instance topic_context
        if topic_context:
            original_context = self.topic_context
            self.topic_context = topic_context

        prompt = self._build_discussion_prompt(
            research_question,
            key_findings,
            extracted_data,
            limitations,
            implications,
            style_patterns,
        )

        if not self.llm_client:
            raise RuntimeError("LLM client is required for discussion generation")

        response = self._call_llm(prompt)
        result = response

        # Restore original context
        if topic_context:
            self.topic_context = original_context

        # Apply text cleaning to remove meta-commentary
        result = clean_writing_output(result)
        return result

    def _build_discussion_prompt(
        self,
        research_question: str,
        key_findings: List[str],
        extracted_data: List[ExtractedData],
        limitations: Optional[List[str]],
        implications: Optional[List[str]],
        style_patterns: Optional[Dict[str, Dict[str, List[str]]]] = None,
    ) -> str:
        """Build prompt for discussion writing."""
        num_studies = len(extracted_data)

        prompt = f"""Write a comprehensive discussion section for a systematic review.

Research Question: {research_question}

Number of Included Studies: {num_studies}

IMPORTANT: Adapt your writing style based on the number of included studies:
- If 0 studies: Focus on why no studies were found, implications for research gaps, and limitations
- If 1 study: Use SINGULAR language (e.g., "the study" not "studies"), acknowledge the limitation of having only one study, and discuss its findings in detail
- If multiple studies: Use standard synthesis language comparing findings across studies

Key Findings:
{chr(10).join(f"- {finding}" for finding in key_findings)}
"""

        # Build limitations section with two types
        limitations_text = "\n\nLimitations to Address:\n"
        limitations_text += "You MUST include TWO types of limitations:\n"
        limitations_text += "1. Limitations of the evidence (study quality, heterogeneity, publication bias, etc.) - ~200-300 words\n"
        limitations_text += "2. Limitations of the review process (search strategy, screening, extraction, etc.) - ~200-300 words\n"
        limitations_text += "Total limitations section should be 400-600 words.\n"

        if limitations:
            limitations_text += (
                f"\nSuggested limitations:\n{chr(10).join(f'- {lim}' for lim in limitations)}"
            )
        else:
            # Add default limitations based on study count
            if num_studies == 0:
                limitations_text += "\nEvidence limitations:\n- No studies met inclusion criteria, limiting ability to draw conclusions"
                limitations_text += "\nReview process limitations:\n- Search may have missed relevant studies, language restrictions"
            elif num_studies == 1:
                limitations_text += "\nEvidence limitations:\n- Only one study was included, limiting generalizability and synthesis"
                limitations_text += (
                    "\nReview process limitations:\n- Single reviewer screening, potential for bias"
                )
            else:
                limitations_text += "\nEvidence limitations:\n- Limited number of included studies may affect generalizability"
                limitations_text += "\nReview process limitations:\n- Potential for publication bias, language restrictions"

        prompt += limitations_text

        # Build implications section with three subsections
        implications_text = "\n\nImplications to Address:\n"
        implications_text += "You MUST include THREE subsections:\n"
        implications_text += "1. Implications for Practice (specific, actionable recommendations for practitioners) - ~120-150 words\n"
        implications_text += "2. Implications for Policy (regulatory, funding, policy recommendations) - ~120-150 words\n"
        implications_text += "3. Implications for Research (future research directions, methodological improvements) - ~120-150 words\n"
        implications_text += "Total implications section should be 350-400 words.\n"

        if implications:
            implications_text += (
                f"\nSuggested implications:\n{chr(10).join(f'- {imp}' for imp in implications)}"
            )
        else:
            implications_text += "\nGenerate specific, actionable implications for each category."

        prompt += implications_text

        # Add style guidelines if patterns available
        style_guidelines = ""
        if style_patterns and "discussion" in style_patterns:
            discussion_patterns = style_patterns["discussion"]
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

            if discussion_patterns.get("sentence_openings"):
                examples = discussion_patterns["sentence_openings"][:3]
                style_guidelines += "\nWRITING PATTERNS FROM INCLUDED PAPERS:\n"
                style_guidelines += f"Sentence opening examples: {', '.join(examples[:3])}\n"

            if discussion_patterns.get("vocabulary"):
                vocab = discussion_patterns["vocabulary"][:5]
                style_guidelines += f"Domain vocabulary examples: {', '.join(vocab)}\n"

        constraint_text = (
            style_guidelines
            + """
CRITICAL OUTPUT CONSTRAINTS:
- Begin IMMEDIATELY with substantive content - do NOT start with phrases like "Let me now discuss..." or "Of course. As an expert..."
- NO conversational preamble, acknowledgments, or meta-commentary whatsoever
- NO separator lines (***, ---) or decorative elements
- NO self-referential statements like "In this section" or "As mentioned above"
- Output ONLY the section content suitable for direct insertion into an academic document

PROHIBITED PHRASES (DO NOT USE):
- "Of course"
- "Here is" / "Here's"
- "As an expert"
- "Certainly"
- "Let me provide" / "Let me now discuss"
- "Below is"
- "I'll provide"
- "Allow me to"
- Any separator lines (***, ---, ===)

EXAMPLE OF CORRECT OUTPUT FORMAT:
[DIRECT CONTENT STARTS HERE - NO PREAMBLE]
This systematic review demonstrates that the intervention produces moderate to large effect sizes...
[END - NO CLOSING REMARKS]
"""
        )

        if num_studies == 0:
            prompt += (
                constraint_text
                + """

Please write a discussion section that includes:
1. Summary of Search Results (explain why no studies were found)
2. Research Gaps (identify gaps in the literature)
3. Implications for Practice (what practitioners should know - ~120-150 words)
4. Implications for Policy (policy recommendations - ~120-150 words)
5. Implications for Research (what research is needed - ~120-150 words)
6. Limitations of the Evidence (no studies found, evidence gaps - ~200-300 words)
7. Limitations of the Review Process (search strategy, screening, extraction - ~200-300 words)
8. Conclusions (brief conclusion about the state of the field)

CRITICAL REQUIREMENTS:
- Limitations section MUST be split into two subsections: "Limitations of the Evidence" and "Limitations of the Review Process"
- Total limitations section: 400-600 words
- Implications section MUST have three subsections: "Implications for Practice", "Implications for Policy", "Implications for Research"
- Total implications section: 350-400 words
- Write in present tense for interpretations, use appropriate academic language, and acknowledge the limitation of having no included studies
- Begin immediately with the summary of findings - do not include any introductory phrases"""
            )
        elif num_studies == 1:
            prompt += (
                constraint_text
                + """

Please write a discussion section that includes:
1. Summary of Main Findings (detailed findings from the single study)
2. Interpretation of Results (what the findings mean)
3. Comparison with Existing Literature (how findings relate to prior research)
4. Implications for Practice (specific, actionable recommendations - ~120-150 words)
5. Implications for Policy (regulatory, funding, policy recommendations - ~120-150 words)
6. Implications for Research (future research directions, methodological improvements - ~120-150 words)
7. Limitations of the Evidence (acknowledge the limitation of having only one study, study quality - ~200-300 words)
8. Limitations of the Review Process (search strategy, screening, extraction - ~200-300 words)
9. Conclusions (brief conclusion)

CRITICAL REQUIREMENTS:
- Limitations section MUST be split into two subsections: "Limitations of the Evidence" and "Limitations of the Review Process"
- Total limitations section: 400-600 words
- Implications section MUST have three subsections: "Implications for Practice", "Implications for Policy", "Implications for Research"
- Total implications section: 350-400 words
- Write in present tense for interpretations, use SINGULAR language (e.g., "the study" not "studies"), use appropriate citations (use [Citation X] format), and ensure logical flow
- IMPORTANT: Do not use plural language like "studies" or "multiple studies"
- Begin immediately with the summary of main findings - do not include any introductory phrases"""
            )
        else:
            prompt += (
                constraint_text
                + """

Please write a detailed discussion section that includes:
1. Summary of Main Findings (synthesize key findings across studies)
2. Interpretation of Results (what the findings mean)
3. Comparison with Existing Literature (how findings relate to prior research)
4. Implications for Practice (specific, actionable recommendations - ~120-150 words)
5. Implications for Policy (regulatory, funding, policy recommendations - ~120-150 words)
6. Implications for Research (future research directions, methodological improvements - ~120-150 words)
7. Limitations of the Evidence (study quality, heterogeneity, publication bias - ~200-300 words)
8. Limitations of the Review Process (search strategy, screening, extraction - ~200-300 words)
9. Conclusions (brief conclusion)

CRITICAL REQUIREMENTS:
- Limitations section MUST be split into two subsections: "Limitations of the Evidence" and "Limitations of the Review Process"
- Total limitations section: 400-600 words
- Implications section MUST have three subsections: "Implications for Practice", "Implications for Policy", "Implications for Research"
- Total implications section: 350-400 words
- Write in present tense for interpretations, use appropriate citations (use [Citation X] format), and ensure logical flow
- Begin immediately with the summary of main findings - do not include any introductory phrases"""
            )

        return prompt
