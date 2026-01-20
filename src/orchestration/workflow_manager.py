"""
Workflow Manager

Main orchestrator that coordinates all phases of the systematic review workflow.
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv
import time
from datetime import datetime

# Load environment variables
load_dotenv()

from rich.console import Console
from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
    SpinnerColumn,
)

from ..utils.logging_config import setup_logging, LogLevel, get_logger
from ..utils.log_context import workflow_phase_context
from ..config.debug_config import load_debug_config, get_debug_config_from_env, DebugLevel
from ..observability.metrics import get_metrics_collector
from ..observability.cost_tracker import get_cost_tracker

try:
    from ..observability.tracing import (
        TracingContext,
        set_tracing_context,
        trace_agent_call,
    )
except ImportError:
    # Tracing is optional
    TracingContext = None

    def set_tracing_context(x):
        return None

    def trace_agent_call(*args, **kwargs):
        return None


logger = get_logger(__name__)
console = Console()

from src.prisma.prisma_generator import PRISMACounter, PRISMAGenerator
from src.search.search_strategy import SearchStrategyBuilder
from src.search.multi_database_searcher import MultiDatabaseSearcher
from src.search.connectors.base import Paper, DatabaseConnector
from src.search.database_connectors import (
    MockConnector,
    PubMedConnector,
    ArxivConnector,
    SemanticScholarConnector,
    CrossrefConnector,
    ScopusConnector,
    ACMConnector,
)
from src.search.cache import SearchCache
from src.search.proxy_manager import ProxyManager, create_proxy_manager_from_config
from src.search.integrity_checker import IntegrityChecker, create_integrity_checker_from_config
from src.deduplication import Deduplicator
from src.screening.title_abstract_agent import TitleAbstractScreener
from src.screening.fulltext_agent import FullTextScreener
from src.extraction.data_extractor_agent import DataExtractorAgent, ExtractedData
from src.visualization.charts import ChartGenerator
from src.writing.introduction_agent import IntroductionWriter
from src.writing.methods_agent import MethodsWriter
from src.writing.results_agent import ResultsWriter
from src.writing.discussion_agent import DiscussionWriter
from src.writing.abstract_agent import AbstractGenerator
from src.config.config_loader import ConfigLoader
from src.orchestration.topic_propagator import TopicContext
from src.orchestration.handoff_protocol import HandoffProtocol
from src.orchestration.workflow_initializer import WorkflowInitializer
from src.orchestration.database_connector_factory import DatabaseConnectorFactory
from src.utils.pdf_retriever import PDFRetriever
from src.utils.screening_validator import ScreeningValidator, ScreeningStage
from src.utils.state_serialization import StateSerializer
from src.enrichment.paper_enricher import PaperEnricher


class WorkflowManager:
    """Manages the complete systematic review workflow."""

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize workflow manager.

        Args:
            config_path: Path to YAML config file (default: config/workflow.yaml)
        """
        # Use WorkflowInitializer to handle all initialization
        initializer = WorkflowInitializer(config_path)

        # Copy all initialized components
        self.config = initializer.config
        self.topic_context = initializer.topic_context
        self.prisma_counter = initializer.prisma_counter
        self.output_dir = initializer.output_dir
        self.search_strategy = initializer.search_strategy
        self.searcher = initializer.searcher
        self.deduplicator = initializer.deduplicator
        self.title_screener = initializer.title_screener
        self.fulltext_screener = initializer.fulltext_screener
        self.extractor = initializer.extractor
        self.chart_generator = initializer.chart_generator
        self.intro_writer = initializer.intro_writer
        self.methods_writer = initializer.methods_writer
        self.results_writer = initializer.results_writer
        self.discussion_writer = initializer.discussion_writer
        self.abstract_generator = initializer.abstract_generator
        self.handoff_protocol = initializer.handoff_protocol
        self.debug_config = initializer.debug_config
        self.metrics = initializer.metrics
        self.cost_tracker = initializer.cost_tracker
        self.tracing_context = initializer.tracing_context

        # Workflow state
        self.all_papers: List[Paper] = []
        self.unique_papers: List[Paper] = []
        self.screened_papers: List[Paper] = []
        self.eligible_papers: List[Paper] = []
        self.final_papers: List[Paper] = []
        self.extracted_data: List[ExtractedData] = []
        self.quality_assessment_data: Optional[Dict[str, Any]] = None
        
        # Initialize PDF retriever
        cache_dir = self.config.get("workflow", {}).get("cache", {}).get("cache_dir", "data/cache")
        pdf_cache_dir = str(Path(cache_dir) / "pdfs")
        self.pdf_retriever = PDFRetriever(cache_dir=pdf_cache_dir)
        self.fulltext_available_count = 0
        self.fulltext_unavailable_count = 0
        
        # Initialize screening validator
        self.screening_validator = ScreeningValidator()
        self.title_abstract_results = []  # Store screening results for validation
        self.fulltext_results = []  # Store screening results for validation
        
        # Initialize paper enricher
        self.paper_enricher = PaperEnricher()
        
        # Checkpoint management
        self.workflow_id = self._generate_workflow_id()
        self.checkpoint_dir = Path("data/checkpoints") / self.workflow_id
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.save_checkpoints = True  # Can be disabled via CLI

    def run(self, start_from_phase: Optional[int] = None) -> Dict[str, Any]:
        """
        Execute the complete workflow.

        Args:
            start_from_phase: Optional phase index to start from (1-based, None = start from beginning)

        Returns:
            Dictionary with workflow results and output paths
        """
        workflow_start = time.time()
        logger.info("=" * 60)
        logger.info("Starting systematic review workflow")
        logger.info(f"Topic: {self.topic_context.topic}")
        
        # Auto-detect and resume from existing checkpoint if available
        if start_from_phase is None and self.save_checkpoints:
            existing_checkpoint = self._find_existing_checkpoint_by_topic()
            if existing_checkpoint:
                logger.info("=" * 60)
                logger.info(f"Found existing checkpoint for this topic!")
                logger.info(f"  Workflow ID: {existing_checkpoint['workflow_id']}")
                logger.info(f"  Latest phase: {existing_checkpoint['latest_phase']}")
                logger.info(f"  Resuming from checkpoint...")
                logger.info("=" * 60)
                
                # Load all prerequisite checkpoints in order
                checkpoint_dir = Path(existing_checkpoint["checkpoint_dir"])
                phase_dependencies = {
                    "search_databases": [],
                    "deduplication": ["search_databases"],
                    "title_abstract_screening": ["deduplication"],
                    "fulltext_screening": ["title_abstract_screening"],
                    "paper_enrichment": ["fulltext_screening"],
                    "data_extraction": ["paper_enrichment"],  # paper_enrichment may not exist, will fallback to fulltext_screening data
                    "quality_assessment": ["data_extraction"],
                    "article_writing": ["data_extraction"],  # Need final_papers from data_extraction for citations
                }
                
                # Get all phases we need to load (dependencies + latest phase)
                # Build full dependency chain recursively
                def get_all_dependencies(phase: str, visited: set = None) -> List[str]:
                    """Recursively get all dependencies for a phase."""
                    if visited is None:
                        visited = set()
                    if phase in visited:
                        return []
                    visited.add(phase)
                    
                    deps = phase_dependencies.get(phase, [])
                    all_deps = []
                    for dep in deps:
                        all_deps.extend(get_all_dependencies(dep, visited))
                        all_deps.append(dep)
                    return all_deps
                
                phases_to_load = get_all_dependencies(existing_checkpoint["latest_phase"])
                phases_to_load.append(existing_checkpoint["latest_phase"])
                # Remove duplicates while preserving order
                seen = set()
                phases_to_load = [p for p in phases_to_load if not (p in seen or seen.add(p))]
                logger.info(f"Checkpoint dependency chain for '{existing_checkpoint['latest_phase']}': {phases_to_load}")
                
                # Load checkpoints in dependency order
                loaded_phases = []
                serializer = StateSerializer()
                
                # Accumulate state from all checkpoints before loading
                # This prevents later checkpoints from overwriting data from earlier phases
                accumulated_state = {"data": {}}
                
                for phase in phases_to_load:
                    checkpoint_file = checkpoint_dir / f"{phase}_state.json"
                    exists = checkpoint_file.exists()
                    if exists:
                        logger.debug(f"Found checkpoint: {phase}")
                        try:
                            checkpoint_data = self._load_phase_state(str(checkpoint_file))
                            
                            # Merge checkpoint data into accumulated state
                            # Later phases override earlier ones for same keys, but preserve keys only in earlier phases
                            if "data" in checkpoint_data:
                                # Log what data keys we're merging
                                data_keys = list(checkpoint_data["data"].keys())
                                logger.debug(f"  Merging data keys from {phase}: {data_keys}")
                                # Update existing keys, but don't remove keys that don't exist in later checkpoints
                                for key, value in checkpoint_data["data"].items():
                                    accumulated_state["data"][key] = value
                            
                            # Merge other top-level keys (use latest phase's values)
                            for key in ["prisma_counts", "database_breakdown", "topic_context", "workflow_id"]:
                                if key in checkpoint_data:
                                    accumulated_state[key] = checkpoint_data[key]
                            
                            loaded_phases.append(phase)
                            logger.info(f"Loaded checkpoint data from: {phase}")
                        except Exception as e:
                            logger.error(f"Failed to load checkpoint file {phase}: {e}", exc_info=True)
                            # Continue loading other phases even if one fails
                    else:
                        logger.debug(f"Missing checkpoint: {phase} (will skip, may use data from later phases)")
                
                if not loaded_phases:
                    logger.error("Failed to load any checkpoints! Starting from scratch.")
                    existing_checkpoint = None  # Reset to start fresh
                else:
                    logger.info(f"Successfully loaded {len(loaded_phases)} checkpoint(s) out of {len(phases_to_load)} attempted: {', '.join(loaded_phases)}")
                    if len(loaded_phases) < len(phases_to_load):
                        missing = set(phases_to_load) - set(loaded_phases)
                        logger.warning(f"Missing checkpoints (will use available data): {', '.join(missing)}")
                    
                    # Handle missing paper_enrichment: use eligible_papers from fulltext_screening as final_papers
                    if "paper_enrichment" not in loaded_phases and "fulltext_screening" in loaded_phases:
                        if "eligible_papers" in accumulated_state.get("data", {}) and "final_papers" not in accumulated_state.get("data", {}):
                            logger.info("paper_enrichment checkpoint missing, using eligible_papers from fulltext_screening as final_papers")
                            accumulated_state["data"]["final_papers"] = accumulated_state["data"]["eligible_papers"]
                    
                    # Log accumulated state summary before loading
                    data_keys = list(accumulated_state.get("data", {}).keys())
                    logger.debug(f"Accumulated state data keys: {data_keys}")
                    
                    # Now load the accumulated state once
                    try:
                        self.load_state_from_dict(accumulated_state)
                        logger.info(
                            f"Restored state: {len(self.all_papers)} all papers, "
                            f"{len(self.unique_papers)} unique, {len(self.screened_papers)} screened, "
                            f"{len(self.eligible_papers)} eligible, {len(self.final_papers)} final"
                        )
                        
                        # Populate results["outputs"] with checkpoint data if available
                        if "article_sections" in accumulated_state.get("data", {}):
                            if not hasattr(self, "_results"):
                                self._results = {"outputs": {}}
                            self._results["outputs"]["article_sections"] = accumulated_state["data"]["article_sections"]
                    except Exception as load_error:
                        logger.warning(f"Error loading accumulated state: {load_error}", exc_info=True)
                        # Try manual fallback loading from accumulated_state
                        if "data" in accumulated_state:
                            try:
                                if "all_papers" in accumulated_state["data"]:
                                    self.all_papers = serializer.deserialize_papers(accumulated_state["data"]["all_papers"])
                            except Exception as e:
                                logger.debug(f"Failed to load all_papers: {e}")
                            
                            try:
                                if "unique_papers" in accumulated_state["data"]:
                                    self.unique_papers = serializer.deserialize_papers(accumulated_state["data"]["unique_papers"])
                            except Exception as e:
                                logger.debug(f"Failed to load unique_papers: {e}")
                            
                            try:
                                if "screened_papers" in accumulated_state["data"]:
                                    self.screened_papers = serializer.deserialize_papers(accumulated_state["data"]["screened_papers"])
                            except Exception as e:
                                logger.debug(f"Failed to load screened_papers: {e}")
                            
                            try:
                                if "eligible_papers" in accumulated_state["data"]:
                                    self.eligible_papers = serializer.deserialize_papers(accumulated_state["data"]["eligible_papers"])
                            except Exception as e:
                                logger.debug(f"Failed to load eligible_papers: {e}")
                            
                            try:
                                if "final_papers" in accumulated_state["data"]:
                                    self.final_papers = serializer.deserialize_papers(accumulated_state["data"]["final_papers"])
                            except Exception as e:
                                logger.debug(f"Failed to load final_papers: {e}")
                            
                            try:
                                if "title_abstract_results" in accumulated_state["data"]:
                                    self.title_abstract_results = serializer.deserialize_screening_results(
                                        accumulated_state["data"]["title_abstract_results"]
                                    )
                            except Exception as e:
                                logger.debug(f"Failed to load title_abstract_results: {e}")
                            
                            try:
                                if "fulltext_results" in accumulated_state["data"]:
                                    self.fulltext_results = serializer.deserialize_screening_results(
                                        accumulated_state["data"]["fulltext_results"]
                                    )
                            except Exception as e:
                                logger.debug(f"Failed to load fulltext_results: {e}")
                            
                            try:
                                if "extracted_data" in accumulated_state["data"]:
                                    self.extracted_data = serializer.deserialize_extracted_data(
                                        accumulated_state["data"]["extracted_data"]
                                    )
                            except Exception as e:
                                logger.debug(f"Failed to load extracted_data: {e}")
                            
                            # Try to restore PRISMA counts manually
                            try:
                                if "prisma_counts" in accumulated_state:
                                    counts = accumulated_state["prisma_counts"]
                                    if "found" in counts:
                                        db_breakdown = accumulated_state.get("database_breakdown", {})
                                        self.prisma_counter.set_found(counts["found"], db_breakdown if db_breakdown else None)
                                    if "no_dupes" in counts:
                                        self.prisma_counter.set_no_dupes(counts["no_dupes"])
                                    if "screened" in counts:
                                        self.prisma_counter.set_screened(counts["screened"])
                                    if "screen_exclusions" in counts:
                                        self.prisma_counter.set_screen_exclusions(counts["screen_exclusions"])
                                    if "full_text_sought" in counts:
                                        self.prisma_counter.set_full_text_sought(counts["full_text_sought"])
                                    if "full_text_not_retrieved" in counts:
                                        self.prisma_counter.set_full_text_not_retrieved(counts["full_text_not_retrieved"])
                                    if "full_text_assessed" in counts:
                                        self.prisma_counter.set_full_text_assessed(counts["full_text_assessed"])
                                    if "full_text_exclusions" in counts:
                                        self.prisma_counter.set_full_text_exclusions(counts["full_text_exclusions"])
                                    if "qualitative" in counts:
                                        self.prisma_counter.set_qualitative(counts["qualitative"])
                                    if "quantitative" in counts:
                                        self.prisma_counter.set_quantitative(counts["quantitative"])
                            except Exception as e:
                                logger.debug(f"Failed to restore PRISMA counts: {e}")
                            
                            logger.info(
                                f"Fallback restore: {len(self.all_papers)} all papers, "
                                f"{len(self.unique_papers)} unique, {len(self.screened_papers)} screened, "
                                f"{len(self.eligible_papers)} eligible, {len(self.final_papers)} final"
                            )
                
                # Update workflow_id and checkpoint_dir from checkpoint
                latest_checkpoint_file = checkpoint_dir / f"{existing_checkpoint['latest_phase']}_state.json"
                if latest_checkpoint_file.exists():
                    latest_checkpoint_data = self._load_phase_state(str(latest_checkpoint_file))
                    if "workflow_id" in latest_checkpoint_data:
                        self.workflow_id = latest_checkpoint_data["workflow_id"]
                        self.checkpoint_dir = Path("data/checkpoints") / self.workflow_id
                
                # Map phase name to phase number (next phase to run)
                phase_to_next_number = {
                    "search_databases": 3,  # Next: deduplication
                    "deduplication": 4,  # Next: title_abstract_screening
                    "title_abstract_screening": 5,  # Next: fulltext_screening
                    "fulltext_screening": 7,  # Next: paper_enrichment
                    "paper_enrichment": 7,  # Next: data_extraction
                    "data_extraction": 8,  # Next: quality_assessment/prisma
                    "quality_assessment": 9,  # Next: prisma/visualization/writing
                    "prisma_generation": 9,  # Next: visualization/writing
                    "visualization_generation": 10,  # Next: article_writing
                    "article_writing": 11,  # Next: report_generation
                    "report_generation": 12,  # Next: export/search_strategies
                }
                
                start_from_phase = phase_to_next_number.get(existing_checkpoint["latest_phase"], None)
                if start_from_phase:
                    logger.info(f"Resuming from phase {start_from_phase} (completed: {existing_checkpoint['latest_phase']})")
                    logger.info(f"Loaded state: {len(self.all_papers)} papers, {len(self.unique_papers)} unique, {len(self.screened_papers)} screened")
                    if self.title_abstract_results:
                        logger.info(f"Found {len(self.title_abstract_results)} title/abstract screening results - will reuse")
                    if self.fulltext_results:
                        logger.info(f"Found {len(self.fulltext_results)} fulltext screening results - will reuse")
        
        if start_from_phase:
            logger.info(f"Resuming from phase {start_from_phase}")
        logger.info("=" * 60)

        results = {"phase": "initialization", "outputs": {}}

        try:
            # Phase 1: Build search strategy
            # Always build search strategy, even when resuming (needed for article writing)
            if not start_from_phase or start_from_phase == 1:
                with workflow_phase_context("build_search_strategy"):
                    self._build_search_strategy()
                    if self.debug_config.show_state_transitions:
                        logger.info("Search strategy built successfully")
            else:
                # If resuming, always rebuild search strategy (needed for article writing and exports)
                # This ensures search_strategy is available even when resuming from later phases
                if self.search_strategy is None:
                    logger.info("Rebuilding search strategy (required for article writing)")
                    try:
                        self._build_search_strategy()
                        logger.info("Search strategy rebuilt successfully")
                    except Exception as e:
                        logger.error(f"Failed to rebuild search strategy: {e}", exc_info=True)
                        raise
                else:
                    # Even if search_strategy exists, rebuild to ensure it's current
                    logger.debug("Rebuilding search strategy to ensure it's current")
                    try:
                        self._build_search_strategy()
                    except Exception as e:
                        logger.warning(f"Failed to rebuild search strategy (will use existing): {e}")

            # Phase 2: Search databases
            if not start_from_phase or start_from_phase <= 2:
                with workflow_phase_context("search_databases"):
                    search_results = self._search_databases()
                    self.all_papers = search_results
                    self.prisma_counter.set_found(len(self.all_papers), self._get_database_breakdown())
                    logger.info(
                        f"Found {len(self.all_papers)} papers across {len(self.config['workflow']['databases'])} databases"
                    )

                    if self.debug_config.show_metrics:
                        db_breakdown = self._get_database_breakdown()
                        for db, count in db_breakdown.items():
                            logger.info(f"  - {db}: {count} papers")
                    
                    # List all papers with titles and authors
                    logger.info("=" * 60)
                    logger.info("ALL PAPERS FOUND:")
                    logger.info("=" * 60)
                    for i, paper in enumerate(self.all_papers, 1):
                        title = paper.title if paper.title else "[No title]"
                        authors_str = ", ".join(paper.authors) if paper.authors else "[No authors]"
                        database = paper.database if paper.database else "Unknown"
                        year = f" ({paper.year})" if paper.year else ""
                        doi_str = f" [DOI: {paper.doi}]" if paper.doi else ""
                        
                        logger.info(f"\n[{i}] {title}{year}")
                        logger.info(f"    Authors: {authors_str}")
                        logger.info(f"    Database: {database}{doi_str}")
                    logger.info("=" * 60)
                    
                    # Save checkpoint after search
                    if self.save_checkpoints:
                        self._save_phase_state("search_databases")

            # Phase 3: Deduplication
            if not start_from_phase or start_from_phase <= 3:
                with workflow_phase_context("deduplication"):
                    dedup_result = self.deduplicator.deduplicate_papers(self.all_papers)
                    self.unique_papers = dedup_result.unique_papers
                    self.prisma_counter.set_no_dupes(len(self.unique_papers))
                    logger.info(
                        f"Removed {dedup_result.duplicates_removed} duplicates, {len(self.unique_papers)} unique papers remain"
                    )
                    
                    # Save checkpoint after deduplication
                    if self.save_checkpoints:
                        self._save_phase_state("deduplication")

            # Phase 4: Title/Abstract Screening
            if not start_from_phase or start_from_phase <= 4:
                with workflow_phase_context("title_abstract_screening"):
                    self._screen_title_abstract()
                    self.prisma_counter.set_screened(len(self.screened_papers))
                    excluded_at_screening = len(self.unique_papers) - len(self.screened_papers)
                    self.prisma_counter.set_screen_exclusions(excluded_at_screening)
                    logger.info(
                        f"Screened {len(self.unique_papers)} papers, {len(self.screened_papers)} included, {excluded_at_screening} excluded"
                    )
                    
                    # Calculate and validate screening statistics
                    if self.title_abstract_results:
                        stats = self.screening_validator.calculate_statistics(
                            self.unique_papers,
                            self.title_abstract_results,
                            ScreeningStage.TITLE_ABSTRACT
                        )
                        self.screening_validator.log_statistics(ScreeningStage.TITLE_ABSTRACT)
                    
                    # Save checkpoint after title screening
                    if self.save_checkpoints:
                        self._save_phase_state("title_abstract_screening")

            # Phase 5: Full-text Screening
            if not start_from_phase or start_from_phase <= 5:
                with workflow_phase_context("fulltext_screening"):
                    self._screen_fulltext()
                    # PRISMA tracking: "sought" = papers that passed title/abstract screening
                    sought_count = len(self.screened_papers)
                    self.prisma_counter.set_full_text_sought(sought_count)
                    # "not_retrieved" = papers where full-text was unavailable
                    not_retrieved_count = self.fulltext_unavailable_count
                    self.prisma_counter.set_full_text_not_retrieved(not_retrieved_count)
                    # "assessed" = papers actually assessed for eligibility
                    # If all papers are assessed (including those without full-text using fallback):
                    #   assessed = sought
                    # If only papers with full-text are assessed:
                    #   assessed = sought - not_retrieved
                    # We assess all papers (with or without full-text), so assessed = sought
                    assessed_count = sought_count
                    self.prisma_counter.set_full_text_assessed(assessed_count)
                    excluded_at_fulltext = len(self.screened_papers) - len(self.eligible_papers)
                    self.prisma_counter.set_full_text_exclusions(excluded_at_fulltext)
                    logger.info(
                        f"Full-text screened {len(self.screened_papers)} papers, {len(self.eligible_papers)} eligible, {excluded_at_fulltext} excluded"
                    )
                    logger.info(
                        f"PRISMA: sought={sought_count}, "
                        f"not_retrieved={not_retrieved_count}, "
                        f"assessed={assessed_count} "
                        f"(sought - not_retrieved = {sought_count - not_retrieved_count} papers with full-text)"
                    )
                    
                    # Save checkpoint after fulltext screening
                    if self.save_checkpoints:
                        self._save_phase_state("fulltext_screening")

            # Phase 6: Final inclusion
            self.final_papers = self.eligible_papers
            self.prisma_counter.set_qualitative(len(self.final_papers))
            self.prisma_counter.set_quantitative(len(self.final_papers))
            logger.info(f"Final included studies: {len(self.final_papers)}")

            # Phase 6.5: Enrich papers with missing metadata (affiliations, etc.)
            if not start_from_phase or start_from_phase <= 7:
                with workflow_phase_context("paper_enrichment"):
                    self._enrich_papers()
                    logger.info(f"Enriched {len(self.final_papers)} papers with metadata")
                    
                    # Save checkpoint after enrichment
                    if self.save_checkpoints:
                        self._save_phase_state("paper_enrichment")

            # Phase 7: Data Extraction
            if not start_from_phase or start_from_phase <= 7:
                with workflow_phase_context("data_extraction"):
                    self._extract_data()
                    logger.info(f"Extracted data from {len(self.extracted_data)} studies")
                    
                    # Save checkpoint after extraction
                    if self.save_checkpoints:
                        self._save_phase_state("data_extraction")

            # Phase 8: Quality Assessment (Risk of Bias + GRADE)
            if not start_from_phase or start_from_phase <= 8:
                with workflow_phase_context("quality_assessment"):
                    quality_assessment_data = self._quality_assessment()
                    results["outputs"]["quality_assessment"] = quality_assessment_data
                    logger.info("Quality assessment phase complete")
                    
                    # Save checkpoint after quality assessment
                    if self.save_checkpoints:
                        self._save_phase_state("quality_assessment")

            # Initialize outputs that may be needed even when resuming
            prisma_path = None
            viz_paths = []
            article_sections = {}
            
            # Phase 9: Generate PRISMA Diagram
            if not start_from_phase or start_from_phase <= 8:
                with workflow_phase_context("prisma_generation"):
                    prisma_path = self._generate_prisma_diagram()
                    results["outputs"]["prisma_diagram"] = prisma_path
                    logger.info(f"PRISMA diagram generated: {prisma_path}")
            else:
                # When resuming, try to load PRISMA path from results or generate it
                if "prisma_diagram" in results.get("outputs", {}):
                    prisma_path = results["outputs"]["prisma_diagram"]
                else:
                    # Generate PRISMA diagram if not found
                    logger.info("PRISMA diagram not found in checkpoint, generating...")
                    prisma_path = self._generate_prisma_diagram()
                    results["outputs"]["prisma_diagram"] = prisma_path

            # Phase 9: Generate Visualizations
            if not start_from_phase or start_from_phase <= 9:
                with workflow_phase_context("visualization_generation"):
                    viz_paths = self._generate_visualizations()
                    results["outputs"]["visualizations"] = viz_paths
                    logger.info(f"Generated {len(viz_paths)} visualizations")
            else:
                # When resuming, try to load visualizations from results
                if "visualizations" in results.get("outputs", {}):
                    viz_paths = results["outputs"]["visualizations"]
                else:
                    # Generate visualizations if not found
                    logger.info("Visualizations not found in checkpoint, generating...")
                    viz_paths = self._generate_visualizations()
                    results["outputs"]["visualizations"] = viz_paths

            # Phase 10: Write Article Sections
            # Check if article_sections were already loaded from checkpoint
            if hasattr(self, "_article_sections") and self._article_sections:
                # Article sections already loaded from checkpoint during initialization
                article_sections = self._article_sections
                results["outputs"]["article_sections"] = article_sections
                logger.info(f"Using {len(article_sections)} article sections loaded from checkpoint")
            else:
                # Check if article_writing checkpoint exists
                article_writing_checkpoint = None
                if self.checkpoint_dir and self.checkpoint_dir.exists():
                    article_writing_checkpoint = self.checkpoint_dir / "article_writing_state.json"
                    if not article_writing_checkpoint.exists():
                        article_writing_checkpoint = None
                
                if article_writing_checkpoint and article_writing_checkpoint.exists():
                    # Load article sections from checkpoint
                    logger.info("Found article_writing checkpoint, loading article sections...")
                    try:
                        with open(article_writing_checkpoint, "r") as f:
                            checkpoint_data = json.load(f)
                        article_sections = checkpoint_data.get("data", {}).get("article_sections", {})
                        if article_sections:
                            self._article_sections = article_sections
                            results["outputs"]["article_sections"] = article_sections
                            logger.info(f"Loaded {len(article_sections)} article sections from checkpoint")
                        else:
                            raise ValueError("No article_sections found in checkpoint data")
                    except Exception as e:
                        logger.warning(f"Failed to load article_writing checkpoint: {e}. Regenerating...")
                        with workflow_phase_context("article_writing"):
                            article_sections = self._write_article()
                            results["outputs"]["article_sections"] = article_sections
                            logger.info(f"Wrote {len(article_sections)} article sections")
                            self._article_sections = article_sections
                            if self.save_checkpoints:
                                self._save_phase_state("article_writing")
                elif not start_from_phase or start_from_phase <= 10:
                    # No checkpoint found, generate article sections
                    with workflow_phase_context("article_writing"):
                        article_sections = self._write_article()
                        results["outputs"]["article_sections"] = article_sections
                        logger.info(f"Wrote {len(article_sections)} article sections")
                        
                        # Store article sections for checkpoint
                        self._article_sections = article_sections
                        
                        # Save checkpoint after writing
                        if self.save_checkpoints:
                            self._save_phase_state("article_writing")
                else:
                    # When resuming from later phase, try to load article sections from results
                    if "article_sections" in results.get("outputs", {}):
                        article_sections = results["outputs"]["article_sections"]
                    else:
                        # Generate article sections if not found
                        logger.info("Article sections not found in checkpoint, generating...")
                        article_sections = self._write_article()
                        results["outputs"]["article_sections"] = article_sections

            # Phase 12: Generate Final Report
            with workflow_phase_context("report_generation"):
                report_path = self._generate_final_report(article_sections, prisma_path, viz_paths)
                results["outputs"]["final_report"] = report_path
                logger.info(f"Final report generated: {report_path}")

            # Phase 13: Export Search Strategies
            supplementary_config = self.config.get("supplementary_materials", {})
            if supplementary_config.get("search_strategies", True):
                with workflow_phase_context("search_strategy_export"):
                    search_strategies_path = self._export_search_strategies()
                    if search_strategies_path:
                        results["outputs"]["search_strategies"] = search_strategies_path
                        logger.info(f"Search strategies exported: {search_strategies_path}")

            # Phase 14: Generate PRISMA Checklist
            with workflow_phase_context("prisma_checklist"):
                checklist_path = self._generate_prisma_checklist(str(report_path))
                if checklist_path:
                    results["outputs"]["prisma_checklist"] = checklist_path
                    logger.info(f"PRISMA checklist generated: {checklist_path}")

            # Phase 15: Generate Data Extraction Forms
            supplementary_config = self.config.get("supplementary_materials", {})
            if supplementary_config.get("extracted_data", True):
                with workflow_phase_context("extraction_forms"):
                    extraction_form_path = self._generate_extraction_forms()
                    if extraction_form_path:
                        results["outputs"]["extraction_form"] = extraction_form_path
                        logger.info(f"Extraction form generated: {extraction_form_path}")

            # Phase 16: Export to Additional Formats
            export_config = self.config.get("output", {}).get("formats", [])
            if "latex" in export_config or "word" in export_config:
                with workflow_phase_context("export"):
                    export_paths = self._export_report(article_sections, prisma_path, viz_paths)
                    results["outputs"]["exports"] = export_paths
                    logger.info(f"Exported to additional formats: {export_paths}")

            # Save workflow state
            state_path = self._save_workflow_state()
            results["outputs"]["workflow_state"] = state_path

            workflow_duration = time.time() - workflow_start
            logger.info("=" * 60)
            logger.info(f"Workflow complete in {workflow_duration:.2f}s")
            logger.info(f"Outputs saved to: {self.output_dir}")

            # Display summary if debug enabled
            if self.debug_config.show_metrics:
                self._display_metrics_summary()

            if self.debug_config.show_costs:
                self._display_cost_summary()
            
            # Display screening validation summary
            validation_report = self.screening_validator.get_summary_report()
            logger.info("\n" + validation_report)

            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"Workflow failed: {e}", exc_info=True)
            raise

        return results

    def _display_metrics_summary(self):
        """Display metrics summary."""
        summary = self.metrics.get_summary()
        logger.info("\n" + "=" * 60)
        logger.info("METRICS SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total agents: {summary['total_agents']}")
        logger.info(f"Total calls: {summary['total_calls']}")
        logger.info(f"Successful: {summary['total_successful']}")
        logger.info(f"Failed: {summary['total_failed']}")
        logger.info(f"Success rate: {summary['overall_success_rate']:.2%}")

        if summary.get("agents") and len(summary["agents"]) > 0:
            logger.info("\nPer-Agent Metrics:")
            for agent_name, agent_metrics in summary["agents"].items():
                logger.info(f"  {agent_name}:")
                logger.info(f"    Calls: {agent_metrics['total_calls']}")
                logger.info(f"    Success rate: {agent_metrics['success_rate']:.2%}")
                logger.info(f"    Avg duration: {agent_metrics['average_duration']:.2f}s")

    def _display_cost_summary(self):
        """Display cost summary."""
        summary = self.cost_tracker.get_summary()
        logger.info("\n" + "=" * 60)
        logger.info("COST SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total cost: ${summary['total_cost_usd']:.4f}")
        logger.info(f"Total calls: {summary['total_calls']}")
        logger.info(f"Total tokens: {summary['total_tokens']}")

        if summary["by_provider"]:
            logger.info("\nBy Provider:")
            for provider, cost in summary["by_provider"].items():
                logger.info(f"  {provider}: ${cost:.4f}")

        if summary["by_agent"]:
            logger.info("\nBy Agent:")
            for agent, cost in summary["by_agent"].items():
                logger.info(f"  {agent}: ${cost:.4f}")

    def _build_search_strategy(self):
        """Build search strategy."""
        self.search_strategy = SearchStrategyBuilder()

        # Get search terms from config
        search_terms = self.config.get("search_terms", {})

        # Merge with topic keywords if available
        if self.topic_context.keywords:
            # Add topic keywords as a search term group
            self.search_strategy.add_term_group(
                self.topic_context.topic.lower().replace(" ", "_"),
                self.topic_context.keywords,
            )

        for main_term, synonyms in search_terms.items():
            self.search_strategy.add_term_group(main_term, synonyms)

        # Set date range
        date_range = self.config["workflow"].get("date_range", {})
        start = date_range.get("start")
        end = date_range.get("end")
        if start or end:
            self.search_strategy.set_date_range(start, end)

        # Set language
        language = self.config["workflow"].get("language", "English")
        self.search_strategy.set_language(language)

    def _create_connector(
        self,
        db_name: str,
        cache: Optional[SearchCache] = None,
        proxy_manager: Optional[ProxyManager] = None,
        integrity_checker: Optional[IntegrityChecker] = None,
        persistent_session: bool = True,
        cookie_jar: Optional[str] = None,
    ) -> Optional[DatabaseConnector]:
        """
        Create appropriate connector based on database name and available API keys.
        
        Args:
            db_name: Name of the database
            cache: Optional search cache instance
            proxy_manager: Optional proxy manager instance
            integrity_checker: Optional integrity checker instance
            persistent_session: Whether to use persistent HTTP sessions
            cookie_jar: Path to cookie jar directory
            
        Returns:
            DatabaseConnector instance or None if database should be skipped
        """
        # Create database-specific integrity checker if needed
        db_integrity_checker = integrity_checker
        if integrity_checker:
            # Create a copy with database name for better error messages
            from src.search.integrity_checker import IntegrityChecker
            db_integrity_checker = IntegrityChecker(
                required_fields=integrity_checker.required_fields,
                action=integrity_checker.action.value,
                database=db_name,
            )
        
        return DatabaseConnectorFactory.create_connector(
            db_name,
            cache,
            proxy_manager,
            db_integrity_checker,
            persistent_session,
            cookie_jar,
        )

    def _validate_database_config(self) -> Dict[str, bool]:
        """
        Validate which databases can be used based on API keys.
        
        Returns:
            Dictionary mapping database names to whether they can be used
        """
        databases = self.config["workflow"]["databases"]
        return DatabaseConnectorFactory.validate_database_config(databases)

    def _search_databases(self) -> List[Paper]:
        """Search all configured databases."""
        databases = self.config["workflow"]["databases"]
        max_results = self.config["workflow"].get("max_results_per_db", 100)

        logger.info(
            f"Starting database search across {len(databases)} databases: {', '.join(databases)}"
        )
        logger.info(f"Max results per database: {max_results}")

        # Validate database configuration
        validation = self._validate_database_config()
        
        # Get cache if enabled
        cache = None
        if self.config["workflow"].get("cache", {}).get("enabled", False):
            cache_dir = self.config["workflow"]["cache"].get("cache_dir", "data/cache")
            cache = SearchCache(cache_dir=cache_dir)

        # Get proxy manager if enabled
        proxy_manager = None
        proxy_config = self.config["workflow"].get("proxy", {})
        if proxy_config.get("enabled", False):
            proxy_manager = create_proxy_manager_from_config(proxy_config)
            if proxy_manager.has_proxy():
                logger.info("Proxy support enabled and configured")
            else:
                logger.warning("Proxy enabled but configuration failed, continuing without proxy")
                proxy_manager = None

        # Get integrity checker if enabled
        integrity_checker = None
        integrity_config = self.config["workflow"].get("integrity", {})
        if integrity_config.get("enabled", True):
            integrity_checker = create_integrity_checker_from_config(integrity_config)

        # Get session configuration
        session_config = self.config["workflow"].get("session", {})
        persistent_session = session_config.get("persistent", True)
        cookie_jar = session_config.get("cookie_jar", "data/cookies")

        # Add connectors (use real connectors when API keys available)
        connectors_added = 0
        for db_name in databases:
            logger.info(f"Adding connector for {db_name}...")
            connector = self._create_connector(db_name, cache, proxy_manager, integrity_checker, persistent_session, cookie_jar)
            if connector:
                self.searcher.add_connector(connector)
                connectors_added += 1
            else:
                logger.warning(f"Skipping {db_name} - connector creation failed")
        
        if connectors_added == 0:
            logger.error("No connectors were added! Check API key configuration.")
            raise RuntimeError("No database connectors available")

        # Build query
        query = self.search_strategy.build_query("generic")
        logger.info(f"Search query: {query[:200]}...")

        # Create handoff for search stage
        search_handoff = self.handoff_protocol.create_handoff(
            from_agent="workflow_manager",
            to_agent="search_agent",
            stage="search",
            topic_context=self.topic_context,
            data={"query": query, "databases": databases},
            metadata={"max_results": max_results},
        )

        if self.debug_config.show_handoffs:
            logger.debug(
                f"Created handoff: {search_handoff.from_agent} -> {search_handoff.to_agent} at stage {search_handoff.stage}"
            )

        # Search
        logger.info("Executing searches...")
        papers = self.searcher.search_all_combined(query, max_results)
        logger.info(f"Search complete: Found {len(papers)} total papers")

        # Enrich topic context with search insights
        self.topic_context.enrich([f"Found {len(papers)} papers across {len(databases)} databases"])

        return papers

    def _get_database_breakdown(self) -> Dict[str, int]:
        """Get breakdown of papers by database."""
        breakdown = {}
        for paper in self.all_papers:
            db = paper.database or "Unknown"
            breakdown[db] = breakdown.get(db, 0) + 1
        return breakdown

    def _get_paper_key(self, paper: Paper) -> str:
        """Get a unique key for a paper (for matching purposes)."""
        # Prefer DOI, fallback to title
        if paper.doi:
            return f"doi:{paper.doi.lower().strip()}"
        elif paper.title:
            return f"title:{paper.title.lower().strip()[:100]}"
        else:
            # Last resort: use first author + year if available
            author = paper.authors[0] if paper.authors else "unknown"
            year = paper.year if paper.year else "unknown"
            return f"author_year:{author.lower().strip()}_{year}"
    
    def _find_existing_screening_result(self, paper: Paper, existing_results: List) -> Optional[Any]:
        """Find existing screening result for a paper."""
        paper_key = self._get_paper_key(paper)
        
        for result in existing_results:
            # Try to match by paper metadata stored in result
            # Results may have paper title/DOI stored, or we need to match by index
            # For now, we'll match by checking if we have results for all papers
            # This is a simplified approach - in practice, results should store paper identifiers
            pass
        
        return None
    
    def _screen_title_abstract(self):
        """Screen papers based on title and abstract using two-stage approach."""
        # Check if we already have screening results loaded from checkpoint
        if self.title_abstract_results and len(self.title_abstract_results) > 0:
            if len(self.title_abstract_results) == len(self.unique_papers):
                logger.info(f"Found existing title/abstract screening results for {len(self.title_abstract_results)} papers")
                logger.info("Reusing existing results - skipping LLM calls")
                
                # Reconstruct screened_papers from results
                self.screened_papers = []
                for i, result in enumerate(self.title_abstract_results):
                    if result.decision.value == "include":
                        if i < len(self.unique_papers):
                            self.screened_papers.append(self.unique_papers[i])
                
                logger.info(
                    f"Title/abstract screening complete (from checkpoint): {len(self.screened_papers)}/{len(self.unique_papers)} papers included"
                )
                return
            else:
                logger.warning(
                    f"Mismatch: have {len(self.title_abstract_results)} screening results but {len(self.unique_papers)} papers. "
                    f"Will re-screen."
                )
        
        self.screened_papers = []
        self.title_abstract_results = []  # Store results for validation

        logger.info(f"Starting title/abstract screening of {len(self.unique_papers)} papers...")

        # Get criteria from config
        inclusion_criteria = self.config["criteria"]["inclusion"]
        exclusion_criteria = self.config["criteria"]["exclusion"]

        # Apply template replacement to criteria
        inclusion_criteria = [self.topic_context.inject_into_prompt(c) for c in inclusion_criteria]
        exclusion_criteria = [self.topic_context.inject_into_prompt(c) for c in exclusion_criteria]

        # Get search_terms from config for comprehensive keyword matching
        search_terms = self.config.get("search_terms", {})

        # Get topic context for screening agent
        screening_context = self.topic_context.get_for_agent("screening_agent")

        # STAGE 1: Keyword-based pre-filtering (NO LLM - FAST!)
        logger.info("Stage 1: Keyword-based pre-filtering (no LLM)...")
        keyword_filtered_papers = []
        keyword_excluded = 0
        keyword_included = 0
        
        # Threshold configuration (can be made configurable in workflow.yaml)
        # More permissive thresholds: err on inclusion at screening stages
        exclude_threshold = 0.8  # Higher threshold for exclusion (more strict)
        include_threshold = 0.6  # Lower threshold for inclusion (more permissive)
        
        # Check if verbose mode is enabled
        is_verbose = self.debug_config.enabled and self.debug_config.level in [
            DebugLevel.DETAILED,
            DebugLevel.FULL,
        ]
        
        for i, paper in enumerate(self.unique_papers, 1):
            # Use enhanced fallback keyword matching with search_terms
            keyword_result = self.title_screener._fallback_screen(
                paper.title or "",
                paper.abstract or "",
                inclusion_criteria,
                exclusion_criteria,
                search_terms=search_terms,
            )
            
            # Verbose output for Stage 1 (using logger to avoid interfering with potential progress bars)
            # Only show verbose output for interesting cases (uncertain, excluded, or every 10th paper)
            if is_verbose:
                should_log = (
                    keyword_result.decision.value == "uncertain" or
                    keyword_result.decision.value == "exclude" or
                    i % 10 == 0 or
                    i == len(self.unique_papers) or
                    self.debug_config.level == DebugLevel.FULL
                )
                
                if should_log:
                    paper_title = (paper.title or "Untitled")[:60]
                    decision_str = keyword_result.decision.value.upper()
                    confidence_str = f"{keyword_result.confidence:.2f}"
                    
                    # Extract matching details from reasoning if available
                    reasoning_preview = keyword_result.reasoning[:80] if keyword_result.reasoning else "No reasoning"
                    
                    logger.debug(
                        f"Paper {i}/{len(self.unique_papers)}: {paper_title}... - "
                        f"Keyword matching: {decision_str} (confidence: {confidence_str})"
                    )
                    if is_verbose and self.debug_config.level == DebugLevel.FULL:
                        logger.debug(f"  -> Reasoning: {reasoning_preview}...")
            
            # Tier 1: High confidence inclusions go through immediately
            if keyword_result.decision.value == "include" and keyword_result.confidence >= include_threshold:
                self.screened_papers.append(paper)
                keyword_included += 1
                self.title_abstract_results.append(keyword_result)  # Store result
            # Tier 2: High confidence exclusions are excluded immediately
            elif keyword_result.decision.value == "exclude" and keyword_result.confidence >= exclude_threshold:
                keyword_excluded += 1
                self.title_abstract_results.append(keyword_result)  # Store result
            # Tier 3: Borderline cases (uncertain or low confidence) need LLM review
            else:
                keyword_filtered_papers.append((paper, keyword_result))
        
        logger.info(
            f"Stage 1 complete: {keyword_included} included (confidence >= {include_threshold}), "
            f"{keyword_excluded} excluded (confidence >= {exclude_threshold}), "
            f"{len(keyword_filtered_papers)} need LLM review (confidence < {exclude_threshold})"
        )
        
        # Log filtering metrics for calibration
        filtering_rate = (keyword_included + keyword_excluded) / len(self.unique_papers) * 100 if self.unique_papers else 0
        logger.info(f"Stage 1 filtering rate: {filtering_rate:.1f}% ({keyword_included + keyword_excluded}/{len(self.unique_papers)} papers filtered)")
        
        # STAGE 2: LLM screening for borderline cases only
        if keyword_filtered_papers and self.title_screener.llm_client:
            logger.info(f"Stage 2: LLM screening for {len(keyword_filtered_papers)} borderline papers...")
            logger.info("This may take a while as each paper requires an LLM call.")
            logger.info(f"LLM call reduction: {len(keyword_filtered_papers)}/{len(self.unique_papers)} papers ({len(keyword_filtered_papers)/len(self.unique_papers)*100:.1f}%)")
            
            # Create handoff
            screening_handoff = self.handoff_protocol.create_handoff(
                from_agent="search_agent",
                to_agent="screening_agent",
                stage="screening",
                topic_context=self.topic_context,
                data={"papers_count": len(keyword_filtered_papers)},
                metadata={"screening_type": "title_abstract"},
            )

            if self.debug_config.show_handoffs:
                logger.info(
                    f"Handoff: {screening_handoff.from_agent} -> {screening_handoff.to_agent} ({len(keyword_filtered_papers)} papers)"
                )

            # Use Rich progress bar for LLM screening
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TextColumn("({task.completed}/{task.total})"),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                task = progress.add_task(
                    f"[cyan]LLM screening borderline papers...",
                    total=len(keyword_filtered_papers),
                )

                for i, (paper, keyword_result) in enumerate(keyword_filtered_papers, 1):
                    paper_title = (paper.title or "Untitled")[:50]
                    progress.update(task, description=f"[cyan]LLM: {paper_title}...")
                    
                    # Verbose output for Stage 2 (using progress.log to work with progress bar)
                    if is_verbose:
                        progress.log(
                            f"[bold cyan]LLM screening paper {i}/{len(keyword_filtered_papers)}:[/bold cyan] "
                            f"[cyan]{paper_title}...[/cyan]"
                        )
                        # Always show prompt building and LLM call info in verbose mode
                        progress.log(
                            f"  [dim]-> Building prompt with {len(inclusion_criteria)} inclusion criteria, "
                            f"{len(exclusion_criteria)} exclusion criteria[/dim]"
                        )
                        progress.log(
                            f"  [dim]-> Calling LLM ({self.title_screener.llm_model})...[/dim]"
                        )
                    
                    # Log progress every 5 papers (only if not verbose to avoid duplication)
                    if not is_verbose and (i == 1 or i % 5 == 0 or i == len(keyword_filtered_papers)):
                        logger.info(f"LLM screening paper {i}/{len(keyword_filtered_papers)}: {paper_title}...")

                    try:
                        # Use LLM for final decision
                        result = self.title_screener.screen(
                            paper.title or "",
                            paper.abstract or "",
                            inclusion_criteria,
                            exclusion_criteria,
                            topic_context=screening_context,
                        )

                        # Verbose output for decision (using progress.log to work with progress bar)
                        if is_verbose:
                            decision_str = result.decision.value.upper()
                            confidence_str = f"{result.confidence:.2f}"
                            reasoning_preview = result.reasoning[:100] if result.reasoning else "No reasoning"
                            
                            if result.decision.value == "include":
                                status_color = "[green]INCLUDE[/green]"
                            elif result.decision.value == "exclude":
                                status_color = "[red]EXCLUDE[/red]"
                            else:
                                status_color = "[yellow]UNCERTAIN[/yellow]"
                            
                            progress.log(
                                f"  [dim]-> Response received:[/dim] Decision: {status_color}, "
                                f"Confidence: {confidence_str}"
                            )
                            if is_verbose and self.debug_config.level == DebugLevel.FULL:
                                progress.log(f"  [dim]-> Reasoning: {reasoning_preview}...[/dim]")
                                if result.exclusion_reason:
                                    progress.log(f"  [dim]-> Exclusion reason: {result.exclusion_reason}[/dim]")

                        # Store result for validation
                        self.title_abstract_results.append(result)
                        
                        if result.decision.value == "include":
                            self.screened_papers.append(paper)
                            if is_verbose:
                                progress.log(f"  [green]Paper included via LLM[/green]")
                            logger.debug(f"Paper included via LLM: {paper_title}")
                        else:
                            if is_verbose:
                                progress.log(f"  [red]Paper excluded via LLM[/red]")
                            logger.debug(f"Paper excluded via LLM: {paper_title}")

                    except Exception as e:
                        logger.error(f"Error LLM screening paper ({paper_title}): {e}")
                        if is_verbose:
                            progress.log(f"  [red]Error: {str(e)}[/red]")
                        # Use keyword result as fallback
                        self.title_abstract_results.append(keyword_result)  # Store fallback result
                        if keyword_result.decision.value == "include":
                            self.screened_papers.append(paper)
                            logger.warning(f"Using keyword result due to LLM error: included")

                    progress.advance(task)
                    
                    # Log summary every 5 papers
                    if i % 5 == 0:
                        logger.info(f"LLM progress: {i}/{len(keyword_filtered_papers)} screened, {len(self.screened_papers)} total included")
        elif keyword_filtered_papers and not self.title_screener.llm_client:
            # No LLM available, use keyword results
            logger.warning("No LLM available, using keyword filtering results only")
            for paper, keyword_result in keyword_filtered_papers:
                self.title_abstract_results.append(keyword_result)  # Store result
                if keyword_result.decision.value == "include":
                    self.screened_papers.append(paper)

                # Update description with current status
                if i % 5 == 0 or i == len(self.unique_papers):
                    progress.update(
                        task,
                        description=f"[cyan]Screening: {paper_title}... ({len(self.screened_papers)} included)",
                    )

        logger.info(
            f"Title/abstract screening complete: {len(self.screened_papers)}/{len(self.unique_papers)} papers included"
        )

        # Enrich topic context
        self.topic_context.enrich(
            [f"Screened {len(self.unique_papers)} papers, {len(self.screened_papers)} included"]
        )

    def _screen_fulltext(self):
        """Screen papers based on full-text (if available)."""
        # Check if we already have fulltext screening results loaded from checkpoint
        if self.fulltext_results and len(self.fulltext_results) > 0:
            if len(self.fulltext_results) == len(self.screened_papers):
                logger.info(f"Found existing full-text screening results for {len(self.fulltext_results)} papers")
                logger.info("Reusing existing results - skipping LLM calls")
                
                # Reconstruct eligible_papers from results
                self.eligible_papers = []
                for i, result in enumerate(self.fulltext_results):
                    if result.decision.value == "include":
                        if i < len(self.screened_papers):
                            self.eligible_papers.append(self.screened_papers[i])
                
                logger.info(
                    f"Full-text screening complete (from checkpoint): {len(self.eligible_papers)}/{len(self.screened_papers)} papers eligible"
                )
                return
            else:
                logger.warning(
                    f"Mismatch: have {len(self.fulltext_results)} fulltext results but {len(self.screened_papers)} screened papers. "
                    f"Will re-screen."
                )
        
        self.eligible_papers = []
        self.fulltext_results = []  # Store results for validation

        logger.info(f"Starting full-text screening of {len(self.screened_papers)} papers...")
        logger.info("This may take a while as each paper requires an LLM call.")

        # Get criteria from config
        inclusion_criteria = self.config["criteria"]["inclusion"]
        exclusion_criteria = self.config["criteria"]["exclusion"]

        # Apply template replacement to criteria
        inclusion_criteria = [self.topic_context.inject_into_prompt(c) for c in inclusion_criteria]
        exclusion_criteria = [self.topic_context.inject_into_prompt(c) for c in exclusion_criteria]

        # Get topic context for full-text screening agent
        fulltext_context = self.topic_context.get_for_agent("screening_agent")

        # Check if verbose mode is enabled
        is_verbose = self.debug_config.enabled and self.debug_config.level in [
            DebugLevel.DETAILED,
            DebugLevel.FULL,
        ]

        # Create handoff
        self.handoff_protocol.create_handoff(
            from_agent="screening_agent",
            to_agent="fulltext_screener",
            stage="fulltext_screening",
            topic_context=self.topic_context,
            data={"papers_count": len(self.screened_papers)},
            metadata={"screening_type": "fulltext"},
        )

        # Use Rich progress bar for full-text screening
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"[cyan]Full-text screening with {self.fulltext_screener.llm_model}...",
                total=len(self.screened_papers),
            )

            for i, paper in enumerate(self.screened_papers, 1):
                paper_title = (paper.title or "Untitled")[:50]
                progress.update(task, description=f"[cyan]Full-text screening: {paper_title}... ({i}/{len(self.screened_papers)})")

                # Verbose output for full-text screening (using progress.log to work with progress bar)
                # Show ALL papers when verbose mode is enabled
                if is_verbose:
                    progress.log(
                        f"[bold cyan]Full-text screening paper {i}/{len(self.screened_papers)}:[/bold cyan] "
                        f"[cyan]{paper_title}...[/cyan]"
                    )

                # Retrieve full-text PDF
                full_text = self.pdf_retriever.retrieve_full_text(paper)
                
                # Track full-text availability
                if full_text:
                    self.fulltext_available_count += 1
                else:
                    self.fulltext_unavailable_count += 1

                # Verbose output about content being analyzed
                if is_verbose:
                    if full_text:
                        text_length = len(full_text)
                        progress.log(
                            f"  [dim]-> Analyzing full-text ({text_length} chars), "
                            f"title ({len(paper.title or '')} chars), "
                            f"abstract ({len(paper.abstract or '')} chars)[/dim]"
                        )
                    else:
                        progress.log(
                            f"  [dim]-> Full-text not available, falling back to title/abstract screening[/dim]"
                        )
                    progress.log(
                        f"  [dim]-> Calling LLM ({self.fulltext_screener.llm_model})...[/dim]"
                    )

                result = self.fulltext_screener.screen(
                    paper.title or "",
                    paper.abstract or "",
                    full_text,
                    inclusion_criteria,
                    exclusion_criteria,
                    topic_context=fulltext_context,
                )
                
                # Store result for validation
                self.fulltext_results.append(result)

                # Verbose output for decision (using progress.log to work with progress bar)
                if is_verbose:
                    decision_str = result.decision.value.upper()
                    confidence_str = f"{result.confidence:.2f}"
                    reasoning_preview = result.reasoning[:100] if result.reasoning else "No reasoning"
                    
                    if result.decision.value == "include":
                        status_color = "[green]INCLUDE[/green]"
                    elif result.decision.value == "exclude":
                        status_color = "[red]EXCLUDE[/red]"
                    else:
                        status_color = "[yellow]UNCERTAIN[/yellow]"
                    
                    progress.log(
                        f"  [dim]-> Decision:[/dim] {status_color}, "
                        f"Confidence: {confidence_str}"
                    )
                    if self.debug_config.level == DebugLevel.FULL:
                        progress.log(f"  [dim]-> Reasoning: {reasoning_preview}...[/dim]")
                        if result.exclusion_reason:
                            progress.log(f"  [dim]-> Exclusion reason: {result.exclusion_reason}[/dim]")

                if result.decision.value == "include":
                    self.eligible_papers.append(paper)
                    if is_verbose:
                        progress.log(f"  [green]Paper eligible[/green]")
                else:
                    if is_verbose:
                        progress.log(f"  [red]Paper excluded[/red]")

                progress.advance(task)

                # Update description with current status
                if i % 5 == 0 or i == len(self.screened_papers):
                    progress.update(
                        task,
                        description=f"[cyan]Full-text screening: {paper_title}... ({len(self.eligible_papers)} eligible)",
                    )

        logger.info(
            f"Full-text screening complete: {len(self.eligible_papers)}/{len(self.screened_papers)} papers eligible"
        )
        logger.info(
            f"Full-text availability: {self.fulltext_available_count} available, "
            f"{self.fulltext_unavailable_count} unavailable"
        )
        
        # Calculate and validate screening statistics
        if self.fulltext_results:
            stats = self.screening_validator.calculate_statistics(
                self.screened_papers,
                self.fulltext_results,
                ScreeningStage.FULL_TEXT
            )
            self.screening_validator.log_statistics(ScreeningStage.FULL_TEXT)

        # Enrich topic context
        self.topic_context.enrich(
            [
                f"Full-text screened {len(self.screened_papers)} papers, {len(self.eligible_papers)} eligible",
                f"Full-text available for {self.fulltext_available_count} papers"
            ]
        )

    def _enrich_papers(self):
        """Enrich papers with missing metadata (affiliations, countries, etc.)."""
        logger.info(f"Enriching {len(self.final_papers)} papers with missing metadata...")
        self.final_papers = self.paper_enricher.enrich_papers(self.final_papers)
        logger.info("Paper enrichment complete")

    def _extract_data(self):
        """Extract structured data from included papers."""
        self.extracted_data = []

        logger.info(f"Starting data extraction from {len(self.final_papers)} papers...")
        logger.info("This may take a while as each paper requires an LLM call.")

        # Check if verbose mode is enabled
        is_verbose = self.debug_config.enabled and self.debug_config.level in [
            DebugLevel.DETAILED,
            DebugLevel.FULL,
        ]

        # Get topic context for extraction agent
        extraction_context = self.topic_context.get_for_agent("extraction_agent")

        # Create handoff
        self.handoff_protocol.create_handoff(
            from_agent="fulltext_screener",
            to_agent="extraction_agent",
            stage="extraction",
            topic_context=self.topic_context,
            data={"papers_count": len(self.final_papers)},
            metadata={"extraction_type": "structured"},
        )

        # Use Rich progress bar for data extraction
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"[cyan]Extracting data with {self.extractor.llm_model}...",
                total=len(self.final_papers),
            )

            for i, paper in enumerate(self.final_papers, 1):
                paper_title = (paper.title or "Untitled")[:50]
                progress.update(task, description=f"[cyan]Extracting: {paper_title}...")

                # Verbose output for data extraction (using progress.log to work with progress bar)
                if is_verbose:
                    progress.log(
                        f"[bold cyan]Extracting paper {i}/{len(self.final_papers)}:[/bold cyan] "
                        f"[cyan]{paper_title}...[/cyan]"
                    )
                    progress.log(
                        f"  [dim]-> Building extraction prompt with fields: study_objectives, methodology, "
                        f"study_design, participants, interventions, outcomes, key_findings, limitations...[/dim]"
                    )
                    progress.log(
                        f"  [dim]-> Calling LLM ({self.extractor.llm_model}) for structured extraction...[/dim]"
                    )

                # In production, would fetch full-text
                full_text = None

                extracted = self.extractor.extract(
                    paper.title or "",
                    paper.abstract or "",
                    full_text,
                    topic_context=extraction_context,
                )

                # Update with paper metadata
                extracted.title = paper.title or ""
                extracted.authors = paper.authors or []
                extracted.year = paper.year
                extracted.journal = paper.journal
                extracted.doi = paper.doi

                self.extracted_data.append(extracted)
                
                # Verbose output for extraction result
                if is_verbose:
                    objectives_count = len(extracted.study_objectives) if extracted.study_objectives else 0
                    outcomes_count = len(extracted.outcomes) if extracted.outcomes else 0
                    findings_count = len(extracted.key_findings) if extracted.key_findings else 0
                    progress.log(
                        f"  [green]Extraction complete[/green] - "
                        f"Objectives: {objectives_count}, Outcomes: {outcomes_count}, Findings: {findings_count}"
                    )
                    if self.debug_config.level == DebugLevel.FULL:
                        methodology_preview = (extracted.methodology or "")[:100]
                        if methodology_preview:
                            progress.log(f"  [dim]-> Methodology preview: {methodology_preview}...[/dim]")
                
                progress.advance(task)

                # Update description with current status
                if i % 5 == 0 or i == len(self.final_papers):
                    progress.update(
                        task,
                        description=f"[cyan]Extracting: {paper_title}... ({len(self.extracted_data)} extracted)",
                    )

        # Accumulate findings in topic context
        findings = [extracted.to_dict() for extracted in self.extracted_data]
        self.topic_context.accumulate_findings(findings)

    def _quality_assessment(self) -> Dict[str, Any]:
        """
        Quality assessment phase: Generate template or load assessments.
        
        Returns:
            Dictionary with risk of bias and GRADE assessment data
        """
        from ..quality import (
            QualityAssessmentTemplateGenerator,
            RiskOfBiasAssessor,
            GRADEAssessor,
        )

        # Get quality assessment config
        qa_config = self.config.get("quality_assessment", {})
        risk_of_bias_tool = qa_config.get("risk_of_bias_tool", "RoB 2")
        grade_assessment = qa_config.get("grade_assessment", True)
        
        # Get template path
        template_path_template = qa_config.get(
            "template_path", 
            f"data/quality_assessments/{{workflow_id}}_assessments.json"
        )
        template_path = template_path_template.format(workflow_id=self.workflow_id)
        template_path_obj = Path(template_path)
        template_path_obj.parent.mkdir(parents=True, exist_ok=True)

        # Initialize assessors
        template_generator = QualityAssessmentTemplateGenerator(risk_of_bias_tool)
        rob_assessor = RiskOfBiasAssessor()
        grade_assessor = GRADEAssessor()

        # Check if assessment file exists
        if not template_path_obj.exists():
            # Generate template and stop workflow
            logger.info("Quality assessment template not found. Generating template...")
            
            # Infer GRADE outcomes from extracted data
            grade_outcomes = []
            if grade_assessment:
                all_outcomes = set()
                for data in self.extracted_data:
                    all_outcomes.update(data.outcomes)
                grade_outcomes = sorted(list(all_outcomes))[:10]  # Limit to 10 outcomes
            
            template_path_str = template_generator.generate_template(
                self.extracted_data,
                str(template_path_obj),
                grade_outcomes=grade_outcomes if grade_outcomes else None,
            )
            
            logger.error("=" * 60)
            logger.error("QUALITY ASSESSMENT REQUIRED")
            logger.error("=" * 60)
            logger.error(f"Quality assessment template generated at: {template_path_str}")
            logger.error("")
            logger.error("Please complete the quality assessments in the template file:")
            logger.error(f"  1. Open: {template_path_str}")
            logger.error(f"  2. Complete risk of bias assessments for all studies")
            if grade_assessment:
                logger.error(f"  3. Complete GRADE assessments for all outcomes")
            logger.error(f"  4. Save the file")
            logger.error(f"  5. Re-run the workflow (it will resume from this point)")
            logger.error("")
            logger.error("The workflow will stop here until assessments are completed.")
            logger.error("=" * 60)
            
            raise RuntimeError(
                f"Quality assessment template generated at {template_path_str}. "
                "Please complete the assessments and re-run the workflow."
            )

        # Load assessments
        logger.info(f"Loading quality assessments from {template_path_obj}")
        
        risk_of_bias_assessments = []
        grade_assessments_list = []
        
        try:
            risk_of_bias_assessments = rob_assessor.load_assessments(str(template_path_obj))
            logger.info(f"Loaded {len(risk_of_bias_assessments)} risk of bias assessments")
        except Exception as e:
            logger.warning(f"Could not load risk of bias assessments: {e}")
        
        if grade_assessment:
            try:
                grade_assessments_list = grade_assessor.load_assessments(str(template_path_obj))
                logger.info(f"Loaded {len(grade_assessments_list)} GRADE assessments")
            except Exception as e:
                logger.warning(f"Could not load GRADE assessments: {e}")

        # Generate summary tables and narratives
        risk_of_bias_table = ""
        risk_of_bias_summary = ""
        if risk_of_bias_assessments:
            risk_of_bias_table = rob_assessor.generate_summary_table(risk_of_bias_assessments)
            risk_of_bias_summary = rob_assessor.generate_narrative_summary(risk_of_bias_assessments)

        grade_table = ""
        grade_summary = ""
        if grade_assessments_list:
            grade_table = grade_assessor.generate_evidence_profile_table(grade_assessments_list)
            grade_summary = grade_assessor.generate_narrative_summary(grade_assessments_list)

        # Store for use in writing agents
        self.quality_assessment_data = {
            "risk_of_bias_assessments": risk_of_bias_assessments,
            "risk_of_bias_table": risk_of_bias_table,
            "risk_of_bias_summary": risk_of_bias_summary,
            "grade_assessments": grade_assessments_list,
            "grade_table": grade_table,
            "grade_summary": grade_summary,
        }

        return self.quality_assessment_data

    def _generate_prisma_diagram(self) -> str:
        """Generate PRISMA flow diagram."""
        generator = PRISMAGenerator(self.prisma_counter)
        output_path = self.output_dir / "prisma_diagram.png"
        path = generator.generate(str(output_path), format="png")
        return path

    def _generate_visualizations(self) -> Dict[str, str]:
        """Generate bibliometric visualizations."""
        paths = {}

        # Papers per year
        year_path = self.chart_generator.papers_per_year(self.final_papers)
        if year_path:
            paths["papers_per_year"] = year_path

        # Network graph
        network_path = self.chart_generator.network_graph(self.final_papers)
        if network_path:
            paths["network_graph"] = network_path

        # Papers by country (placeholder)
        country_path = self.chart_generator.papers_by_country(self.final_papers)
        if country_path:
            paths["papers_by_country"] = country_path

        # Papers by subject (placeholder)
        subject_path = self.chart_generator.papers_by_subject(self.final_papers)
        if subject_path:
            paths["papers_by_subject"] = subject_path

        # Quality assessment visualizations
        if self.quality_assessment_data:
            # Risk of bias plot
            rob_assessments = self.quality_assessment_data.get("risk_of_bias_assessments", [])
            if rob_assessments:
                # Convert to list of dicts for visualization
                rob_data = []
                for assessment in rob_assessments:
                    rob_data.append({
                        "study_id": assessment.study_id if hasattr(assessment, 'study_id') else assessment.get("study_id", ""),
                        "domains": assessment.domains if hasattr(assessment, 'domains') else assessment.get("domains", {}),
                    })
                rob_plot_path = self.chart_generator.generate_risk_of_bias_plot(rob_data)
                if rob_plot_path:
                    paths["risk_of_bias_plot"] = rob_plot_path

            # GRADE evidence profile
            grade_assessments = self.quality_assessment_data.get("grade_assessments", [])
            if grade_assessments:
                # Convert to list of dicts for visualization
                grade_data = []
                for assessment in grade_assessments:
                    grade_data.append({
                        "outcome": assessment.outcome if hasattr(assessment, 'outcome') else assessment.get("outcome", ""),
                        "certainty": assessment.certainty if hasattr(assessment, 'certainty') else assessment.get("certainty", ""),
                    })
                grade_plot_path = self.chart_generator.generate_grade_evidence_profile(grade_data)
                if grade_plot_path:
                    paths["grade_evidence_profile"] = grade_plot_path

        return paths

    def _write_article(self) -> Dict[str, str]:
        """Write all article sections."""
        sections = {}

        logger.info("Starting article writing phase...")
        logger.info("This will generate Introduction, Methods, Results, and Discussion sections.")
        logger.info("Each section requires an LLM call and may take some time.")

        # Get topic context for writing agents
        writing_context = self.topic_context.get_for_agent("introduction_writer")

        # Introduction
        with console.status(
            f"[bold cyan][1/4] Writing Introduction with {self.intro_writer.llm_model}..."
        ):
            research_question = self.topic_context.research_question or self.topic_context.topic
            justification = (
                self.topic_context.context or f"Systematic review of {self.topic_context.topic}"
            )

            self.handoff_protocol.create_handoff(
                from_agent="extraction_agent",
                to_agent="introduction_writer",
                stage="writing",
                topic_context=self.topic_context,
                data={"research_question": research_question},
                metadata={"section": "introduction"},
            )

            intro = self.intro_writer.write(
                research_question, justification, topic_context=writing_context
            )
            sections["introduction"] = intro
        console.print("[green]✓[/green] Introduction section complete")

        # Methods
        with console.status(
            f"[bold cyan][2/4] Writing Methods with {self.methods_writer.llm_model}..."
        ):
            # Ensure search_strategy exists (rebuild if None, e.g., when resuming from checkpoint)
            if self.search_strategy is None:
                logger.warning("search_strategy is None, rebuilding it for article writing")
                try:
                    self._build_search_strategy()
                    if self.search_strategy is None:
                        raise RuntimeError("Failed to build search strategy - search_strategy is still None after _build_search_strategy()")
                except Exception as e:
                    logger.error(f"Failed to build search strategy: {e}", exc_info=True)
                    raise RuntimeError(f"Cannot write Methods section without search strategy: {e}") from e
            
            search_strategy_desc = self.search_strategy.get_strategy_description()
            databases = self.config["workflow"]["databases"]
            inclusion_criteria = [
                self.topic_context.inject_into_prompt(c)
                for c in self.config["criteria"]["inclusion"]
            ]
            exclusion_criteria = [
                self.topic_context.inject_into_prompt(c)
                for c in self.config["criteria"]["exclusion"]
            ]

            self.handoff_protocol.create_handoff(
                from_agent="introduction_writer",
                to_agent="methods_writer",
                stage="writing",
                topic_context=self.topic_context,
                data={"databases": databases},
                metadata={"section": "methods"},
            )

            # Get full search strategies for all databases
            # Ensure search_strategy exists (should already be set above, but double-check)
            if self.search_strategy is None:
                logger.error("search_strategy is None when getting database queries - this should not happen")
                raise RuntimeError("search_strategy is None - cannot get database queries")
            full_search_strategies = self.search_strategy.get_database_queries()
            # Filter to only databases that were actually searched
            searched_db_strategies = {
                db: query for db, query in full_search_strategies.items() if db in databases
            }
            
            # Get protocol information from config
            protocol_info = self.config.get("protocol", {})
            
            # Build automation details
            automation_details = (
                "Large language models (LLMs) were used to assist with: "
                "(1) title/abstract screening for borderline cases after keyword pre-filtering, "
                "(2) full-text screening, and "
                "(3) structured data extraction. "
                "All LLM outputs were verified and supplemented by human reviewers to ensure accuracy."
            )

            methods = self.methods_writer.write(
                search_strategy_desc,
                databases,
                inclusion_criteria,
                exclusion_criteria,
                "Two-stage screening: title/abstract then full-text",
                "Structured data extraction using LLM",
                self.prisma_counter.get_counts(),
                topic_context=writing_context,
                full_search_strategies=searched_db_strategies,
                protocol_info=protocol_info,
                automation_details=automation_details,
            )
            sections["methods"] = methods
        console.print("[green]✓[/green] Methods section complete")

        # Results
        with console.status(
            f"[bold cyan][3/4] Writing Results with {self.results_writer.llm_model}..."
        ):
            key_findings = []
            for data in self.extracted_data:
                key_findings.extend(data.key_findings[:2])  # Top 2 findings per study

            self.handoff_protocol.create_handoff(
                from_agent="methods_writer",
                to_agent="results_writer",
                stage="writing",
                topic_context=self.topic_context,
                data={"extracted_data_count": len(self.extracted_data)},
                metadata={"section": "results"},
            )

            # Get quality assessment data if available
            risk_of_bias_summary = None
            risk_of_bias_table = None
            grade_assessments = None
            grade_table = None
            
            if self.quality_assessment_data:
                risk_of_bias_summary = self.quality_assessment_data.get("risk_of_bias_summary")
                risk_of_bias_table = self.quality_assessment_data.get("risk_of_bias_table")
                grade_assessments = self.quality_assessment_data.get("grade_summary")
                grade_table = self.quality_assessment_data.get("grade_table")

            results = self.results_writer.write(
                self.extracted_data,
                self.prisma_counter.get_counts(),
                key_findings[:10],  # Top 10 findings
                topic_context=writing_context,
                risk_of_bias_summary=risk_of_bias_summary,
                risk_of_bias_table=risk_of_bias_table,
                grade_assessments=grade_assessments,
                grade_table=grade_table,
            )
            sections["results"] = results
        console.print("[green]✓[/green] Results section complete")

        # Discussion
        with console.status(
            f"[bold cyan][4/4] Writing Discussion with {self.discussion_writer.llm_model}..."
        ):
            self.handoff_protocol.create_handoff(
                from_agent="results_writer",
                to_agent="discussion_writer",
                stage="writing",
                topic_context=self.topic_context,
                data={"key_findings_count": len(key_findings[:10])},
                metadata={"section": "discussion"},
            )

            discussion = self.discussion_writer.write(
                research_question,
                key_findings[:10],
                self.extracted_data,
                [
                    "Limited to English-language publications",
                    "Potential publication bias",
                ],
                ["Implications for practice", "Future research directions"],
                topic_context=writing_context,
            )
            sections["discussion"] = discussion
        console.print("[green]✓[/green] Discussion section complete")

        # Abstract (generate after all sections are written)
        with console.status(
            f"[bold cyan][5/5] Generating Abstract..."
        ):
            research_question = self.topic_context.research_question or self.topic_context.topic
            abstract = self.abstract_generator.generate(
                research_question, self.final_papers, sections
            )
            sections["abstract"] = abstract
        console.print("[green]✓[/green] Abstract generation complete")
        console.print(
            "[bold green]Article writing phase complete - all 5 sections generated[/bold green]"
        )

        return sections

    def _generate_final_report(
        self,
        article_sections: Dict[str, str],
        prisma_path: str,
        viz_paths: Dict[str, str],
    ) -> str:
        """Generate final markdown report."""
        from ..citations import CitationManager

        report_path = self.output_dir / "final_report.md"

        # Initialize citation manager with included papers
        citation_manager = CitationManager(self.final_papers)

        with open(report_path, "w") as f:
            # Generate topic-specific title
            topic = self.topic_context.topic or "Systematic Review"
            title = f"{topic}: A Systematic Review"
            f.write(f"# {title}\n\n")
            
            # Abstract
            abstract = article_sections.get("abstract", "")
            if abstract:
                f.write("## Abstract\n\n")
                f.write("**Systematic Review**\n\n")
                f.write(abstract)
                f.write("\n\n---\n\n")
            
            # Keywords - aggregate from topic context and papers
            keywords = self.topic_context.keywords if hasattr(self.topic_context, 'keywords') else []
            
            # Also extract keywords from included papers
            paper_keywords = []
            for paper in self.final_papers:
                if paper.keywords:
                    if isinstance(paper.keywords, list):
                        paper_keywords.extend(paper.keywords)
                    elif isinstance(paper.keywords, str):
                        # Handle comma-separated keywords
                        paper_keywords.extend([kw.strip() for kw in paper.keywords.split(",")])
            
            # Combine and deduplicate keywords
            all_keywords = list(set(keywords + paper_keywords))
            
            # Prioritize topic keywords, then add paper keywords
            # Remove duplicates while preserving order
            seen = set()
            keywords_to_use = []
            for kw in keywords + paper_keywords:
                kw_lower = kw.lower().strip()
                if kw_lower and kw_lower not in seen:
                    seen.add(kw_lower)
                    keywords_to_use.append(kw.strip())
            
            # Limit to 5-10 keywords for IEEE
            keywords_to_use = keywords_to_use[:10]
            
            if keywords_to_use:
                keywords_text = ", ".join(keywords_to_use)
                f.write("## Keywords\n\n")
                f.write(f"**Keywords:** {keywords_text}\n\n")
                f.write("---\n\n")

            # Introduction (with citation processing)
            intro_text = citation_manager.extract_and_map_citations(article_sections["introduction"])
            f.write("## Introduction\n\n")
            f.write(intro_text)
            f.write("\n\n---\n\n")

            # Methods (with citation processing)
            methods_text = citation_manager.extract_and_map_citations(article_sections["methods"])
            f.write("## Methods\n\n")
            f.write(methods_text)
            f.write("\n\n---\n\n")

            # Results (with citation processing)
            results_text = citation_manager.extract_and_map_citations(article_sections["results"])
            
            # Insert PRISMA diagram into Results section after Study Selection subsection
            # Find the end of Study Selection subsection or insert after first paragraph
            prisma_insertion_point = results_text.find("### Study Selection")
            if prisma_insertion_point != -1:
                # Find the end of Study Selection subsection (next ### or end of text)
                next_subsection = results_text.find("\n### ", prisma_insertion_point + 1)
                if next_subsection == -1:
                    # No next subsection, insert before end
                    insertion_pos = len(results_text)
                else:
                    # Insert before next subsection
                    insertion_pos = next_subsection
                
                # Insert PRISMA diagram
                prisma_section = f"\n\n![PRISMA Diagram]({prisma_path})\n\n"
                prisma_section += "**Figure 1:** PRISMA 2020 flow diagram showing the study selection process.\n\n"
                results_text = results_text[:insertion_pos] + prisma_section + results_text[insertion_pos:]
            else:
                # If Study Selection subsection not found, insert PRISMA diagram at the beginning
                prisma_section = f"![PRISMA Diagram]({prisma_path})\n\n"
                prisma_section += "**Figure 1:** PRISMA 2020 flow diagram showing the study selection process.\n\n\n"
                results_text = prisma_section + results_text
            
            # Insert visualizations into Results section after Synthesis subsection
            figure_num = 2  # PRISMA diagram is Figure 1
            if viz_paths:
                # Build visualizations section
                viz_section = "\n\n"
                for name, path in viz_paths.items():
                    viz_name = name.replace('_', ' ').title()
                    # Handle HTML files (network graph) differently from images
                    if path.endswith('.html'):
                        viz_section += f"[Interactive {viz_name}]({path})\n\n"
                        # Also try to reference PNG version if it exists
                        png_path = path.replace('.html', '.png')
                        png_full_path = self.output_dir / Path(png_path).name
                        if png_full_path.exists():
                            caption = f"**Figure {figure_num}:** {viz_name} showing bibliometric analysis of included studies.\n\n"
                            viz_section += f"![{name}]({png_path})\n\n"
                            viz_section += caption
                            figure_num += 1
                    else:
                        caption = f"**Figure {figure_num}:** {viz_name} showing bibliometric analysis of included studies.\n\n"
                        viz_section += f"![{name}]({path})\n\n"
                        viz_section += caption
                        figure_num += 1
                
                # Find Synthesis subsection using multiple patterns (3-level and 4-level headers)
                synthesis_patterns = [
                    "### Synthesis",
                    "### Results of Syntheses",
                    "### Synthesis of Results",
                    "#### Synthesis",
                    "#### Synthesis of Findings",
                    "#### Results of Syntheses",
                    "#### Synthesis of Results"
                ]
                
                synthesis_insertion_point = -1
                for pattern in synthesis_patterns:
                    synthesis_insertion_point = results_text.find(pattern)
                    if synthesis_insertion_point != -1:
                        break
                
                if synthesis_insertion_point != -1:
                    # Find end of Synthesis subsection (next subsection at any level)
                    # Check for both 3-level (###) and 4-level (####) headers
                    next_subsection_3 = results_text.find("\n### ", synthesis_insertion_point + 1)
                    next_subsection_4 = results_text.find("\n#### ", synthesis_insertion_point + 1)
                    
                    # Find the earliest next subsection
                    next_subsection = -1
                    if next_subsection_3 != -1 and next_subsection_4 != -1:
                        next_subsection = min(next_subsection_3, next_subsection_4)
                    elif next_subsection_3 != -1:
                        next_subsection = next_subsection_3
                    elif next_subsection_4 != -1:
                        next_subsection = next_subsection_4
                    
                    if next_subsection == -1:
                        # No next subsection found, check for separator before inserting
                        separator_pos = results_text.find("\n---\n", synthesis_insertion_point)
                        if separator_pos != -1:
                            insertion_pos = separator_pos
                        else:
                            insertion_pos = len(results_text)
                    else:
                        insertion_pos = next_subsection
                    
                    results_text = results_text[:insertion_pos] + viz_section + results_text[insertion_pos:]
                else:
                    # No synthesis subsection found, insert before separator or at end
                    # Check for separator that marks end of Results section
                    separator_pos = results_text.find("\n---\n")
                    if separator_pos != -1:
                        # Insert before separator to keep visualizations in Results section
                        insertion_pos = separator_pos
                        results_text = results_text[:insertion_pos] + viz_section + results_text[insertion_pos:]
                    else:
                        # No separator found, append at end
                        results_text = results_text + viz_section
            
            # Write the modified results text
            f.write("## Results\n\n")
            f.write(results_text)
            f.write("\n\n---\n\n")

            # Discussion (with citation processing)
            discussion_text = citation_manager.extract_and_map_citations(article_sections["discussion"])
            f.write("## Discussion\n\n")
            f.write(discussion_text)
            f.write("\n\n---\n\n")

            # References section (before Summary)
            references_section = citation_manager.generate_references_section()
            f.write(references_section)
            f.write("\n---\n\n")

            # Registration (PRISMA 2020: Other Information)
            protocol_info = self.config.get("protocol", {})
            f.write("## Registration\n\n")
            if protocol_info.get("registered", False):
                registry = protocol_info.get("registry", "PROSPERO")
                reg_number = protocol_info.get("registration_number", "")
                reg_url = protocol_info.get("url", "")
                if reg_number:
                    f.write(f"This systematic review was registered with {registry} (registration number: {reg_number}).")
                    if reg_url:
                        f.write(f" The protocol can be accessed at: {reg_url}")
                    f.write("\n\n")
                else:
                    f.write(f"This systematic review was registered with {registry}.\n\n")
            else:
                f.write("This systematic review was not registered.\n\n")
            f.write("---\n\n")
            
            # Funding Statement (PRISMA 2020: Other Information)
            funding_config = self.config.get("funding", {})
            f.write("## Funding\n\n")
            funding_source = funding_config.get("source", "No funding received")
            grant_number = funding_config.get("grant_number", "")
            funder = funding_config.get("funder", "")
            
            if grant_number:
                f.write(f"This work was supported by {funder} (grant number: {grant_number}).\n\n")
            elif funder:
                f.write(f"This work was supported by {funder}.\n\n")
            else:
                f.write(f"{funding_source}.\n\n")
            f.write("---\n\n")

            # Conflicts of Interest Statement (PRISMA 2020: Other Information)
            coi_config = self.config.get("conflicts_of_interest", {})
            f.write("## Conflicts of Interest\n\n")
            coi_statement = coi_config.get("statement", "The authors declare no conflicts of interest.")
            f.write(f"{coi_statement}\n\n")
            f.write("---\n\n")

            # Data Availability Statement (PRISMA 2020: Other Information)
            supplementary_config = self.config.get("supplementary_materials", {})
            f.write("## Data Availability Statement\n\n")
            available_materials = []
            if supplementary_config.get("search_strategies", True):
                available_materials.append("Full search strategies for all databases")
            if supplementary_config.get("extracted_data", True):
                available_materials.append("Extracted data from included studies")
            if supplementary_config.get("analysis_code", False):
                available_materials.append("Analysis code")
            
            if available_materials:
                f.write("The following materials are available as supplementary materials:\n\n")
                for material in available_materials:
                    f.write(f"- {material}\n")
                f.write("\n")
            else:
                f.write("Data availability information is not specified.\n\n")

        return str(report_path)

    def _export_report(
        self,
        article_sections: Dict[str, str],
        prisma_path: str,
        viz_paths: Dict[str, str],
    ) -> Dict[str, str]:
        """Export report to LaTeX and Word formats."""
        from ..citations import CitationManager
        from ..export.latex_exporter import LaTeXExporter
        from ..export.word_exporter import WordExporter

        export_paths = {}
        citation_manager = CitationManager(self.final_papers)

        # Aggregate keywords from topic context and papers
        keywords = self.topic_context.keywords if hasattr(self.topic_context, 'keywords') else []
        paper_keywords = []
        for paper in self.final_papers:
            if paper.keywords:
                if isinstance(paper.keywords, list):
                    paper_keywords.extend(paper.keywords)
                elif isinstance(paper.keywords, str):
                    paper_keywords.extend([kw.strip() for kw in paper.keywords.split(",")])
        
        # Combine and deduplicate keywords
        seen = set()
        all_keywords = []
        for kw in keywords + paper_keywords:
            kw_lower = kw.lower().strip()
            if kw_lower and kw_lower not in seen:
                seen.add(kw_lower)
                all_keywords.append(kw.strip())
        
        # Limit to 5-10 keywords for IEEE
        all_keywords = all_keywords[:10]
        
        # Prepare report data
        report_data = {
            "title": f"Systematic Review: {self.topic_context.topic}",
            "abstract": article_sections.get("abstract", ""),
            "keywords": all_keywords,
            "introduction": citation_manager.extract_and_map_citations(article_sections.get("introduction", "")),
            "methods": citation_manager.extract_and_map_citations(article_sections.get("methods", "")),
            "results": citation_manager.extract_and_map_citations(article_sections.get("results", "")),
            "discussion": citation_manager.extract_and_map_citations(article_sections.get("discussion", "")),
            "references": citation_manager.get_references(),
            "figures": [],
        }

        # Add figures
        if prisma_path:
            report_data["figures"].append({
                "path": prisma_path,
                "caption": "PRISMA 2020 flow diagram showing the study selection process.",
            })

        for name, path in viz_paths.items():
            if not path.endswith('.html'):
                report_data["figures"].append({
                    "path": path,
                    "caption": f"{name.replace('_', ' ').title()} showing bibliometric analysis of included studies.",
                })

        # Export to LaTeX if requested
        export_config = self.config.get("output", {}).get("formats", [])
        if "latex" in export_config:
            latex_exporter = LaTeXExporter()
            latex_path = self.output_dir / "final_report.tex"
            latex_exporter.export(report_data, str(latex_path), journal="IEEE")
            export_paths["latex"] = str(latex_path)
            logger.info(f"LaTeX export generated: {latex_path}")

        # Export to Word if requested
        if "word" in export_config or "docx" in export_config:
            word_exporter = WordExporter()
            word_path = self.output_dir / "final_report.docx"
            word_exporter.export(report_data, str(word_path))
            export_paths["word"] = str(word_path)
            logger.info(f"Word export generated: {word_path}")

        # Export to BibTeX if requested
        if "bibtex" in export_config:
            bibtex_path = self.output_dir / "references.bib"
            citation_manager.export_bibtex(str(bibtex_path))
            export_paths["bibtex"] = str(bibtex_path)
            logger.info(f"BibTeX file generated: {bibtex_path}")

        # Export to RIS if requested
        if "ris" in export_config:
            ris_path = self.output_dir / "references.ris"
            citation_manager.export_ris(str(ris_path))
            export_paths["ris"] = str(ris_path)
            logger.info(f"RIS file generated: {ris_path}")

        return export_paths

    def _export_search_strategies(self) -> Optional[str]:
        """Export search strategies to markdown file."""
        try:
            # Get search strategies from search_strategy builder
            # Ensure search_strategy exists
            if self.search_strategy is None:
                logger.warning("search_strategy is None, rebuilding it for export")
                self._build_search_strategy()
            database_queries = self.search_strategy.get_database_queries()
            databases_searched = self.config["workflow"]["databases"]

            output_path = self.output_dir / "search_strategies.md"
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("# Search Strategies\n\n")
                f.write("This document contains the complete search strategies used for all databases.\n\n")
                f.write("---\n\n")

                for db_name in databases_searched:
                    if db_name in database_queries:
                        f.write(f"## {db_name}\n\n")
                        f.write("**Full Search Strategy:**\n\n")
                        f.write("```\n")
                        f.write(database_queries[db_name])
                        f.write("\n```\n\n")
                        f.write("---\n\n")

            logger.info(f"Search strategies exported to {output_path}")
            return str(output_path)
        except Exception as e:
            logger.warning(f"Could not export search strategies: {e}")
            return None

    def _generate_extraction_forms(self) -> Optional[str]:
        """Generate data extraction form templates."""
        from ..export.extraction_form_generator import ExtractionFormGenerator

        try:
            generator = ExtractionFormGenerator()
            form_path = self.output_dir / "data_extraction_form.md"
            path = generator.generate_form(str(form_path), format="markdown")
            return path
        except Exception as e:
            logger.warning(f"Could not generate extraction form: {e}")
            return None

    def _generate_prisma_checklist(self, report_path: str) -> Optional[str]:
        """Generate PRISMA 2020 checklist file."""
        from ..prisma.checklist_generator import PRISMAChecklistGenerator

        try:
            with open(report_path, "r", encoding="utf-8") as f:
                report_content = f.read()

            generator = PRISMAChecklistGenerator()
            checklist_path = self.output_dir / "prisma_checklist.json"
            path = generator.generate_checklist(report_content, str(checklist_path))
            return path
        except Exception as e:
            logger.warning(f"Could not generate PRISMA checklist: {e}")
            return None

    def _save_workflow_state(self) -> str:
        """Save workflow state to JSON."""
        state_path = self.output_dir / "workflow_state.json"

        state = {
            "topic_context": self.topic_context.to_dict(),
            "prisma_counts": self.prisma_counter.get_counts(),
            "database_breakdown": self.prisma_counter.get_database_breakdown(),
            "num_papers": {
                "total": len(self.all_papers),
                "unique": len(self.unique_papers),
                "screened": len(self.screened_papers),
                "eligible": len(self.eligible_papers),
                "final": len(self.final_papers),
            },
            "config_summary": {
                "topic": self.topic_context.topic,
                "domain": self.topic_context.domain,
                "research_question": self.topic_context.research_question,
            },
        }

        with open(state_path, "w") as f:
            json.dump(state, f, indent=2, default=str)

        return str(state_path)

    def _generate_workflow_id(self) -> str:
        """Generate unique workflow ID."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        topic_slug = self.topic_context.topic.lower().replace(" ", "_")[:30]
        return f"workflow_{topic_slug}_{timestamp}"
    
    def _find_existing_checkpoint_by_topic(self) -> Optional[Dict[str, Any]]:
        """
        Find existing checkpoint for the same topic.
        
        Returns:
            Dictionary with checkpoint_path and latest_phase, or None if not found
        """
        checkpoint_base = Path("data/checkpoints")
        if not checkpoint_base.exists():
            logger.debug("Checkpoint directory does not exist")
            return None
        
        current_topic = self.topic_context.topic.lower().strip()
        logger.debug(f"Looking for checkpoints matching topic: '{current_topic}'")
        
        workflow_dirs = [d for d in checkpoint_base.iterdir() if d.is_dir()]
        logger.debug(f"Found {len(workflow_dirs)} workflow directories to check")
        
        # Look through all workflow directories
        for workflow_dir in workflow_dirs:
            # Check if this workflow matches our topic
            # Look for any checkpoint file to read topic_context
            checkpoint_files = list(workflow_dir.glob("*_state.json"))
            if not checkpoint_files:
                logger.debug(f"No checkpoint files found in {workflow_dir.name}")
                continue
            
            logger.debug(f"Checking workflow {workflow_dir.name} ({len(checkpoint_files)} checkpoint files)")
            
            # Try to find the latest checkpoint and check its topic
            latest_checkpoint = max(checkpoint_files, key=lambda p: p.stat().st_mtime)
            
            try:
                with open(latest_checkpoint, "r") as f:
                    checkpoint_data = json.load(f)
                
                # Check if topic matches
                checkpoint_topic = checkpoint_data.get("topic_context", {}).get("topic", "").lower().strip()
                logger.debug(f"  Checkpoint topic: '{checkpoint_topic}'")
                
                if checkpoint_topic == current_topic:
                    logger.info(f"  Topic match found in workflow {workflow_dir.name}!")
                    # Find the latest phase checkpoint (check all possible phases)
                    phase_order = [
                        "report_generation",
                        "article_writing",
                        "visualization_generation",
                        "prisma_generation",
                        "quality_assessment",
                        "data_extraction",
                        "paper_enrichment",
                        "fulltext_screening",
                        "title_abstract_screening",
                        "deduplication",
                        "search_databases",
                    ]
                    
                    latest_phase = None
                    latest_phase_time = 0
                    
                    for checkpoint_file in checkpoint_files:
                        try:
                            with open(checkpoint_file, "r") as cf:
                                cp_data = json.load(cf)
                                phase = cp_data.get("phase", "")
                                if phase in phase_order:
                                    mtime = checkpoint_file.stat().st_mtime
                                    if mtime > latest_phase_time:
                                        latest_phase_time = mtime
                                        latest_phase = phase
                        except Exception as e:
                            logger.debug(f"Error reading checkpoint file {checkpoint_file}: {e}")
                            continue
                    
                    if latest_phase:
                        logger.info(f"  Latest phase found: {latest_phase}")
                        return {
                            "checkpoint_dir": str(workflow_dir),
                            "latest_phase": latest_phase,
                            "workflow_id": workflow_dir.name,
                        }
                else:
                    logger.debug(f"  Topic mismatch: '{checkpoint_topic}' != '{current_topic}'")
            except Exception as e:
                logger.debug(f"Error checking checkpoint {latest_checkpoint}: {e}")
                continue
        
        logger.debug("No matching checkpoint found for this topic")
        return None

    def _get_phase_dependencies(self, phase_name: str) -> List[str]:
        """Get list of phases that must complete before this phase."""
        dependencies = {
            "search_databases": ["build_search_strategy"],
            "deduplication": ["search_databases"],
            "title_abstract_screening": ["deduplication"],
            "fulltext_screening": ["title_abstract_screening"],
            "paper_enrichment": ["fulltext_screening"],
            "data_extraction": ["paper_enrichment"],
            "prisma_generation": ["data_extraction"],
            "visualization_generation": ["data_extraction"],
            "article_writing": ["data_extraction"],
            "report_generation": ["article_writing", "prisma_generation", "visualization_generation"],
        }
        return dependencies.get(phase_name, [])

    def _serialize_phase_data(self, phase_name: str) -> Dict[str, Any]:
        """Serialize data for a specific phase."""
        serializer = StateSerializer()
        data = {}
        
        if phase_name == "search_databases":
            data = {
                "all_papers": serializer.serialize_papers(self.all_papers),
                "database_breakdown": self._get_database_breakdown(),
            }
        elif phase_name == "deduplication":
            data = {
                "unique_papers": serializer.serialize_papers(self.unique_papers),
                "all_papers": serializer.serialize_papers(self.all_papers),
            }
        elif phase_name == "title_abstract_screening":
            data = {
                "screened_papers": serializer.serialize_papers(self.screened_papers),
                "title_abstract_results": serializer.serialize_screening_results(self.title_abstract_results),
                "unique_papers": serializer.serialize_papers(self.unique_papers),
            }
        elif phase_name == "fulltext_screening":
            data = {
                "eligible_papers": serializer.serialize_papers(self.eligible_papers),
                "fulltext_results": serializer.serialize_screening_results(self.fulltext_results),
                "screened_papers": serializer.serialize_papers(self.screened_papers),
                "fulltext_available_count": self.fulltext_available_count,
                "fulltext_unavailable_count": self.fulltext_unavailable_count,
            }
        elif phase_name == "paper_enrichment":
            data = {
                "final_papers": serializer.serialize_papers(self.final_papers),
            }
        elif phase_name == "data_extraction":
            data = {
                "extracted_data": serializer.serialize_extracted_data(self.extracted_data),
                "final_papers": serializer.serialize_papers(self.final_papers),
            }
        elif phase_name == "article_writing":
            # Article sections are already dicts, just need to ensure serializable
            data = {
                "article_sections": self._get_article_sections_dict(),
            }
        
        return data

    def _get_article_sections_dict(self) -> Dict[str, str]:
        """Get article sections as dictionary."""
        # This will be populated after writing, stored in results
        # For now, return empty dict - will be set by _write_article
        return getattr(self, "_article_sections", {})

    def _save_phase_state(self, phase_name: str) -> Optional[str]:
        """Save state after phase completion."""
        if not self.save_checkpoints:
            return None
            
        try:
            checkpoint_data = {
                "phase": phase_name,
                "timestamp": datetime.now().isoformat(),
                "workflow_id": self.workflow_id,
                "topic_context": self.topic_context.to_dict(),
                "data": self._serialize_phase_data(phase_name),
                "dependencies": self._get_phase_dependencies(phase_name),
                "prisma_counts": self.prisma_counter.get_counts(),
                "database_breakdown": self.prisma_counter.get_database_breakdown(),
            }
            
            checkpoint_file = self.checkpoint_dir / f"{phase_name}_state.json"
            with open(checkpoint_file, "w") as f:
                json.dump(checkpoint_data, f, indent=2, default=str)
            
            logger.info(f"Saved checkpoint for phase: {phase_name}")
            return str(checkpoint_file)
        except Exception as e:
            logger.warning(f"Failed to save checkpoint for {phase_name}: {e}")
            return None

    def _load_phase_state(self, checkpoint_path: str) -> Dict[str, Any]:
        """Load state from checkpoint file."""
        checkpoint_file = Path(checkpoint_path)
        if not checkpoint_file.exists():
            raise FileNotFoundError(f"Checkpoint file not found: {checkpoint_path}")
        
        with open(checkpoint_file, "r") as f:
            checkpoint_data = json.load(f)
        
        return checkpoint_data

    def load_state_from_dict(self, state: Dict[str, Any]) -> None:
        """Load workflow state from dictionary (works with checkpoints or fixtures)."""
        serializer = StateSerializer()
        
        # Load papers
        if "all_papers" in state.get("data", {}):
            self.all_papers = serializer.deserialize_papers(state["data"]["all_papers"])
        if "unique_papers" in state.get("data", {}):
            self.unique_papers = serializer.deserialize_papers(state["data"]["unique_papers"])
        if "screened_papers" in state.get("data", {}):
            self.screened_papers = serializer.deserialize_papers(state["data"]["screened_papers"])
        if "eligible_papers" in state.get("data", {}):
            self.eligible_papers = serializer.deserialize_papers(state["data"]["eligible_papers"])
        if "final_papers" in state.get("data", {}):
            self.final_papers = serializer.deserialize_papers(state["data"]["final_papers"])
        
        # Load screening results
        if "title_abstract_results" in state.get("data", {}):
            self.title_abstract_results = serializer.deserialize_screening_results(
                state["data"]["title_abstract_results"]
            )
        if "fulltext_results" in state.get("data", {}):
            self.fulltext_results = serializer.deserialize_screening_results(
                state["data"]["fulltext_results"]
            )
        
        # Load extracted data
        if "extracted_data" in state.get("data", {}):
            self.extracted_data = serializer.deserialize_extracted_data(
                state["data"]["extracted_data"]
            )
        
        # Load article sections
        if "article_sections" in state.get("data", {}):
            self._article_sections = state["data"]["article_sections"]
        
        # Load PRISMA counts
        if "prisma_counts" in state:
            try:
                counts = state["prisma_counts"]
                # Restore counts using individual setters
                if "found" in counts:
                    db_breakdown = state.get("database_breakdown", {})
                    self.prisma_counter.set_found(counts["found"], db_breakdown if db_breakdown else None)
                if "found_other" in counts:
                    self.prisma_counter.set_found_other(counts["found_other"])
                if "no_dupes" in counts:
                    self.prisma_counter.set_no_dupes(counts["no_dupes"])
                if "screened" in counts:
                    self.prisma_counter.set_screened(counts["screened"])
                if "screen_exclusions" in counts:
                    self.prisma_counter.set_screen_exclusions(counts["screen_exclusions"])
                if "full_text_sought" in counts:
                    self.prisma_counter.set_full_text_sought(counts["full_text_sought"])
                if "full_text_not_retrieved" in counts:
                    self.prisma_counter.set_full_text_not_retrieved(counts["full_text_not_retrieved"])
                if "full_text_assessed" in counts:
                    self.prisma_counter.set_full_text_assessed(counts["full_text_assessed"])
                if "full_text_exclusions" in counts:
                    self.prisma_counter.set_full_text_exclusions(counts["full_text_exclusions"])
                if "qualitative" in counts:
                    self.prisma_counter.set_qualitative(counts["qualitative"])
                if "quantitative" in counts:
                    self.prisma_counter.set_quantitative(counts["quantitative"])
            except Exception as e:
                logger.warning(f"Failed to restore PRISMA counts: {e}")
        
        # Load topic context if provided
        if "topic_context" in state:
            # Topic context is already initialized, but we can update if needed
            pass
        
        # Load fulltext counts
        if "fulltext_available_count" in state.get("data", {}):
            self.fulltext_available_count = state["data"]["fulltext_available_count"]
        if "fulltext_unavailable_count" in state.get("data", {}):
            self.fulltext_unavailable_count = state["data"]["fulltext_unavailable_count"]

    @classmethod
    def resume_from_phase(
        cls,
        phase_name: str,
        checkpoint_path: str,
        config_path: Optional[str] = None,
    ) -> "WorkflowManager":
        """
        Load checkpoint and resume workflow from specified phase.
        
        Args:
            phase_name: Phase to resume from
            checkpoint_path: Path to checkpoint file or directory
            config_path: Path to config file (uses same as original if None)
        
        Returns:
            WorkflowManager instance ready to continue
        """
        checkpoint_file = Path(checkpoint_path)
        
        # If directory provided, look for phase-specific checkpoint
        if checkpoint_file.is_dir():
            checkpoint_file = checkpoint_file / f"{phase_name}_state.json"
        
        if not checkpoint_file.exists():
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_file}")
        
        # Create new WorkflowManager instance
        manager = cls(config_path)
        
        # Load checkpoint data
        checkpoint_data = manager._load_phase_state(str(checkpoint_file))
        
        # Load state into manager
        manager.load_state_from_dict(checkpoint_data)
        
        # Update workflow_id and checkpoint_dir from checkpoint
        if "workflow_id" in checkpoint_data:
            manager.workflow_id = checkpoint_data["workflow_id"]
            manager.checkpoint_dir = Path("data/checkpoints") / manager.workflow_id
        
        logger.info(f"Resumed workflow from phase: {phase_name}")
        return manager

    def run_from_stage(
        self,
        start_stage: str,
        end_stage: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute workflow from specific stage.
        
        Args:
            start_stage: Stage to start from (short name or full phase name)
            end_stage: Optional stage to end at
        
        Returns:
            Dictionary with workflow results
        """
        # Map short names to full phase names
        stage_to_phase = {
            "search": "search_databases",
            "deduplication": "deduplication",
            "title_screening": "title_abstract_screening",
            "fulltext_screening": "fulltext_screening",
            "extraction": "data_extraction",
            "prisma": "prisma_generation",
            "visualizations": "visualization_generation",
            "writing": "article_writing",
            "report": "report_generation",
        }
        
        # Map phase names to phase numbers (1-based)
        phase_to_number = {
            "build_search_strategy": 1,
            "search_databases": 2,
            "deduplication": 3,
            "title_abstract_screening": 4,
            "fulltext_screening": 5,
            "data_extraction": 7,
            "prisma_generation": 8,
            "visualization_generation": 9,
            "article_writing": 10,
            "report_generation": 11,
        }
        
        # Normalize stage name
        start_phase = stage_to_phase.get(start_stage, start_stage)
        start_phase_num = phase_to_number.get(start_phase)
        
        if start_phase_num is None:
            raise ValueError(f"Unknown stage: {start_stage}")
        
        # Execute from start phase
        return self.run(start_from_phase=start_phase_num)
