"""
Workflow Manager

Main orchestrator that coordinates all phases of the systematic review workflow.
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.rule import Rule

from ..config.debug_config import DebugLevel
from ..utils.log_context import workflow_phase_context
from ..utils.logging_config import get_logger
from ..utils.rich_utils import (
    console,
    print_checkpoint_panel,
    print_phase_panel,
    print_workflow_status_panel,
)

logger = get_logger(__name__)

from src.enrichment.paper_enricher import PaperEnricher
from src.extraction.data_extractor_agent import ExtractedData
from src.orchestration.database_connector_factory import DatabaseConnectorFactory
from src.orchestration.workflow_initializer import WorkflowInitializer
from src.prisma.prisma_generator import PRISMAGenerator
from src.search.author_service import AuthorService
from src.search.bibliometric_enricher import BibliometricEnricher
from src.search.cache import SearchCache
from src.search.connectors.base import DatabaseConnector, Paper
from src.search.integrity_checker import IntegrityChecker, create_integrity_checker_from_config
from src.search.proxy_manager import ProxyManager, create_proxy_manager_from_config
from src.search.search_strategy import SearchStrategyBuilder
from src.utils.pdf_retriever import PDFRetriever
from src.utils.screening_validator import ScreeningStage, ScreeningValidator
from src.utils.state_serialization import StateSerializer

from .checkpoint_manager import CheckpointManager
from .phase_executor import PhaseExecutor
from .phase_registry import PhaseDefinition, PhaseRegistry


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
        self.style_pattern_extractor = initializer.style_pattern_extractor
        self.humanization_agent = initializer.humanization_agent
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
        self.style_patterns: Dict[str, Dict[str, List[str]]] = {}

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

        # Initialize bibliometric enricher if enabled
        bibliometrics_config = self.config.get("workflow", {}).get("bibliometrics", {})
        bibliometrics_enabled = bibliometrics_config.get("enabled", False)

        self.bibliometric_enricher = None
        if bibliometrics_enabled:
            # Get connectors from searcher for AuthorService
            connectors_dict = {}
            for connector in self.searcher.connectors:
                db_name = connector.get_database_name()
                connectors_dict[db_name] = connector

            # Create AuthorService with available connectors
            author_service = AuthorService(connectors_dict) if connectors_dict else None

            # Initialize BibliometricEnricher
            self.bibliometric_enricher = BibliometricEnricher(
                author_service=author_service,
                enabled=True,
                include_author_metrics=bibliometrics_config.get("include_author_metrics", True),
                include_citation_networks=bibliometrics_config.get(
                    "include_citation_networks", False
                ),
                include_subject_areas=bibliometrics_config.get("include_subject_areas", True),
            )
            logger.info("Bibliometric enrichment enabled")
        else:
            logger.debug("Bibliometric enrichment disabled in config")

        # Checkpoint management
        self.save_checkpoints = True  # Can be disabled via CLI

        # Generate workflow_id (will be updated if resuming from checkpoint in run())
        self.workflow_id = self._generate_workflow_id()
        self.checkpoint_dir = Path("data/checkpoints") / self.workflow_id
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # Update output directory to be workflow-specific to prevent overwriting
        # This ensures each topic/workflow gets its own output directory
        # Note: This will be updated in run() if resuming from checkpoint
        base_output_dir = self.output_dir
        workflow_output_dir = base_output_dir / self.workflow_id
        workflow_output_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir = workflow_output_dir

        # Enable audit trail for cost tracking
        self.cost_tracker.enable_audit_trail(str(workflow_output_dir))


        # Initialize phase registry and executor
        self.phase_registry = self._register_all_phases()
        self.checkpoint_manager = CheckpointManager(self)
        self.phase_executor = PhaseExecutor(self.phase_registry, self.checkpoint_manager)

        # Load screening safeguard configuration
        self.safeguard_config = self.config.get("screening_safeguards", {})
        self.min_papers_threshold = self.safeguard_config.get("minimum_papers", 10)
        self.enable_manual_review = self.safeguard_config.get("enable_manual_review", True)

        logger.info(f"Output directory: {self.output_dir}")

    def _register_all_phases(self) -> PhaseRegistry:
        """Register all workflow phases with registry."""
        registry = PhaseRegistry()

        # Phase 1: Build search strategy
        registry.register(
            PhaseDefinition(
                name="build_search_strategy",
                phase_number=1,
                dependencies=[],
                handler=self._build_search_strategy,
                checkpoint=False,  # Always rebuilds
                description="Build search strategy",
            )
        )

        # Phase 2: Search databases
        registry.register(
            PhaseDefinition(
                name="search_databases",
                phase_number=2,
                dependencies=["build_search_strategy"],
                handler=self._search_databases_phase,
                description="Search multiple databases for papers",
            )
        )

        # Phase 3: Deduplication
        registry.register(
            PhaseDefinition(
                name="deduplication",
                phase_number=3,
                dependencies=["search_databases"],
                handler=self._deduplication_phase,
                description="Remove duplicate papers",
            )
        )

        # Phase 4: Title/Abstract Screening
        registry.register(
            PhaseDefinition(
                name="title_abstract_screening",
                phase_number=4,
                dependencies=["deduplication"],
                handler=self._title_abstract_screening_phase,
                description="Screen papers by title and abstract",
            )
        )

        # Phase 5: Full-text Screening
        registry.register(
            PhaseDefinition(
                name="fulltext_screening",
                phase_number=5,
                dependencies=["title_abstract_screening"],
                handler=self._fulltext_screening_phase,
                description="Screen papers by full-text",
            )
        )

        # Phase 6.5: Paper Enrichment
        registry.register(
            PhaseDefinition(
                name="paper_enrichment",
                phase_number=7,
                dependencies=["fulltext_screening"],
                handler=self._enrich_papers,
                description="Enrich papers with missing metadata",
            )
        )

        # Phase 7: Data Extraction
        registry.register(
            PhaseDefinition(
                name="data_extraction",
                phase_number=7,
                dependencies=["paper_enrichment"],
                handler=self._extract_data,
                description="Extract structured data from papers",
            )
        )

        # Phase 8: Quality Assessment
        registry.register(
            PhaseDefinition(
                name="quality_assessment",
                phase_number=8,
                dependencies=["data_extraction"],
                handler=self._quality_assessment,
                description="Assess quality and risk of bias",
            )
        )

        # Phase 9: Visualization Generation (PRISMA removed)
        registry.register(
            PhaseDefinition(
                name="visualization_generation",
                phase_number=10,
                dependencies=["data_extraction"],
                handler=self._generate_visualizations,
                description="Generate bibliometric visualizations",
            )
        )

        # Phase 11: Article Writing
        registry.register(
            PhaseDefinition(
                name="article_writing",
                phase_number=11,
                dependencies=["data_extraction"],
                handler=self._write_article,
                description="Write article sections (Introduction, Methods, Results, Discussion, Abstract)",
            )
        )

        # Phase 12: Report Generation
        registry.register(
            PhaseDefinition(
                name="report_generation",
                phase_number=12,
                dependencies=["article_writing", "prisma_generation", "visualization_generation"],
                handler=self._report_generation_phase,
                description="Generate final report",
            )
        )

        # Phase 17: Manubot Export
        registry.register(
            PhaseDefinition(
                name="manubot_export",
                phase_number=17,
                dependencies=["article_writing"],
                handler=self._manubot_export_phase,
                required=False,
                config_key="manubot.enabled",
                description="Export to Manubot structure",
            )
        )

        # Phase 18: Submission Package
        registry.register(
            PhaseDefinition(
                name="submission_package",
                phase_number=18,
                dependencies=["article_writing", "report_generation"],
                handler=self._submission_package_phase,
                required=False,
                config_key="submission.enabled",
                description="Generate submission package",
            )
        )

        return registry

    def _search_databases_phase(self) -> List[Paper]:
        """Wrapper for search_databases phase with checkpoint handling."""
        search_results = self._search_databases()
        self.all_papers = search_results
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

        return search_results

    def _deduplication_phase(self):
        """Wrapper for deduplication phase with checkpoint handling."""
        dedup_result = self.deduplicator.deduplicate_papers(self.all_papers)
        self.unique_papers = dedup_result.unique_papers
        logger.info(
            f"Removed {dedup_result.duplicates_removed} duplicates, {len(self.unique_papers)} unique papers remain"
        )

    def _title_abstract_screening_phase(self):
        """Wrapper for title/abstract screening phase."""
        self._screen_title_abstract()
        excluded_at_screening = len(self.unique_papers) - len(self.screened_papers)
        logger.info(
            f"Screened {len(self.unique_papers)} papers, {len(self.screened_papers)} included, {excluded_at_screening} excluded"
        )

        # Calculate and validate screening statistics
        if self.title_abstract_results:
            self.screening_validator.calculate_statistics(
                self.unique_papers, self.title_abstract_results, ScreeningStage.TITLE_ABSTRACT
            )
            self.screening_validator.log_statistics(ScreeningStage.TITLE_ABSTRACT)

    def _fulltext_screening_phase(self):
        """Wrapper for fulltext screening phase with PRISMA tracking."""
        self._screen_fulltext()
        # PRISMA tracking: "sought" = papers that passed title/abstract screening
        sought_count = len(self.screened_papers)
        self.prisma_counter.set_full_text_sought(sought_count)
        # "not_retrieved" = papers where full-text was unavailable
        not_retrieved_count = self.fulltext_unavailable_count
        self.prisma_counter.set_full_text_not_retrieved(not_retrieved_count)
        # "assessed" = papers actually assessed for eligibility (only those with full-text available)
        # PRISMA 2020 rule: sought = assessed + not_retrieved
        # Therefore: assessed = sought - not_retrieved
        assessed_count = sought_count - not_retrieved_count
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

        # Phase 6: Final inclusion (happens automatically after fulltext screening)
        self.final_papers = self.eligible_papers
        self.prisma_counter.set_qualitative(len(self.final_papers))
        self.prisma_counter.set_quantitative(len(self.final_papers))
        logger.info(f"Final included studies: {len(self.final_papers)}")

    def _report_generation_phase(self) -> str:
        """Wrapper for report generation phase."""
        # Get article sections from previous phase
        article_sections = getattr(self, "_article_sections", {})
        if not article_sections:
            article_sections = self._load_existing_sections()
            self._article_sections = article_sections

        # Get PRISMA path (may need to generate if not available)
        prisma_path = None
        if hasattr(self, "_prisma_path"):
            prisma_path = self._prisma_path
        else:
            prisma_path = self._generate_prisma_diagram()
            self._prisma_path = prisma_path

        # Get visualization paths (may need to generate if not available)
        viz_paths = {}
        if hasattr(self, "_viz_paths"):
            viz_paths = self._viz_paths
        else:
            viz_paths = self._generate_visualizations()
            self._viz_paths = viz_paths

        # Merge article-generated files (e.g., mermaid diagrams) into viz_paths
        if hasattr(self, "_article_generated_files"):
            article_files = self._article_generated_files
            if article_files:
                logger.info(
                    f"Merging {len(article_files)} article-generated files into visualizations"
                )
                viz_paths.update(article_files)
                self._viz_paths = viz_paths

        # Also scan for mermaid diagrams as fallback
        mermaid_diagrams = self._collect_mermaid_diagrams()
        if mermaid_diagrams:
            logger.info(f"Found {len(mermaid_diagrams)} additional mermaid diagrams via scan")
            # Only add diagrams not already in viz_paths
            for name, path in mermaid_diagrams.items():
                if name not in viz_paths:
                    viz_paths[name] = path
            self._viz_paths = viz_paths

        report_path = self._generate_final_report(article_sections, prisma_path, viz_paths)
        return report_path

    def _manubot_export_phase(self) -> Optional[str]:
        """Wrapper for manubot export phase."""
        article_sections = getattr(self, "_article_sections", {})
        manubot_path = self._export_manubot_structure(article_sections)
        if manubot_path:
            self._manubot_export_path = manubot_path
        return manubot_path

    def _submission_package_phase(self) -> Optional[str]:
        """Wrapper for submission package phase."""
        article_sections = getattr(self, "_article_sections", {})
        report_path = getattr(self, "_report_path", None)
        if not report_path:
            # Generate report if not available
            prisma_path = getattr(self, "_prisma_path", None) or self._generate_prisma_diagram()
            viz_paths = getattr(self, "_viz_paths", {}) or self._generate_visualizations()
            report_path = self._generate_final_report(article_sections, prisma_path, viz_paths)
            self._report_path = report_path

        # Get all outputs
        outputs = {
            "article_sections": article_sections,
            "final_report": report_path,
            "prisma_diagram": getattr(self, "_prisma_path", None),
            "visualizations": getattr(self, "_viz_paths", {}),
        }

        package_path = self._generate_submission_package(outputs, article_sections, report_path)
        if package_path:
            self._submission_package_path = package_path
        return package_path

    def _should_run_phase(self, phase: PhaseDefinition) -> bool:
        """
        Check if phase should run based on config.

        Args:
            phase: Phase definition

        Returns:
            True if phase should run
        """
        if phase.config_key:
            # Check config (e.g., "manubot.enabled")
            keys = phase.config_key.split(".")
            value = self.config
            for key in keys:
                if isinstance(value, dict):
                    value = value.get(key, {})
                else:
                    return False
            return value.get("enabled", False) if isinstance(value, dict) else bool(value)
        return True

    def _determine_start_phase(self, checkpoint: Optional[Dict[str, Any]]) -> Optional[int]:
        """
        Determine start phase from checkpoint.

        Args:
            checkpoint: Checkpoint dictionary with latest_phase, or None

        Returns:
            Phase number to start from, or None
        """
        if checkpoint is None:
            return None

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
            "report_generation": 11,  # Rerun writing to refresh citations before report
            "manubot_export": 18,  # Next: submission_package
            "submission_package": 19,  # All phases complete - skip everything
        }
        return phase_to_next_number.get(checkpoint.get("latest_phase"), None)

    def _copy_checkpoint_data(self, source_workflow_id: str, target_workflow_id: str) -> bool:
        """
        Copy all checkpoint files from old workflow to new workflow.

        Args:
            source_workflow_id: Old workflow ID to copy from
            target_workflow_id: New workflow ID to copy to

        Returns:
            True if successful, False otherwise
        """
        import json

        try:
            source_dir = Path("data/checkpoints") / source_workflow_id
            target_dir = Path("data/checkpoints") / target_workflow_id

            # Validate source directory
            if not source_dir.exists():
                logger.debug(f"Source checkpoint directory does not exist: {source_dir}")
                return False

            if not source_dir.is_dir():
                logger.warning(f"Source checkpoint path is not a directory: {source_dir}")
                return False

            # Get all checkpoint files
            checkpoint_files = list(source_dir.glob("*.json"))
            if not checkpoint_files:
                logger.debug(f"No checkpoint files found in: {source_dir}")
                return False

            # Ensure target directory exists
            target_dir.mkdir(parents=True, exist_ok=True)

            # Copy each checkpoint file and update workflow_id
            copied_count = 0
            failed_files = []

            for source_file in checkpoint_files:
                target_file = target_dir / source_file.name
                try:
                    # Load and validate JSON
                    with open(source_file) as f:
                        checkpoint_data = json.load(f)

                    # Update workflow_id to new value
                    if "workflow_id" in checkpoint_data:
                        checkpoint_data["workflow_id"] = target_workflow_id

                    # Write updated checkpoint to target
                    with open(target_file, "w") as f:
                        json.dump(checkpoint_data, f, indent=2, default=str)

                    logger.debug(f"Copied checkpoint: {source_file.name}")
                    copied_count += 1

                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON in {source_file.name}, skipping: {e}")
                    failed_files.append(source_file.name)
                except Exception as e:
                    logger.warning(f"Failed to copy {source_file.name}: {e}")
                    failed_files.append(source_file.name)

            if failed_files:
                logger.warning(
                    f"Failed to copy {len(failed_files)} checkpoint file(s): {', '.join(failed_files)}"
                )

            logger.info(
                f"Copied {copied_count}/{len(checkpoint_files)} checkpoint file(s) from {source_workflow_id}"
            )
            return copied_count > 0

        except Exception as e:
            logger.error(f"Error copying checkpoint data: {e}", exc_info=True)
            return False

    def _copy_output_data(self, source_output_dir: Path, target_output_dir: Path) -> bool:
        """
        Copy all output files from old workflow to new workflow.

        Args:
            source_output_dir: Old output directory to copy from
            target_output_dir: New output directory to copy to

        Returns:
            True if successful, False otherwise
        """
        import shutil

        try:
            # Validate source directory
            if not source_output_dir.exists():
                logger.debug(f"Source output directory does not exist: {source_output_dir}")
                return False

            if not source_output_dir.is_dir():
                logger.warning(f"Source output path is not a directory: {source_output_dir}")
                return False

            # Get all files and directories
            items = list(source_output_dir.iterdir())
            if not items:
                logger.debug(f"No output files found in: {source_output_dir}")
                return False

            # Ensure target directory exists
            target_output_dir.mkdir(parents=True, exist_ok=True)

            # Copy each item
            copied_count = 0
            skipped_count = 0
            failed_items = []

            for item in items:
                try:
                    target_item = target_output_dir / item.name

                    if item.is_symlink():
                        # Skip symlinks to avoid issues
                        logger.debug(f"Skipped symlink: {item.name}")
                        skipped_count += 1
                        continue

                    if item.is_file():
                        # Copy file with metadata preservation
                        shutil.copy2(item, target_item)
                        logger.debug(f"Copied file: {item.name} ({item.stat().st_size} bytes)")
                        copied_count += 1

                    elif item.is_dir():
                        # Copy directory tree
                        if target_item.exists():
                            logger.debug(f"Removing existing directory: {target_item}")
                            shutil.rmtree(target_item)
                        shutil.copytree(item, target_item, symlinks=False)
                        logger.debug(f"Copied directory: {item.name}")
                        copied_count += 1

                    else:
                        logger.debug(f"Skipped special file: {item.name}")
                        skipped_count += 1

                except PermissionError as e:
                    logger.warning(f"Permission denied copying {item.name}: {e}")
                    failed_items.append(item.name)
                    skipped_count += 1
                except Exception as e:
                    logger.warning(f"Failed to copy {item.name}: {e}")
                    failed_items.append(item.name)
                    skipped_count += 1

            if failed_items:
                logger.warning(
                    f"Failed to copy {len(failed_items)} item(s): {', '.join(failed_items[:5])}"
                )

            # Backward compatibility: if source has final_report.md but not manuscript.md,
            # copy final_report.md as manuscript.md in target
            source_manuscript = target_output_dir / "manuscript.md"
            source_final_report = target_output_dir / "final_report.md"

            if not source_manuscript.exists() and source_final_report.exists():
                try:
                    shutil.copy2(source_final_report, source_manuscript)
                    logger.info(
                        "Copied final_report.md to manuscript.md for backward compatibility"
                    )
                    copied_count += 1
                except Exception as e:
                    logger.warning(f"Failed to create manuscript.md from final_report.md: {e}")

            logger.info(
                f"Copied {copied_count}/{len(items)} item(s) from output directory "
                f"(skipped: {skipped_count})"
            )
            return copied_count > 0

        except Exception as e:
            logger.error(f"Error copying output data: {e}", exc_info=True)
            return False

    async def _execute_phases_parallel(
        self,
        phase_names: List[str],
        phase_handlers: Dict[str, Callable]
    ) -> Dict[str, Any]:
        """
        Execute multiple independent phases in parallel using asyncio.TaskGroup.

        Requires Python 3.11+ for TaskGroup support.

        Args:
            phase_names: List of phase names to execute
            phase_handlers: Dict mapping phase names to their handler functions

        Returns:
            Dict mapping phase names to their results

        Raises:
            RuntimeError: If Python version < 3.11
            ExceptionGroup: If any tasks fail
        """
        # Verify Python version
        if sys.version_info < (3, 11):
            raise RuntimeError(
                f"Parallel execution requires Python 3.11+. "
                f"Current version: {sys.version_info.major}.{sys.version_info.minor}"
            )

        logger.info(f"Starting parallel execution of phases: {', '.join(phase_names)}")
        parallel_start_time = time.time()

        results = {}

        # Use TaskGroup for structured concurrency (Python 3.11+)
        async with asyncio.TaskGroup() as tg:
            # Create tasks for all parallel phases
            # Use to_thread to run synchronous handlers in thread pool
            tasks = {
                phase_name: tg.create_task(
                    asyncio.to_thread(phase_handlers[phase_name]),
                    name=phase_name
                )
                for phase_name in phase_names
            }

        # All tasks completed successfully, collect results
        for phase_name, task in tasks.items():
            results[phase_name] = task.result()
            logger.info(f"Phase '{phase_name}' completed successfully")

        parallel_duration = time.time() - parallel_start_time
        logger.info(
            f"Parallel execution completed in {parallel_duration:.2f}s "
            f"({len(phase_names)} phases)"
        )

        return results

    def run(self, start_from_phase: Optional[int] = None) -> Dict[str, Any]:
        """
        Execute the complete workflow.

        Args:
            start_from_phase: Optional phase index to start from (1-based, None = start from beginning)

        Returns:
            Dictionary with workflow results and output paths
        """
        workflow_start = time.time()
        console.print()
        console.print(
            Rule("[bold cyan]Starting Systematic Review Workflow[/bold cyan]", style="cyan")
        )
        console.print(f"[bold]Topic:[/bold] {self.topic_context.topic}")
        console.print(f"[bold]Output directory:[/bold] [cyan]{self.output_dir}[/cyan]")
        console.print()
        logger.info("=" * 60)
        logger.info("Starting systematic review workflow")
        logger.info(f"Topic: {self.topic_context.topic}")
        logger.info(f"Output directory: {self.output_dir}")

        # Enable audit trail for LLM cost tracking
        self.cost_tracker.enable_audit_trail(str(self.output_dir))

        # Auto-detect and resume from existing checkpoint if available
        if start_from_phase is None and self.save_checkpoints:
            existing_checkpoint = self.checkpoint_manager.find_by_topic(self.topic_context.topic)
            if existing_checkpoint:
                print_workflow_status_panel(
                    title="Checkpoint Detected",
                    message=f"[bold green]Found existing checkpoint for this topic![/bold green]\n\n"
                    f"[bold]Workflow ID:[/bold] {existing_checkpoint['workflow_id']}\n"
                    f"[bold]Latest phase:[/bold] {existing_checkpoint['latest_phase']}\n\n"
                    f"[dim]Resuming from checkpoint...[/dim]",
                    status_color="green",
                )
                console.print()
                logger.info("=" * 60)
                logger.info("Found existing checkpoint for this topic!")
                logger.info(f"  Workflow ID: {existing_checkpoint['workflow_id']}")
                logger.info(f"  Latest phase: {existing_checkpoint['latest_phase']}")
                logger.info("  Resuming from checkpoint...")
                logger.info("=" * 60)

                # Keep NEW workflow_id, copy data from OLD checkpoint
                old_workflow_id = existing_checkpoint["workflow_id"]
                logger.info(f"Copying data from checkpoint: {old_workflow_id}")
                logger.info(f"New workflow ID: {self.workflow_id}")

                # Copy checkpoint files
                checkpoint_success = self._copy_checkpoint_data(old_workflow_id, self.workflow_id)
                if checkpoint_success:
                    logger.info(f"Copied checkpoint data to: {self.checkpoint_dir}")
                else:
                    logger.warning("No checkpoint data copied - will load from original location")

                # Copy output files
                base_output_dir = Path(self.config["output"]["directory"])
                old_output_dir = base_output_dir / old_workflow_id
                output_success = self._copy_output_data(old_output_dir, self.output_dir)
                if output_success:
                    logger.info(f"Copied output files to: {self.output_dir}")
                else:
                    logger.debug("No output files copied - will generate as needed")

                # Update checkpoint to use new workflow_id and checkpoint_dir
                existing_checkpoint["workflow_id"] = self.workflow_id
                existing_checkpoint["checkpoint_dir"] = str(self.checkpoint_dir)

                logger.info(f"Using output directory: {self.output_dir}")

                # Load existing audit trail if present (AFTER checkpoint copying)
                audit_file = self.output_dir / "llm_calls_audit.json"
                if audit_file.exists():
                    logger.info(f"Loading historical metrics from {audit_file}")
                    cost_summary = self.cost_tracker.load_from_audit_trail(audit_file)
                    self.metrics.load_from_audit_trail(audit_file)
                    if cost_summary['historical_calls'] > 0:
                        logger.info(
                            f"Loaded {cost_summary['historical_calls']} historical LLM calls "
                            f"(${cost_summary['historical_cost']:.4f}) from previous runs"
                        )
                else:
                    logger.debug(f"No audit trail found at {audit_file}")

                # Load all prerequisite checkpoints in order
                checkpoint_dir = Path(existing_checkpoint["checkpoint_dir"])
                phase_dependencies = {
                    "search_databases": [],
                    "deduplication": ["search_databases"],
                    "title_abstract_screening": ["deduplication"],
                    "fulltext_screening": ["title_abstract_screening"],
                    "paper_enrichment": ["fulltext_screening"],
                    "data_extraction": [
                        "paper_enrichment"
                    ],  # paper_enrichment may not exist, will fallback to fulltext_screening data
                    "quality_assessment": ["data_extraction"],
                    "prisma_generation": ["data_extraction"],
                    "visualization_generation": ["data_extraction"],
                    "article_writing": [
                        "data_extraction"
                    ],  # Need final_papers from data_extraction for citations
                    "report_generation": [
                        "article_writing",
                        "prisma_generation",
                        "visualization_generation",
                    ],
                    "manubot_export": ["article_writing"],
                    "submission_package": ["article_writing", "report_generation"],
                }

                # Get all phases we need to load (dependencies + latest phase)
                # Build full dependency chain recursively
                def get_all_dependencies(phase: str, visited: Optional[set] = None) -> List[str]:
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
                logger.info(
                    f"Checkpoint dependency chain for '{existing_checkpoint['latest_phase']}': {phases_to_load}"
                )

                # Load checkpoints in dependency order
                print_checkpoint_panel(
                    phases_loaded=[],
                    phases_attempted=len(phases_to_load),
                    status="loading",
                )
                console.print()

                loaded_phases = []
                # Accumulate state from all checkpoints before loading
                # This prevents later checkpoints from overwriting data from earlier phases
                accumulated_state = {"data": {}}

                for phase in phases_to_load:
                    # Special handling for article_writing phase - check for section-level checkpoints
                    if phase == "article_writing":
                        section_checkpoints = self._load_existing_sections()
                        if section_checkpoints:
                            logger.info(
                                f"Found {len(section_checkpoints)} article section checkpoints"
                            )
                            # Load section checkpoints even if phase-level doesn't exist
                            accumulated_state["data"]["article_sections"] = section_checkpoints
                            loaded_phases.append(phase)
                            console.print(
                                f"[green]✓[/green] Loaded: [cyan]{phase}[/cyan] ({len(section_checkpoints)} sections)"
                            )
                            logger.info(
                                f"Loaded {len(section_checkpoints)} article sections from checkpoints"
                            )
                            continue

                    # Try to load phase-level checkpoint
                    checkpoint_file = checkpoint_dir / f"{phase}_state.json"
                    if checkpoint_file.exists():
                        logger.debug(f"Found checkpoint: {phase}")
                        try:
                            checkpoint_data = self.checkpoint_manager.load_phase(
                                str(checkpoint_file)
                            )

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
                            for key in [
                                "prisma_counts",
                                "database_breakdown",
                                "topic_context",
                                "workflow_id",
                            ]:
                                if key in checkpoint_data:
                                    accumulated_state[key] = checkpoint_data[key]

                            loaded_phases.append(phase)
                            console.print(f"[green]✓[/green] Loaded: [cyan]{phase}[/cyan]")
                            logger.info(f"Loaded checkpoint data from: {phase}")
                        except Exception as e:
                            logger.error(
                                f"Failed to load checkpoint file {phase}: {e}", exc_info=True
                            )
                            # Continue loading other phases even if one fails
                    else:
                        logger.debug(
                            f"Missing checkpoint: {phase} (will skip, may use data from later phases)"
                        )

                if not loaded_phases:
                    # Check if we have any useful data (like article sections) before giving up
                    has_article_sections = "article_sections" in accumulated_state.get("data", {})
                    has_any_data = bool(accumulated_state.get("data", {}))

                    if has_article_sections or has_any_data:
                        logger.warning(
                            "No phase-level checkpoints loaded, but found partial data. Continuing with available state."
                        )
                        loaded_phases.append("partial")  # Mark as having partial data
                    else:
                        logger.error("Failed to load any checkpoints! Starting from scratch.")
                        existing_checkpoint = None  # Reset to start fresh
                else:
                    print_checkpoint_panel(
                        phases_loaded=loaded_phases,
                        phases_attempted=len(phases_to_load),
                        status="loaded",
                    )
                    console.print()
                    logger.info(
                        f"Successfully loaded {len(loaded_phases)} checkpoint(s) out of {len(phases_to_load)} attempted: {', '.join(loaded_phases)}"
                    )
                    if len(loaded_phases) < len(phases_to_load):
                        missing = set(phases_to_load) - set(loaded_phases)
                        logger.warning(
                            f"Missing checkpoints (will use available data): {', '.join(missing)}"
                        )

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
                    except Exception as load_error:
                        logger.error(
                            f"Failed to load accumulated state: {load_error}", exc_info=True
                        )
                        raise RuntimeError(
                            f"Checkpoint loading failed: {load_error}"
                        ) from load_error

                # Update workflow_id and checkpoint_dir from checkpoint
                if existing_checkpoint is not None:
                    latest_checkpoint_file = (
                        checkpoint_dir / f"{existing_checkpoint['latest_phase']}_state.json"
                    )
                    if latest_checkpoint_file.exists():
                        latest_checkpoint_data = self.checkpoint_manager.load_phase(
                            str(latest_checkpoint_file)
                        )
                        if latest_checkpoint_data and "workflow_id" in latest_checkpoint_data:
                            self.workflow_id = latest_checkpoint_data["workflow_id"]
                            self.checkpoint_dir = Path("data/checkpoints") / self.workflow_id
                            self.checkpoint_manager.checkpoint_dir = self.checkpoint_dir

                            # Update output directory to match workflow_id and ensure it exists
                            base_output_dir = Path(
                                self.config.get("output", {}).get("directory", "data/outputs")
                            )
                            workflow_output_dir = base_output_dir / self.workflow_id
                            workflow_output_dir.mkdir(parents=True, exist_ok=True)
                            self.output_dir = workflow_output_dir

                # Determine start phase from checkpoint
                start_from_phase = self._determine_start_phase(existing_checkpoint)
                if start_from_phase and start_from_phase >= 12:
                    # Guard: if checkpointed article sections contain invalid/legacy citations,
                    # rerun article writing to regenerate sections with the canonical citation contract.
                    checkpoint_sections = self._load_existing_sections()
                    if checkpoint_sections and self.final_papers:
                        self._ensure_citation_registry()
                        invalid_sections = []
                        for section_name, section_text in checkpoint_sections.items():
                            is_valid = self._validate_section_citations(
                                section_name, section_text, fail_on_invalid=True
                            )
                            if not is_valid:
                                invalid_sections.append(section_name)
                        if invalid_sections:
                            logger.warning(
                                "Detected invalid citations in checkpointed sections (%s); "
                                "forcing resume from article_writing to regenerate sections.",
                                ", ".join(sorted(invalid_sections)),
                            )
                            start_from_phase = 11
                if start_from_phase and existing_checkpoint is not None:
                    resume_info_lines = [
                        f"[bold cyan]Resuming from phase {start_from_phase}[/bold cyan]",
                        "",
                        f"[bold]Completed phase:[/bold] {existing_checkpoint['latest_phase']}",
                        f"[bold]Loaded state:[/bold] {len(self.all_papers)} papers, "
                        f"{len(self.unique_papers)} unique, {len(self.screened_papers)} screened",
                    ]
                    if self.title_abstract_results:
                        resume_info_lines.append(
                            f"[dim]Found {len(self.title_abstract_results)} title/abstract screening results - will reuse[/dim]"
                        )
                    if self.fulltext_results:
                        resume_info_lines.append(
                            f"[dim]Found {len(self.fulltext_results)} fulltext screening results - will reuse[/dim]"
                        )

                    print_workflow_status_panel(
                        title="Resume Information",
                        message="\n".join(resume_info_lines),
                        status_color="cyan",
                    )
                    console.print()

                    logger.info(
                        f"Resuming from phase {start_from_phase} (completed: {existing_checkpoint['latest_phase']})"
                    )
                    logger.info(
                        f"Loaded state: {len(self.all_papers)} papers, {len(self.unique_papers)} unique, {len(self.screened_papers)} screened"
                    )
                    if self.title_abstract_results:
                        logger.info(
                            f"Found {len(self.title_abstract_results)} title/abstract screening results - will reuse"
                        )
                    if self.fulltext_results:
                        logger.info(
                            f"Found {len(self.fulltext_results)} fulltext screening results - will reuse"
                        )

        # Load audit trail for fresh workflows (no checkpoint found)
        if not start_from_phase:
            audit_file = self.output_dir / "llm_calls_audit.json"
            if audit_file.exists():
                logger.info(f"Loading historical metrics from {audit_file}")
                cost_summary = self.cost_tracker.load_from_audit_trail(audit_file)
                self.metrics.load_from_audit_trail(audit_file)
                if cost_summary['historical_calls'] > 0:
                    logger.info(
                        f"Loaded {cost_summary['historical_calls']} historical LLM calls "
                        f"(${cost_summary['historical_cost']:.4f}) from previous runs"
                    )

        if start_from_phase:
            logger.info(f"Resuming from phase {start_from_phase}")
        logger.info("=" * 60)

        results = {"phase": "initialization", "outputs": {}}

        try:
            # Phase 1: Build search strategy (always runs, even when resuming)
            # This ensures search_strategy is available for article writing and exports
            try:
                with workflow_phase_context("build_search_strategy"):
                    self._build_search_strategy()
                    if self.debug_config.show_state_transitions:
                        logger.info("Search strategy built successfully")
            except Exception as e:
                if self.search_strategy is None:
                    logger.error(f"Failed to rebuild search strategy: {e}", exc_info=True)
                    raise
                else:
                    logger.warning(f"Failed to rebuild search strategy (will use existing): {e}")

            # Phase 6: Final inclusion (happens automatically after fulltext screening)
            # This is not a registered phase but happens automatically
            # We'll handle it in the phase execution loop

            # Execute phases using registry
            execution_order = self.phase_registry.get_execution_order()

            # Track outputs for phases that need them
            prisma_path = None
            viz_paths = {}
            article_sections = {}
            report_path = None

            # Load report_path from checkpoint if resuming
            if start_from_phase:
                report_path = getattr(self, "_report_path", None)
                if report_path is None:
                    # Try to find final_report.md in output directory
                    potential_report = self.output_dir / "final_report.md"
                    if potential_report.exists():
                        report_path = str(potential_report)

            for phase_name in execution_order:
                phase = self.phase_registry.get_phase(phase_name)
                if not phase:
                    continue

                # Skip if before start phase
                if start_from_phase and phase.phase_number < start_from_phase:
                    # Display prominent Rich Panel for checkpoint-skipped phase
                    print_phase_panel(
                        phase_name=phase_name,
                        phase_number=phase.phase_number,
                        description=f"{phase.description or phase_name}\n\n[dim]Resuming from phase {start_from_phase}[/dim]",
                        status="skipped_checkpoint",
                        expand=False,
                    )
                    console.print()
                    console.print()  # Extra newline for better separation
                    continue

                # Check if phase should run (config-based for optional phases)
                if not self._should_run_phase(phase):
                    # Display Rich Panel for config-disabled phase
                    print_phase_panel(
                        phase_name=phase_name,
                        phase_number=phase.phase_number,
                        description=phase.description or phase_name,
                        status="skipped_disabled",
                        expand=False,
                    )
                    console.print()
                    console.print()  # Extra newline for better separation
                    logger.info(f"Skipping phase '{phase_name}': disabled in config")
                    continue

                # Special handling for final inclusion (not a registered phase)
                if phase_name == "fulltext_screening":
                    # After fulltext screening, set final papers
                    # We'll do this after the phase executes
                    pass

                # PARALLEL EXECUTION: Check if we should execute phases 8-11 in parallel
                # This happens when we reach quality_assessment (phase 8) and parallel phases haven't run yet
                parallel_phases = ["quality_assessment", "prisma_generation", "visualization_generation", "article_writing"]
                if phase_name == "quality_assessment" and not hasattr(self, "_parallel_phases_executed"):
                    # Check which of the parallel phases need to be executed
                    phases_to_run_parallel = []
                    phase_handlers = {}

                    for parallel_phase_name in parallel_phases:
                        parallel_phase = self.phase_registry.get_phase(parallel_phase_name)
                        if parallel_phase and self._should_run_phase(parallel_phase):
                            # Check if phase was already completed in checkpoint
                            phase_completed = self.checkpoint_manager.is_phase_complete(parallel_phase_name)
                            if not phase_completed:
                                phases_to_run_parallel.append(parallel_phase_name)
                                # Map phase name to handler method
                                phase_handlers[parallel_phase_name] = parallel_phase.handler

                    if phases_to_run_parallel:
                        logger.info(f"Executing {len(phases_to_run_parallel)} phases in parallel: {', '.join(phases_to_run_parallel)}")
                        console.print()
                        console.print(f"[bold cyan]Running phases {', '.join(phases_to_run_parallel)} in parallel...[/bold cyan]")
                        console.print()

                        # Run parallel execution using asyncio
                        parallel_results = asyncio.run(
                            self._execute_phases_parallel(
                                phases_to_run_parallel,
                                phase_handlers
                            )
                        )

                        # Process results for each parallel phase
                        for parallel_phase_name, parallel_result in parallel_results.items():
                            if parallel_phase_name == "quality_assessment":
                                results["outputs"]["quality_assessment"] = parallel_result
                                self.quality_assessment_data = parallel_result
                                self.checkpoint_manager.save_phase("quality_assessment")
                            elif parallel_phase_name == "prisma_generation":
                                prisma_path = parallel_result
                                results["outputs"]["prisma_diagram"] = prisma_path
                                self._prisma_path = prisma_path
                                self.checkpoint_manager.save_phase("prisma_generation")
                            elif parallel_phase_name == "visualization_generation":
                                viz_paths = parallel_result
                                results["outputs"]["visualizations"] = viz_paths
                                self._viz_paths = viz_paths
                                self.checkpoint_manager.save_phase("visualization_generation")
                            elif parallel_phase_name == "article_writing":
                                article_sections = parallel_result
                                results["outputs"]["article_sections"] = article_sections
                                self._article_sections = article_sections
                                self.checkpoint_manager.save_phase("article_writing")

                        logger.info("Parallel execution completed successfully")
                        console.print()
                        console.print("[bold green]Parallel phases completed successfully[/bold green]")
                        console.print()

                        # Mark that parallel phases have been executed
                        self._parallel_phases_executed = True

                        # Skip the individual execution of these phases in the loop
                        if phase_name in parallel_phases:
                            continue
                    else:
                        logger.info("All parallel phases already completed, skipping parallel execution")
                        self._parallel_phases_executed = True

                # Skip if this phase was already executed in parallel
                if phase_name in parallel_phases and hasattr(self, "_parallel_phases_executed"):
                    continue

                # Execute phase
                try:
                    phase_result = self.phase_executor.execute_phase(
                        phase_name, self, {"start_from_phase": start_from_phase}
                    )

                    # Store results based on phase
                    if phase_name == "search_databases":
                        # Already handled in wrapper
                        pass
                    elif phase_name == "prisma_generation":
                        prisma_path = phase_result
                        results["outputs"]["prisma_diagram"] = prisma_path
                        self._prisma_path = prisma_path
                    elif phase_name == "visualization_generation":
                        viz_paths = phase_result
                        results["outputs"]["visualizations"] = viz_paths
                        self._viz_paths = viz_paths
                    elif phase_name == "article_writing":
                        article_sections = phase_result
                        results["outputs"]["article_sections"] = article_sections
                        self._article_sections = article_sections
                    elif phase_name == "report_generation":
                        report_path = phase_result
                        results["outputs"]["final_report"] = report_path
                        self._report_path = report_path
                    elif phase_name == "quality_assessment":
                        results["outputs"]["quality_assessment"] = phase_result
                    elif phase_name == "manubot_export":
                        if phase_result:
                            results["outputs"]["manubot_export"] = phase_result
                    elif phase_name == "submission_package":
                        if phase_result:
                            results["outputs"]["submission_package"] = phase_result

                    # Final inclusion is handled in _fulltext_screening_phase wrapper

                    # Add visual separator between phases
                    console.print()
                    console.print(Rule(style="dim"))
                    console.print()

                except Exception as e:
                    if phase.required:
                        logger.error(f"Required phase '{phase_name}' failed: {e}", exc_info=True)
                        raise
                    else:
                        logger.warning(f"Optional phase '{phase_name}' failed: {e}")
                        continue

            # Handle phases not in registry (supplementary phases)
            # These run after main phases complete
            if not start_from_phase or start_from_phase <= 12:
                # Phase 13: Export Search Strategies
                supplementary_config = self.config.get("supplementary_materials", {})
                if supplementary_config.get("search_strategies", True):
                    with workflow_phase_context("search_strategy_export"):
                        search_strategies_path = self._export_search_strategies()
                        if search_strategies_path:
                            results["outputs"]["search_strategies"] = search_strategies_path
                            logger.info(f"Search strategies exported: {search_strategies_path}")

                # Phase 14: Generate PRISMA Checklist
                if report_path:
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

            # Phase 17: Manubot Export
            # Skip if all phases are complete (start_from_phase >= 19 means everything is done)
            if not (start_from_phase and start_from_phase >= 19):
                manubot_config = self.config.get("manubot", {})
                if manubot_config.get("enabled", False):
                    with workflow_phase_context("manubot_export"):
                        manubot_path = self._export_manubot_structure(article_sections)
                        if manubot_path:
                            results["outputs"]["manubot_export"] = manubot_path
                            self._manubot_export_path = manubot_path
                            logger.info(f"Manubot structure exported: {manubot_path}")
                            self.checkpoint_manager.save_phase("manubot_export")

            # Phase 18: Submission Package Generation
            # Skip if all phases are complete (start_from_phase >= 19 means everything is done)
            if not (start_from_phase and start_from_phase >= 19):
                submission_config = self.config.get("submission", {})
                if submission_config.get("enabled", False):
                    with workflow_phase_context("submission_package"):
                        # Load report_path from checkpoint if not set
                        if report_path is None:
                            report_path = getattr(self, "_report_path", None)
                        if report_path is None:
                            # Try to find final_report.md in output directory
                            report_path = self.output_dir / "final_report.md"
                            if not report_path.exists():
                                report_path = None

                        package_path = self._generate_submission_package(
                            results["outputs"],
                            article_sections,
                            report_path,
                        )
                        if package_path:
                            results["outputs"]["submission_package"] = package_path
                            self._submission_package_path = package_path
                            logger.info(f"Submission package generated: {package_path}")
                            self.checkpoint_manager.save_phase("submission_package")

            # Save workflow state
            state_path = self._save_workflow_state()
            results["outputs"]["workflow_state"] = state_path

            workflow_duration = time.time() - workflow_start

            # Clear any remaining progress displays
            console.print()

            # Display output location summary
            final_report = self.output_dir / "final_report.md"
            prisma_diagram = self.output_dir / "prisma_diagram.png"

            # Find submission package directory
            submission_package_dirs = list(self.output_dir.glob("submission_package_*"))
            submission_package = (
                submission_package_dirs[0].name
                if submission_package_dirs
                else "submission_package_*/"
            )

            print_workflow_status_panel(
                title="Workflow Complete",
                message=f"[bold green]All phases completed successfully![/bold green]\n\n"
                f"[bold]Output Directory:[/bold]\n"
                f"[cyan]{self.output_dir}[/cyan]\n\n"
                f"[bold]Key Files:[/bold]\n"
                f"- Final Report: [cyan]{final_report.name if final_report.exists() else 'final_report.md'}[/cyan]\n"
                f"- PRISMA Diagram: [cyan]{prisma_diagram.name if prisma_diagram.exists() else 'prisma_diagram.png'}[/cyan]\n"
                f"- Submission Package: [cyan]{submission_package}[/cyan]\n\n"
                f"[bold]Duration:[/bold] {workflow_duration:.1f}s\n\n"
                f"[dim]View outputs: cd {self.output_dir}[/dim]",
                status_color="green",
            )
            console.print()

            # Display screening statistics in rich format
            self._display_screening_summary()

            # Display summary if debug enabled
            if self.debug_config.show_metrics:
                self._display_metrics_summary()

            if self.debug_config.show_costs:
                self._display_cost_summary()

            logger.info(f"Workflow completed successfully in {workflow_duration:.2f}s")

        except Exception as e:
            logger.error(f"Workflow failed: {e}", exc_info=True)
            raise

        return results

    def _display_screening_summary(self):
        """Display screening statistics in rich format."""
        from rich.table import Table

        # Check if we have statistics
        if not self.screening_validator.stats_by_stage:
            return

        # Create table for screening statistics
        table = Table(title="Screening Statistics", show_header=True, header_style="bold cyan")
        table.add_column("Stage", style="cyan", width=20)
        table.add_column("Total", justify="right", style="white")
        table.add_column("Included", justify="right", style="green")
        table.add_column("Excluded", justify="right", style="red")
        table.add_column("Inclusion Rate", justify="right", style="yellow")

        for stage in ScreeningStage:
            if stage in self.screening_validator.stats_by_stage:
                stats = self.screening_validator.stats_by_stage[stage]
                stage_name = stage.value.replace("_", " ").title()
                table.add_row(
                    stage_name,
                    str(stats.total_papers),
                    str(stats.included),
                    str(stats.excluded),
                    f"{stats.inclusion_rate:.1%}",
                )

        console.print(table)
        console.print()

    def _display_metrics_summary(self):
        """Display metrics summary."""
        from rich.table import Table

        summary = self.metrics.get_summary()

        # Create metrics table
        table = Table(title="Agent Metrics", show_header=True, header_style="bold cyan")
        table.add_column("Metric", style="cyan", width=20)
        table.add_column("Value", justify="right", style="white")

        table.add_row("Total Agents", str(summary["total_agents"]))
        table.add_row("Total Calls", str(summary["total_calls"]))
        table.add_row("Successful", str(summary["total_successful"]))
        table.add_row("Failed", str(summary["total_failed"]))
        table.add_row("Success Rate", f"{summary['overall_success_rate']:.2%}")

        console.print(table)
        console.print()

        # Display per-agent metrics if available
        if summary.get("agents") and len(summary["agents"]) > 0:
            agent_table = Table(
                title="Per-Agent Metrics", show_header=True, header_style="bold cyan"
            )
            agent_table.add_column("Agent", style="cyan", width=35)
            agent_table.add_column("Calls", justify="right", style="white")
            agent_table.add_column("Success Rate", justify="right", style="green")
            agent_table.add_column("Avg Duration", justify="right", style="yellow")

            for agent_name, agent_metrics in summary["agents"].items():
                agent_table.add_row(
                    agent_name,
                    str(agent_metrics["total_calls"]),
                    f"{agent_metrics['success_rate']:.2%}",
                    f"{agent_metrics['average_duration']:.2f}s",
                )

            console.print(agent_table)
            console.print()

    def _display_cost_summary(self):
        """Display cost summary with historical and current session breakdown."""
        from rich.columns import Columns
        from rich.table import Table

        summary = self.cost_tracker.get_summary()
        has_historical = summary.get('historical_calls', 0) > 0

        if has_historical:
            # Create two tables side-by-side

            # Historical table
            hist_table = Table(
                title="[bold magenta]Previous Runs[/bold magenta]",
                show_header=True,
                header_style="bold magenta"
            )
            hist_table.add_column("Metric", style="magenta", width=20)
            hist_table.add_column("Value", justify="right", style="white")

            hist_table.add_row("Total Cost", f"${summary['historical_cost']:.4f}")
            hist_table.add_row("Total Calls", str(summary["historical_calls"]))
            hist_table.add_row("Total Tokens", f"{summary['historical_tokens']:,}")

            # Current session table
            curr_table = Table(
                title="[bold cyan]This Session[/bold cyan]",
                show_header=True,
                header_style="bold cyan"
            )
            curr_table.add_column("Metric", style="cyan", width=20)
            curr_table.add_column("Value", justify="right", style="white")

            curr_table.add_row("Total Cost", f"${summary['total_cost_usd']:.4f}")
            curr_table.add_row("Total Calls", str(summary["total_calls"]))
            curr_table.add_row("Total Tokens", f"{summary['total_tokens']:,}")

            # Display side-by-side
            console.print(Columns([hist_table, curr_table], equal=True, expand=True))
            console.print()

            # Show historical breakdown by agent if available
            if summary.get("historical_by_agent") and len(summary["historical_by_agent"]) > 0:
                hist_agent_table = Table(
                    title="[bold magenta]Previous Runs - Cost by Agent[/bold magenta]",
                    show_header=True,
                    header_style="bold magenta"
                )
                hist_agent_table.add_column("Agent", style="magenta", width=35)
                hist_agent_table.add_column("Cost", justify="right", style="white")

                for agent_name, cost in summary["historical_by_agent"].items():
                    hist_agent_table.add_row(agent_name, f"${cost:.4f}")

                console.print(hist_agent_table)
                console.print()

            # Show current breakdown by agent if available
            if summary.get("by_agent") and len(summary["by_agent"]) > 0:
                curr_agent_table = Table(
                    title="[bold cyan]This Session - Cost by Agent[/bold cyan]",
                    show_header=True,
                    header_style="bold cyan"
                )
                curr_agent_table.add_column("Agent", style="cyan", width=35)
                curr_agent_table.add_column("Cost", justify="right", style="white")

                for agent_name, cost in summary["by_agent"].items():
                    curr_agent_table.add_row(agent_name, f"${cost:.4f}")

                console.print(curr_agent_table)

        else:
            # Fresh workflow - single table display
            table = Table(title="Cost Summary", show_header=True, header_style="bold cyan")
            table.add_column("Metric", style="cyan", width=20)
            table.add_column("Value", justify="right", style="white")

            table.add_row("Total Cost", f"${summary['total_cost_usd']:.4f}")
            table.add_row("Total Calls", str(summary["total_calls"]))
            table.add_row("Total Tokens", f"{summary['total_tokens']:,}")

            console.print(table)

            # Show breakdown by provider if available
            if summary["by_provider"] and len(summary["by_provider"]) > 0:
                provider_table = Table(
                    title="Cost by Provider", show_header=True, header_style="bold cyan"
                )
                provider_table.add_column("Provider", style="cyan")
                provider_table.add_column("Cost", justify="right", style="green")

                for provider, cost in summary["by_provider"].items():
                    provider_table.add_row(provider, f"${cost:.4f}")

                console.print(provider_table)

            # Show breakdown by agent if available
            if summary.get("by_agent") and len(summary["by_agent"]) > 0:
                agent_table = Table(
                    title="Cost by Agent", show_header=True, header_style="bold cyan"
                )
                agent_table.add_column("Agent", style="cyan", width=35)
                agent_table.add_column("Cost", justify="right", style="green")

                for agent_name, cost in summary["by_agent"].items():
                    agent_table.add_row(agent_name, f"${cost:.4f}")

                console.print(agent_table)

        console.print()

    def _build_search_strategy(self):
        """Build search strategy."""
        self.search_strategy = SearchStrategyBuilder()

        # Use topic keywords as the unified search term system
        if self.topic_context.keywords:
            # Add topic keywords as a single search term group (all ORed together)
            self.search_strategy.add_term_group(
                self.topic_context.topic.lower().replace(" ", "_"),
                self.topic_context.keywords,
            )

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
        self._validate_database_config()

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
            connector = self._create_connector(
                db_name, cache, proxy_manager, integrity_checker, persistent_session, cookie_jar
            )
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

    def _find_existing_screening_result(
        self, paper: Paper, existing_results: List
    ) -> Optional[Any]:
        """Find existing screening result for a paper."""
        self._get_paper_key(paper)

        for _result in existing_results:
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
                logger.info(
                    f"Found existing title/abstract screening results for {len(self.title_abstract_results)} papers"
                )
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

        # Get criteria from config (unified location in topic section)
        if "inclusion" not in self.config.get("topic", {}) or "exclusion" not in self.config.get(
            "topic", {}
        ):
            raise ValueError(
                "No inclusion/exclusion criteria found in config. Add them to topic.inclusion and topic.exclusion sections."
            )

        inclusion_criteria = self.config["topic"]["inclusion"]
        exclusion_criteria = self.config["topic"]["exclusion"]

        # Apply template replacement to criteria
        inclusion_criteria = [self.topic_context.inject_into_prompt(c) for c in inclusion_criteria]
        exclusion_criteria = [self.topic_context.inject_into_prompt(c) for c in exclusion_criteria]

        # Use topic keywords as unified keyword system
        # Convert topic.keywords to search_terms format for _fallback_screen
        topic_keywords = (
            self.topic_context.keywords if hasattr(self.topic_context, "keywords") else []
        )
        search_terms = {}
        if topic_keywords:
            # Create a single search term group from topic keywords
            # This ensures all keywords are ORed together (not ANDed)
            search_terms = {"topic_keywords": topic_keywords}

        # Get topic context for title/abstract screening agent
        screening_context = self.topic_context.get_for_agent("title_abstract_screener")

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
            # Use enhanced fallback keyword matching with topic keywords (unified system)
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
                    keyword_result.decision.value == "uncertain"
                    or keyword_result.decision.value == "exclude"
                    or i % 10 == 0
                    or i == len(self.unique_papers)
                    or self.debug_config.level == DebugLevel.FULL
                )

                if should_log:
                    paper_title = (paper.title or "Untitled")[:60]
                    decision_str = keyword_result.decision.value.upper()
                    confidence_str = f"{keyword_result.confidence:.2f}"

                    # Extract matching details from reasoning if available
                    reasoning_preview = (
                        keyword_result.reasoning[:80]
                        if keyword_result.reasoning
                        else "No reasoning"
                    )

                    logger.debug(
                        f"Paper {i}/{len(self.unique_papers)}: {paper_title}... - "
                        f"Keyword matching: {decision_str} (confidence: {confidence_str})"
                    )
                    if is_verbose and self.debug_config.level == DebugLevel.FULL:
                        logger.debug(f"  -> Reasoning: {reasoning_preview}...")

            # Tier 1: High confidence inclusions go through immediately
            if (
                keyword_result.decision.value == "include"
                and keyword_result.confidence >= include_threshold
            ):
                self.screened_papers.append(paper)
                keyword_included += 1
                self.title_abstract_results.append(keyword_result)  # Store result
            # Tier 2: High confidence exclusions are excluded immediately
            elif (
                keyword_result.decision.value == "exclude"
                and keyword_result.confidence >= exclude_threshold
            ):
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
        filtering_rate = (
            (keyword_included + keyword_excluded) / len(self.unique_papers) * 100
            if self.unique_papers
            else 0
        )
        logger.info(
            f"Stage 1 filtering rate: {filtering_rate:.1f}% ({keyword_included + keyword_excluded}/{len(self.unique_papers)} papers filtered)"
        )

        # STAGE 2: LLM screening for borderline cases only
        if keyword_filtered_papers and self.title_screener.llm_client:
            logger.info(
                f"Stage 2: LLM screening for {len(keyword_filtered_papers)} borderline papers..."
            )
            logger.info("This may take a while as each paper requires an LLM call.")
            logger.info(
                f"LLM call reduction: {len(keyword_filtered_papers)}/{len(self.unique_papers)} papers ({len(keyword_filtered_papers) / len(self.unique_papers) * 100:.1f}%)"
            )

            # Create handoff
            screening_handoff = self.handoff_protocol.create_handoff(
                from_agent="search_agent",
                to_agent="title_abstract_screener",
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
                    "[cyan]LLM screening borderline papers...",
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
                    if not is_verbose and (
                        i == 1 or i % 5 == 0 or i == len(keyword_filtered_papers)
                    ):
                        logger.info(
                            f"LLM screening paper {i}/{len(keyword_filtered_papers)}: {paper_title}..."
                        )

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
                            reasoning_preview = (
                                result.reasoning[:100] if result.reasoning else "No reasoning"
                            )

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
                                    progress.log(
                                        f"  [dim]-> Exclusion reason: {result.exclusion_reason}[/dim]"
                                    )

                        # Store result for validation
                        self.title_abstract_results.append(result)

                        if result.decision.value == "include":
                            self.screened_papers.append(paper)
                            if is_verbose:
                                progress.log("  [green]Paper included via LLM[/green]")
                            logger.debug(f"Paper included via LLM: {paper_title}")
                        else:
                            if is_verbose:
                                progress.log("  [red]Paper excluded via LLM[/red]")
                            logger.debug(f"Paper excluded via LLM: {paper_title}")

                    except Exception as e:
                        logger.error(f"Error LLM screening paper ({paper_title}): {e}")
                        if is_verbose:
                            progress.log(f"  [red]Error: {e!s}[/red]")
                        # Use keyword result as fallback
                        self.title_abstract_results.append(keyword_result)  # Store fallback result
                        if keyword_result.decision.value == "include":
                            self.screened_papers.append(paper)
                            logger.warning("Using keyword result due to LLM error: included")

                    progress.advance(task)

                    # Log summary every 5 papers
                    if i % 5 == 0:
                        logger.info(
                            f"LLM progress: {i}/{len(keyword_filtered_papers)} screened, {len(self.screened_papers)} total included"
                        )
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

        # Check minimum paper safeguard
        safeguard_result = self._check_minimum_papers_safeguard(
            stage="title_abstract",
            included_count=len(self.screened_papers),
            total_count=len(self.unique_papers),
            min_papers=self.min_papers_threshold,
        )

        if not safeguard_result["meets_threshold"]:
            logger.warning("=" * 60)
            logger.warning("MINIMUM PAPER THRESHOLD NOT MET")
            logger.warning("=" * 60)
            logger.warning(
                f"Only {len(self.screened_papers)} papers passed title/abstract screening."
            )
            logger.warning("Recommendations:")
            for rec in safeguard_result["recommendations"]:
                logger.warning(f"  - {rec}")

            if safeguard_result["borderline_papers"]:
                logger.warning(
                    f"\nTop {len(safeguard_result['borderline_papers'])} borderline papers:"
                )
                for i, bp in enumerate(safeguard_result["borderline_papers"], 1):
                    logger.warning(
                        f"  {i}. {bp['paper'].title[:60]}... (confidence: {bp['confidence']:.2f})"
                    )

            logger.warning("=" * 60)
            logger.warning("Consider reviewing inclusion/exclusion criteria before proceeding.")
            logger.warning("=" * 60)

        # Enrich topic context
        self.topic_context.enrich(
            [f"Screened {len(self.unique_papers)} papers, {len(self.screened_papers)} included"]
        )

    def _screen_fulltext(self):
        """Screen papers based on full-text (if available)."""
        # Check if we already have fulltext screening results loaded from checkpoint
        if self.fulltext_results and len(self.fulltext_results) > 0:
            if len(self.fulltext_results) == len(self.screened_papers):
                logger.info(
                    f"Found existing full-text screening results for {len(self.fulltext_results)} papers"
                )
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

                # Check minimum paper safeguard even when resuming from checkpoint
                safeguard_result = self._check_minimum_papers_safeguard(
                    stage="fulltext",
                    included_count=len(self.eligible_papers),
                    total_count=len(self.screened_papers),
                    min_papers=self.min_papers_threshold,
                )

                if not safeguard_result["meets_threshold"]:
                    logger.error("=" * 60)
                    logger.error("CRITICAL: MINIMUM PAPER THRESHOLD NOT MET")
                    logger.error("=" * 60)
                    logger.error(
                        f"Only {len(self.eligible_papers)} papers passed full-text screening."
                    )
                    logger.error("This may indicate:")
                    logger.error("  1. Inclusion criteria are too strict")
                    logger.error("  2. Exclusion criteria are too broad")
                    logger.error("  3. Search strategy needs refinement")
                    logger.error("")
                    logger.error("Recommendations:")
                    for rec in safeguard_result["recommendations"]:
                        logger.error(f"  - {rec}")

                    if safeguard_result["borderline_papers"]:
                        logger.error(
                            f"\nTop {len(safeguard_result['borderline_papers'])} borderline papers:"
                        )
                        for i, bp in enumerate(safeguard_result["borderline_papers"], 1):
                            logger.error(
                                f"  {i}. {bp['paper'].title[:60]}... (confidence: {bp['confidence']:.2f})"
                            )
                            if bp["result"].exclusion_reason:
                                logger.error(
                                    f"      Exclusion reason: {bp['result'].exclusion_reason}"
                                )

                        # Export borderline papers for manual review
                        if self.safeguard_config.get("show_borderline_papers", True):
                            borderline_output_path = (
                                self.output_dir / "borderline_papers_for_review.json"
                            )
                            self._export_borderline_papers(
                                safeguard_result["borderline_papers"], borderline_output_path
                            )

                    logger.error("=" * 60)
                    logger.error("WORKFLOW PAUSED FOR MANUAL REVIEW")
                    logger.error("=" * 60)
                    logger.error("Options:")
                    logger.error("  1. Review and relax criteria in config/workflow.yaml")
                    logger.error(
                        "  2. Review borderline papers and manually include if appropriate"
                    )
                    logger.error("  3. Adjust search strategy to find more relevant papers")
                    logger.error(
                        "  4. Continue with current results (not recommended for systematic review)"
                    )
                    logger.error("")
                    logger.error("After making changes, re-run the workflow.")
                    logger.error("=" * 60)

                    # Raise exception to stop workflow if manual review is enabled
                    if self.enable_manual_review:
                        raise RuntimeError(
                            f"Minimum paper threshold not met: {len(self.eligible_papers)} papers included "
                            f"(required: {self.min_papers_threshold}). Please review screening criteria and borderline papers. "
                            f"See logs above for recommendations."
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

        # Get criteria from config (unified location in topic section)
        if "inclusion" not in self.config.get("topic", {}) or "exclusion" not in self.config.get(
            "topic", {}
        ):
            raise ValueError(
                "No inclusion/exclusion criteria found in config. Add them to topic.inclusion and topic.exclusion sections."
            )

        inclusion_criteria = self.config["topic"]["inclusion"]
        exclusion_criteria = self.config["topic"]["exclusion"]

        # Apply template replacement to criteria
        inclusion_criteria = [self.topic_context.inject_into_prompt(c) for c in inclusion_criteria]
        exclusion_criteria = [self.topic_context.inject_into_prompt(c) for c in exclusion_criteria]

        # Get topic context for full-text screening agent
        fulltext_context = self.topic_context.get_for_agent("fulltext_screener")

        # Check if verbose mode is enabled
        is_verbose = self.debug_config.enabled and self.debug_config.level in [
            DebugLevel.DETAILED,
            DebugLevel.FULL,
        ]

        # Create handoff
        self.handoff_protocol.create_handoff(
            from_agent="title_abstract_screener",
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
                progress.update(
                    task,
                    description=f"[cyan]Full-text screening: {paper_title}... ({i}/{len(self.screened_papers)})",
                )

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
                            "  [dim]-> Full-text not available, falling back to title/abstract screening[/dim]"
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
                    result.decision.value.upper()
                    confidence_str = f"{result.confidence:.2f}"
                    reasoning_preview = (
                        result.reasoning[:100] if result.reasoning else "No reasoning"
                    )

                    if result.decision.value == "include":
                        status_color = "[green]INCLUDE[/green]"
                    elif result.decision.value == "exclude":
                        status_color = "[red]EXCLUDE[/red]"
                    else:
                        status_color = "[yellow]UNCERTAIN[/yellow]"

                    progress.log(
                        f"  [dim]-> Decision:[/dim] {status_color}, Confidence: {confidence_str}"
                    )
                    if self.debug_config.level == DebugLevel.FULL:
                        progress.log(f"  [dim]-> Reasoning: {reasoning_preview}...[/dim]")
                        if result.exclusion_reason:
                            progress.log(
                                f"  [dim]-> Exclusion reason: {result.exclusion_reason}[/dim]"
                            )

                if result.decision.value == "include":
                    self.eligible_papers.append(paper)
                    if is_verbose:
                        progress.log("  [green]Paper eligible[/green]")
                else:
                    if is_verbose:
                        progress.log("  [red]Paper excluded[/red]")

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
            self.screening_validator.calculate_statistics(
                self.screened_papers, self.fulltext_results, ScreeningStage.FULL_TEXT
            )
            self.screening_validator.log_statistics(ScreeningStage.FULL_TEXT)

        # Check minimum paper safeguard
        safeguard_result = self._check_minimum_papers_safeguard(
            stage="fulltext",
            included_count=len(self.eligible_papers),
            total_count=len(self.screened_papers),
            min_papers=self.min_papers_threshold,
        )

        if not safeguard_result["meets_threshold"]:
            logger.error("=" * 60)
            logger.error("CRITICAL: MINIMUM PAPER THRESHOLD NOT MET")
            logger.error("=" * 60)
            logger.error(f"Only {len(self.eligible_papers)} papers passed full-text screening.")
            logger.error("This may indicate:")
            logger.error("  1. Inclusion criteria are too strict")
            logger.error("  2. Exclusion criteria are too broad")
            logger.error("  3. Search strategy needs refinement")
            logger.error("")
            logger.error("Recommendations:")
            for rec in safeguard_result["recommendations"]:
                logger.error(f"  - {rec}")

            if safeguard_result["borderline_papers"]:
                logger.error(
                    f"\nTop {len(safeguard_result['borderline_papers'])} borderline papers:"
                )
                for i, bp in enumerate(safeguard_result["borderline_papers"], 1):
                    logger.error(
                        f"  {i}. {bp['paper'].title[:60]}... (confidence: {bp['confidence']:.2f})"
                    )
                    if bp["result"].exclusion_reason:
                        logger.error(f"      Exclusion reason: {bp['result'].exclusion_reason}")

                # Export borderline papers for manual review
                if self.safeguard_config.get("show_borderline_papers", True):
                    borderline_output_path = self.output_dir / "borderline_papers_for_review.json"
                    self._export_borderline_papers(
                        safeguard_result["borderline_papers"], borderline_output_path
                    )

            logger.error("=" * 60)
            logger.error("WORKFLOW PAUSED FOR MANUAL REVIEW")
            logger.error("=" * 60)
            logger.error("Options:")
            logger.error("  1. Review and relax criteria in config/workflow.yaml")
            logger.error("  2. Review borderline papers and manually include if appropriate")
            logger.error("  3. Adjust search strategy to find more relevant papers")
            logger.error(
                "  4. Continue with current results (not recommended for systematic review)"
            )
            logger.error("")
            logger.error("After making changes, re-run the workflow.")
            logger.error("=" * 60)

            # Raise exception to stop workflow if manual review is enabled
            if self.enable_manual_review:
                raise RuntimeError(
                    f"Minimum paper threshold not met: {len(self.eligible_papers)} papers included "
                    f"(required: {self.min_papers_threshold}). Please review screening criteria and borderline papers. "
                    f"See logs above for recommendations."
                )

        # Enrich topic context
        self.topic_context.enrich(
            [
                f"Full-text screened {len(self.screened_papers)} papers, {len(self.eligible_papers)} eligible",
                f"Full-text available for {self.fulltext_available_count} papers",
            ]
        )

    def _check_minimum_papers_safeguard(
        self, stage: str, included_count: int, total_count: int, min_papers: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Check if minimum paper threshold is met and provide recommendations.

        Args:
            stage: Screening stage name ('title_abstract' or 'fulltext')
            included_count: Number of papers included
            total_count: Total papers screened
            min_papers: Minimum required papers (defaults to self.min_papers_threshold)

        Returns:
            Dict with 'meets_threshold', 'recommendations', 'borderline_papers'
        """
        if min_papers is None:
            min_papers = self.min_papers_threshold

        meets_threshold = included_count >= min_papers
        inclusion_rate = (included_count / total_count * 100) if total_count > 0 else 0

        recommendations = []
        borderline_papers = []

        if not meets_threshold:
            recommendations.append(
                f"Inclusion rate is {inclusion_rate:.1f}% ({included_count}/{total_count} papers). "
                f"Consider reviewing screening criteria."
            )

            # Find borderline papers (excluded but with low confidence, meaning close match)
            if stage == "fulltext" and hasattr(self, "fulltext_results"):
                for i, result in enumerate(self.fulltext_results):
                    if result.decision.value == "exclude" and result.confidence < 0.7:
                        if i < len(self.screened_papers):
                            borderline_papers.append(
                                {
                                    "paper": self.screened_papers[i],
                                    "result": result,
                                    "confidence": result.confidence,
                                }
                            )
            elif stage == "title_abstract" and hasattr(self, "title_abstract_results"):
                for i, result in enumerate(self.title_abstract_results):
                    if result.decision.value == "exclude" and result.confidence < 0.7:
                        if i < len(self.unique_papers):
                            borderline_papers.append(
                                {
                                    "paper": self.unique_papers[i],
                                    "result": result,
                                    "confidence": result.confidence,
                                }
                            )

            # Sort borderline papers by confidence (highest first)
            borderline_papers.sort(key=lambda x: x["confidence"], reverse=True)

            if borderline_papers:
                recommendations.append(
                    f"Found {len(borderline_papers)} borderline papers that were excluded. "
                    f"Review these papers to determine if criteria should be relaxed."
                )

        return {
            "meets_threshold": meets_threshold,
            "inclusion_rate": inclusion_rate,
            "recommendations": recommendations,
            "borderline_papers": borderline_papers[: min_papers - included_count]
            if not meets_threshold
            else [],
        }

    def _export_borderline_papers(self, borderline_papers: List[Dict], output_path: Path):
        """Export borderline papers to a JSON file for manual review."""
        import json

        export_data = []
        for bp in borderline_papers:
            paper = bp["paper"]
            result = bp["result"]
            export_data.append(
                {
                    "title": paper.title,
                    "abstract": paper.abstract[:500] if paper.abstract else "",
                    "authors": paper.authors[:3] if paper.authors else [],
                    "year": paper.year,
                    "doi": paper.doi,
                    "url": paper.url,
                    "screening_confidence": bp["confidence"],
                    "exclusion_reason": result.exclusion_reason,
                    "reasoning": result.reasoning,
                }
            )

        with open(output_path, "w") as f:
            json.dump(export_data, f, indent=2)

        logger.info(f"Exported {len(export_data)} borderline papers to {output_path}")

    def _enrich_papers(self):
        """Enrich papers with missing metadata (affiliations, countries, etc.)."""
        logger.info(f"Enriching {len(self.final_papers)} papers with missing metadata...")

        # First, enrich with Crossref data (affiliations, etc.)
        self.final_papers = self.paper_enricher.enrich_papers(self.final_papers)

        # Then, enrich with bibliometric data if enabled
        if self.bibliometric_enricher:
            self.final_papers = self.bibliometric_enricher.enrich_papers(self.final_papers)

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
                        "  [dim]-> Building extraction prompt with fields: study_objectives, methodology, "
                        "study_design, participants, interventions, outcomes, key_findings, limitations...[/dim]"
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
                    objectives_count = (
                        len(extracted.study_objectives) if extracted.study_objectives else 0
                    )
                    outcomes_count = len(extracted.outcomes) if extracted.outcomes else 0
                    findings_count = len(extracted.key_findings) if extracted.key_findings else 0
                    progress.log(
                        f"  [green]Extraction complete[/green] - "
                        f"Objectives: {objectives_count}, Outcomes: {outcomes_count}, Findings: {findings_count}"
                    )
                    if self.debug_config.level == DebugLevel.FULL:
                        methodology_preview = (extracted.methodology or "")[:100]
                        if methodology_preview:
                            progress.log(
                                f"  [dim]-> Methodology preview: {methodology_preview}...[/dim]"
                            )

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

        # Log extraction statistics
        empty_extraction_count = 0
        for extracted in self.extracted_data:
            objectives_empty = (
                not extracted.study_objectives or len(extracted.study_objectives) == 0
            )
            outcomes_empty = not extracted.outcomes or len(extracted.outcomes) == 0
            findings_empty = not extracted.key_findings or len(extracted.key_findings) == 0
            if objectives_empty and outcomes_empty and findings_empty:
                empty_extraction_count += 1

        if empty_extraction_count > 0:
            percentage = (
                (empty_extraction_count / len(self.extracted_data)) * 100
                if self.extracted_data
                else 0
            )
            if percentage > 50:
                logger.error(
                    f"High number of empty extractions: {empty_extraction_count}/{len(self.extracted_data)} "
                    f"({percentage:.1f}%) papers returned no objectives, outcomes, or findings. "
                    f"This may indicate: (1) papers lack extractable structured data, "
                    f"(2) extraction prompt needs refinement, or (3) LLM issues."
                )
            elif percentage > 20:
                logger.warning(
                    f"Moderate number of empty extractions: {empty_extraction_count}/{len(self.extracted_data)} "
                    f"({percentage:.1f}%) papers returned no objectives, outcomes, or findings."
                )
            else:
                logger.info(
                    f"Extraction statistics: {empty_extraction_count}/{len(self.extracted_data)} "
                    f"({percentage:.1f}%) papers had empty extractions (may be expected for some papers)."
                )

    def _quality_assessment(self) -> Dict[str, Any]:
        """
        Quality assessment phase using CASP framework: Generate template or load assessments.

        Returns:
            Dictionary with CASP quality assessments and GRADE assessment data
        """
        from ..quality import (
            GRADEAssessor,
            QualityAssessmentTemplateGenerator,
        )
        from ..quality.study_type_detector import StudyTypeDetector

        # Get quality assessment config
        qa_config = self.config.get("quality_assessment", {})
        framework = qa_config.get("framework", "CASP")
        grade_assessment = qa_config.get("grade_assessment", True)

        # Get CASP-specific config
        casp_config = qa_config.get("casp", {})
        auto_detect = casp_config.get("auto_detect", {})
        detector_enabled = auto_detect.get("enabled", True)
        detector_model = auto_detect.get("llm_model", "gemini-2.5-flash")

        # Get template path
        template_path_template = qa_config.get(
            "template_path", "data/quality_assessments/{workflow_id}_assessments.json"
        )
        template_path = template_path_template.format(workflow_id=self.workflow_id)
        template_path_obj = Path(template_path)
        template_path_obj.parent.mkdir(parents=True, exist_ok=True)

        # Initialize generators and assessors
        template_generator = QualityAssessmentTemplateGenerator(framework)
        grade_assessor = GRADEAssessor()

        # Check if assessment file exists
        if not template_path_obj.exists():
            # Generate template
            logger.info("Quality assessment template not found. Generating CASP template...")

            # Detect study types if auto-detection is enabled
            detected_types = {}
            if detector_enabled:
                logger.info("Detecting study types for CASP checklist selection...")
                try:
                    # Initialize LLM client for detector
                    from google import genai
                    from google.genai import types

                    api_key = os.getenv("GEMINI_API_KEY")
                    if api_key:
                        llm_client = genai.Client(
                            api_key=api_key, http_options=types.HttpOptions(timeout=120_000)
                        )
                        detector = StudyTypeDetector(
                            llm_client=llm_client,
                            llm_model=detector_model,
                            debug_config=self.debug_config,
                        )

                        # Detect type for each study
                        for study in self.extracted_data:
                            study_dict = study.to_dict() if hasattr(study, "to_dict") else study
                            detection_result = detector.detect_study_type(study_dict)
                            detected_types[study.title] = detection_result

                        logger.info(f"Detected study types for {len(detected_types)} studies")
                    else:
                        logger.warning("GEMINI_API_KEY not found, skipping study type detection")
                except Exception as e:
                    logger.warning(f"Study type detection failed: {e}. Using default checklist.")

            # Infer GRADE outcomes from extracted data
            grade_outcomes = []
            if grade_assessment:
                all_outcomes = set()
                for data in self.extracted_data:
                    all_outcomes.update(data.outcomes)
                grade_outcomes = sorted(all_outcomes)[:10]  # Limit to 10 outcomes

            template_path_str = template_generator.generate_template(
                self.extracted_data,
                str(template_path_obj),
                grade_outcomes=grade_outcomes if grade_outcomes else None,
                detected_types=detected_types if detected_types else None,
            )

            # Check if auto-fill is enabled
            auto_fill = qa_config.get("auto_fill", True)  # Default to True
            if auto_fill:
                logger.info("Auto-filling CASP quality assessments using LLM...")
                try:
                    from ..quality.auto_filler import auto_fill_assessments

                    # Get LLM provider/model from config
                    assessment_llm_config = qa_config.get("assessment_llm", {})
                    llm_provider = os.getenv("LLM_PROVIDER", "gemini")
                    llm_model = assessment_llm_config.get("model", "gemini-2.5-pro")

                    # Determine verbose mode for quality assessment
                    is_verbose = self.debug_config.enabled and self.debug_config.level in [
                        DebugLevel.DETAILED,
                        DebugLevel.FULL,
                    ]

                    if is_verbose:
                        logger.info("Verbose mode enabled - showing detailed LLM call information")

                    success = auto_fill_assessments(
                        template_path_str,
                        self.extracted_data,
                        llm_provider=llm_provider,
                        llm_model=llm_model,
                        debug_config=self.debug_config,
                        framework=framework,
                        detector_model=detector_model,
                    )
                    if success:
                        logger.info("CASP quality assessments auto-filled successfully!")
                    else:
                        logger.warning(
                            "Auto-fill failed, but template is ready for manual completion"
                        )
                        raise RuntimeError(
                            f"Quality assessment template generated at {template_path_str}. "
                            "Auto-fill failed. Please complete the assessments manually and re-run the workflow."
                        )
                except ImportError as e:
                    logger.warning(
                        f"Could not import auto-fill module: {e}. Falling back to manual assessment."
                    )
                    auto_fill = False
                except Exception as e:
                    logger.warning(f"Auto-fill failed: {e}. Falling back to manual assessment.")
                    auto_fill = False

            # If auto-fill is disabled or failed, stop workflow
            if not auto_fill:
                logger.error("=" * 60)
                logger.error("QUALITY ASSESSMENT REQUIRED")
                logger.error("=" * 60)
                logger.error(f"Quality assessment template generated at: {template_path_str}")
                logger.error("")
                logger.error("Please complete the quality assessments in the template file:")
                logger.error(f"  1. Open: {template_path_str}")
                logger.error("  2. Complete risk of bias assessments for all studies")
                if grade_assessment:
                    logger.error("  3. Complete GRADE assessments for all outcomes")
                logger.error("  4. Save the file")
                logger.error("  5. Re-run the workflow (it will resume from this point)")
                logger.error("")
                logger.error("The workflow will stop here until assessments are completed.")
                logger.error("=" * 60)

                raise RuntimeError(
                    f"Quality assessment template generated at {template_path_str}. "
                    "Please complete the assessments and re-run the workflow."
                )

        # Load assessments
        logger.info(f"Loading quality assessments from {template_path_obj}")

        casp_assessments = []
        grade_assessments_list = []

        # Load CASP assessments from template
        try:
            with open(template_path_obj) as f:
                template_data = json.load(f)

            casp_assessments = template_data.get("studies", [])
            logger.info(f"Loaded {len(casp_assessments)} CASP quality assessments")

            # Log summary of quality ratings
            if casp_assessments:
                high_count = sum(
                    1
                    for s in casp_assessments
                    if s.get("quality_assessment", {}).get("score", {}).get("quality_rating")
                    == "High"
                )
                moderate_count = sum(
                    1
                    for s in casp_assessments
                    if s.get("quality_assessment", {}).get("score", {}).get("quality_rating")
                    == "Moderate"
                )
                low_count = sum(
                    1
                    for s in casp_assessments
                    if s.get("quality_assessment", {}).get("score", {}).get("quality_rating")
                    == "Low"
                )
                logger.info(
                    f"Quality ratings: {high_count} High, {moderate_count} Moderate, {low_count} Low"
                )
        except Exception as e:
            logger.warning(f"Could not load CASP assessments: {e}")

        if grade_assessment:
            try:
                grade_assessments_list = grade_assessor.load_assessments(str(template_path_obj))
                logger.info(f"Loaded {len(grade_assessments_list)} GRADE assessments")
            except Exception as e:
                logger.warning(f"Could not load GRADE assessments: {e}")

        # Generate summary tables and narratives for CASP
        casp_table = ""
        casp_summary = ""
        if casp_assessments:
            casp_table = self._generate_casp_summary_table(casp_assessments)
            casp_summary = self._generate_casp_narrative_summary(casp_assessments)

        grade_table = ""
        grade_summary = ""
        if grade_assessments_list:
            grade_table = grade_assessor.generate_evidence_profile_table(grade_assessments_list)
            grade_summary = grade_assessor.generate_narrative_summary(grade_assessments_list)

        # Store for use in writing agents
        self.quality_assessment_data = {
            "framework": framework,
            "casp_assessments": casp_assessments,
            "casp_table": casp_table,
            "casp_summary": casp_summary,
            # Keep backward-compatible keys for writing agents
            "risk_of_bias_assessments": casp_assessments,  # Alias for compatibility
            "risk_of_bias_table": casp_table,
            "risk_of_bias_summary": casp_summary,
            "grade_assessments": grade_assessments_list,
            "grade_table": grade_table,
            "grade_summary": grade_summary,
        }

        return self.quality_assessment_data

    def _generate_casp_summary_table(self, casp_assessments: List[Dict[str, Any]]) -> str:
        """Generate markdown table summarizing CASP quality assessments."""
        if not casp_assessments:
            return ""

        lines = []
        lines.append("| Study | Checklist | Quality Rating | Yes Count | Total Questions |")
        lines.append("|-------|-----------|----------------|-----------|-----------------|")

        for assessment in casp_assessments:
            study_title = assessment.get("study_title", "Unknown")[:50]
            qa = assessment.get("quality_assessment", {})
            checklist = qa.get("checklist_used", "Unknown")
            score = qa.get("score", {})
            rating = score.get("quality_rating", "Unknown")
            yes_count = score.get("yes_count", 0)
            total = score.get("total_questions", 0)

            # Shorten checklist name
            checklist_short = checklist.replace("casp_", "").upper()

            lines.append(
                f"| {study_title} | {checklist_short} | {rating} | {yes_count} | {total} |"
            )

        return "\n".join(lines)

    def _generate_casp_narrative_summary(self, casp_assessments: List[Dict[str, Any]]) -> str:
        """Generate narrative summary of CASP quality assessments."""
        if not casp_assessments:
            return "No quality assessments available."

        total_studies = len(casp_assessments)

        # Count by quality rating
        high_count = sum(
            1
            for s in casp_assessments
            if s.get("quality_assessment", {}).get("score", {}).get("quality_rating") == "High"
        )
        moderate_count = sum(
            1
            for s in casp_assessments
            if s.get("quality_assessment", {}).get("score", {}).get("quality_rating") == "Moderate"
        )
        low_count = sum(
            1
            for s in casp_assessments
            if s.get("quality_assessment", {}).get("score", {}).get("quality_rating") == "Low"
        )

        # Count by checklist type
        rct_count = sum(
            1
            for s in casp_assessments
            if s.get("quality_assessment", {}).get("checklist_used") == "casp_rct"
        )
        cohort_count = sum(
            1
            for s in casp_assessments
            if s.get("quality_assessment", {}).get("checklist_used") == "casp_cohort"
        )
        qual_count = sum(
            1
            for s in casp_assessments
            if s.get("quality_assessment", {}).get("checklist_used") == "casp_qualitative"
        )

        summary = []
        summary.append(
            f"Quality assessment was conducted using the CASP (Critical Appraisal Skills Programme) framework for {total_studies} included studies."
        )
        summary.append(
            f"Studies were assessed using three CASP checklists: {rct_count} RCT studies, {cohort_count} cohort studies, and {qual_count} qualitative studies."
        )

        if high_count > 0:
            summary.append(
                f"{high_count} studies ({high_count / total_studies * 100:.0f}%) were rated as high quality, meeting >80% of CASP quality criteria."
            )
        if moderate_count > 0:
            summary.append(
                f"{moderate_count} studies ({moderate_count / total_studies * 100:.0f}%) were rated as moderate quality, meeting 50-80% of criteria."
            )
        if low_count > 0:
            summary.append(
                f"{low_count} studies ({low_count / total_studies * 100:.0f}%) were rated as low quality, meeting <50% of criteria."
            )

        summary.append(
            "The CASP checklists assess study design appropriateness, methodological rigor, reporting quality, and applicability of findings."
        )

        return " ".join(summary)

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
            framework = self.quality_assessment_data.get("framework", "CASP")

            # Quality assessment plot (framework-dependent)
            if framework == "CASP":
                # For CASP, skip traditional RoB plot as structure is different
                # CASP uses Yes/No/Can't Tell questions rather than domain ratings
                logger.info(
                    "Skipping traditional RoB plot for CASP framework (use CASP-specific visualization)"
                )
            else:
                # Traditional risk of bias plot for RoB 2, ROBINS-I, etc.
                rob_assessments = self.quality_assessment_data.get("risk_of_bias_assessments", [])
                if rob_assessments:
                    # Convert to list of dicts for visualization
                    rob_data = []
                    for assessment in rob_assessments:
                        domains = (
                            assessment.domains
                            if hasattr(assessment, "domains")
                            else assessment.get("domains", {})
                        )
                        # Only include if domains exist and are non-empty
                        if domains:
                            rob_data.append(
                                {
                                    "study_id": assessment.study_id
                                    if hasattr(assessment, "study_id")
                                    else assessment.get("study_id", ""),
                                    "domains": domains,
                                }
                            )
                    if rob_data:  # Only generate if we have valid data
                        rob_plot_path = self.chart_generator.generate_risk_of_bias_plot(rob_data)
                        if rob_plot_path:
                            paths["risk_of_bias_plot"] = rob_plot_path

            # GRADE evidence profile
            grade_assessments = self.quality_assessment_data.get("grade_assessments", [])
            if grade_assessments:
                # Convert to list of dicts for visualization
                grade_data = []
                for assessment in grade_assessments:
                    grade_data.append(
                        {
                            "outcome": assessment.outcome
                            if hasattr(assessment, "outcome")
                            else assessment.get("outcome", ""),
                            "certainty": assessment.certainty
                            if hasattr(assessment, "certainty")
                            else assessment.get("certainty", ""),
                        }
                    )
                grade_plot_path = self.chart_generator.generate_grade_evidence_profile(grade_data)
                if grade_plot_path:
                    paths["grade_evidence_profile"] = grade_plot_path

        return paths

    def _validate_section_citations(
        self, section_name: str, section_text: str, fail_on_invalid: bool = False
    ) -> bool:
        """
        Validate citations in a section.
        
        Args:
            section_name: Name of the section
            section_text: Section text to validate
            
        Returns:
            True if all citations are valid, False otherwise
        """
        if not hasattr(self, 'citation_registry') or not self.citation_registry:
            logger.warning(f"Citation registry not available for validation of {section_name}")
            return True  # Skip validation if registry not built
        
        # Extract all citekeys from section
        citekeys = self.citation_registry.extract_citekeys_from_text(section_text)
        
        if not citekeys:
            logger.info(f"No citations found in {section_name} section")
            return True
        
        # Validate citekeys
        valid, invalid = self.citation_registry.validate_citekeys(citekeys)
        
        if invalid:
            logger.warning(f"Found {len(invalid)} invalid citations in {section_name}: {invalid[:5]}")
            logger.warning("These citations do not match any paper in final_papers")
            if fail_on_invalid:
                return False
        
        unique_valid = len(set(valid))
        logger.info(f"Validated {section_name}: {unique_valid} unique valid citations, {len(invalid)} invalid")
        
        return True

    def _ensure_citation_registry(self) -> None:
        """Build citation registry if not already initialized."""
        if hasattr(self, "citation_registry") and self.citation_registry is not None:
            return
        from .citation_registry import CitationRegistry

        self.citation_registry = CitationRegistry(self.final_papers)
        logger.info(
            f"Initialized citation registry with {len(self.citation_registry.citekey_to_paper)} papers"
        )
    
    def _extract_and_map_citations(self, text: str, citation_map: dict) -> str:
        """
        Extract author-year citations and replace with numbered citations.
        
        Args:
            text: Text containing citations like [Kaufman2020]
            citation_map: Dict mapping citekeys to paper indices
            
        Returns:
            Text with citations replaced with [1], [2], etc.
        """
        import re
        
        # Pattern to match author-year citations: [Author2020], [AuthorName2020a]
        pattern = r'\[([A-Z][a-zA-Z]+\d{4}[a-z]?)\]'
        
        def replace_citation(match):
            citekey = match.group(1)
            if citekey in citation_map:
                return f"[{citation_map[citekey]}]"
            else:
                # Citation not found in papers - keep original
                logger.warning(f"Citation {citekey} not found in final papers")
                return match.group(0)
        
        return re.sub(pattern, replace_citation, text)
    
    def _build_citation_map(self, all_text: str) -> dict:
        """
        Build a mapping from citekeys to paper indices.
        
        Args:
            all_text: Combined text from all sections
            
        Returns:
            Dict mapping citekeys like 'Kaufman2020' to citation numbers like 1, 2, 3
        """
        import re
        
        # Extract all citekeys from text
        pattern = r'\[([A-Z][a-zA-Z]+\d{4}[a-z]?)\]'
        citekeys = re.findall(pattern, all_text)
        unique_citekeys = list(dict.fromkeys(citekeys))  # Preserve order, remove dupes
        
        # Map each citekey to a paper
        citation_map = {}
        citation_number = 1
        
        for citekey in unique_citekeys:
            # Extract author surname and year from citekey
            match = re.match(r'([A-Z][a-zA-Z]+)(\d{4})([a-z]?)', citekey)
            if not match:
                continue
                
            author_surname = match.group(1).lower()
            year_str = match.group(2)
            
            # Find matching paper in final_papers
            for paper in self.final_papers:
                if not paper.authors or not paper.year:
                    continue
                    
                # Check if first author surname matches (case-insensitive)
                first_author = paper.authors[0].lower()
                # Extract surname from "Firstname Surname" or "Surname, Firstname"
                if ',' in first_author:
                    paper_surname = first_author.split(',')[0].strip()
                else:
                    # Take last word as surname
                    paper_surname = first_author.split()[-1]
                
                # Check year match
                if paper_surname == author_surname.lower() and str(paper.year) == year_str:
                    citation_map[citekey] = citation_number
                    citation_number += 1
                    break
            else:
                # No matching paper found - still assign a number to avoid breaking citations
                logger.warning(f"No paper found for citation {citekey}")
                citation_map[citekey] = citation_number
                citation_number += 1
        
        return citation_map
    
    def _generate_references_from_citations(self, citation_map: dict) -> str:
        """
        Generate references section for cited papers only.
        
        Args:
            citation_map: Dict mapping citekeys to citation numbers
            
        Returns:
            Formatted references section
        """
        if not citation_map:
            return "## References\n\nNo citations found in the document.\n\n"
        
        # Create reverse map: citation_number -> citekey
        reverse_map = {num: key for key, num in citation_map.items()}
        
        # Generate references in numerical order
        refs = ["## References\n\n"]
        for num in sorted(reverse_map.keys()):
            citekey = reverse_map[num]
            
            # Find the paper for this citekey
            match = re.match(r'([A-Z][a-zA-Z]+)(\d{4})([a-z]?)', citekey)
            if not match:
                refs.append(f"[{num}] {citekey} (citation not found)\n\n")
                continue
                
            author_surname = match.group(1).lower()
            year_str = match.group(2)
            
            # Find paper
            paper = None
            for p in self.final_papers:
                if not p.authors or not p.year:
                    continue
                first_author = p.authors[0].lower()
                if ',' in first_author:
                    paper_surname = first_author.split(',')[0].strip()
                else:
                    paper_surname = first_author.split()[-1]
                
                if paper_surname == author_surname.lower() and str(p.year) == year_str:
                    paper = p
                    break
            
            if not paper:
                refs.append(f"[{num}] {citekey} (paper not found)\n\n")
                continue
            
            # Format reference in IEEE/Vancouver style
            authors = paper.authors[:3] if paper.authors else ["Unknown"]
            authors_str = ", ".join(authors)
            if len(paper.authors) > 3:
                authors_str += " et al."
            
            title = paper.title or "Untitled"
            journal = paper.journal or ""
            year = paper.year or "n.d."
            doi = paper.doi or ""
            
            ref = f"[{num}] {authors_str}. {title}."
            if journal:
                ref += f" {journal},"
            ref += f" {year}."
            if doi:
                ref += f" DOI: {doi}"
            
            refs.append(ref + "\n\n")
        
        return "".join(refs)

    def _collect_mermaid_diagrams(self) -> Dict[str, str]:
        """
        Scan output directory for mermaid diagram SVG files (fallback method).

        This method scans the output directory for SVG files that match mermaid
        diagram naming patterns and adds them to visualizations.

        Returns:
            Dictionary mapping diagram names to relative file paths
        """
        mermaid_paths = {}
        output_path = Path(self.output_dir)

        if not output_path.exists():
            return mermaid_paths

        # Look for SVG files matching mermaid naming pattern (diagram_type_title.svg)
        svg_files = list(output_path.glob("*.svg"))

        for svg_file in svg_files:
            stem = svg_file.stem
            # Check if it matches mermaid diagram naming patterns
            # Mermaid diagrams typically have format: {diagram_type}_{title}.svg
            # e.g., pie_bias_prevalence.svg, mindmap_themes.svg, flowchart_process.svg
            mermaid_types = [
                "pie",
                "mindmap",
                "flowchart",
                "gantt",
                "sankey",
                "treemap",
                "quadrant",
                "xy",
                "sequence",
                "timeline",
                "state",
                "class",
                "er",
                "journey",
                "block",
                "architecture",
            ]

            # Check if filename starts with a known mermaid diagram type
            for diagram_type in mermaid_types:
                if stem.startswith(f"{diagram_type}_"):
                    # This looks like a mermaid diagram
                    stem.replace("_", " ").title()
                    # Use relative path for report
                    rel_path = svg_file.name
                    mermaid_paths[stem] = rel_path
                    logger.debug(f"Found mermaid diagram: {stem} -> {rel_path}")
                    break

        if mermaid_paths:
            logger.info(f"Collected {len(mermaid_paths)} mermaid diagram(s) via directory scan")

        return mermaid_paths

    def _extract_style_patterns(self):
        """Extract writing style patterns from eligible papers - feature removed."""
        logger.warning("Style pattern extraction is no longer available")
        self.style_patterns = {}

    def _save_section_checkpoint(self, section_name: str, sections: Dict[str, str]) -> bool:
        """
        Save checkpoint after a section completes.

        Args:
            section_name: Name of the section (e.g., 'introduction', 'methods')
            sections: Dictionary of all completed sections

        Returns:
            True if checkpoint was saved successfully, False otherwise
        """
        if not self.save_checkpoints:
            return True  # Not saving is not a failure

        writing_config = self.config.get("writing", {})
        checkpoint_per_section = writing_config.get("checkpoint_per_section", True)

        if not checkpoint_per_section:
            return True  # Not saving is not a failure

        try:
            # Save individual section checkpoint file
            checkpoint_data = {
                "phase": "article_writing",
                "section_name": section_name,
                "timestamp": datetime.now().isoformat(),
                "workflow_id": self.workflow_id,
                "topic_context": self.topic_context.to_dict(),
                "data": {
                    "section_content": sections[section_name],
                },
                "style_patterns": self.style_patterns,
                "prisma_counts": self.prisma_counter.get_counts(),
            }

            checkpoint_file = self.checkpoint_dir / f"article_writing_{section_name}_state.json"
            with open(checkpoint_file, "w") as f:
                import json

                json.dump(checkpoint_data, f, indent=2, default=str)

            logger.info(
                f"Saved checkpoint after {section_name} section completion: {checkpoint_file.name}"
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to save section checkpoint for {section_name}: {e}")
            return False

    def _load_existing_sections(self) -> Dict[str, str]:
        """
        Load existing sections from checkpoint if available.
        Scans for all article_writing_*_state.json files and loads each section individually.

        Returns:
            Dictionary of existing sections, empty dict if none found
        """
        sections = {}
        checkpoint_pattern = "article_writing_*_state.json"

        for checkpoint_file in self.checkpoint_dir.glob(checkpoint_pattern):
            # Extract section name from filename: article_writing_introduction_state.json -> introduction
            section_name = checkpoint_file.stem.replace("article_writing_", "").replace(
                "_state", ""
            )

            try:
                import json

                with open(checkpoint_file) as f:
                    checkpoint_data = json.load(f)

                # Validate workflow_id matches
                if checkpoint_data.get("workflow_id") == self.workflow_id:
                    if "data" in checkpoint_data and "section_content" in checkpoint_data["data"]:
                        sections[section_name] = checkpoint_data["data"]["section_content"]
                        logger.info(
                            f"Loaded {section_name} section from checkpoint: {checkpoint_file.name}"
                        )
                else:
                    logger.debug(
                        f"Skipping checkpoint {checkpoint_file.name} - workflow_id mismatch"
                    )
            except Exception as e:
                logger.warning(f"Failed to load checkpoint {checkpoint_file.name}: {e}")

        if sections:
            logger.info(f"Found {len(sections)} existing sections: {', '.join(sections.keys())}")

        return sections

    def _write_section_with_retry(
        self, section_name: str, writer_func: callable, *args, **kwargs
    ) -> tuple:
        """
        Write a section with retry logic and exponential backoff.

        Args:
            section_name: Name of the section
            writer_func: Function to write the section
            *args, **kwargs: Arguments to pass to writer_func

        Returns:
            Tuple of (section_text, duration, word_count)
        """
        import time

        from ..utils.rich_utils import print_section_retry_panel

        writing_config = self.config.get("writing", {})
        retry_count = writing_config.get("retry_count", 2)
        max_attempts = retry_count + 1  # Initial attempt + retries

        section_start_time = time.time()
        last_error_reason = "Unknown error"

        # Get context for better error messages
        model_name = getattr(writer_func, "__self__", None)
        if model_name:
            model_name = getattr(model_name, "llm_model", "unknown")
        else:
            model_name = "unknown"

        paper_count = len(self.extracted_data) if hasattr(self, "extracted_data") else 0

        for attempt in range(max_attempts):
            # Show retry panel if this is not the first attempt
            if attempt > 0:
                # Exponential backoff: 2^(attempt-1) seconds (2s, 4s, 8s, ...)
                backoff_delay = 2 ** (attempt - 1)
                logger.info(f"Waiting {backoff_delay}s before retry (exponential backoff)...")
                time.sleep(backoff_delay)

                print_section_retry_panel(
                    section_name=section_name.title(),
                    attempt_number=attempt + 1,
                    max_attempts=max_attempts,
                    reason=last_error_reason,
                )

            try:
                logger.info(
                    f"Writing {section_name} section - attempt {attempt + 1}/{max_attempts} "
                    f"(model: {model_name}, papers: {paper_count})"
                )
                result = writer_func(*args, **kwargs)
                if result is not None and result.strip():
                    if attempt > 0:
                        logger.info(f"{section_name} section succeeded on attempt {attempt + 1}")

                    # Calculate metrics
                    duration = time.time() - section_start_time
                    word_count = len(result.split())

                    return result, duration, word_count
                else:
                    last_error_reason = "Empty response from LLM"
                    logger.warning(
                        f"{section_name} section returned empty result on attempt {attempt + 1}. "
                        f"Context: model={model_name}, papers={paper_count}. "
                        f"Possible causes: (1) Gemini API rate limiting, (2) API timeout (increase llm_timeout in config), "
                        f"(3) prompt too complex (reduce paper count or simplify), or (4) temporary API unavailability."
                    )
            except TimeoutError as e:
                last_error_reason = f"Timeout: {e!s}"
                logger.warning(
                    f"{section_name} section timed out on attempt {attempt + 1}: {e}. "
                    f"SOLUTION: Increase 'llm_timeout' in config/workflow.yaml under writing section. "
                    f"Current timeout may be too short for {paper_count} papers with model {model_name}."
                )
            except Exception as e:
                last_error_reason = f"{type(e).__name__}: {e!s}"
                logger.warning(
                    f"{section_name} section failed on attempt {attempt + 1}: {e}. "
                    f"Error type: {type(e).__name__}. "
                    f"Context: model={model_name}, papers={paper_count}"
                )

        # All retries failed, provide actionable error message
        actionable_suggestions = [
            f"1. Check API key and quota for {model_name}",
            "2. Increase llm_timeout in config/workflow.yaml",
            f"3. Reduce number of papers (currently {paper_count})",
            "4. Simplify extraction criteria",
            "5. Try a different LLM model (e.g., switch between gemini-2.5-pro and gemini-2.5-flash)",
            "6. Check network connectivity and API status",
        ]

        error_msg = (
            f"All {max_attempts} attempts failed for {section_name} section. "
            f"Last error: {last_error_reason}\n\n"
            f"Actionable suggestions:\n" + "\n".join(actionable_suggestions)
        )

        logger.error(error_msg)
        raise RuntimeError(
            f"Failed to write {section_name} section after {max_attempts} attempts: {last_error_reason}"
        )

    def _write_article(self) -> Dict[str, str]:
        """Write all article sections with checkpointing and retry support."""
        # Load existing sections from checkpoint if resuming
        sections = self._load_existing_sections()
        completed_sections = list(sections.keys())

        console.print()
        logger.info("Starting article writing phase...")
        if completed_sections:
            logger.info(
                f"Resuming from checkpoint - already completed: {', '.join(completed_sections)}"
            )
        else:
            logger.info(
                "This will generate Introduction, Methods, Results, and Discussion sections."
            )
            logger.info("Each section requires an LLM call and may take some time.")
        console.print()

        # Build citation registry from final papers
        self._ensure_citation_registry()
        citation_catalog = self.citation_registry.catalog_for_prompt()
        logger.info(f"Built citation registry with {len(self.citation_registry.citekey_to_paper)} papers")

        # Validate checkpointed sections against current citation registry.
        # If citations are invalid (legacy/hallucinated keys), force regeneration.
        removed_sections = []
        for section_name, section_text in list(sections.items()):
            is_valid = self._validate_section_citations(
                section_name, section_text, fail_on_invalid=True
            )
            if not is_valid:
                sections.pop(section_name, None)
                removed_sections.append(section_name)
        if removed_sections:
            logger.warning(
                "Removed checkpointed sections with invalid citations; will regenerate: "
                + ", ".join(sorted(removed_sections))
            )
            completed_sections = list(sections.keys())

        # Extract style patterns before writing
        self._extract_style_patterns()

        # Get topic context for writing agents
        writing_context = self.topic_context.get_for_agent("introduction_writer")

        # Humanization disabled - writing module removed
        humanization_enabled = False

        # Introduction
        if "introduction" not in sections:
            from ..utils.rich_utils import print_section_complete_panel, print_section_start_panel

            # Show START panel
            print_section_start_panel(
                section_name="Introduction",
                section_number=1,
                total_sections=5,
                model=self.intro_writer.llm_model,
                status="Starting...",
            )

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

            intro, duration, word_count = self._write_section_with_retry(
                "introduction",
                self.intro_writer.write,
                research_question,
                justification,
                topic_context=writing_context,
                style_patterns=self.style_patterns,
                citation_catalog=citation_catalog,
            )

            # Humanize if enabled
            humanized = False
            if humanization_enabled and intro:
                logger.debug("Humanizing introduction section...")
                intro = self.humanization_agent.humanize_section(
                    intro,
                    "introduction",
                    style_patterns=self.style_patterns,
                    context={
                        "domain": self.topic_context.domain,
                        "topic": self.topic_context.topic,
                    },
                )
                humanized = True

            sections["introduction"] = intro
            
            # Validate citations in introduction
            if not self._validate_section_citations(
                "introduction", intro, fail_on_invalid=True
            ):
                raise RuntimeError("Generated introduction contains invalid citations")
            
            checkpoint_saved = self._save_section_checkpoint("introduction", sections)

            # Show COMPLETE panel
            print_section_complete_panel(
                section_name="Introduction",
                word_count=word_count,
                duration=duration,
                humanized=humanized,
                checkpoint_saved=checkpoint_saved,
            )
        else:
            from ..utils.rich_utils import print_panel

            logger.info("Introduction section already exists in checkpoint, skipping")
            print_panel(
                content="Section already completed in previous run",
                title="Introduction (Skipped)",
                border_style="yellow",
            )

        # Methods
        if "methods" not in sections:
            from ..utils.rich_utils import print_section_complete_panel, print_section_start_panel

            # Show START panel
            print_section_start_panel(
                section_name="Methods",
                section_number=2,
                total_sections=5,
                model=self.methods_writer.llm_model,
                status="Starting...",
            )

            # Ensure search_strategy exists (rebuild if None, e.g., when resuming from checkpoint)
            if self.search_strategy is None:
                logger.warning("search_strategy is None, rebuilding it for article writing")
                try:
                    self._build_search_strategy()
                    if self.search_strategy is None:
                        raise RuntimeError(
                            "Failed to build search strategy - search_strategy is still None after _build_search_strategy()"
                        )
                except Exception as e:
                    logger.error(f"Failed to build search strategy: {e}", exc_info=True)
                    raise RuntimeError(
                        f"Cannot write Methods section without search strategy: {e}"
                    ) from e

            search_strategy_desc = self.search_strategy.get_strategy_description()
            databases = self.config["workflow"]["databases"]
            inclusion_criteria = [
                self.topic_context.inject_into_prompt(c)
                for c in self.config.get("topic", {}).get("inclusion", [])
            ]
            exclusion_criteria = [
                self.topic_context.inject_into_prompt(c)
                for c in self.config.get("topic", {}).get("exclusion", [])
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
                logger.error(
                    "search_strategy is None when getting database queries - this should not happen"
                )
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

            methods, duration, word_count = self._write_section_with_retry(
                "methods",
                self.methods_writer.write,
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
                citation_catalog=citation_catalog,
                automation_details=automation_details,
                style_patterns=self.style_patterns,
                output_dir=str(self.output_dir),
            )

            # Humanize if enabled
            humanized = False
            if humanization_enabled and methods:
                logger.debug("Humanizing methods section...")
                methods = self.humanization_agent.humanize_section(
                    methods,
                    "methods",
                    style_patterns=self.style_patterns,
                    context={
                        "domain": self.topic_context.domain,
                        "topic": self.topic_context.topic,
                    },
                )
                humanized = True

            sections["methods"] = methods
            
            # Validate citations in methods
            if not self._validate_section_citations(
                "methods", methods, fail_on_invalid=True
            ):
                raise RuntimeError("Generated methods contains invalid citations")
            
            checkpoint_saved = self._save_section_checkpoint("methods", sections)

            # Show COMPLETE panel
            print_section_complete_panel(
                section_name="Methods",
                word_count=word_count,
                duration=duration,
                humanized=humanized,
                checkpoint_saved=checkpoint_saved,
            )
        else:
            from ..utils.rich_utils import print_panel

            logger.info("Methods section already exists in checkpoint, skipping")
            print_panel(
                content="Section already completed in previous run",
                title="Methods (Skipped)",
                border_style="yellow",
            )

        # Results
        if "results" not in sections:
            from ..utils.rich_utils import print_section_complete_panel, print_section_start_panel

            # Show START panel
            print_section_start_panel(
                section_name="Results",
                section_number=3,
                total_sections=5,
                model=self.results_writer.llm_model,
                status="Starting...",
            )

            # Validation checks before writing results section
            if not self.extracted_data:
                error_msg = (
                    "Cannot write results section: No extracted data available. "
                    "Ensure data extraction phase completed successfully."
                )
                logger.error(error_msg)
                raise RuntimeError(error_msg)

            key_findings = []
            for data in self.extracted_data:
                key_findings.extend(data.key_findings[:2])  # Top 2 findings per study

            # Warn if key findings are insufficient
            if not key_findings:
                logger.warning(
                    f"No key findings found in {len(self.extracted_data)} extracted papers. "
                    f"Results section may be limited. This could indicate: "
                    f"(1) papers lack findings data, (2) extraction failed, or "
                    f"(3) papers are not suitable for systematic review."
                )
            elif len(key_findings) < len(self.extracted_data) * 0.3:
                # Less than 30% of expected findings (assuming ~1-2 per paper)
                logger.warning(
                    f"Low number of key findings: {len(key_findings)} findings from {len(self.extracted_data)} papers. "
                    f"Results section may lack sufficient detail."
                )

            logger.info(
                f"Writing results section with {len(self.extracted_data)} papers, "
                f"{len(key_findings)} key findings"
            )

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
            results, duration, word_count = self._write_section_with_retry(
                "results",
                self.results_writer.write,
                self.extracted_data,
                self.prisma_counter.get_counts(),
                key_findings[:10],  # Top 10 findings
                topic_context=writing_context,
                risk_of_bias_summary=risk_of_bias_summary,
                risk_of_bias_table=risk_of_bias_table,
                grade_assessments=grade_assessments,
                grade_table=grade_table,
                style_patterns=self.style_patterns,
                output_dir=str(self.output_dir),
                citation_catalog=citation_catalog,
            )

            # Humanize if enabled
            humanized = False
            if humanization_enabled and results:
                logger.debug("Humanizing results section...")
                results = self.humanization_agent.humanize_section(
                    results,
                    "results",
                    style_patterns=self.style_patterns,
                    context={
                        "domain": self.topic_context.domain,
                        "topic": self.topic_context.topic,
                    },
                )
                humanized = True

            sections["results"] = results
            
            # Validate citations in results
            if not self._validate_section_citations(
                "results", results, fail_on_invalid=True
            ):
                raise RuntimeError("Generated results contains invalid citations")
            
            checkpoint_saved = self._save_section_checkpoint("results", sections)

            # Show COMPLETE panel
            print_section_complete_panel(
                section_name="Results",
                word_count=word_count,
                duration=duration,
                humanized=humanized,
                checkpoint_saved=checkpoint_saved,
            )
        else:
            from ..utils.rich_utils import print_panel

            logger.info("Results section already exists in checkpoint, skipping")
            print_panel(
                content="Section already completed in previous run",
                title="Results (Skipped)",
                border_style="yellow",
            )

        # Collect generated files from results_writer (e.g., mermaid diagrams)
        generated_files = {}
        if hasattr(self.results_writer, "get_generated_files"):
            files = self.results_writer.get_generated_files()
            for file_path in files:
                # Extract diagram name from path
                file_name = Path(file_path).stem
                # Make path relative to output_dir for report
                try:
                    rel_path = Path(file_path).relative_to(self.output_dir)
                    generated_files[file_name] = str(rel_path)
                    logger.info(f"Collected generated file: {file_name} -> {rel_path}")
                except ValueError:
                    # File is not relative to output_dir, use absolute path
                    generated_files[file_name] = file_path
                    logger.info(f"Collected generated file: {file_name} -> {file_path}")

        # Store generated files for later use
        self._article_generated_files = generated_files

        # Discussion
        if "discussion" not in sections:
            from ..utils.rich_utils import print_section_complete_panel, print_section_start_panel

            # Show START panel
            print_section_start_panel(
                section_name="Discussion",
                section_number=4,
                total_sections=5,
                model=self.discussion_writer.llm_model,
                status="Starting...",
            )

            key_findings = []
            for data in self.extracted_data:
                key_findings.extend(data.key_findings[:2])  # Top 2 findings per study

            research_question = self.topic_context.research_question or self.topic_context.topic

            self.handoff_protocol.create_handoff(
                from_agent="results_writer",
                to_agent="discussion_writer",
                stage="writing",
                topic_context=self.topic_context,
                data={"key_findings_count": len(key_findings[:10])},
                metadata={"section": "discussion"},
            )

            discussion, duration, word_count = self._write_section_with_retry(
                "discussion",
                self.discussion_writer.write,
                research_question,
                key_findings[:10],
                self.extracted_data,
                [
                    "Limited to English-language publications",
                    "Potential publication bias",
                ],
                ["Implications for practice", "Future research directions"],
                topic_context=writing_context,
                style_patterns=self.style_patterns,
                citation_catalog=citation_catalog,
            )

            # Humanize if enabled
            humanized = False
            if humanization_enabled and discussion:
                logger.debug("Humanizing discussion section...")
                discussion = self.humanization_agent.humanize_section(
                    discussion,
                    "discussion",
                    style_patterns=self.style_patterns,
                    context={
                        "domain": self.topic_context.domain,
                        "topic": self.topic_context.topic,
                    },
                )
                humanized = True

            sections["discussion"] = discussion
            
            # Validate citations in discussion
            if not self._validate_section_citations(
                "discussion", discussion, fail_on_invalid=True
            ):
                raise RuntimeError("Generated discussion contains invalid citations")
            
            checkpoint_saved = self._save_section_checkpoint("discussion", sections)

            # Show COMPLETE panel
            print_section_complete_panel(
                section_name="Discussion",
                word_count=word_count,
                duration=duration,
                humanized=humanized,
                checkpoint_saved=checkpoint_saved,
            )
        else:
            from ..utils.rich_utils import print_panel

            logger.info("Discussion section already exists in checkpoint, skipping")
            print_panel(
                content="Section already completed in previous run",
                title="Discussion (Skipped)",
                border_style="yellow",
            )

        # Abstract (generate after all sections are written)
        if "abstract" not in sections:
            from ..utils.rich_utils import print_section_complete_panel, print_section_start_panel

            # Show START panel
            print_section_start_panel(
                section_name="Abstract",
                section_number=5,
                total_sections=5,
                model=self.abstract_generator.llm_model,
                status="Starting...",
            )

            research_question = self.topic_context.research_question or self.topic_context.topic
            abstract, duration, word_count = self._write_section_with_retry(
                "abstract",
                self.abstract_generator.generate,
                research_question,
                self.final_papers,
                sections,
                style_patterns=self.style_patterns,
            )

            # Humanize if enabled
            humanized = False
            if humanization_enabled and abstract:
                logger.debug("Humanizing abstract...")
                abstract = self.humanization_agent.humanize_section(
                    abstract,
                    "abstract",
                    style_patterns=self.style_patterns,
                    context={
                        "domain": self.topic_context.domain,
                        "topic": self.topic_context.topic,
                    },
                )
                humanized = True

            sections["abstract"] = abstract
            checkpoint_saved = self._save_section_checkpoint("abstract", sections)

            # Show COMPLETE panel
            print_section_complete_panel(
                section_name="Abstract",
                word_count=word_count,
                duration=duration,
                humanized=humanized,
                checkpoint_saved=checkpoint_saved,
            )
        else:
            from ..utils.rich_utils import print_panel

            logger.info("Abstract already exists in checkpoint, skipping")
            print_panel(
                content="Section already completed in previous run",
                title="Abstract (Skipped)",
                border_style="yellow",
            )
        console.print(
            "[bold green]Article writing phase complete - all 5 sections generated[/bold green]"
        )
        console.print()

        # Log generated files summary
        if generated_files:
            console.print(f"[cyan]Generated {len(generated_files)} file(s) during writing:[/cyan]")
            for name, path in generated_files.items():
                console.print(f"  - {name}: {path}")
        console.print()

        return sections

    def _prepare_figure_paths(self, prisma_path: str, viz_paths: Dict[str, str]) -> Dict[str, str]:
        """
        Organize figures into figures/ directory and return path mapping.

        Args:
            prisma_path: Path to PRISMA diagram
            viz_paths: Dictionary of visualization paths

        Returns:
            Dictionary mapping figure names to relative paths (figures/figure_N.ext)
        """
        import shutil

        # Create figures directory in output_dir
        figures_dir = self.output_dir / "figures"
        figures_dir.mkdir(exist_ok=True)

        # Collect all figure paths
        figures = []
        figure_names = []

        # Add PRISMA diagram first (will be figure_1)
        if prisma_path:
            prisma_path_obj = Path(prisma_path)
            if prisma_path_obj.exists():
                figures.append(prisma_path_obj)
                figure_names.append("prisma_diagram")

        # Add visualizations
        if viz_paths:
            for name, path in viz_paths.items():
                # Skip HTML files (network graphs)
                if not str(path).endswith(".html"):
                    path_obj = Path(path)
                    if path_obj.exists():
                        figures.append(path_obj)
                        figure_names.append(name)

        # Copy figures and build path mapping
        path_mapping = {}
        for i, (fig_path, fig_name) in enumerate(zip(figures, figure_names), 1):
            # Use figure_N naming convention
            target = figures_dir / f"figure_{i}{fig_path.suffix}"
            shutil.copy2(fig_path, target)
            logger.debug(f"Copied figure to: {target}")

            # Store mapping with relative path from output_dir
            relative_path = f"figures/figure_{i}{fig_path.suffix}"
            path_mapping[fig_name] = relative_path

        return path_mapping

    def _generate_final_report(
        self,
        article_sections: Dict[str, str],
        prisma_path: str,
        viz_paths: Dict[str, str],
    ) -> str:
        """Generate final markdown report."""
        import re
        self._ensure_citation_registry()

        # Prepare figures and get path mapping
        figure_paths = self._prepare_figure_paths(prisma_path, viz_paths)

        # Use citation registry to convert citekeys to numbers
        all_text = "\n\n".join([
            article_sections.get("abstract", ""),
            article_sections.get("introduction", ""),
            article_sections.get("methods", ""),
            article_sections.get("results", ""),
            article_sections.get("discussion", "")
        ])
        
        # Get transformed text and used citekeys from registry
        _, used_citekeys = self.citation_registry.replace_citekeys_with_numbers(all_text)
        logger.info(f"Found {len(used_citekeys)} unique citations in article")

        # Generate manuscript.md with correct figure paths
        manuscript_path = self.output_dir / "manuscript.md"

        # Ensure output directory exists
        manuscript_path.parent.mkdir(parents=True, exist_ok=True)

        with open(manuscript_path, "w") as f:
            # Generate topic-specific title
            topic = self.topic_context.topic or "Systematic Review"
            title = f"{topic}: A Systematic Review"
            f.write(f"# {title}\n\n")

            # Abstract
            abstract = article_sections.get("abstract", "")
            if abstract:
                f.write("## Abstract\n\n")
                f.write("**Systematic Review**\n\n")
                # Replace citations in abstract
                abstract_with_numbers, _ = self.citation_registry.replace_citekeys_with_numbers(abstract)
                f.write(abstract_with_numbers)
                f.write("\n\n---\n\n")

            # Keywords - aggregate from topic context and papers
            keywords = (
                self.topic_context.keywords if hasattr(self.topic_context, "keywords") else []
            )

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
            list(set(keywords + paper_keywords))

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

            # Introduction
            intro_text = article_sections.get("introduction", "")
            intro_text_with_numbers, _ = self.citation_registry.replace_citekeys_with_numbers(intro_text)
            f.write("## Introduction\n\n")
            f.write(intro_text_with_numbers)
            f.write("\n\n---\n\n")

            # Methods
            methods_text = article_sections.get("methods", "")
            methods_text_with_numbers, _ = self.citation_registry.replace_citekeys_with_numbers(methods_text)
            f.write("## Methods\n\n")
            f.write(methods_text_with_numbers)
            f.write("\n\n---\n\n")

            # Results
            results_text = article_sections.get("results", "")

            # Insert PRISMA diagram into Results section after Study Selection subsection
            # Use the figure path from the mapping (figures/figure_1.xxx)
            prisma_fig_path = figure_paths.get("prisma_diagram", "")
            if prisma_fig_path:
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

                    # Insert PRISMA diagram with correct figure path
                    prisma_section = f"\n\n![PRISMA Diagram]({prisma_fig_path})\n\n"
                    prisma_section += "**Figure 1:** PRISMA 2020 flow diagram showing the study selection process.\n\n"
                    results_text = (
                        results_text[:insertion_pos] + prisma_section + results_text[insertion_pos:]
                    )
                else:
                    # If Study Selection subsection not found, insert PRISMA diagram at the beginning
                    prisma_section = f"![PRISMA Diagram]({prisma_fig_path})\n\n"
                    prisma_section += "**Figure 1:** PRISMA 2020 flow diagram showing the study selection process.\n\n\n"
                    results_text = prisma_section + results_text

            # Insert visualizations into Results section after Synthesis subsection
            figure_num = 2  # PRISMA diagram is Figure 1
            if figure_paths:
                # Build visualizations section using figure_paths mapping
                viz_section = "\n\n"
                for name, fig_path in figure_paths.items():
                    # Skip PRISMA diagram (already handled)
                    if name == "prisma_diagram":
                        continue

                    viz_name = name.replace("_", " ").title()
                    # Use the correct figure path
                    caption = f"**Figure {figure_num}:** {viz_name} showing bibliometric analysis of included studies.\n\n"
                    viz_section += f"![{name}]({fig_path})\n\n"
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
                    "#### Synthesis of Results",
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

                    results_text = (
                        results_text[:insertion_pos] + viz_section + results_text[insertion_pos:]
                    )
                else:
                    # No synthesis subsection found, insert before separator or at end
                    # Check for separator that marks end of Results section
                    separator_pos = results_text.find("\n---\n")
                    if separator_pos != -1:
                        # Insert before separator to keep visualizations in Results section
                        insertion_pos = separator_pos
                        results_text = (
                            results_text[:insertion_pos]
                            + viz_section
                            + results_text[insertion_pos:]
                        )
                    else:
                        # No separator found, append at end
                        results_text = results_text + viz_section

            # Write the modified results text (with citations replaced)
            results_text_with_numbers, _ = self.citation_registry.replace_citekeys_with_numbers(results_text)
            f.write("## Results\n\n")
            f.write(results_text_with_numbers)
            f.write("\n\n---\n\n")

            # Discussion
            discussion_text = article_sections.get("discussion", "")
            discussion_text_with_numbers, _ = self.citation_registry.replace_citekeys_with_numbers(discussion_text)
            f.write("## Discussion\n\n")
            f.write(discussion_text_with_numbers)
            f.write("\n\n---\n\n")

            # References section (before Summary)
            references_section = self.citation_registry.references_markdown(used_citekeys)
            f.write(references_section)
            f.write("\n---\n\n")

            # Registration (PRISMA 2020: Other Information)
            protocol_info = self.config.get("topic", {}).get("protocol", {})
            f.write("## Registration\n\n")
            if protocol_info.get("registered", False):
                registry = protocol_info.get("registry", "PROSPERO")
                reg_number = protocol_info.get("registration_number", "")
                reg_url = protocol_info.get("url", "")
                if reg_number:
                    f.write(
                        f"This systematic review was registered with {registry} (registration number: {reg_number})."
                    )
                    if reg_url:
                        f.write(f" The protocol can be accessed at: {reg_url}")
                    f.write("\n\n")
                else:
                    f.write(f"This systematic review was registered with {registry}.\n\n")
            else:
                f.write("This systematic review was not registered.\n\n")
            f.write("---\n\n")

            # Funding Statement (PRISMA 2020: Other Information)
            funding_config = self.config.get("topic", {}).get("funding", {})
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
            coi_config = self.config.get("topic", {}).get("conflicts_of_interest", {})
            f.write("## Conflicts of Interest\n\n")
            coi_statement = coi_config.get(
                "statement", "The authors declare no conflicts of interest."
            )
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

        # Copy manuscript.md to final_report.md for backward compatibility
        import shutil

        final_report_path = self.output_dir / "final_report.md"
        shutil.copy2(manuscript_path, final_report_path)
        logger.info(
            "Generated manuscript.md and copied to final_report.md for backward compatibility"
        )

        return str(manuscript_path)

    def _export_report(
        self,
        article_sections: Dict[str, str],
        prisma_path: str,
        viz_paths: Dict[str, str],
    ) -> Dict[str, str]:
        """Export report to BibTeX and RIS formats using citation registry."""
        self._ensure_citation_registry()
        export_paths = {}
        
        # Get export configuration
        export_config = self.config.get("output", {}).get("formats", [])
        
        if not export_config:
            logger.info("No export formats configured")
            return export_paths
        
        # Get used citations from all sections
        all_text = "\n\n".join([
            article_sections.get("abstract", ""),
            article_sections.get("introduction", ""),
            article_sections.get("methods", ""),
            article_sections.get("results", ""),
            article_sections.get("discussion", "")
        ])
        
        _, used_citekeys = self.citation_registry.replace_citekeys_with_numbers(all_text)
        
        # Export to BibTeX if requested
        if "bibtex" in export_config or "bib" in export_config:
            bibtex_path = self.output_dir / "references.bib"
            bibtex_content = self.citation_registry.to_bibtex(used_citekeys)
            with open(bibtex_path, 'w') as f:
                f.write(bibtex_content)
            export_paths["bibtex"] = str(bibtex_path)
            logger.info(f"BibTeX file generated: {bibtex_path}")
        
        # Export to RIS if requested
        if "ris" in export_config:
            ris_path = self.output_dir / "references.ris"
            ris_content = self.citation_registry.to_ris(used_citekeys)
            with open(ris_path, 'w') as f:
                f.write(ris_content)
            export_paths["ris"] = str(ris_path)
            logger.info(f"RIS file generated: {ris_path}")
        
        # LaTeX and Word export not currently supported
        if "latex" in export_config:
            logger.warning("LaTeX export not currently supported (export modules removed)")
        if "word" in export_config or "docx" in export_config:
            logger.warning("Word export not currently supported (export modules removed)")
        
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
                f.write(
                    "This document contains the complete search strategies used for all databases.\n\n"
                )
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
        """Generate data extraction form templates - export modules removed."""
        logger.warning("Extraction form generation is no longer available")
        return None

    def _generate_prisma_checklist(self, report_path: str) -> Optional[str]:
        """Generate PRISMA 2020 checklist file - PRISMA modules removed."""
        logger.warning("PRISMA checklist generation is no longer available")
        return None

    def _export_manubot_structure(self, article_sections: Dict[str, str]) -> Optional[str]:
        """
        Export article sections to Manubot structure.

        Args:
            article_sections: Dictionary with section names and content

        Returns:
            None - export functionality removed
        """
        logger.warning("Manubot export functionality is no longer available")
        return None

    def _generate_submission_package(
        self,
        workflow_outputs: Dict[str, Any],
        article_sections: Dict[str, str],
        report_path: str,
    ) -> Optional[str]:
        """
        Generate submission package for journal.

        Args:
            workflow_outputs: Dictionary with workflow output paths
            article_sections: Dictionary with article sections
            report_path: Path to final report markdown

        Returns:
            Path to submission package directory, or None if disabled
        """
        from pathlib import Path

        submission_config = self.config.get("submission", {})
        if not submission_config.get("enabled", False):
            return None

        try:
            try:
                from ..export.submission_package import SubmissionPackageBuilder
            except ModuleNotFoundError:
                logger.warning(
                    "Submission package module is unavailable (src.export removed); skipping submission package generation"
                )
                return None

            # Get journal
            journal = submission_config.get("default_journal", "ieee")

            # Get manuscript path - look for manuscript.md first, then fallback to final_report.md
            if report_path is None:
                manuscript_path = self.output_dir / "manuscript.md"
            else:
                manuscript_path = Path(report_path)

            # Try manuscript.md first, then fallback to final_report.md for backward compatibility
            if not manuscript_path.exists():
                manuscript_path = self.output_dir / "manuscript.md"

            if not manuscript_path.exists():
                # Fallback to final_report.md for backward compatibility
                manuscript_path = self.output_dir / "final_report.md"

            if not manuscript_path.exists():
                logger.warning(
                    "Manuscript file not found for submission package (tried manuscript.md and final_report.md)"
                )
                return None

            # Create builder
            builder = SubmissionPackageBuilder(self.output_dir)

            # Build package
            package_dir = builder.build_package(
                workflow_outputs,
                journal,
                manuscript_path,
                generate_pdf=submission_config.get("generate_pdf", True),
                generate_docx=submission_config.get("generate_docx", True),
                generate_html=submission_config.get("generate_html", True),
                include_supplementary=submission_config.get("include_supplementary", True),
            )

            logger.info(f"Submission package generated: {package_dir}")
            return str(package_dir)

        except Exception as e:
            logger.error(f"Failed to generate submission package: {e}", exc_info=True)
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
        """Generate unique workflow ID with timestamp-first naming for chronological sorting."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        topic_slug = self.topic_context.topic.lower().replace(" ", "_")[:30]
        return f"{timestamp}_workflow_{topic_slug}"

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
                "title_abstract_results": serializer.serialize_screening_results(
                    self.title_abstract_results
                ),
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
            # Load all section checkpoints from individual files
            sections_dict = {}
            for checkpoint_file in self.checkpoint_dir.glob("article_writing_*_state.json"):
                # Extract section name from filename: article_writing_introduction_state.json -> introduction
                section_name = checkpoint_file.stem.replace("article_writing_", "").replace(
                    "_state", ""
                )
                try:
                    import json

                    with open(checkpoint_file) as f:
                        checkpoint_data = json.load(f)
                    # Validate workflow_id matches
                    if checkpoint_data.get("workflow_id") == self.workflow_id:
                        if (
                            "data" in checkpoint_data
                            and "section_content" in checkpoint_data["data"]
                        ):
                            sections_dict[section_name] = checkpoint_data["data"]["section_content"]
                except Exception as e:
                    logger.warning(
                        f"Failed to load section checkpoint {checkpoint_file.name} for serialization: {e}"
                    )

            data = {
                "style_patterns": self.style_patterns,
                "article_sections": sections_dict,
                "completed_sections": list(sections_dict.keys()),
            }
        elif phase_name == "manubot_export":
            data = {
                "manubot_export_path": str(getattr(self, "_manubot_export_path", "")),
                "article_sections": self._get_article_sections_dict(),
            }
        elif phase_name == "submission_package":
            data = {
                "submission_package_path": str(getattr(self, "_submission_package_path", "")),
                "article_sections": self._get_article_sections_dict(),
            }

        return data

    def _get_article_sections_dict(self) -> Dict[str, str]:
        """Get article sections as dictionary."""
        # This will be populated after writing, stored in results
        # For now, return empty dict - will be set by _write_article
        return getattr(self, "_article_sections", {})

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

        # Load style patterns
        if "style_patterns" in state.get("data", {}):
            self.style_patterns = state["data"]["style_patterns"]

        # Load article sections
        # Try loading from state first
        article_sections = {}
        if "article_sections" in state.get("data", {}):
            article_sections = state["data"]["article_sections"]

        # Also load from individual section checkpoint files (new approach)
        section_checkpoints = self._load_existing_sections()
        if section_checkpoints:
            # Merge with any sections from state (section files take precedence)
            article_sections.update(section_checkpoints)

        if article_sections:
            self._article_sections = article_sections
            logger.info(
                f"Loaded {len(article_sections)} article sections: {', '.join(article_sections.keys())}"
            )

        # Load PRISMA counts
        if "prisma_counts" in state:
            try:
                counts = state["prisma_counts"]
                # Restore counts using individual setters
                if "found" in counts:
                    db_breakdown = state.get("database_breakdown", {})
                    self.prisma_counter.set_found(
                        counts["found"], db_breakdown if db_breakdown else None
                    )
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
                    self.prisma_counter.set_full_text_not_retrieved(
                        counts["full_text_not_retrieved"]
                    )
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
        checkpoint_data = manager.checkpoint_manager.load_phase(str(checkpoint_file))
        if checkpoint_data is None:
            checkpoint_data = {}

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
    ) -> Dict[str, Any]:
        """
        Execute workflow from specific stage.

        Args:
            start_stage: Stage to start from (short name or full phase name)

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
