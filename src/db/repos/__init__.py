"""Domain-specific sub-repository modules for WorkflowRepository."""

from src.db.repos.costs import CostsRepo
from src.db.repos.events import EventsRepo
from src.db.repos.extraction import ExtractionRepo
from src.db.repos.papers import PapersRepo
from src.db.repos.quality import QualityRepo
from src.db.repos.screening import ScreeningRepo
from src.db.repos.validation import ValidationRepo
from src.db.repos.workflow_state import WorkflowStateRepo
from src.db.repos.writing import WritingRepo

__all__ = [
    "CostsRepo",
    "EventsRepo",
    "ExtractionRepo",
    "PapersRepo",
    "QualityRepo",
    "ScreeningRepo",
    "ValidationRepo",
    "WorkflowStateRepo",
    "WritingRepo",
]
