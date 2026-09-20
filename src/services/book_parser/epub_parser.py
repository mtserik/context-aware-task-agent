import os
import re
import hashlib
import logging
from typing import List, Dict, Any, Optional, Tuple
from bs4 import BeautifulSoup
import markdownify

from src.services.book_parser.base import (
    BaseBookParser,
    BookMode,
    ParsedImage,
    ParsedChapter,
    ParsedBook
)
from src.services.book_parser.detector import BookModeDetector

logger = logging.getLogger("EPUBBookParser")

class EPUBBookParser(BaseBookParser):
    """
    Parser semântico de EPUBs para a Maeve.
    Extrai capítulos em HTML/XHTML, converte para Markdown GitHub Flavored
    e preserva imagens e estrutura de tópicos.
    """

    async def parse(
        self,
        file_path: str,
        filename: Optional[str] = None,
        mode: Optional[BookMode] = None,
        extract_images: bool = True,
        max_images: int = 100,
        **kwargs
    ) -> ParsedBook:
        """Extrai a obra completa em formato EPUB."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Arquivo EPUB não encontrado: {file_path}")

        try:
            import ebooklib
            from ebooklib import epub
        except ImportError:
            raise RuntimeError("ebooklib não está instalado no ambiente.")

        fname = filename or os.path.basename(file_path)
        book = epub.read_epub(file_path)

        # 1. Metadados Dublin Core
        title_meta = book.get_metadata("DC", "title")
        raw_title = title_meta[0][0] if title_meta else os.path.splitext(fname)[0]
        # Sanitiza caracteres proibidos para nomes de pasta/arquivo no Windows e Obsidian
        clean_title = re.sub(r'[\r\n\t]+', ' ', str(raw_title))
        clean_title = re.sub(r'[:/\\?*|"<>]', ' - ', clean_title)
        clean_title = re.sub(r'\s{2,}', ' ', clean_title).strip()

        author_meta = book.get_metadata("DC", "creator")
        author = author_meta[0][0] if author_meta else "Desconhecido"

        date_meta = book.get_metadata("DC", "date")
        year = None
        if date_meta and date_meta[0][0]:
            match = re.search(r'\b(19\d\d|20\d\d)\b', str(date_meta[0][0]))
            year = int(match.group(1)) if match else None

        # 2. Detecção de Modo
        if mode is None:
            detected_mode, _ = BookModeDetector.detect_mode(file_path, fname)
            effective_mode = detected_mode
        else:
            effective_mode = mode

        logger.info(f"Processando EPUB '{clean_title}' no modo {effective_mode.value.upper()}.")

        # 3. Extração de Imagens
        cover_image: Optional[ParsedImage] = None
        attachments: List[ParsedImage] = []
        image_name_map: Dict[str, ParsedImage] = {}

        if extract_images:
            img_items = list(book.get_items_of_type(ebooklib.ITEM_IMAGE))
            img_counter = 1
            for it in img_items:
                content = it.get_content()
                if len(content) < 5000:  # descarta ícones minúsculos
                    continue

                item_name = it.get_name()
                ext = os.path.splitext(item_name)[1].lstrip(".").lower() or "jpg"
                md5_hash = hashlib.md5(content).hexdigest()
                out_name = f"img_{img_counter:03d}.{ext}"

                # Detecta se é capa
                is_cov = "cover" in item_name.lower() or img_counter == 1

                parsed_img = ParsedImage(
                    name=out_name,
                    page_number=1,
                    image_bytes=content,
                    extension=ext,
                    width=600,
                    height=800,
                    md5_hash=md5_hash,
                    is_cover=is_cov,
                    rel_path=f"attachments/{out_name}"
                )

                if is_cov and not cover_image:
                    parsed_img.name = f"cover.{ext}"
                    parsed_img.rel_path = f"attachments/{parsed_img.name}"
                    cover_image = parsed_img

                attachments.append(parsed_img)
                # Mapeia tanto o nome do item quanto basename para substituição no Markdown
                image_name_map[item_name] = parsed_img
                image_name_map[os.path.basename(item_name)] = parsed_img

                img_counter += 1
                if len(attachments) >= max_images:
                    break

        # 4. Processamento dos Documentos de Texto (Capítulos)
        doc_items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
        chapters: List[ParsedChapter] = []

        order = 1
        for it in doc_items:
            html_content = it.get_content().decode("utf-8", errors="ignore")
            soup = BeautifulSoup(html_content, "html.parser")

            # Remove tags irrelevantes
            for tag in soup(["script", "style"]):
                tag.decompose()

            raw_text = soup.get_text().strip()
            if len(raw_text) < 150:  # pula páginas vazias ou de copyright minúsculas
                continue

            # Detecta título do capítulo a partir de H1, H2 ou title tag
            h1 = soup.find(["h1", "h2"])
            chap_title = h1.get_text().strip() if h1 else f"Capítulo {order:02d}"
            clean_chap_title = re.sub(r'[\r\n\t]+', ' ', chap_title)
            clean_chap_title = re.sub(r'[:/\\?*|"<>]', ' - ', clean_chap_title)
            clean_chap_title = re.sub(r'\s{2,}', ' ', clean_chap_title).strip()
            if len(clean_chap_title) > 80:
                clean_chap_title = clean_chap_title[:77] + "..."

            # Ignora páginas de copyright de compartilhamento ou fichas catalográficas
            lower_chap = clean_chap_title.lower()
            if any(p in lower_chap for p in ["dados de copyright", "lelivros", "sobre nós", "ficha catalográfica"]):
                continue

            # Converte caixas de destaque, avisos e sidebars em callouts para o Obsidian
            for box in soup.find_all(["aside", "div"], class_=lambda c: c and any(k in str(c).lower() for k in ["sidebar", "box", "quadro", "callout", "destaque", "textbox"])):
                box.name = "blockquote"
                title_tag = box.find(class_=lambda c: c and "title" in str(c).lower()) or box.find(["h1", "h2", "h3", "h4", "h5"])
                if title_tag:
                    t_text = title_tag.get_text().strip()
                    new_p = soup.new_tag("p")
                    new_p.string = f"[!NOTE] {t_text}"
                    title_tag.replace_with(new_p)

            # Converte HTML para Markdown limpo
            md_content = markdownify.markdownify(
                str(soup),
                heading_style="ATX",
                autolinks=False,
                strip=["nav", "footer"]
            ).strip()

            # Ajusta links de imagens no Markdown para o padrão Obsidian [[attachments/...]]
            for orig_name, img_obj in image_name_map.items():
                md_content = re.sub(
                    rf'!\[.*?\]\(.*?{re.escape(orig_name)}.*?\)',
                    f'![[{img_obj.rel_path}]]',
                    md_content
                )

            # Remove declarações XML residuais
            md_content = re.sub(r'<\?xml[^>]*\?>', '', md_content, flags=re.IGNORECASE)
            md_content = re.sub(r'xml\s+version=[\'"][^\'"]*[\'"][^\n]*\??', '', md_content, flags=re.IGNORECASE)
            md_content = re.sub(r'\n{3,}', '\n\n', md_content).strip()

            # Evita título duplicado se o markdown já começar com o cabeçalho
            if md_content.startswith("# ") and (clean_chap_title.lower() in md_content[:150].lower()):
                final_content = md_content
            else:
                final_content = f"# {clean_chap_title}\n\n{md_content}"

            est_tokens = len(final_content.split()) * 4 // 3

            chapters.append(ParsedChapter(
                title=clean_chap_title,
                order=order,
                content_markdown=final_content,
                start_page=order,
                end_page=order,
                images=[],
                estimated_tokens=est_tokens
            ))
            order += 1

        return ParsedBook(
            title=clean_title,
            author=author,
            year=year,
            mode=effective_mode,
            source_filename=fname,
            total_pages=len(chapters),
            chapters=chapters,
            cover_image=cover_image,
            attachments=attachments,
            metadata={"format": "EPUB", "chapter_count": len(chapters)}
        )
