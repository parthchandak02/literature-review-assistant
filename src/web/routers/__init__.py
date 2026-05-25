"""Web API domain routers."""

from src.web.routers.config import router as config_router
from src.web.routers.system import router as system_router

__all__ = ["config_router", "system_router"]
