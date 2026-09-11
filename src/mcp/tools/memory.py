"""
MCP Memory Tools — deterministic wrappers over VectorDBService and KnowledgeDomainService.

Zero-Token Principle: nenhuma chamada a modelos generativos e feita aqui.
Toda logica de embedding e matematica vetorial (text-embedding-3-small via
VectorDBService.search_context) e restrita a geracao de vetores de busca.
"""
import logging
from typing import Annotated, Optional

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
        score_threshold: Annotated[Optional[float], "Limiar mínimo de similaridade cossenoidal (ex: 0.70). Se omitido, retorna os mais próximos."] = None,
    ) -> str:
        """Busca semantica vetorial no Obsidian Vault. Retorna chunks Markdown brutos com score."""
        try:
            limit = max(1, min(limit, 20))
            vector_db = get_vector_db_service()
            results = await vector_db.search_context(query=query, limit=limit, score_threshold=score_threshold)

            if not results:
                return "Nenhum resultado relevante encontrado para a query fornecida."

            lines = []
            for i, r in enumerate(results, 1):
                content = r.get("content", "").strip()
                metadata = r.get("metadata", {})
                path = metadata.get("path", "desconhecido")
                title = metadata.get("title", path)
                score = r.get("score")
                score_str = f" [Score: {score:.3f}]" if score is not None else ""
                lines.append(f"## [{i}] {title}{score_str}\nCaminho: {path}\n\n{content}")

            return "\n\n---\n\n".join(lines)
        except Exception as e:
            logger.error("Erro em memory_search: %s", e)
            return f"Erro ao buscar na memoria semantica: {str(e)}"

    @mcp.tool(
        name="memory_store",
        description=(
            "Cria ou atualiza uma nota no Obsidian Vault com versionamento Git e Write-Through imediato no Qdrant. "
            "Use para registrar insights, projetos densos, decisões ou documentação gerada "
            "durante sessões de trabalho no Antigravity. "
            "O conteúdo deve ser em Markdown estruturado com notação matemática em LaTeX "
            "(MathJax: $inline$ e $$bloco$$) quando aplicável."
        ),
    )
    async def memory_store(
        title: Annotated[str, "Titulo da nota (sera usado como nome do arquivo .md)"],
        content: Annotated[str, "Conteudo da nota em Markdown estruturado com LaTeX para matematica"],
        folder: Annotated[str, "Pasta destino no Vault (ex: '00 - Inbox/Maeve', '02 - Projects', '03 - Decisions')"] = "00 - Inbox/Maeve",
        category: Annotated[Optional[str], "Categoria da nota ('projeto', 'decisao', 'reuniao', 'conceito', 'brainstorming')"] = "projeto",
        tags: Annotated[Optional[str], "Tags separadas por virgula (ex: 'maeve, arquitetura, mcp')"] = None,
    ) -> str:
        """Cria uma nota no Obsidian Vault com commit Git e Write-Through imediato no Qdrant."""
        try:
            from src.domain.temporal import get_local_now
            frontmatter = {
                "author": "maeve",
                "created_at": get_local_now().isoformat(),
            }
            if category:
                frontmatter["category"] = category
            if tags:
                tag_list = [t.strip().lstrip("#") for t in tags.split(",") if t.strip()]
                if tag_list:
                    frontmatter["tags"] = tag_list

            svc = KnowledgeDomainService()
            result = await svc.create_note(
                title=title,
                content=content,
                folder=folder,
                frontmatter=frontmatter,
                sync_vector_db=True
            )
            return result.message
        except Exception as e:
            logger.error("Erro em memory_store: %s", e)
            return f"Erro ao salvar nota no Vault: {str(e)}"

    @mcp.tool(
        name="append_session_note",
        description=(
            "Anexa uma síntese estruturada de reunião, conversa, projeto ou brainstorming "
            "na Daily Note do dia (ex: '01 - Daily/YYYY-MM-DD.md') com timestamp e tags. "
            "Garante o princípio anti-bagunça da Maeve (Append-First), evitando fragmentação "
            "do Vault em dezenas de micro-arquivos avulsos. "
            "Executa Write-Through imediato no Qdrant para refletir o conteúdo atualizado na memória vetorial."
        ),
    )
    async def append_session_note(
        title: Annotated[str, "Título ou tópico da sessão/reunião/brainstorming"],
        summary: Annotated[str, "Síntese em Markdown estruturado dos pontos discutidos, decisões e próximos passos (LaTeX para matemática quando aplicável)"],
        category: Annotated[str, "Categoria: 'reuniao', 'projeto', 'brainstorming', 'ideia', 'alinhamento'"] = "projeto",
        tags: Annotated[str, "Tags separadas por vírgula (ex: 'maeve, arquitetura, mcp')"] = "",
    ) -> str:
        """Anexa sessão na Daily Note do dia com commit Git e Write-Through no Qdrant."""
        try:
            svc = KnowledgeDomainService()
            tag_list = [t.strip().lstrip("#") for t in tags.split(",") if t.strip()] if tags else []
            result = await svc.append_to_daily_note(
                content=summary,
                title=title,
                category=category,
                tags=tag_list
            )
            return result.message
        except Exception as e:
            logger.error("Erro em append_session_note: %s", e)
            return f"Erro ao registrar sessão no Vault: {str(e)}"

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