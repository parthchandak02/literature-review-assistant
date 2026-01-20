"""
Tests for Citation Network Builder
"""

import pytest
from src.search.citation_network import CitationNetworkBuilder, CitationEdge
from src.search.connectors.base import Paper


@pytest.fixture
def sample_papers():
    """Create sample papers for testing."""
    return [
        Paper(
            title="Paper 1",
            abstract="Abstract 1",
            authors=["Author 1"],
            doi="10.1000/paper1",
            citation_count=10,
        ),
        Paper(
            title="Paper 2",
            abstract="Abstract 2",
            authors=["Author 2"],
            doi="10.1000/paper2",
            citation_count=5,
        ),
    ]


@pytest.fixture
def network_builder():
    """Create citation network builder."""
    return CitationNetworkBuilder()


class TestCitationNetworkBuilder:
    """Test Citation Network Builder."""
    
    def test_add_paper(self, network_builder, sample_papers):
        """Test adding papers to network."""
        paper_id = network_builder.add_paper(sample_papers[0])
        
        assert paper_id is not None
        assert paper_id in network_builder.papers
        assert network_builder.papers[paper_id] == sample_papers[0]
    
    def test_add_citation(self, network_builder, sample_papers):
        """Test adding citation relationships."""
        network_builder.add_citation(sample_papers[0], sample_papers[1])
        
        assert len(network_builder.edges) == 1
        edge = network_builder.edges[0]
        assert edge.citing_paper_id is not None
        assert edge.cited_paper_id is not None
    
    def test_build_network_from_papers(self, network_builder, sample_papers):
        """Test building network from papers."""
        network_data = network_builder.build_network_from_papers(sample_papers)
        
        assert "nodes" in network_data
        assert "edges" in network_data
        assert "statistics" in network_data
        assert network_data["statistics"]["total_papers"] == 2
    
    def test_get_citation_statistics(self, network_builder, sample_papers):
        """Test getting citation statistics."""
        network_builder.build_network_from_papers(sample_papers)
        stats = network_builder.get_citation_statistics()
        
        assert "total_papers" in stats
        assert "total_citations" in stats
        assert stats["total_papers"] == 2
    
    def test_export_networkx_graph(self, network_builder, sample_papers):
        """Test exporting NetworkX graph."""
        network_builder.build_network_from_papers(sample_papers)
        
        try:
            G = network_builder.export_networkx_graph()
            assert G is not None
            assert len(G.nodes()) == 2
        except ImportError:
            pytest.skip("networkx not available")
    
    def test_get_paper_id(self, network_builder, sample_papers):
        """Test paper ID generation."""
        paper_id = network_builder._get_paper_id(sample_papers[0])
        
        assert paper_id.startswith("doi:")
        assert "10.1000/paper1" in paper_id
