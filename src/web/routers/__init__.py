"""Web API domain routers."""

from src.web.routers.advanced import router as advanced_router
from src.web.routers.artifacts import router as artifacts_router
from src.web.routers.config import router as config_router
from src.web.routers.costs import router as costs_router
from src.web.routers.database_explorer import router as database_explorer_router
from src.web.routers.history import router as history_router
from src.web.routers.run_lifecycle import router as run_lifecycle_router
from src.web.routers.screening_review import router as screening_review_router
from src.web.routers.system import router as system_router
from src.web.routers.validation import router as validation_router

__all__ = [
    "advanced_router",
    "artifacts_router",
    "config_router",
    "costs_router",
    "database_explorer_router",
    "history_router",
    "run_lifecycle_router",
    "screening_review_router",
    "system_router",
    "validation_router",
]
