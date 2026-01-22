"""
Table Generation Tool

Generates markdown tables for thematic analysis, topic-specific summaries, and inclusion/exclusion criteria.
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

try:
    from tabulate import tabulate
    TABULATE_AVAILABLE = True
except ImportError:
    TABULATE_AVAILABLE = False
    tabulate = None  # Set to None so code can check TABULATE_AVAILABLE
    logger.warning("tabulate not installed. Table generation will be disabled.")


def generate_thematic_table(
    themes: List[str],
    output_dir: str,
    extracted_data: Optional[List[Any]] = None,
    theme_descriptions: Optional[Dict[str, str]] = None,
) -> str:
    """
    Generate thematic analysis table using tabulate.

    Args:
        extracted_data: List of extracted study data (ExtractedData objects or dicts)
        themes: List of identified themes
        output_dir: Directory to save table file
        theme_descriptions: Optional dictionary mapping theme names to descriptions

    Returns:
        Path to markdown table file
    """
    if not TABULATE_AVAILABLE:
        raise ImportError(
            "tabulate is not installed. Install it with: pip install tabulate"
        )

    # Create output directory if it doesn't exist
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Extract theme descriptions and evidence from extracted_data
    table_data = []
    for theme in themes:
        # Get description if provided
        description = theme_descriptions.get(theme, "") if theme_descriptions else ""

        # Find evidence for theme in extracted_data (if provided)
        evidence_studies = []
        if extracted_data:
            for data in extracted_data:
                # Check if this study mentions the theme
                # Look in key_findings, study_objectives, outcomes, etc.
                # Handle both ExtractedData objects and dicts (from JSON)
                text_to_search = ""
                
                # Get key_findings
                if isinstance(data, dict):
                    key_findings = data.get("key_findings", [])
                    study_objectives = data.get("study_objectives", [])
                    outcomes = data.get("outcomes", [])
                    title = data.get("title", "")
                else:
                    key_findings = getattr(data, "key_findings", [])
                    study_objectives = getattr(data, "study_objectives", [])
                    outcomes = getattr(data, "outcomes", [])
                    title = getattr(data, "title", "") or ""
                
                # Build search text
                if key_findings:
                    text_to_search += " ".join(
                        key_findings if isinstance(key_findings, list) else [key_findings]
                    )
                if study_objectives:
                    text_to_search += " ".join(
                        study_objectives if isinstance(study_objectives, list) else [study_objectives]
                    )
                if outcomes:
                    text_to_search += " ".join(
                        outcomes if isinstance(outcomes, list) else [outcomes]
                    )
                if title:
                    text_to_search += " " + str(title)

                # Simple keyword matching (LLM should have identified themes from this data)
                if theme.lower() in text_to_search.lower():
                    study_ref = title or "Unknown Study"
                    evidence_studies.append(study_ref)

        # Build evidence string
        if evidence_studies:
            evidence = f"Found in {len(evidence_studies)} studies: {', '.join(evidence_studies[:3])}"
            if len(evidence_studies) > 3:
                evidence += f" and {len(evidence_studies) - 3} more"
        elif extracted_data:
            evidence = "Evidence to be synthesized from included studies"
        else:
            evidence = "Theme identified from analysis of included studies"

        # Combine description and evidence
        combined = f"{description}\n\n{evidence}" if description else evidence
        table_data.append([theme, combined])

    # Generate markdown table
    headers = ["Theme", "Description and Evidence"]
    markdown_table = tabulate(table_data, headers=headers, tablefmt="github")

    # Save to file
    output_file = output_path / "thematic_table.md"
    output_file.write_text(markdown_table, encoding="utf-8")

    logger.info(f"Generated thematic table: {output_file}")
    return str(output_file)


def generate_topic_analysis_table(
    topic_focus: str,
    output_dir: str,
    extracted_data: Optional[List[Any]] = None,
    focus_areas: Optional[List[str]] = None,
) -> str:
    """
    Generate topic-specific summary table.

    Args:
        extracted_data: List of extracted study data
        topic_focus: Focus area (e.g., "bias prevalence", "governance", "usability")
        output_dir: Directory to save table file
        focus_areas: Optional list of specific focus areas within the topic

    Returns:
        Path to markdown table file
    """
    if not TABULATE_AVAILABLE:
        raise ImportError(
            "tabulate is not installed. Install it with: pip install tabulate"
        )

    # Create output directory if it doesn't exist
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # If focus_areas not provided, use topic_focus as default
    if not focus_areas:
        focus_areas = [topic_focus]

    table_data = []
    for area in focus_areas:
        # Find evidence for this focus area (if extracted_data provided)
        evidence_studies = []
        if extracted_data:
            for data in extracted_data:
                # Handle both ExtractedData objects and dicts (from JSON)
                if isinstance(data, dict):
                    key_findings = data.get("key_findings", [])
                    outcomes = data.get("outcomes", [])
                    title = data.get("title", "")
                else:
                    key_findings = getattr(data, "key_findings", [])
                    outcomes = getattr(data, "outcomes", [])
                    title = getattr(data, "title", "") or ""
                
                text_to_search = ""
                if key_findings:
                    text_to_search += " ".join(
                        key_findings if isinstance(key_findings, list) else [key_findings]
                    )
                if outcomes:
                    text_to_search += " ".join(
                        outcomes if isinstance(outcomes, list) else [outcomes]
                    )

                if area.lower() in text_to_search.lower() or topic_focus.lower() in text_to_search.lower():
                    study_ref = title or "Unknown Study"
                    evidence_studies.append(study_ref)

        if evidence_studies:
            evidence = f"Found in {len(evidence_studies)} studies"
        elif extracted_data:
            evidence = "Evidence to be synthesized from included studies"
        else:
            evidence = "Analysis based on included studies"
        description = f"Analysis of {area} based on included studies"

        table_data.append([area, description, evidence])

    # Generate markdown table
    headers = ["Focus Area", "Description", "Evidence"]
    markdown_table = tabulate(table_data, headers=headers, tablefmt="github")

    # Save to file
    safe_topic = topic_focus.replace(" ", "_").lower()
    safe_topic = "".join(c for c in safe_topic if c.isalnum() or c in ("_", "-"))
    output_file = output_path / f"topic_analysis_{safe_topic}.md"
    output_file.write_text(markdown_table, encoding="utf-8")

    logger.info(f"Generated topic analysis table: {output_file}")
    return str(output_file)


def generate_inclusion_exclusion_table(
    inclusion_criteria: List[str],
    exclusion_criteria: List[str],
    output_dir: str,
) -> str:
    """
    Generate inclusion/exclusion criteria table.

    Args:
        inclusion_criteria: List of inclusion criteria
        exclusion_criteria: List of exclusion criteria
        output_dir: Directory to save table file

    Returns:
        Path to markdown table file
    """
    if not TABULATE_AVAILABLE:
        raise ImportError(
            "tabulate is not installed. Install it with: pip install tabulate"
        )

    # Create output directory if it doesn't exist
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Build table data
    # Match inclusion and exclusion criteria by index if possible
    max_len = max(len(inclusion_criteria), len(exclusion_criteria))
    table_data = []

    for i in range(max_len):
        inclusion = inclusion_criteria[i] if i < len(inclusion_criteria) else ""
        exclusion = exclusion_criteria[i] if i < len(exclusion_criteria) else ""
        table_data.append([inclusion, exclusion])

    # Generate markdown table
    headers = ["Inclusion Criteria", "Exclusion Criteria"]
    markdown_table = tabulate(table_data, headers=headers, tablefmt="github")

    # Save to file
    output_file = output_path / "inclusion_exclusion_table.md"
    output_file.write_text(markdown_table, encoding="utf-8")

    logger.info(f"Generated inclusion/exclusion table: {output_file}")
    return str(output_file)


def create_table_generator_tools(output_dir: str):
    """
    Create tool definitions for table generation.

    Args:
        output_dir: Default output directory for tables

    Returns:
        List of Tool objects
    """
    from .tool_registry import Tool, ToolParameter

    tools = []

    # Thematic table tool
    def execute_thematic_table(
        themes: List[str],
        output_dir_override: Optional[str] = None,
        extracted_data: Optional[List[Any]] = None,
        theme_descriptions: Optional[Dict[str, str]] = None,
    ) -> str:
        dir_to_use = output_dir_override or output_dir
        return generate_thematic_table(
            themes=themes,
            output_dir=dir_to_use,
            extracted_data=extracted_data,
            theme_descriptions=theme_descriptions,
        )

    thematic_tool = Tool(
        name="generate_thematic_table",
        description="Generate a thematic analysis table from extracted study data. Returns path to markdown table file.",
        parameters=[
            ToolParameter(
                name="themes",
                type="array",
                description="List of identified themes",
                required=True,
            ),
            ToolParameter(
                name="output_dir",
                type="string",
                description="Directory to save table file",
                required=False,
            ),
            ToolParameter(
                name="extracted_data",
                type="array",
                description="Optional list of extracted study data (can be empty array if data is in prompt context)",
                required=False,
            ),
            ToolParameter(
                name="theme_descriptions",
                type="object",
                description="Optional dictionary mapping theme names to descriptions",
                required=False,
            ),
        ],
        execute_fn=execute_thematic_table,
    )
    tools.append(thematic_tool)

    # Topic analysis table tool
    def execute_topic_table(
        topic_focus: str,
        output_dir_override: Optional[str] = None,
        extracted_data: Optional[List[Any]] = None,
        focus_areas: Optional[List[str]] = None,
    ) -> str:
        dir_to_use = output_dir_override or output_dir
        return generate_topic_analysis_table(
            topic_focus=topic_focus,
            output_dir=dir_to_use,
            extracted_data=extracted_data,
            focus_areas=focus_areas,
        )

    topic_tool = Tool(
        name="generate_topic_analysis_table",
        description="Generate a topic-specific summary table from extracted study data. Returns path to markdown table file.",
        parameters=[
            ToolParameter(
                name="topic_focus",
                type="string",
                description="Focus area (e.g., 'bias prevalence', 'governance', 'usability')",
                required=True,
            ),
            ToolParameter(
                name="output_dir",
                type="string",
                description="Directory to save table file",
                required=False,
            ),
            ToolParameter(
                name="extracted_data",
                type="array",
                description="Optional list of extracted study data (can be empty array if data is in prompt context)",
                required=False,
            ),
            ToolParameter(
                name="focus_areas",
                type="array",
                description="Optional list of specific focus areas within the topic",
                required=False,
            ),
        ],
        execute_fn=execute_topic_table,
    )
    tools.append(topic_tool)

    # Inclusion/exclusion table tool
    def execute_inclusion_table(
        inclusion_criteria: List[str],
        exclusion_criteria: List[str],
        output_dir_override: Optional[str] = None,
    ) -> str:
        dir_to_use = output_dir_override or output_dir
        return generate_inclusion_exclusion_table(
            inclusion_criteria=inclusion_criteria,
            exclusion_criteria=exclusion_criteria,
            output_dir=dir_to_use,
        )

    inclusion_tool = Tool(
        name="generate_inclusion_exclusion_table",
        description="Generate an inclusion/exclusion criteria table. Returns path to markdown table file.",
        parameters=[
            ToolParameter(
                name="inclusion_criteria",
                type="array",
                description="List of inclusion criteria",
                required=True,
            ),
            ToolParameter(
                name="exclusion_criteria",
                type="array",
                description="List of exclusion criteria",
                required=True,
            ),
            ToolParameter(
                name="output_dir",
                type="string",
                description="Directory to save table file",
                required=False,
            ),
        ],
        execute_fn=execute_inclusion_table,
    )
    tools.append(inclusion_tool)

    return tools
