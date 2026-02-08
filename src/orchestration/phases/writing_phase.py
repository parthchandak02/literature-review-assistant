"""
Writing Phase

Handles manuscript generation and article writing.
"""

from typing import Dict

from ...utils.logging_config import get_logger
from . import PhaseResult, PhaseStatus, WorkflowPhase

logger = get_logger(__name__)


class ArticleWritingPhase(WorkflowPhase):
    """
    Phase for writing the manuscript.
    
    Responsibilities:
    - Write Introduction section
    - Write Methods section
    - Write Results section
    - Write Discussion section
    - Generate Abstract
    """
    
    @property
    def name(self) -> str:
        return "article_writing"
    
    @property
    def description(self) -> str:
        return "Write article sections (Introduction, Methods, Results, Discussion, Abstract)"
    
    def execute(self, **kwargs) -> PhaseResult:
        """
        Execute the article writing phase.
        
        Returns:
            PhaseResult with article sections
        """
        self.log_start()
        
        try:
            # Execute writing using existing manager method
            article_sections = self.manager._write_article()
            
            sections_written = len(article_sections) if article_sections else 0
            message = f"Generated {sections_written} article sections"
            logger.info(message)
            
            result = self._create_result(
                status=PhaseStatus.COMPLETED,
                data=article_sections,
                message=message,
                sections_written=sections_written
            )
            
            self.log_completion(result)
            return result
            
        except Exception as e:
            logger.error(f"Article writing failed: {str(e)}", exc_info=True)
            result = self._create_result(
                status=PhaseStatus.FAILED,
                message=f"Article writing failed: {str(e)}",
                error=e
            )
            return result


class PRISMAGenerationPhase(WorkflowPhase):
    """
    Phase for generating PRISMA flow diagram.
    
    Responsibilities:
    - Generate PRISMA 2020 flow diagram
    - Export diagram in multiple formats
    """
    
    @property
    def name(self) -> str:
        return "prisma_generation"
    
    @property
    def description(self) -> str:
        return "Generate PRISMA flow diagram"
    
    def execute(self, **kwargs) -> PhaseResult:
        """
        Execute the PRISMA generation phase.
        
        Returns:
            PhaseResult with PRISMA diagram path
        """
        self.log_start()
        
        try:
            # Execute PRISMA generation using existing manager method
            prisma_path = self.manager._generate_prisma_diagram()
            
            message = f"Generated PRISMA diagram at {prisma_path}"
            logger.info(message)
            
            result = self._create_result(
                status=PhaseStatus.COMPLETED,
                data=prisma_path,
                message=message,
                prisma_path=str(prisma_path)
            )
            
            self.log_completion(result)
            return result
            
        except Exception as e:
            logger.error(f"PRISMA generation failed: {str(e)}", exc_info=True)
            result = self._create_result(
                status=PhaseStatus.FAILED,
                message=f"PRISMA generation failed: {str(e)}",
                error=e
            )
            return result


class VisualizationGenerationPhase(WorkflowPhase):
    """
    Phase for generating bibliometric visualizations.
    
    Responsibilities:
    - Generate charts and visualizations
    - Create bibliometric analysis
    """
    
    @property
    def name(self) -> str:
        return "visualization_generation"
    
    @property
    def description(self) -> str:
        return "Generate bibliometric visualizations"
    
    def execute(self, **kwargs) -> PhaseResult:
        """
        Execute the visualization generation phase.
        
        Returns:
            PhaseResult with visualization paths
        """
        self.log_start()
        
        try:
            # Execute visualization generation using existing manager method
            visualizations = self.manager._generate_visualizations()
            
            message = "Generated bibliometric visualizations"
            logger.info(message)
            
            result = self._create_result(
                status=PhaseStatus.COMPLETED,
                data=visualizations,
                message=message
            )
            
            self.log_completion(result)
            return result
            
        except Exception as e:
            logger.error(f"Visualization generation failed: {str(e)}", exc_info=True)
            result = self._create_result(
                status=PhaseStatus.FAILED,
                message=f"Visualization generation failed: {str(e)}",
                error=e
            )
            return result
