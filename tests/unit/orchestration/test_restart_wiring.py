from types import SimpleNamespace

import pytest

from src.orchestration.workflow_manager import WorkflowManager
from src.restart.reliability_gates import GateResult


class _FakeIngestionHub:
    def search_core_sources(self, query: str, per_source_limit: int):
        assert query
        assert per_source_limit > 0
        return {
            "openalex": [
                {
                    "title": "Fallback title",
                    "abstract": "Fallback abstract text that is long enough for conversion.",
                    "doi": "10.1000/fallback",
                    "url": "https://example.com/paper",
                }
            ]
        }


def test_search_via_restart_ingestion_returns_papers():
    manager = WorkflowManager.__new__(WorkflowManager)
    manager.restart_ingestion_hub = _FakeIngestionHub()
    papers = manager._search_via_restart_ingestion("test query", max_results=5)
    assert len(papers) == 1
    assert papers[0].database == "openalex"
    assert papers[0].doi == "10.1000/fallback"


def test_restart_pre_export_checks_strict_mode_raises():
    manager = WorkflowManager.__new__(WorkflowManager)
    manager.restart_runtime_checks = True
    manager.restart_strict_checks = True
    manager.restart_services = {
        "reliability_gates": SimpleNamespace(
            run=lambda state: [GateResult("citation_quality", False, "invalid ratio")]
        )
    }
    manager._build_restart_validation_state = lambda sections: {
        "prisma_diagram_path": None,
        "citation_validation_passed": False,
        "checkpoint_resume_enabled": True,
        "manuscript_sections": sections,
        "invalid_citation_count": 1,
        "total_citation_count": 2,
        "total_cost_usd": 0.1,
    }
    manager._log_gate_results = lambda gate_results: None

    with pytest.raises(RuntimeError):
        manager._run_restart_pre_export_checks({"introduction": "draft"})


def test_restart_pre_export_checks_non_strict_warns_only():
    manager = WorkflowManager.__new__(WorkflowManager)
    manager.restart_runtime_checks = True
    manager.restart_strict_checks = False
    manager.restart_services = {
        "reliability_gates": SimpleNamespace(
            run=lambda state: [GateResult("citation_quality", False, "invalid ratio")]
        )
    }
    manager._build_restart_validation_state = lambda sections: {
        "prisma_diagram_path": None,
        "citation_validation_passed": False,
        "checkpoint_resume_enabled": True,
        "manuscript_sections": sections,
        "invalid_citation_count": 1,
        "total_citation_count": 2,
        "total_cost_usd": 0.1,
    }
    manager._log_gate_results = lambda gate_results: None

    manager._run_restart_pre_export_checks({"introduction": "draft"})
