"""
Extraction Phase

Handles data extraction from included papers.
"""

from ...utils.logging_config import get_logger
from . import PhaseResult, PhaseStatus, WorkflowPhase

logger = get_logger(__name__)


class DataExtractionPhase(WorkflowPhase):
    """
    Phase for extracting structured data from papers.
    
    Responsibilities:
    - Extract key data points from each paper
    - Validate extracted data
    - Store extraction results
    """
    
    @property
    def name(self) -> str:
        return "data_extraction"
    
    @property
    def description(self) -> str:
        return "Extract structured data from papers"
    
    def execute(self, **kwargs) -> PhaseResult:
        """
        Execute the data extraction phase.
        
        Returns:
            PhaseResult with extracted data
        """
        self.log_start()
        
        try:
            # Execute extraction using existing manager method
            extracted_data = self.manager._extract_data()
            
            message = f"Extracted data from {len(self.manager.extracted_data)} papers"
            logger.info(message)
            
            result = self._create_result(
                status=PhaseStatus.COMPLETED,
                data=extracted_data,
                message=message,
                papers_processed=len(self.manager.extracted_data)
            )
            
            self.log_completion(result)
            return result
            
        except Exception as e:
            logger.error(f"Data extraction failed: {str(e)}", exc_info=True)
            result = self._create_result(
                status=PhaseStatus.FAILED,
                message=f"Data extraction failed: {str(e)}",
                error=e
            )
            return result
