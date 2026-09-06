"""
MCP Culture Tools — Registro cultural, curadoria de entretenimento e pensamento crítico.

Busca capas em alta definição (pôsteres de filmes/séries, capas de livros, box art de jogos)
via APIs externas públicas e formata notas no padrão 'Letterboxd / Goodreads' no Obsidian Vault.
"""
import logging
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from src.services.culture import CultureService

logger = logging.getLogger("MaeveMCP.tools.culture")

def register_culture_tools(mcp: FastMCP) -> None:
    """Registra as ferramentas de curadoria cultural e resenhas no servidor FastMCP."""

    culture_service = CultureService()

    @mcp.tool(
        name="log_cultural_review",
        description=(
            "Registra uma resenha cultural de filme, série, livro ou jogo no Segundo Cérebro do Erik. "
            "Busca automaticamente a capa/pôster oficial em alta definição (TMDB/Wikipedia/OpenLibrary), "
            "gera uma nota completa no padrão 'Letterboxd / Goodreads' em 'Recursos/Entretenimento/{titulo}.md' "
            "com metadados YAML, ficha técnica e desconstrução crítica, atualiza o catálogo geral e sincroniza com o Git."
        ),
    )
    async def log_cultural_review(
        title: Annotated[str, "Título da obra cultural (ex: 'Midsommar', 'Sapiens', 'Elden Ring')"],
        media_type: Annotated[str, "Tipo da obra: 'filme', 'serie', 'livro', 'jogo', 'podcast'"] = "filme",
        review_text: Annotated[str, "Reflexões pessoais, crítica ou comentários do Erik sobre a obra"] = "",
        rating: Annotated[str, "Avaliação pessoal do Erik (ex: '4.5/5', '5/5')"] = "4.5/5",
    ) -> str:
        """Registra a resenha cultural e enriquece com pôster e metadados."""
        try:
            result = await culture_service.log_cultural_entry(
                title=title,
                media_type=media_type,
                review_text=review_text,
                rating=rating
            )
            if result.get("success"):
                poster = result.get("poster_url")
                poster_info = f"\n🖼️ Pôster HD embutido: {poster}" if poster else "\n⚠️ Pôster não encontrado (usado layout padrão)."
                return (
                    f"✅ Resenha cultural de '{result.get('title')}' salva com sucesso!\n"
                    f"📂 Caminho: {result.get('path')}\n"
                    f"⭐ Nota: {result.get('rating')}"
                    f"{poster_info}\n"
                    f"🔗 Catálogo e MOC de Entretenimento atualizados e commitados no Git."
                )
            else:
                return f"Erro ao registrar resenha cultural: {result.get('error')}"
        except Exception as e:
            logger.error("Erro em log_cultural_review: %s", e)
            return f"Erro ao executar log_cultural_review: {str(e)}"
