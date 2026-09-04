from fastapi import APIRouter, HTTPException, Depends
from src.models.schemas import ChatRequest, ChatResponse
from src.api.deps import get_api_key
from src.services.registry import get_maeve_agent

router = APIRouter(tags=["Chat"])

@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(get_api_key)])
async def chat_with_maeve(request: ChatRequest):
    maeve = get_maeve_agent()
    if not maeve:
        raise HTTPException(status_code=503, detail="Agente não inicializado.")
    try:
        agent_response = await maeve.run(request.message, thread_id=request.thread_id)
        return ChatResponse(response=agent_response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
