"""
Search Phase

Handles multi-database searching and result aggregation.
"""

from pathlib import Path
from typing import List

from ...search.connectors.base import Paper
from ...utils.logging_config import get_logger
from . import PhaseResult, PhaseStatus, WorkflowPhase

logger = get_logger(__name__)


class SearchPhase(WorkflowPhase):
    """
    Phase for searching multiple databases and aggregating results.
    
    Responsibilities:
    - Execute search strategy across multiple databases
    - Aggregate and deduplicate results
    - Track PRISMA metrics for papers found
    """
    
    @property
    def name(self) -> str:
        return "search_databases"
    
    @property
    def description(self) -> str:
        return "Search multiple databases for papers"
    
    def execute(self, **kwargs) -> PhaseResult:
        """
        Execute the search phase.
        
        Returns:
            PhaseResult with all papers found
        """
        self.log_start()
        
        try:
            # Execute database search using existing manager method
            search_results = self.manager._search_databases()
            self.manager.all_papers = search_results
            
            # Update PRISMA counter
            self.manager.prisma_counter.set_found(
                len(self.manager.all_papers),
                self.manager._get_database_breakdown()
            )
            
            # Log summary
            num_papers = len(self.manager.all_papers)
            num_databases = len(self.manager.config['workflow']['databases'])
            message = f"Found {num_papers} papers across {num_databases} databases"
            logger.info(message)
            
            # Show database breakdown if metrics enabled
            if self.manager.debug_config.show_metrics:
                db_breakdown = self.manager._get_database_breakdown()
                for db, count in db_breakdown.items():
                    logger.info(f"  - {db}: {count} papers")
            
            # List all papers found
            self._log_papers_found(self.manager.all_papers)
            
            result = self._create_result(
                status=PhaseStatus.COMPLETED,
                data=search_results,
                message=message,
                papers_found=num_papers,
                databases_searched=num_databases
            )
            
            self.log_completion(result)
            return result
            
        except Exception as e:
            logger.error(f"Search phase failed: {str(e)}", exc_info=True)
            result = self._create_result(
                status=PhaseStatus.FAILED,
                message=f"Search failed: {str(e)}",
                error=e
            )
            return result
    
    def _log_papers_found(self, papers: List[Paper]):
        """Log all papers found with details"""
        logger.info("=" * 60)
        logger.info("ALL PAPERS FOUND:")
        logger.info("=" * 60)
        
        for i, paper in enumerate(papers, 1):
            title = paper.title if paper.title else "[No title]"
            authors_str = ", ".join(paper.authors) if paper.authors else "[No authors]"
            database = paper.database if paper.database else "Unknown"
            year = f" ({paper.year})" if paper.year else ""
            doi_str = f" [DOI: {paper.doi}]" if paper.doi else ""
            
            logger.info(f"\n[{i}] {title}{year}")
            logger.info(f"    Authors: {authors_str}")
            logger.info(f"    Database: {database}{doi_str}")
        
        logger.info("=" * 60)


class DeduplicationPhase(WorkflowPhase):
    """
    Phase for deduplicating papers.
    
    Responsibilities:
    - Identify and remove duplicate papers
    - Track PRISMA metrics for deduplication
    """
    
    @property
    def name(self) -> str:
        return "deduplication"
    
    @property
    def description(self) -> str:
        return "Remove duplicate papers"
    
    def execute(self, **kwargs) -> PhaseResult:
        """
        Execute the deduplication phase.
        
        Returns:
            PhaseResult with unique papers
        """
        self.log_start()
        
        try:
            # Deduplicate using existing deduplicator
            dedup_result = self.manager.deduplicator.deduplicate_papers(
                self.manager.all_papers
            )
            
            self.manager.unique_papers = dedup_result.unique_papers
            self.manager.prisma_counter.set_no_dupes(len(self.manager.unique_papers))
            
            duplicates_removed = dedup_result.duplicates_removed
            unique_count = len(self.manager.unique_papers)
            
            message = f"Removed {duplicates_removed} duplicates, {unique_count} unique papers remain"
            logger.info(message)
            
            result = self._create_result(
                status=PhaseStatus.COMPLETED,
                data=dedup_result.unique_papers,
                message=message,
                duplicates_removed=duplicates_removed,
                unique_papers=unique_count
            )
            
            self.log_completion(result)
            return result
            
        except Exception as e:
            logger.error(f"Deduplication phase failed: {str(e)}", exc_info=True)
            result = self._create_result(
                status=PhaseStatus.FAILED,
                message=f"Deduplication failed: {str(e)}",
                error=e
            )
            return result
