"""
Integration tests for workflow registry system.
"""

from src.orchestration.workflow_manager import WorkflowManager


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
