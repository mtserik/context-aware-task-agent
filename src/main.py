import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from dotenv import load_dotenv

from src.agent.engine import MaeveAgent
from src.services.registry import (
    get_database_service,
    get_telegram_service,
    set_maeve_agent,
    shutdown_all_services
)
from src.services.reminder_worker import reminder_worker
from src.api.routes import health_router, chat_router, sync_router

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("MaeveMain")

# Conjunto de tarefas em background para evitar coleta prematura pelo Garbage Collector
background_tasks = set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia o ciclo de vida da aplicação (bootstrap, workers e encerramento)."""
    db_service = get_database_service()
    telegram_bot = get_telegram_service()

    # 1. Inicializa o motor da Maeve (com persistência Supabase ou memória)
    try:
        checkpointer = await db_service.get_checkpointer()
        maeve = MaeveAgent(checkpointer=checkpointer)
        set_maeve_agent(maeve)
        logger.info("✅ Maeve Agent inicializado com persistência no Supabase.")
    except Exception as e:
        logger.warning(f"⚠️ Erro ao conectar ao Supabase: {e}. Usando memória volátil (MemorySaver).")
        from langgraph.checkpoint.memory import MemorySaver
        maeve = MaeveAgent(checkpointer=MemorySaver())
        set_maeve_agent(maeve)

    # 2. Inicializa e inicia o Telegram Bot em background
    try:
        if telegram_bot.token:
            tg_task = asyncio.create_task(telegram_bot.start_bot())
            background_tasks.add(tg_task)
            tg_task.add_done_callback(background_tasks.discard)
            logger.info("🚀 Interface Telegram iniciada em background.")
        else:
            logger.warning("⚠️ TELEGRAM_BOT_TOKEN não configurado. Interface Telegram desativada.")
    except Exception as e:
        logger.error(f"❌ Erro ao iniciar Telegram: {e}")

    # 3. Inicia o Worker de Lembretes agendados
    rem_task = asyncio.create_task(reminder_worker(telegram_bot, db_service))
    background_tasks.add(rem_task)
    rem_task.add_done_callback(background_tasks.discard)

    # 4. Inicia o MCP Session Manager para transporte HTTP Streamable
    from src.mcp.server import mcp
    async with mcp.session_manager.run():
        yield

    # Shutdown: Encerra conexões e pools de forma limpa
    logger.info("🛑 Encerrando todos os serviços ativos...")
    await shutdown_all_services()

# --- App Initialization (Composition Root) ---
app = FastAPI(
    title="Maeve AI Agent",
    description="Context-Aware Task & Knowledge Orchestrator",
    version="0.4.0",
    lifespan=lifespan
)

# Inbound Route Adapters
app.include_router(health_router)
app.include_router(chat_router)
app.include_router(sync_router)

# Mount MCP Remote Server (Transporte SSE com autenticação para Antigravity remoto)
from src.mcp.server import get_mcp_asgi_app
app.mount("/mcp", get_mcp_asgi_app())
