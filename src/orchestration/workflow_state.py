"""
Workflow State

Type-safe workflow state management for systematic review workflow.
"""

from typing import Any, Dict, List, Optional, TypedDict

from ..extraction.data_extractor_agent import ExtractedData
from ..search.connectors.base import Paper


class WorkflowState(TypedDict, total=False):
    """
    Type-safe workflow state.
    
    Defines all state managed throughout the workflow with proper typing.
    Using total=False allows optional fields.
    """
    
    # Search phase
    all_papers: List[Paper]
    search_complete: bool
    database_breakdown: Dict[str, int]
    
    # Deduplication phase
    unique_papers: List[Paper]
    duplicates_removed: int
    
    # Title/Abstract screening phase
    screened_papers: List[Paper]
    title_abstract_excluded: int
    title_abstract_results: List[Any]
    
    # Full-text screening phase
    eligible_papers: List[Paper]
    fulltext_excluded: int
    fulltext_results: List[Any]
    fulltext_available_count: int
    fulltext_unavailable_count: int
    
    # Final inclusion
    final_papers: List[Paper]
    
    # Enrichment phase
    enriched_papers: List[Paper]
    
    # Extraction phase
    extracted_data: List[ExtractedData]
    extraction_complete: bool
    
    # Quality assessment phase
    quality_assessment_data: Optional[Dict[str, Any]]
    quality_complete: bool
    
    # PRISMA generation
    prisma_diagram_path: Optional[str]
    
    # Visualization generation
    visualization_paths: List[str]
    
    # Writing phase
    manuscript_sections: Dict[str, str]
    introduction: Optional[str]
    methods: Optional[str]
    results: Optional[str]
    discussion: Optional[str]
    abstract: Optional[str]
    manuscript: Optional[str]
    
    # Report generation
    report_path: Optional[str]
    
    # Manubot export
    manubot_export_path: Optional[str]
    
    # Style patterns (for humanization)
    style_patterns: Dict[str, Dict[str, List[str]]]
    
    # Metadata
    workflow_id: str
    output_dir: str
    checkpoint_dir: str
    current_phase: Optional[str]
    start_time: Optional[str]
    end_time: Optional[str]


def create_empty_state() -> WorkflowState:
    """
    Create an empty workflow state with default values.
    
    Returns:
        Empty WorkflowState
    """
    return WorkflowState(
        all_papers=[],
        unique_papers=[],
        screened_papers=[],
        eligible_papers=[],
        final_papers=[],
        enriched_papers=[],
        extracted_data=[],
        manuscript_sections={},
        style_patterns={},
        search_complete=False,
        extraction_complete=False,
        quality_complete=False,
        duplicates_removed=0,
        title_abstract_excluded=0,
        fulltext_excluded=0,
        fulltext_available_count=0,
        fulltext_unavailable_count=0,
        database_breakdown={},
        title_abstract_results=[],
        fulltext_results=[],
        visualization_paths=[],
    )


def validate_state_transition(
    to_phase: str,
    state: WorkflowState
) -> bool:
    """
    Validate that state is ready for phase transition.
    
    Args:
        to_phase: Target phase name
        state: Current workflow state
    
    Returns:
        True if transition is valid, False otherwise
    """
    # Define required state for each phase
    phase_requirements = {
        "deduplication": lambda s: len(s.get("all_papers", [])) > 0,
        "title_abstract_screening": lambda s: len(s.get("unique_papers", [])) > 0,
        "fulltext_screening": lambda s: len(s.get("screened_papers", [])) > 0,
        "paper_enrichment": lambda s: len(s.get("eligible_papers", [])) > 0,
        "data_extraction": lambda s: len(s.get("final_papers", [])) > 0,
        "quality_assessment": lambda s: len(s.get("extracted_data", [])) > 0,
        "article_writing": lambda s: len(s.get("extracted_data", [])) > 0,
    }
    
    if to_phase in phase_requirements:
        validator = phase_requirements[to_phase]
        return validator(state)
    
    return True  # Allow transition if no specific requirements
