"""
Results Writer Agent

Generates results section for research articles.
"""

from typing import List, Dict, Optional, Any
from ..screening.base_agent import BaseScreeningAgent
from ..extraction.data_extractor_agent import ExtractedData
from ..utils.text_cleaner import clean_writing_output


class ResultsWriter(BaseScreeningAgent):
    """Writes results sections for research articles."""

    def _get_system_instruction(self):
        """Return academic writing system instruction for results writing."""
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
        extracted_data: List[ExtractedData],
        prisma_counts: Dict[str, int],
        key_findings: Optional[List[str]] = None,
        topic_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Write results section.

        Args:
            extracted_data: List of extracted data from included studies
            prisma_counts: PRISMA flow counts
            key_findings: Optional list of key findings to highlight

        Returns:
            Results text
        """
        # Use provided topic_context or instance topic_context
        if topic_context:
            original_context = self.topic_context
            self.topic_context = topic_context

        prompt = self._build_results_prompt(extracted_data, prisma_counts, key_findings)

        if not self.llm_client:
            result = self._fallback_results(extracted_data, prisma_counts)
        else:
            response = self._call_llm(prompt)
            result = response

        # Restore original context
        if topic_context:
            self.topic_context = original_context

        # Apply text cleaning to remove meta-commentary
        result = clean_writing_output(result)
        return result

    def _build_results_prompt(
        self,
        extracted_data: List[ExtractedData],
        prisma_counts: Dict[str, int],
        key_findings: Optional[List[str]],
    ) -> str:
        """Build prompt for results writing."""
        num_studies = len(extracted_data)

        prompt = f"""Write a comprehensive results section for a systematic review.

Study Selection:
- Total records identified: {prisma_counts.get("found", 0)}
- Records after duplicates removed: {prisma_counts.get("no_dupes", 0)}
- Records screened: {prisma_counts.get("screened", 0)}
- Full-text articles assessed: {prisma_counts.get("full_text_assessed", prisma_counts.get("full_text", 0))}
- Studies included in synthesis: {prisma_counts.get("quantitative", prisma_counts.get("qualitative", 0))}

Number of Included Studies: {num_studies}

IMPORTANT: Adapt your writing style based on the number of included studies:
- If 0 studies: Write a "no studies found" section explaining the search results and why no studies met inclusion criteria
- If 1 study: Write a single-study narrative synthesis (do not use plural language like "studies" or "multiple studies")
- If multiple studies: Write standard synthesis with comparisons across studies

Study Characteristics:
"""

        if num_studies == 0:
            prompt += "\nNo studies were included in this systematic review."
        elif num_studies == 1:
            data = extracted_data[0]
            prompt += f"""
The included study: {data.title}
- Methodology: {data.methodology}
- Study Design: {data.study_design or "Not specified"}
- Key Findings: {", ".join(data.key_findings[:5]) if data.key_findings else "Not specified"}
"""
        else:
            for i, data in enumerate(extracted_data[:10], 1):  # Limit to first 10 for prompt
                prompt += f"""
Study {i}: {data.title}
- Methodology: {data.methodology}
- Study Design: {data.study_design or "Not specified"}
- Key Findings: {", ".join(data.key_findings[:3]) if data.key_findings else "Not specified"}
"""

        if key_findings:
            prompt += (
                f"\nKey Findings to Highlight:\n{chr(10).join(f'- {f}' for f in key_findings)}"
            )

        constraint_text = """
CRITICAL OUTPUT CONSTRAINTS:
- Begin IMMEDIATELY with substantive content - do NOT start with phrases like "Here is a results section..." or "Of course. Here is..."
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
- "This section presents"
- "I'll provide"
- "Allow me to"
- Any separator lines (***, ---, ===)

EXAMPLE OF CORRECT OUTPUT FORMAT:
[DIRECT CONTENT STARTS HERE - NO PREAMBLE]
The initial search identified 1,247 potentially relevant studies...
[END - NO CLOSING REMARKS]
"""

        if num_studies == 0:
            prompt += constraint_text + """

Please write a results section that includes:
1. Study Selection (PRISMA flow summary)
2. Explanation of why no studies met inclusion criteria
3. Summary of search results and screening process

Write in past tense and use appropriate academic language. Begin immediately with the study selection summary - do not include any introductory phrases."""
        elif num_studies == 1:
            prompt += constraint_text + """

Please write a results section that includes:
1. Study Selection (PRISMA flow summary)
2. Study Characteristics (detailed description of the single included study)
3. Key Findings (detailed findings from the single study)
4. Note the limitation of having only one study

Write in past tense, use SINGULAR language (e.g., "the study" not "studies"), and use appropriate academic language. Begin immediately with the study selection summary - do not include any introductory phrases."""
        else:
            prompt += constraint_text + """

Please write a detailed results section that includes:
1. Study Selection (PRISMA flow summary)
2. Study Characteristics (overview of included studies)
3. Key Findings Synthesis (synthesize findings across studies)
4. Patterns and Themes (identify common patterns)
5. Quantitative Results (if applicable)

Write in past tense, synthesize findings across studies, and use appropriate academic language. Begin immediately with the study selection summary - do not include any introductory phrases."""

        return prompt

    def _fallback_results(
        self, extracted_data: List[ExtractedData], prisma_counts: Dict[str, int]
    ) -> str:
        """Fallback results."""
        num_studies = len(extracted_data)

        if num_studies == 0:
            return f"""## Results

### Study Selection

A total of {prisma_counts.get("found", 0)} records were identified through database searching. After removing {prisma_counts.get("found", 0) - prisma_counts.get("no_dupes", 0)} duplicate records, {prisma_counts.get("no_dupes", 0)} unique records remained. After title and abstract screening, {prisma_counts.get("screened", 0)} records were assessed for eligibility. Following full-text review, no studies met the inclusion criteria and were included in the final synthesis.

### No Studies Found

No studies met the inclusion criteria for this systematic review. This may be due to the specificity of the inclusion criteria or the limited availability of research in this area."""
        elif num_studies == 1:
            study = extracted_data[0]
            return f"""## Results

### Study Selection

A total of {prisma_counts.get("found", 0)} records were identified through database searching. After removing {prisma_counts.get("found", 0) - prisma_counts.get("no_dupes", 0)} duplicate records, {prisma_counts.get("no_dupes", 0)} unique records remained. After title and abstract screening, {prisma_counts.get("screened", 0)} records were assessed for eligibility. Following full-text review, one study was included in the final synthesis.

### Study Characteristics

One study was included in this systematic review: {study.title if hasattr(study, 'title') else 'The included study'}."""
        else:
            return f"""## Results

### Study Selection

A total of {prisma_counts.get("found", 0)} records were identified through database searching. After removing {prisma_counts.get("found", 0) - prisma_counts.get("no_dupes", 0)} duplicate records, {prisma_counts.get("no_dupes", 0)} unique records remained. After title and abstract screening, {prisma_counts.get("screened", 0)} records were assessed for eligibility. Following full-text review, {prisma_counts.get("quantitative", prisma_counts.get("qualitative", 0))} studies were included in the final synthesis.

### Study Characteristics

{num_studies} studies were included in this systematic review. The studies varied in methodology and focus areas."""
