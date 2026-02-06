"""
Integration Test Utilities

Helper functions for integration testing of workflow components.
Provides mock data generators and validation helpers.
"""

from typing import List, Dict, Any
from pathlib import Path
import json

from src.search.connectors.base import Paper
from src.extraction.data_extractor_agent import ExtractedData
from src.search.database_connectors import MockConnector


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


def create_mock_extracted_data_with_null_methodology(count: int) -> List[ExtractedData]:
    """
    Generate mock ExtractedData objects with null methodology for testing.
    
    Args:
        count: Number of extracted data objects to generate
    
    Returns:
        List of ExtractedData objects
    """
    extracted_data = []
    
    for i in range(count):
        # Some with null methodology, some with actual methodology
        methodology = None if i % 2 == 0 else f"Research methodology {i+1}"
        
        data = ExtractedData(
            title=f"Test Paper {i+1}",
            authors=[f"Author {i+1}"],
            year=2020 + (i % 5),
            journal=f"Journal {i+1}",
            doi=f"10.1000/test.{i+1}",
            study_objectives=[f"Objective {i+1}"],
            methodology=methodology,  # Can be None
            study_design="RCT" if i % 3 == 0 else None,
            participants=f"Participants {i+1}",
            interventions=f"Intervention {i+1}",
            outcomes=[f"Outcome {i+1}"],
            key_findings=[f"Finding {i+1}"],
            limitations=f"Limitation {i+1}",
            country="USA",
            setting="Hospital",
            sample_size=100 + i * 10,
            detailed_outcomes=[f"Detailed outcome {i+1}"],
            quantitative_results=f"Results {i+1}",
            ux_strategies=[],
            adaptivity_frameworks=[],
            patient_populations=[],
            accessibility_features=[],
        )
        extracted_data.append(data)
    
    return extracted_data


def validate_extracted_data(extracted_data: ExtractedData) -> List[str]:
    """
    Validate extracted data and return list of issues.
    
    Args:
        extracted_data: ExtractedData object to validate
    
    Returns:
        List of validation issues (empty if valid)
    """
    issues = []
    
    if not extracted_data.title:
        issues.append("Missing title")
    
    if not extracted_data.authors:
        issues.append("Missing authors")
    
    # Methodology can be None, so we don't validate it
    
    if not extracted_data.study_objectives:
        issues.append("Missing study objectives")
    
    return issues


def validate_phase_output(phase_name: str, output_dir: Path) -> Dict[str, Any]:
    """
    Validate output from a workflow phase.
    
    Args:
        phase_name: Name of the phase
        output_dir: Output directory
    
    Returns:
        Dictionary with validation results
    """
    results = {
        "phase": phase_name,
        "valid": True,
        "issues": [],
        "files_found": [],
    }
    
    # Check for expected output files based on phase
    expected_files = {
        "search_databases": ["papers.json"],
        "deduplication": ["deduplicated_papers.json"],
        "title_abstract_screening": ["screened_papers.json"],
        "fulltext_screening": ["final_papers.json"],
        "data_extraction": ["extracted_data.json"],
        "quality_assessment": ["quality_assessments.json"],
    }
    
    if phase_name in expected_files:
        for filename in expected_files[phase_name]:
            file_path = output_dir / filename
            if file_path.exists():
                results["files_found"].append(filename)
            else:
                results["valid"] = False
                results["issues"].append(f"Missing expected file: {filename}")
    
    return results


def create_mock_database_searcher() -> Any:
    """
    Create a mock database searcher for testing.
    
    Returns:
        MultiDatabaseSearcher with mock connectors
    """
    from src.search.multi_database_searcher import MultiDatabaseSearcher
    
    searcher = MultiDatabaseSearcher()
    
    # Add mock connectors
    searcher.add_connector(MockConnector("MockDB1"))
    searcher.add_connector(MockConnector("MockDB2"))
    
    return searcher


def validate_checkpoint(checkpoint_path: Path) -> Dict[str, Any]:
    """
    Validate a checkpoint file.
    
    Args:
        checkpoint_path: Path to checkpoint file
    
    Returns:
        Dictionary with validation results
    """
    results = {
        "valid": False,
        "issues": [],
        "data": None,
    }
    
    if not checkpoint_path.exists():
        results["issues"].append(f"Checkpoint file not found: {checkpoint_path}")
        return results
    
    try:
        with open(checkpoint_path, 'r') as f:
            data = json.load(f)
        
        # Basic validation
        if "phase" not in data:
            results["issues"].append("Missing 'phase' field")
        elif "papers" not in data and "final_papers" not in data:
            results["issues"].append("Missing papers data")
        else:
            results["valid"] = True
            results["data"] = data
    
    except json.JSONDecodeError as e:
        results["issues"].append(f"Invalid JSON: {e}")
    except Exception as e:
        results["issues"].append(f"Error reading checkpoint: {e}")
    
    return results


def compare_papers(papers1: List[Paper], papers2: List[Paper]) -> Dict[str, Any]:
    """
    Compare two lists of papers.
    
    Args:
        papers1: First list of papers
        papers2: Second list of papers
    
    Returns:
        Dictionary with comparison results
    """
    results = {
        "count_match": len(papers1) == len(papers2),
        "count1": len(papers1),
        "count2": len(papers2),
        "titles_match": True,
        "differences": [],
    }
    
    if len(papers1) != len(papers2):
        results["differences"].append(
            f"Count mismatch: {len(papers1)} vs {len(papers2)}"
        )
    
    # Compare titles
    titles1 = {p.title for p in papers1}
    titles2 = {p.title for p in papers2}
    
    if titles1 != titles2:
        results["titles_match"] = False
        missing_in_2 = titles1 - titles2
        missing_in_1 = titles2 - titles1
        if missing_in_2:
            results["differences"].append(f"Missing in papers2: {missing_in_2}")
        if missing_in_1:
            results["differences"].append(f"Missing in papers1: {missing_in_1}")
    
    return results
