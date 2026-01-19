"""
Discussion Writer Agent

Generates discussion section for research articles.
"""

from typing import List, Dict, Optional, Any
from ..screening.base_agent import BaseScreeningAgent
from ..extraction.data_extractor_agent import ExtractedData
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
        from ..screening.base_agent import ScreeningResult, InclusionDecision

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
            research_question, key_findings, extracted_data, limitations, implications
        )

        if not self.llm_client:
            result = self._fallback_discussion(research_question, key_findings, extracted_data)
        else:
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

        if limitations:
            prompt += f"\nLimitations:\n{chr(10).join(f'- {lim}' for lim in limitations)}"
        else:
            # Add default limitations based on study count
            if num_studies == 0:
                prompt += "\nLimitations:\n- No studies met inclusion criteria, limiting ability to draw conclusions"
            elif num_studies == 1:
                prompt += "\nLimitations:\n- Only one study was included, limiting generalizability and synthesis"
            else:
                prompt += "\nLimitations:\n- Limited number of included studies may affect generalizability"

        if implications:
            prompt += f"\nImplications:\n{chr(10).join(f'- {imp}' for imp in implications)}"

        constraint_text = """
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

        if num_studies == 0:
            prompt += constraint_text + """

Please write a discussion section that includes:
1. Summary of Search Results (explain why no studies were found)
2. Research Gaps (identify gaps in the literature)
3. Implications for Future Research (what research is needed)
4. Limitations (acknowledge limitations of the review process)
5. Conclusions (brief conclusion about the state of the field)

Write in present tense for interpretations, use appropriate academic language, and acknowledge the limitation of having no included studies. Begin immediately with the summary of findings - do not include any introductory phrases."""
        elif num_studies == 1:
            prompt += constraint_text + """

Please write a discussion section that includes:
1. Summary of Main Findings (detailed findings from the single study)
2. Interpretation of Results (what the findings mean)
3. Comparison with Existing Literature (how findings relate to prior research)
4. Implications for Practice (practical applications)
5. Implications for Research (future research directions)
6. Limitations (acknowledge the limitation of having only one study, plus other limitations)
7. Conclusions (brief conclusion)

Write in present tense for interpretations, use SINGULAR language (e.g., "the study" not "studies"), use appropriate citations (use [Citation X] format), and ensure logical flow. IMPORTANT: Do not use plural language like "studies" or "multiple studies". Begin immediately with the summary of main findings - do not include any introductory phrases."""
        else:
            prompt += constraint_text + """

Please write a detailed discussion section that includes:
1. Summary of Main Findings (synthesize key findings across studies)
2. Interpretation of Results (what the findings mean)
3. Comparison with Existing Literature (how findings relate to prior research)
4. Implications for Practice (practical applications)
5. Implications for Research (future research directions)
6. Limitations (acknowledge study limitations)
7. Conclusions (brief conclusion)

Write in present tense for interpretations, use appropriate citations (use [Citation X] format), and ensure logical flow. Begin immediately with the summary of main findings - do not include any introductory phrases."""

        return prompt

    def _fallback_discussion(self, research_question: str, key_findings: List[str], extracted_data: Optional[List] = None) -> str:
        """Fallback discussion."""
        num_studies = len(extracted_data) if extracted_data else 0
        
        if num_studies == 0:
            return f"""## Discussion

### Summary of Findings

This systematic review addressed the research question: {research_question}

No studies met the inclusion criteria for this systematic review. This indicates a significant gap in the literature.

### Implications

The absence of studies meeting inclusion criteria highlights the need for future research in this area."""
        elif num_studies == 1:
            return f"""## Discussion

### Summary of Findings

This systematic review addressed the research question: {research_question}

Key findings from the included study include:
{chr(10).join(f"- {finding}" for finding in key_findings)}

### Implications

These findings have important implications for both practice and future research. However, the limitation of having only one included study should be considered when interpreting these results."""
        else:
            return f"""## Discussion

### Summary of Findings

This systematic review addressed the research question: {research_question}

Key findings from the included studies include:
{chr(10).join(f"- {finding}" for finding in key_findings)}

### Implications

These findings have important implications for both practice and future research."""
