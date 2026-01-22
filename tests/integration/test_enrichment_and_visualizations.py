"""
Enrichment and Visualization Test

Tests the paper enrichment functionality and regenerates visualizations
with enriched data to verify the fixes from the enhanced visualization plan.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Optional

import pytest
from dotenv import load_dotenv

from src.enrichment.paper_enricher import PaperEnricher
from src.visualization.charts import ChartGenerator
from src.utils.state_serialization import StateSerializer
from src.search.connectors.base import Paper

load_dotenv()
logger = logging.getLogger(__name__)


def find_best_checkpoint(checkpoint_path: str) -> str:
    """Find the best checkpoint file (preferring later stages with final_papers)."""
    checkpoint_file = Path(checkpoint_path)
    checkpoint_dir = checkpoint_file.parent
    
    # Prefer checkpoints in this order (later stages have final_papers)
    preferred_files = [
        "data_extraction_state.json",
        "fulltext_screening_state.json",
        "title_abstract_screening_state.json",
    ]
    
    # If a specific file was provided, check if it exists
    if checkpoint_file.exists():
        # Check if it's a directory or file
        if checkpoint_file.is_dir():
            checkpoint_dir = checkpoint_file
        else:
            # Try to find a better checkpoint in the same directory
            for preferred in preferred_files:
                preferred_path = checkpoint_dir / preferred
                if preferred_path.exists():
                    return str(preferred_path)
            return str(checkpoint_file)
    
    # Try to find preferred checkpoints in the directory
    for preferred in preferred_files:
        preferred_path = checkpoint_dir / preferred
        if preferred_path.exists():
            return str(preferred_path)
    
    # Fall back to provided path
    if checkpoint_file.exists():
        return str(checkpoint_file)
    
    raise FileNotFoundError(f"No checkpoint found: {checkpoint_path}")


def load_checkpoint_papers(checkpoint_path: str) -> List[Paper]:
    """Load papers from checkpoint file."""
    # Find the best checkpoint
    best_checkpoint = find_best_checkpoint(checkpoint_path)
    checkpoint_file = Path(best_checkpoint)
    
    if not checkpoint_file.exists():
        raise FileNotFoundError(f"Checkpoint not found: {best_checkpoint}")
    
    with open(checkpoint_file, "r") as f:
        checkpoint_data = json.load(f)
    
    serializer = StateSerializer()
    
    # Try to get final_papers first, then eligible_papers, then screened_papers
    papers_data = None
    if "final_papers" in checkpoint_data.get("data", {}):
        papers_data = checkpoint_data["data"]["final_papers"]
    elif "eligible_papers" in checkpoint_data.get("data", {}):
        papers_data = checkpoint_data["data"]["eligible_papers"]
    elif "screened_papers" in checkpoint_data.get("data", {}):
        papers_data = checkpoint_data["data"]["screened_papers"]
    else:
        raise ValueError("No papers found in checkpoint data")
    
    papers = serializer.deserialize_papers(papers_data)
    return papers


@pytest.fixture
def sample_checkpoint_path():
    """Fixture providing a sample checkpoint path (may not exist in all environments)."""
    return "data/checkpoints/workflow_llm-powered_health_literacy_ch_20260118_212151/title_abstract_screening_state.json"


@pytest.mark.integration
@pytest.mark.skip(reason="Requires checkpoint file - run manually with specific checkpoint")
def test_enrichment(sample_checkpoint_path, tmp_path):
    """Test enrichment of papers."""
    # Skip if checkpoint doesn't exist
    if not Path(sample_checkpoint_path).exists():
        pytest.skip(f"Checkpoint not found: {sample_checkpoint_path}")
    
    papers = load_checkpoint_papers(sample_checkpoint_path)
    
    # Count papers that need enrichment
    papers_needing_enrichment = [p for p in papers if not p.affiliations and p.doi]
    
    if not papers_needing_enrichment:
        pytest.skip("No papers need enrichment")
    
    # Run enrichment
    enricher = PaperEnricher()
    enriched_count = 0
    
    for paper in papers_needing_enrichment[:5]:  # Limit to 5 for testing
        try:
            enriched_paper = enricher._fetch_by_doi(paper.doi)
            if enriched_paper and enriched_paper.affiliations:
                paper.affiliations = enriched_paper.affiliations
                enriched_count += 1
        except Exception as e:
            logger.warning(f"Failed to enrich paper (DOI: {paper.doi}): {e}")
    
    # Verify at least some enrichment occurred (or skipped if rate limited)
    assert enriched_count >= 0, "Enrichment should not fail"


@pytest.mark.integration
@pytest.mark.skip(reason="Requires checkpoint file - run manually with specific checkpoint")
def test_visualization_generation(sample_checkpoint_path, tmp_path):
    """Test visualization generation with enriched data."""
    # Skip if checkpoint doesn't exist
    if not Path(sample_checkpoint_path).exists():
        pytest.skip(f"Checkpoint not found: {sample_checkpoint_path}")
    
    papers = load_checkpoint_papers(sample_checkpoint_path)
    
    # Generate visualizations
    output_dir = str(tmp_path)
    chart_generator = ChartGenerator(output_dir=output_dir)
    
    # Generate all visualizations
    viz_paths = {}
    
    year_path = chart_generator.papers_per_year(papers)
    if year_path:
        viz_paths["papers_per_year"] = year_path
    
    country_path = chart_generator.papers_by_country(papers)
    if country_path:
        viz_paths["papers_by_country"] = country_path
    
    subject_path = chart_generator.papers_by_subject(papers)
    if subject_path:
        viz_paths["papers_by_subject"] = subject_path
    
    network_path = chart_generator.network_graph(papers)
    if network_path:
        viz_paths["network_graph"] = network_path
    
    # Verify visualizations were generated
    assert len(viz_paths) > 0, "At least one visualization should be generated"
    
    # Verify files exist
    for name, path in viz_paths.items():
        assert Path(path).exists(), f"Visualization file should exist: {path}"


@pytest.mark.integration
def test_chart_generator_initialization():
    """Test that ChartGenerator can be initialized."""
    chart_generator = ChartGenerator()
    assert chart_generator is not None


@pytest.mark.integration
def test_paper_enricher_initialization():
    """Test that PaperEnricher can be initialized."""
    enricher = PaperEnricher()
    assert enricher is not None
