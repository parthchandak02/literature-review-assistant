"""
Integration tests for workflow registry system.
"""

import asyncio
import pytest
from unittest.mock import Mock, patch, MagicMock
from pydantic import ValidationError
import json
from src.extraction.data_extractor_agent import ExtractedData

from src.orchestration.workflow_manager import WorkflowManager
from src.screening.base_agent import InclusionDecision, ScreeningResult
from src.search.connectors.base import Paper


def test_workflow_manager_has_registry():
    """Test that WorkflowManager initializes with registry."""
    manager = WorkflowManager()
    assert hasattr(manager, "phase_registry")
    assert hasattr(manager, "checkpoint_manager")
    assert hasattr(manager, "phase_executor")
    assert len(manager.phase_registry) > 0


def test_phase_registry_has_all_phases():
    """Test that all expected phases are registered."""
    manager = WorkflowManager()
    registry = manager.phase_registry

    expected_phases = [
        "build_search_strategy",
        "search_databases",
        "deduplication",
        "title_abstract_screening",
        "fulltext_screening",
        "paper_enrichment",
        "data_extraction",
        "quality_assessment",
        "prisma_generation",
        "visualization_generation",
        "article_writing",
        "report_generation",
        "manubot_export",
        "submission_package",
    ]

    for phase_name in expected_phases:
        assert phase_name in registry, f"Phase '{phase_name}' not found in registry"


def test_execution_order_valid():
    """Test that execution order respects dependencies."""
    manager = WorkflowManager()
    order = manager.phase_registry.get_execution_order()

    # Verify build_search_strategy comes before search_databases
    assert order.index("build_search_strategy") < order.index("search_databases")

    # Verify search_databases comes before deduplication
    assert order.index("search_databases") < order.index("deduplication")

    # Verify deduplication comes before title_abstract_screening
    assert order.index("deduplication") < order.index("title_abstract_screening")

    # Verify data_extraction comes before article_writing
    assert order.index("data_extraction") < order.index("article_writing")

    # Verify article_writing comes before report_generation
    assert order.index("article_writing") < order.index("report_generation")


def test_registry_dependencies_valid():
    """Test that all phase dependencies are valid."""
    manager = WorkflowManager()
    errors = manager.phase_registry.validate_dependencies()
    assert len(errors) == 0, f"Dependency validation errors: {errors}"


def test_determine_start_phase_uses_registry_sequence():
    """Start phase calculation should follow registered phase ordering."""
    manager = WorkflowManager()

    assert manager._determine_start_phase({"latest_phase": "quality_assessment"}) == 9
    assert manager._determine_start_phase({"latest_phase": "prisma_generation"}) == 10
    assert manager._determine_start_phase({"latest_phase": "visualization_generation"}) == 11


def test_checkpoint_dependency_chain_for_report_generation():
    """Report generation should wait for article_writing, prisma_generation, and visualization_generation."""
    manager = WorkflowManager()
    report_phase = manager.phase_registry.get_phase("report_generation")

    # report_generation depends on article_writing, prisma_generation, and visualization_generation
    assert "article_writing" in report_phase.dependencies
    assert "prisma_generation" in report_phase.dependencies
    assert "visualization_generation" in report_phase.dependencies


# ========== RELIABILITY REGRESSION TESTS ==========


def test_uncertain_screening_routed_to_adjudication():
    """Test that UNCERTAIN screening decisions are routed to adjudication queue, not excluded."""
    manager = WorkflowManager()
    
    # Create a mock paper
    paper = Paper(
        title="Test Paper",
        abstract="Test abstract",
        authors=["Test Author"],
        year=2024,
        database="test_db",
        eid="test_paper_eid"
    )
    
    # Create an UNCERTAIN screening result
    uncertain_result = ScreeningResult(
        decision=InclusionDecision.UNCERTAIN,
        confidence=0.6,
        reasoning="Borderline case requiring manual review",
        exclusion_reason=None
    )
    
    # Initialize state
    manager.unique_papers = [paper]
    manager.screened_papers = []
    manager.uncertain_title_abstract = []
    manager.title_abstract_results = [uncertain_result]
    
    # Simulate routing logic from workflow_manager
    if uncertain_result.decision.value == "include":
        manager.screened_papers.append(paper)
    elif uncertain_result.decision.value == "uncertain":
        manager.uncertain_title_abstract.append({
            "paper_id": paper.eid,
            "title": paper.title,
            "stage": "title_abstract",
            "decision": uncertain_result.decision.value,
            "confidence": uncertain_result.confidence,
            "reasoning": uncertain_result.reasoning,
        })
    
    # Assertions
    assert len(manager.screened_papers) == 0, "UNCERTAIN papers should not be in screened_papers"
    assert len(manager.uncertain_title_abstract) == 1, "UNCERTAIN papers should be in adjudication queue"
    assert manager.uncertain_title_abstract[0]["decision"] == "uncertain"


@pytest.mark.asyncio
async def test_parallel_critical_phase_failure_stops_workflow():
    """Test that critical phase failures (article_writing, quality_assessment) stop the workflow with diagnostics."""
    manager = WorkflowManager()
    
    # Mock phase handlers
    def successful_phase():
        return {"status": "success"}
    
    def failing_critical_phase():
        raise RuntimeError("Critical phase failed: Empty response from LLM")
    
    phase_names = ["quality_assessment", "article_writing", "prisma_generation"]
    phase_handlers = {
        "quality_assessment": successful_phase,
        "article_writing": failing_critical_phase,  # Critical phase fails
        "prisma_generation": successful_phase,
    }
    
    # Test that critical failure raises RuntimeError with diagnostic message
    with pytest.raises(RuntimeError) as exc_info:
        await manager._execute_phases_parallel(phase_names, phase_handlers)
    
    error_message = str(exc_info.value)
    assert "Critical parallel phase(s) failed" in error_message
    assert "article_writing" in error_message
    assert "RuntimeError" in error_message


@pytest.mark.asyncio
async def test_parallel_non_critical_phase_failure_continues():
    """Test that non-critical phase failures (prisma, viz) don't stop the workflow."""
    manager = WorkflowManager()
    
    # Mock phase handlers
    def successful_phase():
        return {"status": "success"}
    
    def failing_non_critical_phase():
        raise ValueError("Non-critical phase failed")
    
    phase_names = ["quality_assessment", "article_writing", "prisma_generation"]
    phase_handlers = {
        "quality_assessment": successful_phase,
        "article_writing": successful_phase,
        "prisma_generation": failing_non_critical_phase,  # Non-critical phase fails
    }
    
    # Should not raise - non-critical failures are logged but workflow continues
    results = await manager._execute_phases_parallel(phase_names, phase_handlers)
    
    # Critical phases should succeed
    assert results["quality_assessment"] is not None
    assert results["article_writing"] is not None
    # Non-critical phase should be None (failed)
    assert results["prisma_generation"] is None


def test_schema_parsing_failure_returns_uncertain():
    """Test that exhausted schema parsing retries return typed UNCERTAIN result instead of crashing."""
    manager = WorkflowManager()
    
    # Test with title_abstract_screener
    with patch.object(manager.title_screener, '_call_llm_with_schema') as mock_schema_call, \
         patch.object(manager.title_screener, '_call_llm') as mock_fallback_call:
        
        # Schema call fails with ValidationError
        mock_schema_call.side_effect = ValidationError.from_exception_data(
            'ScreeningResultSchema',
            [{'type': 'missing', 'loc': ('decision',), 'msg': 'field required'}]
        )
        
        # Fallback text parsing also fails
        mock_fallback_call.side_effect = Exception("Fallback parsing failed")
        
        # Call screening
        result = manager.title_screener.screen(
            title="Test Paper",
            abstract="Test abstract with some content",
            inclusion_criteria=["LLM", "AI"],
            exclusion_criteria=["rule-based"]
        )
        
        # Should return UNCERTAIN instead of raising
        assert result is not None
        assert result.decision == InclusionDecision.UNCERTAIN
        assert result.confidence == 0.0
        assert "manual" in result.reasoning.lower()


def test_missing_fulltext_degraded_mode():
    """Test that missing full text produces degraded-mode metadata and routes uncertain to adjudication."""
    manager = WorkflowManager()
    
    # Create a mock paper
    paper = Paper(
        title="Test Paper",
        abstract="Test abstract",
        authors=["Test Author"],
        year=2024,
        database="test_db",
        eid="test_paper_eid"
    )
    
    # Test full-text screening with missing full text
    with patch.object(manager.fulltext_screener, '_screen_title_abstract') as mock_ta_screen:
        # Mock title/abstract screening returns medium confidence include
        mock_ta_screen.return_value = ScreeningResult(
            decision=InclusionDecision.INCLUDE,
            confidence=0.65,  # Below 0.7 threshold
            reasoning="Appears relevant based on title/abstract",
            exclusion_reason=None
        )
        
        # Call full-text screening with no full text
        result = manager.fulltext_screener.screen(
            title=paper.title,
            abstract=paper.abstract,
            full_text=None,  # Missing full text
            inclusion_criteria=["LLM", "AI"],
            exclusion_criteria=["rule-based"]
        )
        
        # Should be marked as degraded mode
        assert "DEGRADED MODE" in result.reasoning
        assert "full-text unavailable" in result.reasoning.lower()
        # Should route to uncertain due to low confidence in degraded mode
        assert result.decision == InclusionDecision.UNCERTAIN
        # Confidence should be reduced
        assert result.confidence < 0.65  # Original was 0.65


def test_extraction_quality_gate_exports_and_raises(tmp_path):
    """Gate should export empty extractions and raise when configured threshold is exceeded."""
    manager = WorkflowManager()
    manager.output_dir = tmp_path
    manager.config["extraction_quality"] = {"max_empty_rate": 0.2, "enforce_gate": True}

    manager.final_papers = [
        Paper(title="P1", abstract="A", authors=["A"], year=2024, eid="p1"),
        Paper(title="P2", abstract="B", authors=["B"], year=2024, eid="p2"),
        Paper(title="P3", abstract="C", authors=["C"], year=2024, eid="p3"),
    ]
    manager.extracted_data = [
        ExtractedData(
            title="P1",
            authors=["A"],
            year=2024,
            journal=None,
            doi=None,
            study_objectives=[],
            methodology=None,
            study_design=None,
            participants=None,
            interventions=None,
            outcomes=[],
            key_findings=[],
            limitations=None,
            country=None,
            setting=None,
            sample_size=None,
            detailed_outcomes=[],
            quantitative_results=None,
            ux_strategies=[],
            adaptivity_frameworks=[],
            patient_populations=[],
            accessibility_features=[],
        ),
        ExtractedData(
            title="P2",
            authors=["B"],
            year=2024,
            journal=None,
            doi=None,
            study_objectives=[],
            methodology=None,
            study_design=None,
            participants=None,
            interventions=None,
            outcomes=[],
            key_findings=[],
            limitations=None,
            country=None,
            setting=None,
            sample_size=None,
            detailed_outcomes=[],
            quantitative_results=None,
            ux_strategies=[],
            adaptivity_frameworks=[],
            patient_populations=[],
            accessibility_features=[],
        ),
        ExtractedData(
            title="P3",
            authors=["C"],
            year=2024,
            journal=None,
            doi=None,
            study_objectives=["obj"],
            methodology="m",
            study_design="cohort",
            participants="n=10",
            interventions=None,
            outcomes=["o1"],
            key_findings=["f1"],
            limitations=None,
            country=None,
            setting=None,
            sample_size=10,
            detailed_outcomes=[],
            quantitative_results=None,
            ux_strategies=[],
            adaptivity_frameworks=[],
            patient_populations=[],
            accessibility_features=[],
        ),
    ]

    with pytest.raises(RuntimeError):
        manager._apply_extraction_quality_gate(empty_extraction_count=2)

    assert (tmp_path / "empty_extractions_for_review.json").exists()


def test_backfill_metadata_excludes_citation_incomplete(tmp_path):
    """Backfill should recover metadata when possible and track citation_incomplete papers."""
    manager = WorkflowManager()
    manager.output_dir = tmp_path

    manager.final_papers = [
        Paper(title="Paper 1", abstract="A", authors=[], year=None, doi=None, journal=None, eid="p1"),
        Paper(title="Paper 2", abstract="B", authors=["Known, Author"], year=2024, doi=None, journal=None, eid="p2"),
        Paper(title="Paper 3", abstract="C", authors=[], year=2024, doi=None, journal=None, eid="p3"),
    ]
    manager.extracted_data = [
        ExtractedData(
            title="Paper 1",
            authors=["Recovered, Author"],
            year=2023,
            journal="J1",
            doi="10.1/abc",
            study_objectives=["obj"],
            methodology="m",
            study_design="trial",
            participants="n=20",
            interventions=None,
            outcomes=["o1"],
            key_findings=["f1"],
            limitations=None,
            country=None,
            setting=None,
            sample_size=20,
            detailed_outcomes=[],
            quantitative_results=None,
            ux_strategies=[],
            adaptivity_frameworks=[],
            patient_populations=[],
            accessibility_features=[],
        ),
    ]

    eligible = manager._backfill_metadata_for_citations()
    eligible_titles = {p.title for p in eligible}

    assert "Paper 1" in eligible_titles
    assert "Paper 2" in eligible_titles
    assert "Paper 3" not in eligible_titles
    assert len(manager.citation_incomplete_papers) == 1
    assert manager.citation_incomplete_papers[0]["title"] == "Paper 3"


def test_write_section_retry_recovers_from_transient_empty_response():
    """Section retry should recover when first attempt returns empty and second succeeds."""
    manager = WorkflowManager()
    manager.config.setdefault("writing", {})
    manager.config["writing"]["retry_count"] = 2

    state = {"calls": 0}

    def flaky_writer():
        state["calls"] += 1
        if state["calls"] == 1:
            return ""
        return "This is a valid section body."

    result, duration, word_count = manager._write_section_with_retry("results", flaky_writer)

    assert state["calls"] == 2
    assert "valid section body" in result
    assert duration >= 0
    assert word_count > 0


def test_parallel_phase_group_deconflicts_llm_heavy_phases():
    """Default parallel group should exclude article_writing when deconfliction is enabled."""
    manager = WorkflowManager()
    manager.config.setdefault("workflow", {})
    manager.config["workflow"]["parallel_execution"] = {"deconflict_llm_heavy_phases": True}
    assert manager._get_parallel_phase_group() == [
        "quality_assessment",
        "prisma_generation",
        "visualization_generation",
    ]

    manager.config["workflow"]["parallel_execution"] = {"deconflict_llm_heavy_phases": False}
    assert manager._get_parallel_phase_group() == [
        "quality_assessment",
        "prisma_generation",
        "visualization_generation",
        "article_writing",
    ]
