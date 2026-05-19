import os
from notion_client import AsyncClient
from typing import List, Dict, Any

class NotionService:
    """
    Serviço responsável pela integração com a API do Notion.
    Permite extrair conteúdo de páginas e bancos de dados para o Second Brain.
    """
    def __init__(self):
        self.notion = AsyncClient(auth=os.getenv("NOTION_API_KEY"))

    async def list_available_objects(self) -> List[Dict[str, Any]]:
        """
        Busca por páginas e bancos de dados que a integração tem acesso.
        """
        # Sem filtro específico para encontrar tanto 'page' quanto 'database'
        response = await self.notion.search()
        return response.get("results", [])

    async def get_page_text_content(self, page_id: str) -> str:
        """
        Extrai todo o conteúdo de texto de uma página, percorrendo seus blocos.
        """
        # Simplificação: pegamos os primeiros 100 blocos da página
        blocks = await self.notion.blocks.children.list(block_id=page_id)
        text_parts = []
        
        for block in blocks.get("results", []):
            block_type = block.get("type")
            content = block.get(block_type, {})
            
            # Alguns blocos têm 'rich_text', outros não
            rich_text = content.get("rich_text", [])
            
            for text in rich_text:
                plain_text = text.get("plain_text", "")
                if plain_text:
                    text_parts.append(plain_text)
        
        return "\n".join(text_parts)

    async def fetch_database_pages(self, database_id: str) -> List[Dict[str, Any]]:
        """
        Retorna todas as páginas de um banco de dados específico.
        """
        response = await self.notion.databases.query(database_id=database_id)
        return response.get("results", [])
