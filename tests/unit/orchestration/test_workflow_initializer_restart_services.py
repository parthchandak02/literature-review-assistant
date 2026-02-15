from src.orchestration.workflow_initializer import WorkflowInitializer


def test_workflow_initializer_exposes_restart_services():
    initializer = WorkflowInitializer("config/workflow.yaml")
    services = initializer.get_restart_services()
    assert "capability_contract" in services
    assert "orchestration_decision" in services
    assert "ingestion_hub" in services
    assert "fulltext_pipeline" in services
    assert "citation_pipeline" in services
    assert "reliability_gates" in services
