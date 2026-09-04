from typing import Optional, List, Dict, Any

from src.domain.models import DomainResult
from src.services.registry import get_search_service
from src.services.search import SearchService

class SearchDomainService:
    """
    Serviço de Domínio responsável pelas buscas na web e sínteses de pesquisa profunda.
    """
    def __init__(self, search_service: Optional[SearchService] = None):
        self._search = search_service

    @property
    def search(self) -> SearchService:
        if self._search is None:
            self._search = get_search_service()
        return self._search

    async def search_web(self, query: str) -> DomainResult:
        """Executa busca rápida na web para fatos e informações em tempo real."""
        try:
            results = await self.search.search(query)
            if not results or (isinstance(results, list) and "error" in results[0]):
                err = results[0].get('error') if results else 'Sem resultados'
                return DomainResult(success=False, message=f"Erro na pesquisa: {err}")

            formatted = "\n".join([
                f"- {r['title']} ({r['url']}): {r['content'][:300]}..." for r in results
            ])
            return DomainResult(
                success=True,
                message=f"Resultados da Pesquisa Web:\n{formatted}",
                data=results
            )
        except Exception as e:
            return DomainResult(success=False, message=f"Erro ao pesquisar web: {str(e)}")

    async def deep_research(self, query: str) -> DomainResult:
        """Executa pesquisa aprofundada sintetizando múltiplas fontes."""
        try:
            synthesis = await self.search.deep_research(query)
            return DomainResult(
                success=True,
                message=f"Síntese da Pesquisa Aprofundada:\n{synthesis}",
                data=synthesis
            )
        except Exception as e:
            return DomainResult(success=False, message=f"Erro na pesquisa profunda: {str(e)}")
