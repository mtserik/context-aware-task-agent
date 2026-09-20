import os
import re
import uuid
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

from src.services.registry import (
    get_obsidian_service,
    get_culture_service,
    get_vector_db_service
)
from src.services.obsidian import ObsidianService
from src.services.culture import CultureService
from src.services.vector_db import VectorDBService
from src.services.book_parser import (
    BookMode,
    ParsedBook,
    ParsedChapter,
    PDFBookParser,
    EPUBBookParser
)
from src.domain.tokenization import MarkdownSemanticChunker

logger = logging.getLogger("BookDomainService")

class BookDomainService:
    """
    Serviço de Domínio responsável pelo ciclo de vida completo de livros:
    Extração determinística, enriquecimento cultural, modelagem MOC no Obsidian,
    commit Git atômico e vetorização sintática no Qdrant.
    """

    def __init__(
        self,
        obsidian_service: Optional[ObsidianService] = None,
        culture_service: Optional[CultureService] = None,
        vector_db_service: Optional[VectorDBService] = None,
        chunker: Optional[MarkdownSemanticChunker] = None
    ):
        self._obsidian = obsidian_service
        self._culture = culture_service
        self._vector_db = vector_db_service
        self.chunker = chunker or MarkdownSemanticChunker()
        self.pdf_parser = PDFBookParser()
        self.epub_parser = EPUBBookParser()

    @property
    def obsidian(self) -> ObsidianService:
        if self._obsidian is None:
            self._obsidian = get_obsidian_service()
        return self._obsidian

    @property
    def culture(self) -> CultureService:
        if self._culture is None:
            self._culture = get_culture_service()
        return self._culture

    @property
    def vector_db(self) -> VectorDBService:
        if self._vector_db is None:
            self._vector_db = get_vector_db_service()
        return self._vector_db

    async def ingest_book(
        self,
        file_path: str,
        filename: Optional[str] = None,
        mode: Optional[str] = None,
        extract_images: bool = True,
        sync_git: bool = True,
        sync_vector_db: bool = True
    ) -> Dict[str, Any]:
        """
        Executa a ingestão completa com o invariante Zero-Token:
        1. Parsing PDF ou EPUB determinístico em CPU.
        2. Enriquecimento de metadados / capa.
        3. Gravação de notas MOC e Capítulos no Obsidian com 1 único commit/push Git.
        4. Fatiamento sintático com tiktoken e indexação no Qdrant.
        """
        fname = filename or os.path.basename(file_path)
        ext = os.path.splitext(fname.lower())[1]

        # Converte string de modo para BookMode enum se fornecida
        book_mode_enum: Optional[BookMode] = None
        if mode:
            try:
                book_mode_enum = BookMode(mode.lower().strip())
            except ValueError:
                logger.warning(f"Modo '{mode}' inválido. Usando detecção automática.")

        # 1. Parsing determinístico
        if ext == ".pdf":
            parsed_book: ParsedBook = await self.pdf_parser.parse(
                file_path=file_path,
                filename=fname,
                mode=book_mode_enum,
                extract_images=extract_images
            )
        elif ext in [".epub", ".mobi"]:
            parsed_book: ParsedBook = await self.epub_parser.parse(
                file_path=file_path,
                filename=fname,
                mode=book_mode_enum,
                extract_images=extract_images
            )
        else:
            raise ValueError(f"Formato de livro não suportado: '{ext}'. Suportados: .pdf, .epub")

        clean_title = parsed_book.title
        book_dir = f"Recursos/Livros/{clean_title}"
        attachments_dir = f"{book_dir}/attachments"

        # 2. Enriquecimento de Metadados via CultureService (OpenLibrary/Wikipedia)
        meta_online = {}
        try:
            meta_online = self.culture.search_metadata(clean_title, "livro") or {}
        except Exception as cul_err:
            logger.debug(f"Aviso na busca online de metadados para '{clean_title}': {cul_err}")

        final_author = (
            meta_online.get("creator")
            if meta_online.get("creator") and meta_online.get("creator") != "Desconhecido"
            else parsed_book.author
        )
        final_year = meta_online.get("year") or parsed_book.year or datetime.now().year
        synopsis = meta_online.get("synopsis") or f"Obra técnica/literária '{clean_title}'."
        poster_url = meta_online.get("poster_url")

        # 3. Gravação de Anexos / Capa no Vault
        saved_attachments = []
        cover_rel_path = None

        for img in parsed_book.attachments:
            img_rel_path = f"{attachments_dir}/{img.name}"
            await self.obsidian.write_binary_file(img_rel_path, img.image_bytes)
            img.rel_path = f"attachments/{img.name}"
            saved_attachments.append(img_rel_path)
            if img.is_cover:
                cover_rel_path = f"attachments/{img.name}"

        # 4. Gravação dos Capítulos Atômicos
        saved_chapters_paths = []
        all_chunks_to_index: List[Dict[str, Any]] = []

        total_chapters = len(parsed_book.chapters)
        for chap in parsed_book.chapters:
            chap_filename = f"{chap.order:02d} - {chap.title}.md"
            chap_rel_path = f"{book_dir}/{chap_filename}"

            prev_link = f"[[{chap.order-1:02d} - {parsed_book.chapters[chap.order-2].title}|← Anterior]]" if chap.order > 1 else ""
            next_link = f"[[{chap.order+1:02d} - {parsed_book.chapters[chap.order].title}|Próximo →]]" if chap.order < total_chapters else ""
            nav_bar = f"\n\n---\n**Navegação:** {prev_link} | [[{clean_title}|Índice do Livro]] | {next_link}\n"

            chap_frontmatter = {
                "livro": f"[[{clean_title}]]",
                "capitulo": chap.order,
                "ordem": chap.order,
                "paginas": f"{chap.start_page or 1}-{chap.end_page or 1}",
                "tokens_estimados": chap.estimated_tokens,
                "tags": ["recursos/livros/capitulo", parsed_book.mode.value]
            }

            full_chapter_content = f"{chap.content_markdown}{nav_bar}"
            await self.obsidian.write_note_with_frontmatter(
                relative_path=chap_rel_path,
                content=full_chapter_content,
                frontmatter=chap_frontmatter
            )
            saved_chapters_paths.append(chap_rel_path)

            # Segmentação sintática do capítulo para o RAG
            chunks = self.chunker.chunk_markdown(chap.content_markdown, chapter_title=chap.title)
            for chk in chunks:
                all_chunks_to_index.append({
                    "text": chk.content,
                    "metadata": {
                        "source": "book",
                        "book_title": clean_title,
                        "author": final_author,
                        "chapter": chap.title,
                        "order": chap.order,
                        "mode": parsed_book.mode.value,
                        "chunk_index": chk.chunk_index,
                        "total_chunks": chk.total_chunks,
                        "path": chap_rel_path
                    }
                })

        # 5. Geração e Gravação da Nota Hub / MOC Central
        moc_rel_path = f"{book_dir}/{clean_title}.md"
        moc_content = self._format_moc(
            clean_title=clean_title,
            author=final_author,
            year=final_year,
            mode=parsed_book.mode,
            total_pages=parsed_book.total_pages,
            chapters=parsed_book.chapters,
            synopsis=synopsis,
            poster_url=poster_url,
            cover_rel_path=cover_rel_path
        )

        moc_frontmatter = {
            "tipo": "livro",
            "titulo": clean_title,
            "autor": final_author,
            "ano": final_year,
            "modo": parsed_book.mode.value,
            "status": "Ingerido",
            "data_ingestao": datetime.now().strftime("%Y-%m-%d"),
            "paginas": parsed_book.total_pages,
            "total_capitulos": total_chapters,
            "tags": [
                "recursos/livros",
                "literatura",
                f"modo/{parsed_book.mode.value}"
            ]
        }

        await self.obsidian.write_note_with_frontmatter(
            relative_path=moc_rel_path,
            content=moc_content,
            frontmatter=moc_frontmatter
        )

        # 6. Commit & Push Atômico Único no Git
        if sync_git:
            commit_msg = (
                f"Maeve: Ingestão de '{clean_title}' ({total_chapters} capítulos, "
                f"{len(saved_attachments)} anexos, modo {parsed_book.mode.value})"
            )
            try:
                await self.obsidian.push(commit_msg)
                logger.info(f"Git push atômico concluído para '{clean_title}'.")
            except Exception as git_err:
                logger.error(f"Erro no Git push de '{clean_title}': {git_err}")

        # 7. Vetorização Sintática no Qdrant
        vectors_count = 0
        if sync_vector_db and all_chunks_to_index:
            try:
                texts = [c["text"] for c in all_chunks_to_index]
                metas = [c["metadata"] for c in all_chunks_to_index]
                await self.vector_db.upsert_documents(texts=texts, metadatas=metas)
                vectors_count = len(texts)
                logger.info(f"Vetorização no Qdrant concluída: {vectors_count} chunks indexados.")
            except Exception as vec_err:
                logger.error(f"Falha ao indexar chunks no Qdrant: {vec_err}")

        return {
            "success": True,
            "title": clean_title,
            "author": final_author,
            "year": final_year,
            "mode": parsed_book.mode.value,
            "total_pages": parsed_book.total_pages,
            "chapter_count": total_chapters,
            "attachments_count": len(saved_attachments),
            "vectors_indexed": vectors_count,
            "moc_path": moc_rel_path,
            "cover_url": poster_url or (f"{attachments_dir}/cover.png" if cover_rel_path else None)
        }

    def _format_moc(
        self,
        clean_title: str,
        author: str,
        year: int,
        mode: BookMode,
        total_pages: int,
        chapters: List[ParsedChapter],
        synopsis: str,
        poster_url: Optional[str],
        cover_rel_path: Optional[str]
    ) -> str:
        """Gera o Markdown do MOC (Map of Content) da obra no padrão visual da Maeve."""
        today = datetime.now().strftime("%Y-%m-%d")

        # Banner de capa (online ou anexo local)
        banner_html = ""
        if poster_url:
            banner_html = (
                f'<div align="center">\n'
                f'  <img src="{poster_url}" alt="Capa de {clean_title}" width="260" '
                f'style="border-radius: 8px; box-shadow: 0 4px 14px rgba(0,0,0,0.35); margin-bottom: 16px;"/>\n'
                f'</div>\n\n'
            )
        elif cover_rel_path:
            banner_html = f'<div align="center">\n  ![[{cover_rel_path}|260]]\n</div>\n\n'

        chapter_links = []
        for ch in chapters:
            token_hint = f" (~{ch.estimated_tokens} tokens)" if ch.estimated_tokens else ""
            chapter_links.append(f"- [[{ch.order:02d} - {ch.title}|Capítulo {ch.order:02d}: {ch.title}]]{token_hint}")

        chapters_list_md = "\n".join(chapter_links) if chapter_links else "- Nenhum capítulo isolado."

        moc_text = f"""# 📚 {clean_title} ({year})

{banner_html}> [!ABSTRACT] **Ficha Técnica & Metadados**
> - **Título Oficial:** {clean_title}
> - **Autoria:** {author}
> - **Ano:** {year}
> - **Modo Operacional:** {mode.value.upper()}
> - **Volume Total:** {total_pages} páginas | {len(chapters)} capítulos estruturados
> - **Data de Ingestão:** {today}

---

## 📝 Sinopse & Visão Geral
{synopsis}

---

## 📑 Sumário & Capítulos
{chapters_list_md}

---

## 💡 Principais Modelos Mentais & Aprendizados do Erik
<!-- Registre aqui suas reflexões, anotações de estudo e conexões com outros projetos -->

---

### 🔗 Conexões & Órbitas
- **MOC Geral:** [[MOC - Livros e Leituras]]
- **Prática:** Gestão de Conhecimento, Leitura Ativa e Engenharia de Prompt
"""
        return moc_text
