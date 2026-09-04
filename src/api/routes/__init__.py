from src.api.routes.health import router as health_router
from src.api.routes.chat import router as chat_router
from src.api.routes.sync import router as sync_router

__all__ = ["health_router", "chat_router", "sync_router"]
