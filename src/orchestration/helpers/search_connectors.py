from __future__ import annotations

from src.search.arxiv import ArxivConnector
from src.search.base import SearchConnector
from src.search.clinicaltrials import ClinicalTrialsConnector
from src.search.core import CoreConnector
from src.search.crossref import CrossrefConnector
from src.search.dblp import DblpConnector
from src.search.embase import EmbaseConnector
from src.search.europepmc import EuropePmcConnector
from src.search.ieee_xplore import IEEEXploreConnector
from src.search.openalex import OpenAlexConnector
from src.search.perplexity_search import PerplexitySearchConnector
from src.search.pubmed import PubMedConnector
from src.search.scopus import ScopusConnector
from src.search.semantic_scholar import SemanticScholarConnector
from src.search.web_of_science import WebOfScienceConnector


def build_connectors(workflow_id: str, target_databases: list[str]) -> tuple[list[SearchConnector], dict[str, str]]:
    connectors: list[SearchConnector] = []
    failures: dict[str, str] = {}
    for name in target_databases:
        normalized = name.lower()
        try:
            if normalized == "openalex":
                connectors.append(OpenAlexConnector(workflow_id))
            elif normalized == "pubmed":
                connectors.append(PubMedConnector(workflow_id))
            elif normalized == "arxiv":
                connectors.append(ArxivConnector(workflow_id))
            elif normalized == "ieee_xplore":
                connectors.append(IEEEXploreConnector(workflow_id))
            elif normalized == "semantic_scholar":
                connectors.append(SemanticScholarConnector(workflow_id))
            elif normalized == "crossref":
                connectors.append(CrossrefConnector(workflow_id))
            elif normalized == "perplexity_search":
                connectors.append(PerplexitySearchConnector(workflow_id))
            elif normalized == "scopus":
                connectors.append(ScopusConnector(workflow_id))
            elif normalized in {"web_of_science", "wos"}:
                connectors.append(WebOfScienceConnector(workflow_id))
            elif normalized in {"clinicaltrials", "clinicaltrials_gov"}:
                connectors.append(ClinicalTrialsConnector(workflow_id))
            elif normalized == "dblp":
                connectors.append(DblpConnector(workflow_id))
            elif normalized == "core":
                connectors.append(CoreConnector(workflow_id))
            elif normalized == "europepmc":
                connectors.append(EuropePmcConnector(workflow_id))
            elif normalized == "embase":
                connectors.append(EmbaseConnector(workflow_id))
            else:
                failures[normalized] = "unsupported_connector"
        except Exception as exc:
            failures[normalized] = f"{type(exc).__name__}: {exc}"
    return connectors, failures
