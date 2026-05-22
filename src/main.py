import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv

from src.agent.engine import MaeveAgent
from src.models.schemas import ChatRequest, ChatResponse
from src.services.obsidian import ObsidianService
from src.services.vector_db import VectorDBService
from src.services.ticktick import TickTickService

load_dotenv()

# --- App Initialization ---
app = FastAPI(
    title="Maeve AI Agent", 
    description="Context-Aware Task Orchestrator (Obsidian-Powered)"
)

# Singleton instances
maeve = MaeveAgent()
obsidian_service = ObsidianService()
vector_db = VectorDBService()
ticktick_service = TickTickService()

@app.get("/")
async def read_root():
    return {"status": "Maeve is online", "version": "0.1.0"}

# --- TickTick OAuth Flow ---
@app.get("/auth/ticktick")
async def auth_ticktick():
    """Redireciona o usuário para o login do TickTick."""
    return RedirectResponse(ticktick_service.get_authorization_url())

@app.get("/callback/ticktick")
async def callback_ticktick(code: str):
    """Recebe o código do TickTick e gera o Access Token."""
    try:
        token_data = await ticktick_service.get_access_token(code)
        return {
            "status": "success", 
            "message": "Token obtido com sucesso! Adicione-o ao seu .env",
            "access_token": token_data.get("access_token")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat", response_model=ChatResponse)
async def chat_with_maeve(request: ChatRequest):
    try:
        agent_response = await maeve.run(request.message)
        return ChatResponse(response=agent_response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/sync/obsidian")
async def sync_obsidian():
    """
    Endpoint para sincronizar o Vault do Obsidian com o Qdrant.
    Realiza git pull e indexa todos os arquivos .md.
    """
    try:
        # 1. Sincronizar com o Git (Pull)
        await obsidian_service.sync()
        
        # 2. Listar todos os arquivos .md
        notes = await obsidian_service.list_all_notes()
        if not notes:
            return {"status": "success", "message": "Nenhuma nota encontrada no Vault."}

        # 3. Processar e indexar cada nota
        texts = []
        metadatas = []
        
        for note_path in notes:
            content = await obsidian_service.get_note_content(note_path)
            if content.strip():
                # Nome do arquivo como título
                title = os.path.basename(note_path).replace(".md", "")
                full_text = f"Título: {title}\nConteúdo: {content}"
                
                texts.append(full_text)
                metadatas.append({
                    "source": "obsidian", 
                    "path": note_path, 
                    "title": title
                })

        # 4. Upsert no Qdrant
        if texts:
            await vector_db.upsert_documents(texts=texts, metadatas=metadatas)

        return {"status": "success", "notes_synced": len(texts)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na sincronização do Obsidian: {str(e)}")
