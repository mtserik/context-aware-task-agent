import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv

from src.agent.engine import MaeveAgent, db_service
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

# Global instances
maeve = None
obsidian_service = ObsidianService()
vector_db = VectorDBService()
ticktick_service = TickTickService()

@app.on_event("startup")
async def startup_event():
    global maeve
    try:
        # Inicializa persistência no Supabase
        checkpointer = await db_service.get_checkpointer()
        maeve = MaeveAgent(checkpointer=checkpointer)
        print("✅ Maeve Agent inicializado com persistência no Supabase.")
    except Exception as e:
        print(f"❌ Erro ao inicializar Maeve: {e}")
        # Fallback para sem persistência se falhar
        maeve = MaeveAgent()

@app.on_event("shutdown")
async def shutdown_event():
    await db_service.close()

@app.get("/")
async def read_root():
    return {"status": "Maeve is online", "version": "0.1.0"}

# ... (OAuth endpoints)

@app.post("/chat", response_model=ChatResponse)
async def chat_with_maeve(request: ChatRequest):
    if not maeve:
        raise HTTPException(status_code=503, detail="Agente não inicializado.")
    try:
        agent_response = await maeve.run(request.message, thread_id=request.thread_id)
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
                # Obter metadados da nota
                metadata = await obsidian_service.get_note_metadata(note_path)
                
                # Criar um texto amigável para busca vetorial
                full_text = f"Título: {metadata['title']}\nCaminho: {metadata['path']}\nConteúdo: {content}"
                
                texts.append(full_text)
                metadatas.append({
                    "source": "obsidian", 
                    "path": metadata['path'], 
                    "title": metadata['title'],
                    "folder": metadata['folder']
                })

        # 4. Upsert no Qdrant
        if texts:
            await vector_db.upsert_documents(texts=texts, metadatas=metadatas)

        return {"status": "success", "notes_synced": len(texts)}
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(error_details)
        raise HTTPException(status_code=500, detail=f"Erro na sincronização do Obsidian: {str(e)}")
