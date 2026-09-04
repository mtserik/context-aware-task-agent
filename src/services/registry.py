import asyncio
import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.obsidian import ObsidianService
    from src.services.vector_db import VectorDBService
    from src.services.ticktick import TickTickService
    from src.services.database import DatabaseService
    from src.services.search import SearchService
    from src.services.telegram_bot import TelegramService
    from src.agent.engine import MaeveAgent

logger = logging.getLogger("ServiceRegistry")

# Instâncias únicas globais (Singletons)
_obsidian_service: Optional["ObsidianService"] = None
_vector_db_service: Optional["VectorDBService"] = None
_ticktick_service: Optional["TickTickService"] = None
_database_service: Optional["DatabaseService"] = None
_search_service: Optional["SearchService"] = None
_telegram_service: Optional["TelegramService"] = None
_maeve_agent: Optional["MaeveAgent"] = None

def get_obsidian_service() -> "ObsidianService":
    global _obsidian_service
    if _obsidian_service is None:
        from src.services.obsidian import ObsidianService
        _obsidian_service = ObsidianService()
    return _obsidian_service

def get_vector_db_service() -> "VectorDBService":
    global _vector_db_service
    if _vector_db_service is None:
        from src.services.vector_db import VectorDBService
        _vector_db_service = VectorDBService()
    return _vector_db_service

def get_ticktick_service() -> "TickTickService":
    global _ticktick_service
    if _ticktick_service is None:
        from src.services.ticktick import TickTickService
        _ticktick_service = TickTickService()
    return _ticktick_service

def get_database_service() -> "DatabaseService":
    global _database_service
    if _database_service is None:
        from src.services.database import DatabaseService
        _database_service = DatabaseService()
    return _database_service

def get_search_service() -> "SearchService":
    global _search_service
    if _search_service is None:
        from src.services.search import SearchService
        _search_service = SearchService()
    return _search_service

def get_telegram_service() -> "TelegramService":
    global _telegram_service
    if _telegram_service is None:
        from src.services.telegram_bot import TelegramService
        _telegram_service = TelegramService()
    return _telegram_service

def get_maeve_agent() -> Optional["MaeveAgent"]:
    global _maeve_agent
    return _maeve_agent

def set_maeve_agent(agent: "MaeveAgent") -> None:
    global _maeve_agent
    _maeve_agent = agent

async def shutdown_all_services() -> None:
    """Encerra todas as conexões ativas dos serviços de forma limpa."""
    global _telegram_service, _database_service, _ticktick_service, _vector_db_service
    
    if _telegram_service:
        try:
            await _telegram_service.stop_bot()
        except Exception as e:
            logger.warning(f"Erro ao parar Telegram bot: {e}")

    if _ticktick_service:
        try:
            await _ticktick_service.aclose()
        except Exception as e:
            logger.warning(f"Erro ao fechar TickTick client: {e}")

    if _vector_db_service:
        try:
            await _vector_db_service.close()
        except Exception as e:
            logger.warning(f"Erro ao fechar VectorDB client: {e}")

    if _database_service:
        try:
            await _database_service.close()
        except Exception as e:
            logger.warning(f"Erro ao fechar Database pool: {e}")
