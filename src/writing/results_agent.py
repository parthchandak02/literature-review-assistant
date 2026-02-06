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
        risk_of_bias_summary: Optional[str] = None,
        risk_of_bias_table: Optional[str] = None,
        grade_assessments: Optional[str] = None,
        grade_table: Optional[str] = None,
        style_patterns: Optional[Dict[str, Dict[str, List[str]]]] = None,
        output_dir: Optional[str] = None,
    ) -> str:
        """
        Write results section.

        Args:
            extracted_data: List of extracted data from included studies
            prisma_counts: PRISMA flow counts
            key_findings: Optional list of key findings to highlight
            risk_of_bias_summary: Narrative summary of risk of bias assessments
            risk_of_bias_table: Markdown table of risk of bias assessments
            grade_assessments: Narrative summary of GRADE assessments
            grade_table: Markdown table of GRADE evidence profile

        Returns:
            Results text
        """
        # Use provided topic_context or instance topic_context
        if topic_context:
            original_context = self.topic_context
            self.topic_context = topic_context

        # Generate study characteristics table
        study_characteristics_table = self._generate_study_characteristics_table(extracted_data)

        # Set output_dir for tools if provided
        if output_dir:
            # Update tool output directories if tools are registered
            for tool_name in ["generate_mermaid_diagram", "generate_thematic_table", "generate_topic_analysis_table"]:
                tool = self.tool_registry.get_tool(tool_name)
                if tool and hasattr(tool.execute_fn, "__defaults__"):
                    # Tools will use output_dir parameter if provided
                    pass

        prompt = self._build_results_prompt(
            extracted_data, prisma_counts, key_findings,
            study_characteristics_table, risk_of_bias_summary, risk_of_bias_table,
            grade_assessments, grade_table, style_patterns, output_dir
        )

        if not self.llm_client:
            result = self._fallback_results(extracted_data, prisma_counts)
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

    def _generate_study_characteristics_table(
        self, extracted_data: List[ExtractedData]
    ) -> str:
        """
        Generate markdown table of study characteristics.

        Args:
            extracted_data: List of extracted study data

        Returns:
            Markdown table string
        """
        if not extracted_data:
            return "No studies included."

        # Build table header
        header = "| Study ID | Author, Year | Country | Design | Population | Intervention | Outcomes | Key Findings |\n"
        separator = "|" + "|".join(["---"] * 8) + "|\n"

        rows = []
        for i, data in enumerate(extracted_data, 1):
            study_id = f"Study {i}"

            # Extract author and year
            author_year = ""
            if data.authors:
                first_author = data.authors[0].split(",")[0] if "," in data.authors[0] else data.authors[0]
                author_year = f"{first_author} et al."
            if data.year:
                author_year += f", {data.year}"
            if not author_year:
                author_year = "Not specified"

            # Truncate long fields for table
            country = (data.country or "Not specified")[:30]
            design = (data.study_design or "Not specified")[:30]
            population = (data.participants or "Not specified")[:50]
            intervention = (data.interventions or "Not specified")[:50]
            outcomes = ", ".join(data.outcomes[:3])[:50] if data.outcomes else "Not specified"
            if len(data.outcomes) > 3:
                outcomes += "..."
            key_findings = ", ".join(data.key_findings[:2])[:50] if data.key_findings else "Not specified"
            if len(data.key_findings) > 2:
                key_findings += "..."

            row = (
                f"| {study_id} | {author_year} | {country} | {design} | "
                f"{population} | {intervention} | {outcomes} | {key_findings} |\n"
            )
            rows.append(row)

        table = header + separator + "".join(rows)
        return table

    def _build_results_prompt(
        self,
        extracted_data: List[ExtractedData],
        prisma_counts: Dict[str, int],
        key_findings: Optional[List[str]],
        study_characteristics_table: str,
        risk_of_bias_summary: Optional[str] = None,
        risk_of_bias_table: Optional[str] = None,
        grade_assessments: Optional[str] = None,
        grade_table: Optional[str] = None,
        style_patterns: Optional[Dict[str, Dict[str, List[str]]]] = None,
        output_dir: Optional[str] = None,
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

        # Add study characteristics table
        prompt += f"\n\nStudy Characteristics Table:\n{study_characteristics_table}\n"

        # Add risk of bias information if available
        if risk_of_bias_table:
            prompt += f"\n\nRisk of Bias Assessment Table:\n{risk_of_bias_table}\n"
        if risk_of_bias_summary:
            prompt += f"\n\nRisk of Bias Summary:\n{risk_of_bias_summary}\n"

        # Add GRADE information if available
        if grade_table:
            prompt += f"\n\nGRADE Evidence Profile Table:\n{grade_table}\n"
        if grade_assessments:
            prompt += f"\n\nGRADE Assessments Summary:\n{grade_assessments}\n"

        # Add style guidelines if patterns available
        style_guidelines = ""
        if style_patterns and "results" in style_patterns:
            results_patterns = style_patterns["results"]
            style_guidelines = "\n\nSTYLE GUIDELINES (based on analysis of included papers in this review):\n"
            style_guidelines += "- Vary sentence structures: mix simple, compound, and complex sentences\n"
            style_guidelines += "- Use natural academic vocabulary with domain-specific terms from the field\n"
            style_guidelines += "- Integrate citations naturally: vary placement and phrasing\n"
            style_guidelines += "- Create natural flow: avoid formulaic transitions\n"
            style_guidelines += "- Maintain scholarly tone: precise but not robotic\n"

            if results_patterns.get("sentence_openings"):
                examples = results_patterns["sentence_openings"][:3]
                style_guidelines += "\nWRITING PATTERNS FROM INCLUDED PAPERS:\n"
                style_guidelines += f"Sentence opening examples: {', '.join(examples[:3])}\n"

            if results_patterns.get("vocabulary"):
                vocab = results_patterns["vocabulary"][:5]
                style_guidelines += f"Domain vocabulary examples: {', '.join(vocab)}\n"

        constraint_text = style_guidelines + """
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

Write in past tense and use appropriate academic language. Begin immediately with the study selection summary - do not include any introductory phrases.
- DO NOT include a "Results" subsection header (### Results) - the Results section header is already provided, start directly with "### Study Selection" """
        elif num_studies == 1:
            prompt += constraint_text + """

Please write a results section that includes:
1. Study Selection (PRISMA flow summary)
2. Study Characteristics (include the study characteristics table provided above)
3. Risk of Bias in Studies (if risk of bias table is provided above, include it)
4. Key Findings (detailed findings from the single study)
5. Note the limitation of having only one study

Write in past tense, use SINGULAR language (e.g., "the study" not "studies"), and use appropriate academic language. Begin immediately with the study selection summary - do not include any introductory phrases.
- DO NOT include a "Results" subsection header (### Results) - the Results section header is already provided, start directly with "### Study Selection" """
        else:
            # Add tool calling instructions and Mermaid diagram guide
            tool_instructions = ""
            mermaid_guide = ""

            if self.tool_registry.list_tools():
                tool_instructions = """
AVAILABLE TOOLS FOR GENERATING TABLES AND DIAGRAMS:

You have access to the following tools that you should use when appropriate:

1. generate_thematic_table - Generate a thematic analysis table
   - Use when: You identify themes from the extracted data
   - Parameters:
     * themes (array, REQUIRED): List of theme names you've identified
     * output_dir (string, optional): Use """ + (output_dir or "data/outputs") + """ (defaults to configured directory)
     * extracted_data (array, optional): Can pass empty array [] - tool will work from prompt context
     * theme_descriptions (object, optional): Dictionary mapping theme names to descriptions
   - Returns: Path to markdown table file - reference this in your text

2. generate_topic_analysis_table - Generate a topic-specific summary table
   - Use when: You want to create a focused analysis table for a specific topic (e.g., "bias prevalence", "governance", "usability")
   - Parameters:
     * topic_focus (string, REQUIRED): Focus area (e.g., "bias prevalence", "governance", "usability")
     * output_dir (string, optional): Use """ + (output_dir or "data/outputs") + """ (defaults to configured directory)
     * extracted_data (array, optional): Can pass empty array [] - tool will work from prompt context
     * focus_areas (array, optional): List of specific focus areas within the topic
   - Returns: Path to markdown table file - reference this in your text

3. generate_mermaid_diagram - Generate a Mermaid diagram dynamically
   - Use when: You want to visualize data (themes, percentages, flows, timelines, etc.)
   - Parameters:
     * diagram_type (string): One of: pie, mindmap, flowchart, gantt, sankey, treemap, quadrant, xy, sequence, timeline
     * mermaid_code (string): Complete Mermaid syntax code (see guide below)
     * output_dir (string): Use """ + (output_dir or "data/outputs") + """
     * diagram_title (string, optional): Title for the diagram file
   - Returns: Path to SVG file - reference this in your text as a figure

TOOL USAGE INSTRUCTIONS:
- Analyze your data and decide when tables or diagrams would enhance the results section
- Call tools BEFORE writing about the data they represent
- For extracted_data parameter: You can pass an empty array [] or a simplified representation - the tool will extract information from the study data you've described in the prompt
- Reference the generated file paths in your text (e.g., "Table 1 shows..." or "Figure 2 illustrates...")
- Organize results by themes/topics and use tools to generate supporting tables/figures for each theme

MERMAID DIAGRAM TYPE GUIDE:

Choose the appropriate diagram type based on your data:

1. PIE CHART - For percentages, proportions, distributions
   Example: "65% of studies showed bias" -> use diagram_type="pie"
   Syntax example:
   ```
   pie title "Bias Prevalence"
       "Bias Present" : 65
       "No Bias" : 35
   ```

2. MINDMAP - For themes/concepts radiating from central topic
   Example: Thematic framework with 5 themes -> use diagram_type="mindmap"
   Syntax example:
   ```
   mindmap
     root((Central Topic))
       Theme1
       Theme2
       Theme3
   ```

3. FLOWCHART - For processes, workflows, decision trees
   Example: Study selection process -> use diagram_type="flowchart"
   Syntax example:
   ```
   flowchart TD
       Start[Start] --> Process[Process]
       Process --> End[End]
   ```

4. GANTT CHART - For timelines, publication trends
   Example: Publication timeline by year -> use diagram_type="gantt"
   Syntax example:
   ```
   gantt
       title Publication Timeline
       dateFormat YYYY
       section Studies
       Study 1 :2020, 2021
   ```

5. SANKEY - For flows, transformations
   Example: Papers through screening stages -> use diagram_type="sankey"
   Syntax example:
   ```
   sankey-beta
       flows
       Start --> Stage1 : 3561
       Stage1 --> Stage2 : 3200
   ```

6. TREEMAP - For hierarchical data, nested categories
   Example: Theme hierarchies -> use diagram_type="treemap"
   Syntax example:
   ```
   treemap
       root Root
           Branch1
           Branch2
   ```

7. QUADRANT CHART - For two-dimensional comparisons
   Example: Effectiveness vs. cost -> use diagram_type="quadrant"

8. XY CHART - For scatter plots, correlations
   Example: Effectiveness vs. sample size -> use diagram_type="xy"

9. SEQUENCE DIAGRAM - For interactions over time
   Example: Data extraction process -> use diagram_type="sequence"

10. TIMELINE - For chronological events
    Example: Publication timeline -> use diagram_type="timeline"

DECISION PROCESS FOR DIAGRAMS:
1. Analyze your data: What type of data? (percentages, themes, processes, timelines, flows, hierarchies)
2. Choose diagram type: Match data type to diagram type (see guide above)
3. Generate Mermaid code: Use syntax examples as templates, adapt to your data
4. Call generate_mermaid_diagram tool with diagram_type and mermaid_code
5. Reference the SVG file path in your text (e.g., "Figure 2 shows the thematic framework...")
"""
                mermaid_guide = tool_instructions

            prompt += constraint_text + mermaid_guide + """

Please write a detailed results section that includes:
1. Study Selection (PRISMA flow summary - note that the PRISMA diagram will be inserted separately)
2. Study Characteristics (include the study characteristics table provided above - it is already formatted as a markdown table)
3. Risk of Bias in Studies (if risk of bias table is provided above, include it and write a narrative summary)
4. Results of Individual Studies (synthesize findings across studies)
5. Results of Syntheses (identify common patterns and themes, include quantitative results if applicable with effect sizes, confidence intervals, p-values)
   - ORGANIZE BY THEMES: Structure subsections by identified themes (e.g., 4.1 Theme 1, 4.2 Theme 2, etc.)
   - USE TOOLS: Generate thematic tables and diagrams using available tools to support your analysis
   - Generate at least 2-3 topic-specific tables and 1-2 diagrams (mindmap for themes, pie charts for percentages, etc.)
6. Reporting Biases (assessment of publication bias, selective outcome reporting, and other reporting biases)
7. Certainty of Evidence (if GRADE table is provided above, include it and write a narrative summary)

IMPORTANT:
- Include the study characteristics table exactly as provided above
- If risk of bias information is provided, include the table and write a narrative summary (150-200 words)
- If GRADE information is provided, include the GRADE evidence profile table and write a narrative summary
- Write in past tense, synthesize findings across studies, and use appropriate academic language
- Begin immediately with the study selection summary - do not include any introductory phrases
- DO NOT include a "Results" subsection header (### Results) - the Results section header is already provided, start directly with "### Study Selection"
- USE TOOLS ACTIVELY: Call generate_thematic_table, generate_topic_analysis_table, and generate_mermaid_diagram tools when appropriate
- Reference generated tables and figures in your text (e.g., "Table 1 shows..." or "Figure 2 illustrates...") """

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
