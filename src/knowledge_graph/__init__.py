"""Knowledge graph module: build, analyze, and serve paper relationship networks."""

from src.knowledge_graph.builder import build_paper_graph
from src.knowledge_graph.community import detect_communities
from src.knowledge_graph.gap_detector import detect_research_gaps

__all__ = ["build_paper_graph", "detect_communities", "detect_research_gaps"]
