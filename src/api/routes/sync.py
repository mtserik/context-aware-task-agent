from fastapi import APIRouter, HTTPException, Depends
from src.api.deps import get_api_key
from src.domain.knowledge import KnowledgeDomainService

router = APIRouter(tags=["Knowledge Synchronization"])

@router.post("/sync/obsidian", dependencies=[Depends(get_api_key)])
async def sync_obsidian():
    """
    Sincroniza o Vault do Obsidian via Git pull e reindexa notas no Qdrant.
    Consome diretamente a camada de domínio KnowledgeDomainService.
    """
    domain = KnowledgeDomainService()
    result = await domain.sync_knowledge()
    if not result.success:
        raise HTTPException(status_code=500, detail=result.message)
    return {"status": "success", "message": result.message, "data": result.data}
