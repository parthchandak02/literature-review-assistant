"""
Methods Writer Agent

Generates methods section for research articles.
"""

from typing import List, Dict, Optional, Any
from ..screening.base_agent import BaseScreeningAgent
from ..utils.text_cleaner import clean_writing_output


class MethodsWriter(BaseScreeningAgent):
    """Writes methods sections for research articles."""

    def _get_system_instruction(self):
        """Return academic writing system instruction for methods writing."""
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
        search_strategy: str,
        databases: List[str],
        inclusion_criteria: List[str],
        exclusion_criteria: List[str],
        screening_process: str,
        data_extraction_process: str,
        prisma_counts: Optional[Dict[str, int]] = None,
        topic_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Write methods section.

        Args:
            search_strategy: Description of search strategy
            databases: List of databases searched
            inclusion_criteria: Inclusion criteria
            exclusion_criteria: Exclusion criteria
            screening_process: Description of screening process
            data_extraction_process: Description of data extraction process
            prisma_counts: PRISMA flow counts (optional)

        Returns:
            Methods text
        """
        # Use provided topic_context or instance topic_context
        if topic_context:
            original_context = self.topic_context
            self.topic_context = topic_context

        prompt = self._build_methods_prompt(
            search_strategy,
            databases,
            inclusion_criteria,
            exclusion_criteria,
            screening_process,
            data_extraction_process,
            prisma_counts,
        )

        if not self.llm_client:
            result = self._fallback_methods(
                search_strategy, databases, inclusion_criteria, exclusion_criteria
            )
        else:
            response = self._call_llm(prompt)
            result = response

        # Restore original context
        if topic_context:
            self.topic_context = original_context

        # Apply text cleaning to remove meta-commentary
        result = clean_writing_output(result)
        return result

    def _build_methods_prompt(
        self,
        search_strategy: str,
        databases: List[str],
        inclusion_criteria: List[str],
        exclusion_criteria: List[str],
        screening_process: str,
        data_extraction_process: str,
        prisma_counts: Optional[Dict[str, int]],
    ) -> str:
        """Build prompt for methods writing."""
        prompt = f"""Write a comprehensive methods section for a systematic review following PRISMA 2020 guidelines.

Search Strategy:
{search_strategy}

Databases Searched: {", ".join(databases)}

Inclusion Criteria:
{chr(10).join(f"- {criterion}" for criterion in inclusion_criteria)}

Exclusion Criteria:
{chr(10).join(f"- {criterion}" for criterion in exclusion_criteria)}

Screening Process: {screening_process}

Data Extraction Process: {data_extraction_process}
"""

        if prisma_counts:
            prompt += f"""
PRISMA Flow:
- Records identified: {prisma_counts.get("found", 0)}
- Records after duplicates removed: {prisma_counts.get("no_dupes", 0)}
- Records screened: {prisma_counts.get("screened", 0)}
- Full-text articles assessed: {prisma_counts.get("full_text", 0)}
- Studies included: {prisma_counts.get("quantitative", prisma_counts.get("qualitative", 0))}
"""

        prompt += """

CRITICAL OUTPUT CONSTRAINTS:
- Begin IMMEDIATELY with substantive content - do NOT start with phrases like "Here is a methods section..." or "The following describes..."
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
- "The following describes"
- "I'll provide"
- "Allow me to"
- Any separator lines (***, ---, ===)

EXAMPLE OF CORRECT OUTPUT FORMAT:
[DIRECT CONTENT STARTS HERE - NO PREAMBLE]
This systematic review followed PRISMA 2020 guidelines. We registered the protocol...
[END - NO CLOSING REMARKS]

Please write a detailed methods section that includes:
1. Search Strategy (databases, search terms, date ranges)
2. Eligibility Criteria (inclusion and exclusion)
3. Study Selection Process (screening stages)
4. Data Extraction Methods
5. Quality Assessment (if applicable)
6. Data Synthesis Methods

Write in past tense, use PRISMA 2020 terminology, and ensure all methodological details are clearly described. Begin immediately with the search strategy or protocol details - do not include any introductory phrases."""

        return prompt

    def _fallback_methods(
        self,
        search_strategy: str,
        databases: List[str],
        inclusion_criteria: List[str],
        exclusion_criteria: List[str],
    ) -> str:
        """Fallback methods."""
        return f"""## Methods

### Search Strategy

{search_strategy}

The following databases were searched: {", ".join(databases)}.

### Eligibility Criteria

Studies were included if they met the following criteria:
{chr(10).join(f"- {criterion}" for criterion in inclusion_criteria)}

Studies were excluded if they:
{chr(10).join(f"- {criterion}" for criterion in exclusion_criteria)}

### Study Selection

All retrieved articles were screened in two stages: (1) title and abstract screening and (2) full-text review."""
