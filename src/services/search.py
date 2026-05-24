import os
import logging
from typing import List, Dict, Any
from tavily import TavilyClient

logger = logging.getLogger("SearchService")

class SearchService:
    def __init__(self):
        self.api_key = os.getenv("TAVILY_API_KEY")
        if not self.api_key:
            logger.warning("⚠️ TAVILY_API_KEY não configurada no ambiente.")
            self.client = None
        else:
            self.client = TavilyClient(api_key=self.api_key)

    async def search(self, query: str, search_depth: str = "basic", max_results: int = 5) -> List[Dict[str, Any]]:
        """
        Realiza uma busca na web usando Tavily.
        search_depth: "basic" ou "advanced".
        """
        if not self.client:
            return [{"error": "Tavily API Key não configurada."}]

        try:
            # Tavily client uses sync calls, but we can wrap it or just use it 
            # as it's typically fast. For better performance in async flows, 
            # we run it in a thread if needed.
            response = self.client.search(
                query=query,
                search_depth=search_depth,
                max_results=max_results,
                include_answer=True
            )
            return response.get("results", [])
        except Exception as e:
            logger.error(f"Erro na busca Tavily: {e}")
            return [{"error": str(e)}]

    async def deep_research(self, query: str) -> str:
        """
        Realiza uma pesquisa aprofundada e retorna uma síntese.
        """
        if not self.client:
            return "Erro: Tavily API Key não configurada."

        try:
            # O modo 'qna' do Tavily já faz uma síntese inicial
            response = self.client.qna_search(query=query, search_depth="advanced")
            return response
        except Exception as e:
            logger.error(f"Erro no Deep Research: {e}")
            return f"Erro ao realizar pesquisa aprofundada: {str(e)}"
