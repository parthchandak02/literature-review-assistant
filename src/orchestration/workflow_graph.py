"""
LangGraph-based Workflow Orchestration

Provides graph-based workflow execution with conditional routing and parallel execution.
"""

from typing import Dict, List, Optional, Any, Literal

try:
    from typing import TypedDict
except ImportError:
    # Python < 3.8
    from typing_extensions import TypedDict
from langgraph.graph import StateGraph, END
from langgraph.checkpoint import MemorySaver
import logging

from .workflow_manager import WorkflowManager

logger = logging.getLogger(__name__)


class WorkflowState(TypedDict):
    """State for workflow graph."""

    topic_context: Dict[str, Any]
    phase: str
    papers: List[Dict[str, Any]]
    unique_papers: List[Dict[str, Any]]
    screened_papers: List[Dict[str, Any]]
    eligible_papers: List[Dict[str, Any]]
    final_papers: List[Dict[str, Any]]
    extracted_data: List[Dict[str, Any]]
    prisma_counts: Dict[str, int]
    outputs: Dict[str, Any]
    errors: List[Dict[str, Any]]


class WorkflowGraph:
    """LangGraph-based workflow orchestrator."""

    def __init__(self, workflow_manager: WorkflowManager):
        """
        Initialize workflow graph.

        Args:
            workflow_manager: WorkflowManager instance
        """
        self.workflow_manager = workflow_manager
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the workflow graph."""
        graph = StateGraph(WorkflowState)

        # Add nodes
        graph.add_node("build_search_strategy", self._build_search_strategy_node)
        graph.add_node("search_databases", self._search_databases_node)
        graph.add_node("deduplicate", self._deduplicate_node)
        graph.add_node("screen_title_abstract", self._screen_title_abstract_node)
        graph.add_node("screen_fulltext", self._screen_fulltext_node)
        graph.add_node("enrich_papers", self._enrich_papers_node)
        graph.add_node("extract_data", self._extract_data_node)
        graph.add_node("generate_prisma", self._generate_prisma_node)
        graph.add_node("generate_visualizations", self._generate_visualizations_node)
        graph.add_node("write_article", self._write_article_node)
        graph.add_node("generate_report", self._generate_report_node)

        # Set entry point
        graph.set_entry_point("build_search_strategy")

        # Add edges (sequential flow)
        graph.add_edge("build_search_strategy", "search_databases")
        graph.add_edge("search_databases", "deduplicate")
        graph.add_edge("deduplicate", "screen_title_abstract")
        graph.add_edge("screen_title_abstract", "screen_fulltext")
        graph.add_edge("screen_fulltext", "enrich_papers")
        graph.add_edge("enrich_papers", "extract_data")

        # Conditional routing after extraction
        graph.add_conditional_edges(
            "extract_data",
            self._should_generate_outputs,
            {"yes": "generate_prisma", "no": END},
        )

        # Parallel execution for outputs
        graph.add_edge("generate_prisma", "generate_visualizations")
        graph.add_edge("generate_visualizations", "write_article")
        graph.add_edge("write_article", "generate_report")
        graph.add_edge("generate_report", END)

        # Compile with checkpointing
        memory = MemorySaver()
        return graph.compile(checkpointer=memory)

    def _should_generate_outputs(self, state: WorkflowState) -> Literal["yes", "no"]:
        """Determine if outputs should be generated."""
        if len(state.get("final_papers", [])) > 0:
            return "yes"
        return "no"

    def _build_search_strategy_node(self, state: WorkflowState) -> WorkflowState:
        """Build search strategy node."""
        try:
            self.workflow_manager._build_search_strategy()
            state["phase"] = "search_strategy_built"
            logger.info("Search strategy built")
        except Exception as e:
            logger.error(f"Error building search strategy: {e}", exc_info=True)
            state.setdefault("errors", []).append(
                {"phase": "build_search_strategy", "error": str(e)}
            )
        return state

    def _search_databases_node(self, state: WorkflowState) -> WorkflowState:
        """Search databases node."""
        try:
            papers = self.workflow_manager._search_databases()
            state["papers"] = [self._paper_to_dict(p) for p in papers]
            state["phase"] = "searched"
            logger.info(f"Searched databases, found {len(papers)} papers")
        except Exception as e:
            logger.error(f"Error searching databases: {e}", exc_info=True)
            state.setdefault("errors", []).append({"phase": "search_databases", "error": str(e)})
        return state

    def _deduplicate_node(self, state: WorkflowState) -> WorkflowState:
        """Deduplicate node."""
        try:
            papers = [self._dict_to_paper(p) for p in state.get("papers", [])]
            dedup_result = self.workflow_manager.deduplicator.deduplicate_papers(papers)
            state["unique_papers"] = [self._paper_to_dict(p) for p in dedup_result.unique_papers]
            state["phase"] = "deduplicated"
            logger.info(f"Deduplicated, {len(dedup_result.unique_papers)} unique papers")
        except Exception as e:
            logger.error(f"Error deduplicating: {e}", exc_info=True)
            state.setdefault("errors", []).append({"phase": "deduplicate", "error": str(e)})
        return state

    def _screen_title_abstract_node(self, state: WorkflowState) -> WorkflowState:
        """Screen title/abstract node."""
        try:
            unique_papers = [self._dict_to_paper(p) for p in state.get("unique_papers", [])]
            self.workflow_manager.unique_papers = unique_papers
            self.workflow_manager._screen_title_abstract()
            state["screened_papers"] = [
                self._paper_to_dict(p) for p in self.workflow_manager.screened_papers
            ]
            state["phase"] = "screened_title_abstract"
            logger.info(
                f"Screened title/abstract, {len(self.workflow_manager.screened_papers)} papers"
            )
        except Exception as e:
            logger.error(f"Error screening title/abstract: {e}", exc_info=True)
            state.setdefault("errors", []).append(
                {"phase": "screen_title_abstract", "error": str(e)}
            )
        return state

    def _screen_fulltext_node(self, state: WorkflowState) -> WorkflowState:
        """Screen fulltext node."""
        try:
            screened_papers = [self._dict_to_paper(p) for p in state.get("screened_papers", [])]
            self.workflow_manager.screened_papers = screened_papers
            self.workflow_manager._screen_fulltext()
            state["eligible_papers"] = [
                self._paper_to_dict(p) for p in self.workflow_manager.eligible_papers
            ]
            state["final_papers"] = state["eligible_papers"]
            state["phase"] = "screened_fulltext"
            logger.info(
                f"Screened fulltext, {len(self.workflow_manager.eligible_papers)} eligible papers"
            )
        except Exception as e:
            logger.error(f"Error screening fulltext: {e}", exc_info=True)
            state.setdefault("errors", []).append({"phase": "screen_fulltext", "error": str(e)})
        return state

    def _enrich_papers_node(self, state: WorkflowState) -> WorkflowState:
        """Enrich papers node."""
        try:
            final_papers = [self._dict_to_paper(p) for p in state.get("final_papers", [])]
            self.workflow_manager.final_papers = final_papers
            self.workflow_manager._enrich_papers()
            state["final_papers"] = [
                self._paper_to_dict(p) for p in self.workflow_manager.final_papers
            ]
            state["phase"] = "enriched"
            logger.info(f"Enriched {len(self.workflow_manager.final_papers)} papers")
        except Exception as e:
            logger.error(f"Error enriching papers: {e}", exc_info=True)
            state.setdefault("errors", []).append({"phase": "enrich_papers", "error": str(e)})
        return state

    def _extract_data_node(self, state: WorkflowState) -> WorkflowState:
        """Extract data node."""
        try:
            final_papers = [self._dict_to_paper(p) for p in state.get("final_papers", [])]
            self.workflow_manager.final_papers = final_papers
            self.workflow_manager._extract_data()
            state["extracted_data"] = [ed.to_dict() for ed in self.workflow_manager.extracted_data]
            state["phase"] = "extracted"
            logger.info(f"Extracted data from {len(self.workflow_manager.extracted_data)} papers")
        except Exception as e:
            logger.error(f"Error extracting data: {e}", exc_info=True)
            state.setdefault("errors", []).append({"phase": "extract_data", "error": str(e)})
        return state

    def _generate_prisma_node(self, state: WorkflowState) -> WorkflowState:
        """Generate PRISMA diagram node."""
        try:
            prisma_path = self.workflow_manager._generate_prisma_diagram()
            state.setdefault("outputs", {})["prisma_diagram"] = prisma_path
            state["prisma_counts"] = self.workflow_manager.prisma_counter.get_counts()
            state["phase"] = "prisma_generated"
            logger.info("Generated PRISMA diagram")
        except Exception as e:
            logger.error(f"Error generating PRISMA: {e}", exc_info=True)
            state.setdefault("errors", []).append({"phase": "generate_prisma", "error": str(e)})
        return state

    def _generate_visualizations_node(self, state: WorkflowState) -> WorkflowState:
        """Generate visualizations node."""
        try:
            [self._dict_to_paper(p) for p in state.get("final_papers", [])]
            viz_paths = self.workflow_manager._generate_visualizations()
            state.setdefault("outputs", {})["visualizations"] = viz_paths
            state["phase"] = "visualizations_generated"
            logger.info("Generated visualizations")
        except Exception as e:
            logger.error(f"Error generating visualizations: {e}", exc_info=True)
            state.setdefault("errors", []).append(
                {"phase": "generate_visualizations", "error": str(e)}
            )
        return state

    def _write_article_node(self, state: WorkflowState) -> WorkflowState:
        """Write article sections node."""
        try:
            article_sections = self.workflow_manager._write_article()
            state.setdefault("outputs", {})["article_sections"] = article_sections
            state["phase"] = "article_written"
            logger.info("Wrote article sections")
        except Exception as e:
            logger.error(f"Error writing article: {e}", exc_info=True)
            state.setdefault("errors", []).append({"phase": "write_article", "error": str(e)})
        return state

    def _generate_report_node(self, state: WorkflowState) -> WorkflowState:
        """Generate final report node."""
        try:
            article_sections = state.get("outputs", {}).get("article_sections", {})
            prisma_path = state.get("outputs", {}).get("prisma_diagram", "")
            viz_paths = state.get("outputs", {}).get("visualizations", {})

            report_path = self.workflow_manager._generate_final_report(
                article_sections, prisma_path, viz_paths
            )
            state.setdefault("outputs", {})["final_report"] = report_path
            state["phase"] = "completed"
            logger.info("Generated final report")
        except Exception as e:
            logger.error(f"Error generating report: {e}", exc_info=True)
            state.setdefault("errors", []).append({"phase": "generate_report", "error": str(e)})
        return state

    def _paper_to_dict(self, paper) -> Dict[str, Any]:
        """Convert Paper object to dictionary."""
        return {
            "title": paper.title,
            "abstract": paper.abstract,
            "authors": paper.authors,
            "year": paper.year,
            "doi": paper.doi,
            "journal": paper.journal,
            "database": paper.database,
            "url": paper.url,
            "keywords": paper.keywords,
            "affiliations": paper.affiliations,
            "subjects": paper.subjects,
            "country": paper.country,
        }

    def _dict_to_paper(self, data: Dict[str, Any]):
        """Convert dictionary to Paper object."""
        from ..search.database_connectors import Paper

        return Paper(
            title=data.get("title", ""),
            abstract=data.get("abstract", ""),
            authors=data.get("authors", []),
            year=data.get("year"),
            doi=data.get("doi"),
            journal=data.get("journal"),
            database=data.get("database"),
            url=data.get("url"),
            keywords=data.get("keywords"),
            affiliations=data.get("affiliations"),
            subjects=data.get("subjects"),
            country=data.get("country"),
        )

    def run(self, initial_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Run the workflow graph.

        Args:
            initial_state: Optional initial state

        Returns:
            Final state dictionary
        """
        if initial_state is None:
            initial_state = {
                "topic_context": self.workflow_manager.topic_context.to_dict(),
                "phase": "initialized",
                "papers": [],
                "unique_papers": [],
                "screened_papers": [],
                "eligible_papers": [],
                "final_papers": [],
                "extracted_data": [],
                "prisma_counts": {},
                "outputs": {},
                "errors": [],
            }

        # Run graph
        final_state = self.graph.invoke(initial_state)

        return final_state
