"""
Export Phase

Handles report generation and export to various formats.
"""

from ...utils.logging_config import get_logger
from . import PhaseResult, PhaseStatus, WorkflowPhase

logger = get_logger(__name__)


class ReportGenerationPhase(WorkflowPhase):
    """
    Phase for generating the final report.
    
    Responsibilities:
    - Combine all sections into final report
    - Export to multiple formats (HTML, PDF, MD)
    - Include all figures and tables
    """
    
    @property
    def name(self) -> str:
        return "report_generation"
    
    @property
    def description(self) -> str:
        return "Generate final report"
    
    def execute(self, **kwargs) -> PhaseResult:
        """
        Execute the report generation phase.
        
        Returns:
            PhaseResult with report path
        """
        self.log_start()
        
        try:
            # Get article sections from previous phase
            article_sections = getattr(self.manager, "_article_sections", {})
            
            # Get PRISMA path
            prisma_path = getattr(self.manager, "_prisma_path", None)
            if not prisma_path:
                prisma_path = self.manager._generate_prisma_diagram()
            
            # Generate report using workflow manager method
            viz_paths = getattr(self.manager, "_viz_paths", {})
            report_path = self.manager._generate_final_report(
                article_sections, prisma_path, viz_paths
            )
            
            message = f"Generated final report at {report_path}"
            logger.info(message)
            
            result = self._create_result(
                status=PhaseStatus.COMPLETED,
                data=report_path,
                message=message,
                report_path=str(report_path)
            )
            
            self.log_completion(result)
            return result
            
        except Exception as e:
            logger.error(f"Report generation failed: {str(e)}", exc_info=True)
            result = self._create_result(
                status=PhaseStatus.FAILED,
                message=f"Report generation failed: {str(e)}",
                error=e
            )
            return result


class ManubotExportPhase(WorkflowPhase):
    """
    Phase for exporting to Manubot format (optional).
    
    Responsibilities:
    - Export manuscript to Manubot structure
    - Include citations and references
    """
    
    @property
    def name(self) -> str:
        return "manubot_export"
    
    @property
    def description(self) -> str:
        return "Export to Manubot structure"
    
    def execute(self, **kwargs) -> PhaseResult:
        """
        Execute the Manubot export phase.
        
        Returns:
            PhaseResult with export path
        """
        self.log_start()
        
        # Check if Manubot export is enabled
        manubot_config = self.manager.config.get("manubot", {})
        if not manubot_config.get("enabled", False):
            message = "Manubot export disabled in config"
            logger.info(message)
            result = self._create_result(
                status=PhaseStatus.SKIPPED,
                message=message
            )
            return result
        
        try:
            # Execute Manubot export using existing manager method
            export_path = self.manager._manubot_export_phase()
            
            message = f"Exported to Manubot at {export_path}"
            logger.info(message)
            
            result = self._create_result(
                status=PhaseStatus.COMPLETED,
                data=export_path,
                message=message,
                export_path=str(export_path)
            )
            
            self.log_completion(result)
            return result
            
        except Exception as e:
            logger.error(f"Manubot export failed: {str(e)}", exc_info=True)
            result = self._create_result(
                status=PhaseStatus.FAILED,
                message=f"Manubot export failed: {str(e)}",
                error=e
            )
            return result
