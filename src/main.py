from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv

from src.agent.engine import MaeveAgent
from src.models.schemas import ChatRequest, ChatResponse

load_dotenv()

# --- App Initialization ---
app = FastAPI(
    title="Maeve AI Agent", 
    description="Refactored Context-Aware Task Orchestrator"
)

# Singleton instance
maeve = MaeveAgent()

@app.get("/")
async def read_root():
    return {"status": "Maeve is online", "version": "0.1.0"}

@app.post("/chat", response_model=ChatResponse)
async def chat_with_maeve(request: ChatRequest):
    try:
        agent_response = await maeve.run(request.message)
        return ChatResponse(response=agent_response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
