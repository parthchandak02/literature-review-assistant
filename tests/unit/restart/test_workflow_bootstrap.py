from src.restart.workflow_bootstrap import build_restart_services


def test_workflow_bootstrap_builds_core_services(tmp_path):
    services = build_restart_services(output_dir=str(tmp_path), contact_email="test@example.com")
    assert "capability_contract" in services
    assert "orchestration_decision" in services
    assert "ingestion_hub" in services
    assert "fulltext_pipeline" in services
    assert "citation_pipeline" in services
    assert "reliability_gates" in services
