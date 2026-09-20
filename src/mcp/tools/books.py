import os
import logging
from typing import Annotated, Optional
from mcp.server.fastmcp import FastMCP

from src.services.registry import get_book_domain_service

logger = logging.getLogger("MaeveMCP.tools.books")

def register_book_tools(mcp: FastMCP) -> None:
    """Registra ferramentas de ingestão de livros no servidor FastMCP."""

    @mcp.tool(
        name="ingest_book",
        description=(
            "Ingere um livro completo (PDF ou EPUB) local no Obsidian Vault e no Qdrant RAG sob o "
            "invariante Zero-Token (custo generativo $0,00). Fatia automaticamente em capítulos, "
            "aplica perfilador de modo (matemática, rpg, narrativa), extrai imagens de alta resolução "
            "com filtro anti-ruído e gera a nota MOC central com links bidirecionais e commit Git atômico. "
            "Aceita caminhos absolutos do disco (ex: da biblioteca do Calibre ou pasta de RPGs)."
        ),
    )
    async def ingest_book(
        file_path: Annotated[str, "Caminho absoluto do arquivo (.pdf ou .epub) no disco local"],
        mode: Annotated[Optional[str], "Modo operacional opcional: 'math', 'rpg', 'narrative', 'general' ou omitido para auto-detecção"] = None,
        extract_images: Annotated[bool, "Se verdadeiro, extrai capa e ilustrações aprovadas pelo filtro anti-ruído"] = True,
    ) -> str:
        """Processa e ingere o livro no Obsidian e Qdrant."""
        if not os.path.exists(file_path):
            return f"Erro: Arquivo não encontrado no caminho informado: '{file_path}'"

        try:
            domain = get_book_domain_service()
            result = await domain.ingest_book(
                file_path=file_path,
                mode=mode,
                extract_images=extract_images,
                sync_git=True,
                sync_vector_db=True
            )

            lines = [
                f"✅ **Livro '{result['title']}' ingerido com sucesso!**",
                f"- **Modo Operacional:** {result['mode'].upper()}",
                f"- **Autoria:** {result['author']} ({result['year']})",
                f"- **Páginas Processadas:** {result['total_pages']}",
                f"- **Capítulos Gerados:** {result['chapter_count']} notas no Obsidian",
                f"- **Anexos / Imagens:** {result['attachments_count']} arquivos salvos",
                f"- **Chunks no Qdrant:** {result['vectors_indexed']} vetores indexados para RAG",
                f"- **Nota MOC Central:** `{result['moc_path']}`",
                "",
                "A obra foi commitada de forma atômica no Git e já está disponível para busca semântica via `memory_search`."
            ]
            return "\n".join(lines)

        except Exception as e:
            logger.error(f"Falha na tool ingest_book para '{file_path}': {e}", exc_info=True)
            return f"❌ Falha ao processar e ingerir o livro: {str(e)}"
