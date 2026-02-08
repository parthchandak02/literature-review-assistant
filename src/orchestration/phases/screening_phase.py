"""
Screening Phase

Handles title/abstract and full-text screening of papers.
"""

from ...utils.logging_config import get_logger
from ...utils.screening_validator import ScreeningStage
from . import PhaseResult, PhaseStatus, WorkflowPhase

logger = get_logger(__name__)


class TitleAbstractScreeningPhase(WorkflowPhase):
    """
    Phase for screening papers by title and abstract.
    
    Responsibilities:
    - Screen papers using title/abstract criteria
    - Track PRISMA metrics for screening
    - Validate screening results
    """
    
    @property
    def name(self) -> str:
        return "title_abstract_screening"
    
    @property
    def description(self) -> str:
        return "Screen papers by title and abstract"
    
    def execute(self, **kwargs) -> PhaseResult:
        """
        Execute the title/abstract screening phase.
        
        Returns:
            PhaseResult with screened papers
        """
        self.log_start()
        
        try:
            # Execute screening using existing manager method
            self.manager._screen_title_abstract()
            
            # Update PRISMA counter
            self.manager.prisma_counter.set_screened(len(self.manager.screened_papers))
            excluded_at_screening = len(self.manager.unique_papers) - len(self.manager.screened_papers)
            self.manager.prisma_counter.set_screen_exclusions(excluded_at_screening)
            
            message = (
                f"Screened {len(self.manager.unique_papers)} papers, "
                f"{len(self.manager.screened_papers)} included, "
                f"{excluded_at_screening} excluded"
            )
            logger.info(message)
            
            # Calculate and validate screening statistics
            if self.manager.title_abstract_results:
                self.manager.screening_validator.calculate_statistics(
                    self.manager.unique_papers,
                    self.manager.title_abstract_results,
                    ScreeningStage.TITLE_ABSTRACT
                )
                self.manager.screening_validator.log_statistics(ScreeningStage.TITLE_ABSTRACT)
            
            result = self._create_result(
                status=PhaseStatus.COMPLETED,
                data=self.manager.screened_papers,
                message=message,
                papers_screened=len(self.manager.unique_papers),
                papers_included=len(self.manager.screened_papers),
                papers_excluded=excluded_at_screening
            )
            
            self.log_completion(result)
            return result
            
        except Exception as e:
            logger.error(f"Title/abstract screening failed: {str(e)}", exc_info=True)
            result = self._create_result(
                status=PhaseStatus.FAILED,
                message=f"Title/abstract screening failed: {str(e)}",
                error=e
            )
            return result


class FullTextScreeningPhase(WorkflowPhase):
    """
    Phase for screening papers by full text.
    
    Responsibilities:
    - Screen papers using full-text criteria
    - Track PDF retrieval and availability
    - Track PRISMA metrics for full-text assessment
    """
    
    @property
    def name(self) -> str:
        return "fulltext_screening"
    
    @property
    def description(self) -> str:
        return "Screen papers by full-text"
    
    def execute(self, **kwargs) -> PhaseResult:
        """
        Execute the full-text screening phase.
        
        Returns:
            PhaseResult with eligible papers
        """
        self.log_start()
        
        try:
            # Execute full-text screening using existing manager method
            self.manager._screen_fulltext()
            
            # PRISMA tracking
            sought_count = len(self.manager.screened_papers)
            self.manager.prisma_counter.set_full_text_sought(sought_count)
            
            not_retrieved_count = self.manager.fulltext_unavailable_count
            self.manager.prisma_counter.set_full_text_not_retrieved(not_retrieved_count)
            
            # assessed = sought - not_retrieved
            assessed_count = sought_count - not_retrieved_count
            self.manager.prisma_counter.set_full_text_assessed(assessed_count)
            
            excluded_at_fulltext = len(self.manager.screened_papers) - len(self.manager.eligible_papers)
            self.manager.prisma_counter.set_full_text_exclusions(excluded_at_fulltext)
            
            # Final inclusion (happens automatically after fulltext screening)
            self.manager.final_papers = self.manager.eligible_papers
            self.manager.prisma_counter.set_qualitative(len(self.manager.final_papers))
            self.manager.prisma_counter.set_quantitative(len(self.manager.final_papers))
            
            message = (
                f"Full-text screened {len(self.manager.screened_papers)} papers, "
                f"{len(self.manager.eligible_papers)} eligible, "
                f"{excluded_at_fulltext} excluded"
            )
            logger.info(message)
            logger.info(
                f"PRISMA: sought={sought_count}, "
                f"not_retrieved={not_retrieved_count}, "
                f"assessed={assessed_count}"
            )
            logger.info(f"Final included studies: {len(self.manager.final_papers)}")
            
            result = self._create_result(
                status=PhaseStatus.COMPLETED,
                data=self.manager.eligible_papers,
                message=message,
                papers_sought=sought_count,
                papers_not_retrieved=not_retrieved_count,
                papers_assessed=assessed_count,
                papers_excluded=excluded_at_fulltext,
                final_papers=len(self.manager.final_papers)
            )
            
            self.log_completion(result)
            return result
            
        except Exception as e:
            logger.error(f"Full-text screening failed: {str(e)}", exc_info=True)
            result = self._create_result(
                status=PhaseStatus.FAILED,
                message=f"Full-text screening failed: {str(e)}",
                error=e
            )
            return result


class PaperEnrichmentPhase(WorkflowPhase):
    """
    Phase for enriching papers with missing metadata.
    
    Responsibilities:
    - Fill in missing metadata (authors, abstracts, etc.)
    - Enrich with bibliometric data if enabled
    """
    
    @property
    def name(self) -> str:
        return "paper_enrichment"
    
    @property
    def description(self) -> str:
        return "Enrich papers with missing metadata"
    
    def execute(self, **kwargs) -> PhaseResult:
        """
        Execute the paper enrichment phase.
        
        Returns:
            PhaseResult with enriched papers
        """
        self.log_start()
        
        try:
            # Execute enrichment using existing manager method
            enriched_papers = self.manager._enrich_papers()
            
            message = f"Enriched {len(enriched_papers)} papers with missing metadata"
            logger.info(message)
            
            result = self._create_result(
                status=PhaseStatus.COMPLETED,
                data=enriched_papers,
                message=message,
                papers_enriched=len(enriched_papers)
            )
            
            self.log_completion(result)
            return result
            
        except Exception as e:
            logger.error(f"Paper enrichment failed: {str(e)}", exc_info=True)
            result = self._create_result(
                status=PhaseStatus.FAILED,
                message=f"Paper enrichment failed: {str(e)}",
                error=e
            )
            return result
