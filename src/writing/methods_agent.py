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
        full_search_strategies: Optional[Dict[str, str]] = None,
        protocol_info: Optional[Dict[str, Any]] = None,
        automation_details: Optional[str] = None,
        style_patterns: Optional[Dict[str, Dict[str, List[str]]]] = None,
        output_dir: Optional[str] = None,
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
            full_search_strategies: Dictionary mapping database names to full search queries
            protocol_info: Protocol registration information (registry, number, url)
            automation_details: Details about automation tools used (LLM for screening/extraction)

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
            full_search_strategies,
            protocol_info,
            automation_details,
            style_patterns,
            output_dir,
        )

        if not self.llm_client:
            result = self._fallback_methods(
                search_strategy, databases, inclusion_criteria, exclusion_criteria
            )
        else:
            # Use tool calling if tools are available
            if self.tool_registry.list_tools():
                response = self._call_llm_with_tools(prompt, max_iterations=10)
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
        full_search_strategies: Optional[Dict[str, str]] = None,
        protocol_info: Optional[Dict[str, Any]] = None,
        automation_details: Optional[str] = None,
        style_patterns: Optional[Dict[str, Dict[str, List[str]]]] = None,
        output_dir: Optional[str] = None,
    ) -> str:
        """Build prompt for methods writing."""
        # Build protocol registration text
        protocol_text = ""
        if protocol_info:
            if protocol_info.get("registered"):
                registry = protocol_info.get("registry", "PROSPERO")
                reg_number = protocol_info.get("registration_number", "")
                reg_url = protocol_info.get("url", "")
                if reg_number:
                    protocol_text = f"The review protocol was registered with {registry} (registration number: {reg_number})."
                    if reg_url:
                        protocol_text += f" The protocol can be accessed at: {reg_url}"
                else:
                    protocol_text = f"The review protocol was registered with {registry}."
            else:
                protocol_text = "The review protocol was not registered."
        else:
            protocol_text = "Protocol registration information not available."

        # Build full search strategies text
        search_strategies_text = ""
        if full_search_strategies:
            search_strategies_text = "\n\nFull Search Strategies:\n\n"
            for db_name, query in full_search_strategies.items():
                search_strategies_text += f"{db_name}:\n{query}\n\n"
        else:
            search_strategies_text = "\n\nFull search strategies for all databases are provided in the supplementary materials."

        # Build automation details text
        automation_text = ""
        if automation_details:
            automation_text = f"\n\nAutomation Tools:\n{automation_details}"
        else:
            automation_text = "\n\nAutomation: Large language models (LLMs) were used to assist with title/abstract screening, full-text screening, and data extraction. All LLM outputs were verified and supplemented by human reviewers."

        prompt = f"""Write a comprehensive methods section for a systematic review following PRISMA 2020 guidelines.

{protocol_text}

Search Strategy Overview:
{search_strategy}
{search_strategies_text}

Databases Searched: {", ".join(databases)}
{automation_text}

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

        # Add style guidelines if patterns available
        style_guidelines = ""
        if style_patterns and "methods" in style_patterns:
            methods_patterns = style_patterns["methods"]
            style_guidelines = "\n\nSTYLE GUIDELINES (based on analysis of included papers in this review):\n"
            style_guidelines += "- Vary sentence structures: mix simple, compound, and complex sentences\n"
            style_guidelines += "- Use natural academic vocabulary with domain-specific terms from the field\n"
            style_guidelines += "- Integrate citations naturally: vary placement and phrasing\n"
            style_guidelines += "- Create natural flow: avoid formulaic transitions\n"
            style_guidelines += "- Maintain scholarly tone: precise but not robotic\n"
            
            if methods_patterns.get("sentence_openings"):
                examples = methods_patterns["sentence_openings"][:3]
                style_guidelines += "\nWRITING PATTERNS FROM INCLUDED PAPERS:\n"
                style_guidelines += f"Sentence opening examples: {', '.join(examples[:3])}\n"
            
            if methods_patterns.get("vocabulary"):
                vocab = methods_patterns["vocabulary"][:5]
                style_guidelines += f"Domain vocabulary examples: {', '.join(vocab)}\n"

        prompt += style_guidelines + """

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
1. Protocol and Registration (if registered, include registry name and registration number)
2. Eligibility Criteria (inclusion and exclusion criteria using PICOS framework)
3. Information Sources (all databases searched with dates)
4. Search Strategy (include full search strategies for all databases - these are provided above)
5. Study Selection Process (screening stages, number of reviewers, automation tools used)
6. Data Collection Process (data extraction methods, automation tools used)
7. Risk of Bias Assessment (methods used to assess risk of bias)
8. Reporting Bias Assessment (methods used to assess reporting biases, such as publication bias, selective outcome reporting, etc.)
9. Certainty Assessment (GRADE or other methods used to assess certainty of evidence)
10. Data Synthesis Methods (narrative synthesis, meta-analysis if applicable)

IMPORTANT: Include the full search strategies for ALL databases in the methods section. The full search queries are provided above. Write in past tense, use PRISMA 2020 terminology, and ensure all methodological details are clearly described. Begin immediately with protocol registration or search strategy - do not include any introductory phrases."""

        # Add tool calling instructions if tools are available
        if self.tool_registry.list_tools():
            tool_instructions = f"""
AVAILABLE TOOLS FOR GENERATING TABLES:

You have access to the following tool that you should use:

1. generate_inclusion_exclusion_table - Generate an inclusion/exclusion criteria table
   - Use when: Writing the Eligibility Criteria subsection
   - Parameters: inclusion_criteria (array), exclusion_criteria (array), output_dir (string)
   - Returns: Path to markdown table file - reference this in your text

TOOL USAGE INSTRUCTIONS:
- Call generate_inclusion_exclusion_table tool when writing the Eligibility Criteria subsection
- Use output_dir: {output_dir or "data/outputs"} for the tool call
- Reference the generated table file path in your text (e.g., "Table 1 shows the inclusion and exclusion criteria...")
- Include the table in your methods section text
"""
            prompt += tool_instructions

        return prompt

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
