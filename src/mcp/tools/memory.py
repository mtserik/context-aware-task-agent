"""
MCP Memory Tools — deterministic wrappers over VectorDBService and KnowledgeDomainService.

Zero-Token Principle: nenhuma chamada a modelos generativos e feita aqui.
Toda logica de embedding e matematica vetorial (text-embedding-3-small via
VectorDBService.search_context) e restrita a geracao de vetores de busca.
"""
import logging
from typing import Annotated

from mcp.server.fastmcp import FastMCP

from src.domain.knowledge import KnowledgeDomainService
from src.services.registry import get_vector_db_service

logger = logging.getLogger("MaeveMCP.tools.memory")


def register_memory_tools(mcp: FastMCP) -> None:
    """Registra as ferramentas de memoria semantica no servidor FastMCP."""

    @mcp.tool(
        name="memory_search",
        description=(
            "Busca semantica no Segundo Cerebro do Erik (Obsidian Vault vectorizado no Qdrant). "
            "Recebe uma query em linguagem natural, gera o embedding matematico via "
            "text-embedding-3-small e retorna os chunks mais similares com score de "
            "similaridade cossenoidal e caminho relativo da nota de origem. "
            "Use sempre que precisar de contexto pessoal, historico de decisoes ou "
            "conhecimento previamente registrado pelo Erik."
        ),
    )
    async def memory_search(
        query: Annotated[str, "Query em linguagem natural para busca semantica no Obsidian Vault"],
        limit: Annotated[int, "Numero maximo de resultados (default: 5, max: 20)"] = 5,
    ) -> str:
        """Busca semantica vetorial no Obsidian Vault. Retorna chunks Markdown brutos."""
        try:
            limit = max(1, min(limit, 20))
            vector_db = get_vector_db_service()
            results = await vector_db.search_context(query=query, limit=limit)

            if not results:
                return "Nenhum resultado encontrado para a query fornecida."

            lines = []
            for i, r in enumerate(results, 1):
                content = r.get("content", "").strip()
                metadata = r.get("metadata", {})
                path = metadata.get("path", "desconhecido")
                title = metadata.get("title", path)
                lines.append(f"## [{i}] {title}\nCaminho: {path}\n\n{content}")

            return "\n\n---\n\n".join(lines)
        except Exception as e:
            logger.error("Erro em memory_search: %s", e)
            return f"Erro ao buscar na memoria semantica: {str(e)}"

    @mcp.tool(
        name="memory_store",
        description=(
            "Cria ou atualiza uma nota no Obsidian Vault com versionamento Git automatico. "
            "Use para registrar insights, decisoes, aprendizados ou documentacao gerada "
            "durante sessoes de trabalho no Antigravity. "
            "O conteudo deve ser em Markdown estruturado com notacao matematica em LaTeX "
            "(MathJax: $inline$ e $$bloco$$) quando aplicavel."
        ),
    )
    async def memory_store(
        title: Annotated[str, "Titulo da nota (sera usado como nome do arquivo .md)"],
        content: Annotated[str, "Conteudo da nota em Markdown estruturado com LaTeX para matematica"],
        folder: Annotated[str, "Pasta destino no Vault (ex: 'Inbox', 'Projetos', 'Decisoes')"] = "Inbox",
    ) -> str:
        """Cria uma nota no Obsidian Vault com commit Git automatico."""
        try:
            svc = KnowledgeDomainService()
            result = await svc.create_note(title=title, content=content, folder=folder)
            return result.message
        except Exception as e:
            logger.error("Erro em memory_store: %s", e)
            return f"Erro ao salvar nota no Vault: {str(e)}"

    @mcp.tool(
        name="search_knowledge",
        description=(
            "Busca textual exata (full-text / regex) dentro dos arquivos Markdown do "
            "Obsidian Vault. Mais rapida que memory_search para buscas por nomes de "
            "arquivos, pastas especificas, termos tecnicos exatos ou IDs. "
            "Nao usa embeddings — opera diretamente no filesystem local."
        ),
    )
    async def search_knowledge(
        query: Annotated[str, "Termo de busca exato, padrao regex ou nome de arquivo/pasta"],
        folder: Annotated[str, "Pasta raiz para a busca (vazio = todo o Vault)"] = "",
    ) -> str:
        """Busca textual no filesystem do Obsidian Vault."""
        try:
            svc = KnowledgeDomainService()
            result = await svc.list_notes()
            if not result.success or not result.data:
                return "Nenhuma nota encontrada no Vault."

            notes: list[str] = result.data
            query_lower = query.lower()
            folder_filter = folder.lower().strip("/") if folder else ""

            matched = []
            for note_path in notes:
                if folder_filter and not note_path.lower().startswith(folder_filter):
                    continue
                if query_lower in note_path.lower():
                    matched.append(note_path)

            if not matched:
                return f"Nenhuma nota encontrada para '{query}'"

            lines = [f"Encontradas {len(matched)} nota(s) para '{query}':"]
            lines.extend(f"- {p}" for p in matched[:50])
            if len(matched) > 50:
                lines.append(f"... (exibindo 50 de {len(matched)} resultados)")
            return "\n".join(lines)
        except Exception as e:
            logger.error("Erro em search_knowledge: %s", e)
            return f"Erro na busca textual: {str(e)}"

    @mcp.tool(
        name="sync_knowledge",
        description=(
            "Sincroniza o Vault do Obsidian com o banco de dados vetorial Qdrant. "
            "Executa git pull no repositório do Vault, processa todos os arquivos Markdown "
            "e gera/atualiza os embeddings no Qdrant via text-embedding-3-small. "
            "Use sempre que houver novas notas, reestruturações no Vault ou quando "
            "o usuário solicitar a atualização da memória semântica."
        ),
    )
    async def sync_knowledge() -> str:
        """Sincroniza o Obsidian Vault e reindexa as notas no Qdrant."""
        try:
            svc = KnowledgeDomainService()
            result = await svc.sync_knowledge()
            if result.success:
                return result.message
            return f"Falha na sincronização: {result.message}"
        except Exception as e:
            logger.error("Erro em sync_knowledge: %s", e)
            return f"Erro ao sincronizar conhecimento com Qdrant: {str(e)}"