"""Factory helpers to bootstrap the restart architecture with existing components."""

from __future__ import annotations

from .capability_contract import DEFAULT_CAPABILITY_CONTRACT
from .citation_publishing import CitationPublishingPipeline
from .fulltext_pipeline import FullTextRetrievalPipeline
from .orchestration_profile import OrchestrationProfile, choose_orchestration_backend
from .reliability_gates import ReliabilityGateRunner
from .scholarly_ingestion import ScholarlyIngestionHub


def build_restart_services(output_dir: str, contact_email: str | None = None) -> dict[str, object]:
    """Creates the core services required by the restart plan."""

    orchestration_decision = choose_orchestration_backend(
        estimated_runtime_hours=4.0,
        max_human_wait_hours=2.0,
        uses_cross_service_workers=False,
        profile=OrchestrationProfile(),
    )
    return {
        "capability_contract": DEFAULT_CAPABILITY_CONTRACT,
        "orchestration_decision": orchestration_decision,
        "ingestion_hub": ScholarlyIngestionHub(contact_email=contact_email),
        "fulltext_pipeline": FullTextRetrievalPipeline(),
        "citation_pipeline": CitationPublishingPipeline(output_dir=output_dir),
        "reliability_gates": ReliabilityGateRunner(),
    }
