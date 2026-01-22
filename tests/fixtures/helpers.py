"""
Test Helpers

Utilities for generating mock test data and managing test state.
"""

from typing import List, Dict, Any
from dataclasses import asdict

from src.search.connectors.base import Paper
from src.screening.base_agent import ScreeningResult, InclusionDecision
from src.extraction.data_extractor_agent import ExtractedData


def create_mock_papers(count: int, topic: str = "test topic") -> List[Paper]:
    """
    Generate mock Paper objects for testing.
    
    Args:
        count: Number of papers to generate
        topic: Topic for generating relevant titles
    
    Returns:
        List of Paper objects
    """
    papers = []
    countries = ["USA", "UK", "Canada", "Australia", "Germany", "France"]
    subjects = ["Machine Learning", "Health", "Education", "Technology"]
    journals = ["Journal A", "Journal B", "Conference C"]
    
    for i in range(count):
        paper = Paper(
            title=f"{topic} Research Paper {i+1}",
            abstract=f"This paper discusses {topic} and presents findings from study {i+1}. "
                     f"It explores various aspects and provides insights into the field.",
            authors=[f"Author {i+1}A", f"Author {i+1}B", f"Author {i+1}C"],
            year=2020 + (i % 5),
            doi=f"10.1000/test.{i+1}",
            journal=journals[i % len(journals)],
            database=["PubMed", "arXiv", "Semantic Scholar"][i % 3],
            url=f"https://example.com/paper{i+1}",
            keywords=[topic, subjects[i % len(subjects)], "research"],
            affiliations=[f"University {i+1}", f"Institution {i+1}"],
            subjects=[subjects[i % len(subjects)]],
            country=countries[i % len(countries)],
        )
        papers.append(paper)
    
    return papers


def create_mock_screening_results(
    papers: List[Paper],
    include_ratio: float = 0.7,
) -> List[ScreeningResult]:
    """
    Generate mock ScreeningResult objects.
    
    Args:
        papers: List of papers to create results for
        include_ratio: Ratio of papers to include (default: 0.7)
    
    Returns:
        List of ScreeningResult objects
    """
    results = []
    import random
    
    for i, paper in enumerate(papers):
        # Determine decision based on ratio
        if i < len(papers) * include_ratio:
            decision = InclusionDecision.INCLUDE
            confidence = 0.7 + random.random() * 0.3  # 0.7-1.0
            reasoning = f"Paper is relevant to the research topic: {paper.title}"
            exclusion_reason = None
        else:
            decision = InclusionDecision.EXCLUDE
            confidence = 0.5 + random.random() * 0.3  # 0.5-0.8
            reasoning = "Paper does not meet inclusion criteria"
            exclusion_reason = "Not relevant to research question"
        
        result = ScreeningResult(
            decision=decision,
            confidence=confidence,
            reasoning=reasoning,
            exclusion_reason=exclusion_reason,
        )
        results.append(result)
    
    return results


def create_mock_extracted_data(
    papers: List[Paper],
) -> List[ExtractedData]:
    """
    Generate mock ExtractedData objects.
    
    Args:
        papers: List of papers to create extracted data for
    
    Returns:
        List of ExtractedData objects
    """
    extracted = []
    
    for paper in papers:
        data = ExtractedData(
            title=paper.title,
            authors=paper.authors,
            year=paper.year,
            journal=paper.journal,
            doi=paper.doi,
            study_objectives=[
                f"Objective 1 for {paper.title}",
                f"Objective 2 for {paper.title}",
            ],
            methodology="Mixed methods study with quantitative and qualitative components",
            study_design="Randomized controlled trial",
            participants=f"Sample size: {50 + len(paper.authors) * 10} participants",
            interventions="Intervention group received treatment, control group received standard care",
            outcomes=["Outcome 1", "Outcome 2", "Outcome 3"],
            key_findings=[
                f"Finding 1 from {paper.title}",
                f"Finding 2 from {paper.title}",
            ],
            limitations="Sample size may limit generalizability",
            ux_strategies=["User-centered design", "Iterative prototyping"],
            adaptivity_frameworks=["Framework A", "Framework B"],
            patient_populations=["Population 1", "Population 2"],
            accessibility_features=["Feature 1", "Feature 2"],
        )
        extracted.append(data)
    
    return extracted


def load_state_from_checkpoint(checkpoint_path: str) -> Dict[str, Any]:
    """
    Load and deserialize state from checkpoint.
    
    Args:
        checkpoint_path: Path to checkpoint file
    
    Returns:
        State dictionary
    """
    import json
    from pathlib import Path
    
    checkpoint_file = Path(checkpoint_path)
    if not checkpoint_file.exists():
        raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")
    
    with open(checkpoint_file, "r") as f:
        return json.load(f)


def save_test_state(
    state: Dict[str, Any],
    output_dir: str,
    filename: str = "test_state.json",
) -> str:
    """
    Save test state to JSON file.
    
    Args:
        state: State dictionary
        output_dir: Output directory
        filename: Output filename
    
    Returns:
        Path to saved file
    """
    import json
    from pathlib import Path
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    file_path = output_path / filename
    
    with open(file_path, "w") as f:
        json.dump(state, f, indent=2, default=str)
    
    return str(file_path)


def serialize_papers_for_json(papers: List[Paper]) -> List[Dict[str, Any]]:
    """Convert Paper objects to JSON-serializable dicts."""
    return [asdict(paper) for paper in papers]


def serialize_screening_results_for_json(
    results: List[ScreeningResult],
) -> List[Dict[str, Any]]:
    """Convert ScreeningResult objects to JSON-serializable dicts."""
    serialized = []
    for result in results:
        serialized.append({
            "decision": result.decision.value,
            "confidence": result.confidence,
            "reasoning": result.reasoning,
            "exclusion_reason": result.exclusion_reason,
        })
    return serialized


def serialize_extracted_data_for_json(
    data: List[ExtractedData],
) -> List[Dict[str, Any]]:
    """Convert ExtractedData objects to JSON-serializable dicts."""
    return [item.to_dict() for item in data]
