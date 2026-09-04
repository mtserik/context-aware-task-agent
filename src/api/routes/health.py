from fastapi import APIRouter
from src.services.registry import get_database_service, get_maeve_agent

router = APIRouter(tags=["Health & Status"])

@router.get("/")
async def read_root():
    return {"status": "Maeve is online", "version": "0.4.0"}

@router.get("/health")
async def health_check():
    db_service = get_database_service()
    maeve = get_maeve_agent()
    return {
        "status": "healthy",
        "version": "0.4.0",
        "agent_initialized": maeve is not None,
        "database": "connected" if db_service.pool is not None else "standby"
    }
