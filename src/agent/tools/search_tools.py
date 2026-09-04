from langchain_core.tools import tool
from src.domain.search import SearchDomainService

_search_domain = SearchDomainService()

@tool
async def web_search(query: str):
    """
    Realiza uma busca rápida na internet para fatos atuais ou informações gerais.
    Ideal para perguntas como 'qual a previsão do tempo' ou 'quem venceu o jogo'.
    """
    print(f"WEB_SEARCH_START: {query}")
    result = await _search_domain.search_web(query)
    return result.to_agent_message()

@tool
async def deep_research(query: str):
    """
    Realiza uma pesquisa aprofundada na web para tópicos complexos.
    Sintetiza informações de múltiplas fontes. Use quando o usuário pedir
    uma 'investigação', 'estudo detalhado' ou 'pesquisa profunda'.
    """
    print(f"DEEP_RESEARCH_START: {query}")
    result = await _search_domain.deep_research(query)
    return result.to_agent_message()

SEARCH_TOOLS = [
    web_search,
    deep_research,
]
