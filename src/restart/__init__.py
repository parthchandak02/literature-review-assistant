"""Restart architecture modules for the next workflow generation."""

from .capability_contract import (
    DEFAULT_CAPABILITY_CONTRACT,
    CapabilityContract,
    CapabilityContractValidation,
)
from .citation_publishing import CitationPublishingPipeline, PublicationArtifact
from .fulltext_pipeline import FullTextResult, FullTextRetrievalPipeline
from .mvp_pipeline import MVPGraphPipeline, MVPGraphState
from .orchestration_profile import OrchestrationDecision, OrchestrationProfile
from .reliability_gates import GateResult, ReliabilityGateRunner
from .scholarly_ingestion import ScholarlyIngestionHub

__all__ = [
    "DEFAULT_CAPABILITY_CONTRACT",
    "CapabilityContract",
    "CapabilityContractValidation",
    "CitationPublishingPipeline",
    "FullTextResult",
    "FullTextRetrievalPipeline",
    "GateResult",
    "MVPGraphPipeline",
    "MVPGraphState",
    "OrchestrationDecision",
    "OrchestrationProfile",
    "PublicationArtifact",
    "ReliabilityGateRunner",
    "ScholarlyIngestionHub",
]
