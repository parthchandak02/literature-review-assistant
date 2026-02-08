"""
Quality Phase

Handles quality assessment and risk of bias evaluation.
"""

from ...utils.logging_config import get_logger
from . import PhaseResult, PhaseStatus, WorkflowPhase

logger = get_logger(__name__)


class QualityAssessmentPhase(WorkflowPhase):
    """
    Phase for assessing quality and risk of bias in papers.
    
    Responsibilities:
    - Assess study quality (CASP, GRADE, etc.)
    - Evaluate risk of bias
    - Generate quality assessment reports
    """
    
    @property
    def name(self) -> str:
        return "quality_assessment"
    
    @property
    def description(self) -> str:
        return "Assess quality and risk of bias"
    
    def execute(self, **kwargs) -> PhaseResult:
        """
        Execute the quality assessment phase.
        
        Returns:
            PhaseResult with quality assessment data
        """
        self.log_start()
        
        try:
            # Execute quality assessment using existing manager method
            quality_data = self.manager._quality_assessment()
            
            message = "Quality assessment completed"
            logger.info(message)
            
            result = self._create_result(
                status=PhaseStatus.COMPLETED,
                data=quality_data,
                message=message
            )
            
            self.log_completion(result)
            return result
            
        except Exception as e:
            logger.error(f"Quality assessment failed: {str(e)}", exc_info=True)
            result = self._create_result(
                status=PhaseStatus.FAILED,
                message=f"Quality assessment failed: {str(e)}",
                error=e
            )
            return result
