from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv

from src.agent.engine import MaeveAgent
from src.models.schemas import ChatRequest, ChatResponse
from src.services.notion import NotionService
from src.services.vector_db import VectorDBService

load_dotenv()

# --- App Initialization ---
app = FastAPI(
    title="Maeve AI Agent", 
    description="Refactored Context-Aware Task Orchestrator"
)

# Singleton instances
maeve = MaeveAgent()
notion_service = NotionService()
vector_db = VectorDBService()

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

@app.post("/sync/notion")
async def sync_notion():
    """
    Endpoint para sincronizar o Second Brain do Notion com o Qdrant.
    """
    try:
        # 1. Buscar todos os objetos (páginas e bancos) disponíveis
        objects = await notion_service.list_available_objects()
        if not objects:
            return {"status": "success", "message": "Nenhum conteúdo encontrado. Verifique as permissões no Notion."}

        pages_synced = 0
        processed_page_ids = set()

        async def process_page(page_id: str, title: str):
            if page_id in processed_page_ids:
                return
            content = await notion_service.get_page_text_content(page_id)
            full_text = f"Título: {title}\nConteúdo: {content}"
            await vector_db.upsert_documents(
                texts=[full_text],
                metadatas=[{"source": "notion", "page_id": page_id, "title": title}]
            )
            processed_page_ids.add(page_id)

        for obj in objects:
            obj_type = obj.get("object")
            
            if obj_type == "page":
                # Extrair título da página
                properties = obj.get("properties", {})
                title_list = properties.get("title", {}).get("title", []) or \
                             properties.get("Name", {}).get("title", [])
                title = title_list[0].get("plain_text", "Sem Título") if title_list else "Sem Título"
                await process_page(obj["id"], title)
                pages_synced += 1

            elif obj_type == "database":
                # Buscar páginas dentro do banco de dados
                pages = await notion_service.fetch_database_pages(obj["id"])
                for page in pages:
                    properties = page.get("properties", {})
                    title_list = properties.get("title", {}).get("title", []) or \
                                 properties.get("Name", {}).get("title", [])
                    title = title_list[0].get("plain_text", "Sem Título") if title_list else "Sem Título"
                    await process_page(page["id"], title)
                    pages_synced += 1

        return {"status": "success", "pages_synced": len(processed_page_ids)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na sincronização: {str(e)}")
