"""
MCP Search Tools — FastMCP wrappers over SearchDomainService (Tavily).

Disponibiliza busca na web (web_search) e pesquisa aprofundada (deep_research)
diretamente via protocolo MCP para clientes externos e para o agente interno.
"""
import logging
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from src.domain.search import SearchDomainService

logger = logging.getLogger("MaeveMCP.tools.search")
_search_service = SearchDomainService()


def register_search_tools(mcp: FastMCP) -> None:
    """Registra as ferramentas de pesquisa na web no servidor FastMCP."""

    @mcp.tool(
        name="web_search",
        description=(
            "Realiza uma busca rápida na internet via Tavily para fatos atuais, documentação ou notícias em tempo real. "
            "Use para perguntas como previsões, lançamentos de bibliotecas ou dados que não estão no Vault."
        ),
    )
    async def web_search(
        query: Annotated[str, "Query de pesquisa na internet"],
    ) -> str:
        """Busca rápida na web via Tavily Search."""
        try:
            logger.info("Executando web_search MCP: %s", query)
            result = await _search_service.search_web(query)
            return result.to_agent_message()
        except Exception as e:
            logger.error("Erro em web_search MCP: %s", e)
            return f"Erro na pesquisa web: {str(e)}"

    @mcp.tool(
        name="deep_research",
        description=(
            "Realiza uma pesquisa aprofundada e investigativa na web sintetizando múltiplas fontes. "
            "Ideal para benchmarks de mercado, arquiteturas de sistemas ou temas complexos."
        ),
    )
    async def deep_research(
        query: Annotated[str, "Tópico de investigação aprofundada"],
    ) -> str:
        """Pesquisa aprofundada multi-fonte na web."""
        try:
            logger.info("Executando deep_research MCP: %s", query)
            result = await _search_service.deep_research(query)
            return result.to_agent_message()
        except Exception as e:
            logger.error("Erro em deep_research MCP: %s", e)
            return f"Erro na pesquisa profunda: {str(e)}"
