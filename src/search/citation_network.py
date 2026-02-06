"""
Citation Network Builder

Builds citation networks from papers, tracks citing papers, and exports network graphs.
"""

from typing import List, Dict, Optional, Any
import logging
from dataclasses import dataclass

from .connectors.base import Paper
from .connectors.google_scholar_connector import GoogleScholarConnector

logger = logging.getLogger(__name__)


@dataclass
class CitationEdge:
    """Represents a citation relationship between two papers."""
    citing_paper_id: str  # ID of paper that cites
    cited_paper_id: str   # ID of paper being cited
    citing_paper_title: Optional[str] = None
    cited_paper_title: Optional[str] = None


class CitationNetworkBuilder:
    """
    Builds citation networks from papers.

    Tracks citation relationships and can export network graphs
    for visualization.
    """

    def __init__(self, google_scholar_connector: Optional[GoogleScholarConnector] = None):
        """
        Initialize citation network builder.

        Args:
            google_scholar_connector: Optional Google Scholar connector for citation tracking
        """
        self.google_scholar_connector = google_scholar_connector
        self.edges: List[CitationEdge] = []
        self.papers: Dict[str, Paper] = {}  # Map paper ID to Paper object
        self._paper_id_map: Dict[str, str] = {}  # Map DOI/EID/etc to internal ID

    def add_paper(self, paper: Paper) -> str:
        """
        Add a paper to the network.

        Args:
            paper: Paper object to add

        Returns:
            Internal paper ID
        """
        # Generate ID from DOI, EID, or title
        paper_id = self._get_paper_id(paper)

        self.papers[paper_id] = paper

        # Map various identifiers to internal ID
        if paper.doi:
            self._paper_id_map[paper.doi] = paper_id
        if paper.eid:
            self._paper_id_map[paper.eid] = paper_id
        if paper.scopus_id:
            self._paper_id_map[paper.scopus_id] = paper_id
        if paper.scholar_id:
            self._paper_id_map[paper.scholar_id] = paper_id

        return paper_id

    def add_citation(self, citing_paper: Paper, cited_paper: Paper):
        """
        Add a citation relationship.

        Args:
            citing_paper: Paper that cites
            cited_paper: Paper being cited
        """
        citing_id = self._get_paper_id(citing_paper)
        cited_id = self._get_paper_id(cited_paper)

        # Add papers if not already in network
        if citing_id not in self.papers:
            self.add_paper(citing_paper)
        if cited_id not in self.papers:
            self.add_paper(cited_paper)

        # Add edge
        edge = CitationEdge(
            citing_paper_id=citing_id,
            cited_paper_id=cited_id,
            citing_paper_title=citing_paper.title,
            cited_paper_title=cited_paper.title,
        )

        # Avoid duplicates
        if not any(e.citing_paper_id == citing_id and e.cited_paper_id == cited_id for e in self.edges):
            self.edges.append(edge)

    def find_citing_papers(
        self,
        paper: Paper,
        max_results: int = 100,
    ) -> List[Paper]:
        """
        Find papers that cite the given paper.

        Args:
            paper: Paper to find citations for
            max_results: Maximum number of citing papers

        Returns:
            List of Paper objects that cite the given paper
        """
        if not self.google_scholar_connector:
            logger.warning("Google Scholar connector required for citation tracking")
            return []

        try:
            citing_papers = self.google_scholar_connector.get_cited_by(paper, max_results)

            # Add citation relationships
            for citing_paper in citing_papers:
                self.add_citation(citing_paper, paper)

            return citing_papers
        except Exception as e:
            logger.error(f"Error finding citing papers: {e}")
            return []

    def build_network_from_papers(self, papers: List[Paper]) -> Dict[str, Any]:
        """
        Build citation network from a list of papers.

        Args:
            papers: List of Paper objects

        Returns:
            Dictionary with network data (nodes, edges, statistics)
        """
        # Add all papers to network
        for paper in papers:
            self.add_paper(paper)

        # Try to find citation relationships
        # This is limited without full citation data, but we can use
        # citation_count and cited_by_count if available
        citation_stats = {
            "total_papers": len(self.papers),
            "total_edges": len(self.edges),
            "papers_with_citations": sum(1 for p in self.papers.values() if p.citation_count),
            "papers_cited_by_others": sum(1 for p in self.papers.values() if p.cited_by_count),
        }

        return {
            "nodes": [self._paper_to_node(p) for p in self.papers.values()],
            "edges": [self._edge_to_dict(e) for e in self.edges],
            "statistics": citation_stats,
        }

    def export_networkx_graph(self):
        """
        Export network as NetworkX graph for visualization.

        Returns:
            networkx.Graph object
        """
        try:
            import networkx as nx
        except ImportError:
            logger.error("networkx not available. Install with: pip install networkx")
            return None

        G = nx.DiGraph()  # Directed graph for citations

        # Add nodes
        for paper_id, paper in self.papers.items():
            G.add_node(paper_id, **self._paper_to_node(paper))

        # Add edges
        for edge in self.edges:
            G.add_edge(
                edge.citing_paper_id,
                edge.cited_paper_id,
                citing_title=edge.citing_paper_title,
                cited_title=edge.cited_paper_title,
            )

        return G

    def get_citation_statistics(self) -> Dict[str, Any]:
        """
        Get citation statistics for the network.

        Returns:
            Dictionary with statistics
        """
        if not self.papers:
            return {}

        citation_counts = [p.citation_count for p in self.papers.values() if p.citation_count]

        stats = {
            "total_papers": len(self.papers),
            "total_citations": sum(citation_counts) if citation_counts else 0,
            "average_citations": sum(citation_counts) / len(citation_counts) if citation_counts else 0,
            "max_citations": max(citation_counts) if citation_counts else 0,
            "papers_with_citations": len(citation_counts),
            "citation_edges": len(self.edges),
        }

        return stats

    def _get_paper_id(self, paper: Paper) -> str:
        """Generate a unique ID for a paper."""
        if paper.doi:
            return f"doi:{paper.doi}"
        elif paper.eid:
            return f"eid:{paper.eid}"
        elif paper.scopus_id:
            return f"scopus:{paper.scopus_id}"
        elif paper.scholar_id:
            return f"scholar:{paper.scholar_id}"
        elif paper.pubmed_id:
            return f"pmid:{paper.pubmed_id}"
        else:
            # Fallback to title hash
            import hashlib
            return f"title:{hashlib.md5(paper.title.encode()).hexdigest()[:8]}"

    def _paper_to_node(self, paper: Paper) -> Dict[str, Any]:
        """Convert Paper to network node data."""
        return {
            "id": self._get_paper_id(paper),
            "title": paper.title,
            "year": paper.year,
            "citation_count": paper.citation_count or 0,
            "authors": paper.authors,
            "journal": paper.journal,
        }

    def _edge_to_dict(self, edge: CitationEdge) -> Dict[str, Any]:
        """Convert CitationEdge to dictionary."""
        return {
            "citing_paper_id": edge.citing_paper_id,
            "cited_paper_id": edge.cited_paper_id,
            "citing_paper_title": edge.citing_paper_title,
            "cited_paper_title": edge.cited_paper_title,
        }
