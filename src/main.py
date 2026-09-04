import asyncio
import os
from fastapi import FastAPI, HTTPException, Request, Depends, Security
from fastapi.security.api_key import APIKeyHeader
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv

from src.agent.engine import MaeveAgent
from src.models.schemas import ChatRequest, ChatResponse
from src.services.registry import (
    get_obsidian_service,
    get_vector_db_service,
    get_ticktick_service,
    get_database_service,
    get_telegram_service,
    set_maeve_agent,
    shutdown_all_services
)
from src.services.reminder_worker import reminder_worker

load_dotenv()

# --- Security Setup ---
API_KEY = os.getenv("API_KEY")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def get_api_key(api_key_header: str = Security(api_key_header)):
    if not API_KEY:
        if ENVIRONMENT == "production":
            raise HTTPException(
                status_code=500, 
                detail="Configuração insegura: API_KEY obrigatória em ambiente de produção."
            )
        # Permite modo dev apenas fora de produção
        return "dev-mode"
    if api_key_header == API_KEY:
        return api_key_header
    raise HTTPException(status_code=403, detail="Acesso não autorizado: API Key inválida.")

from contextlib import asynccontextmanager

# Background tasks tracking to prevent garbage collection
background_tasks = set()

# Shared singletons via Registry
obsidian_service = get_obsidian_service()
vector_db = get_vector_db_service()
ticktick_service = get_ticktick_service()
db_service = get_database_service()
telegram_bot = get_telegram_service()
maeve = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global maeve, telegram_bot
    
    # 1. Inicializa Maeve (com ou sem Supabase)
    try:
        checkpointer = await db_service.get_checkpointer()
        maeve = MaeveAgent(checkpointer=checkpointer)
        set_maeve_agent(maeve)
        print("✅ Maeve Agent inicializado com persistência no Supabase.")
    except Exception as e:
        print(f"⚠️ Erro ao conectar ao Supabase: {e}. Usando memória volátil.")
        maeve = MaeveAgent()
        set_maeve_agent(maeve)
    
    # 2. Inicializa e inicia o Telegram Bot em background
    try:
        if telegram_bot.token:
            tg_task = asyncio.create_task(telegram_bot.start_bot())
            background_tasks.add(tg_task)
            tg_task.add_done_callback(background_tasks.discard)
            print("🚀 Tentando iniciar Interface Telegram em background...")
        else:
            print("⚠️ TELEGRAM_BOT_TOKEN não configurado. Interface Telegram desativada.")
    except Exception as e:
        print(f"❌ Erro ao iniciar Telegram: {e}")

    # 3. Inicia o Worker de Lembretes
    rem_task = asyncio.create_task(reminder_worker(telegram_bot, db_service))
    background_tasks.add(rem_task)
    rem_task.add_done_callback(background_tasks.discard)

    yield

    # Shutdown limpo e centralizado de todos os serviços
    await shutdown_all_services()

# --- App Initialization ---
app = FastAPI(
    title="Maeve AI Agent", 
    description="Context-Aware Task Orchestrator (Obsidian-Powered)",
    lifespan=lifespan
)

@app.get("/")
async def read_root():
    return {"status": "Maeve is online", "version": "0.3.0"}

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "0.3.0",
        "agent_initialized": maeve is not None,
        "database": "connected" if db_service.pool is not None else "standby"
    }

# ... (OAuth endpoints)

@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(get_api_key)])
async def chat_with_maeve(request: ChatRequest):
    if not maeve:
        raise HTTPException(status_code=503, detail="Agente não inicializado.")
    try:
        agent_response = await maeve.run(request.message, thread_id=request.thread_id)
        return ChatResponse(response=agent_response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/sync/obsidian", dependencies=[Depends(get_api_key)])
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
