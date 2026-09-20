import os
import re
import logging
from typing import List, Dict, Any, Optional, Tuple
import fitz

from src.services.book_parser.base import (
    BaseBookParser,
    BookMode,
    ParsedImage,
    ParsedChapter,
    ParsedBook
)
from src.services.book_parser.detector import BookModeDetector
from src.services.book_parser.image_extractor import BookImageExtractor

logger = logging.getLogger("PDFBookParser")

class PDFBookParser(BaseBookParser):
    """
    Parser universal de PDFs para a Maeve.
    Converte livros acadêmicos (Math), livros de RPG (bicolunares com ilustrações)
    e literatura geral em capítulos estruturados e notas Markdown prontas para o Obsidian.
    """

    def __init__(self, image_extractor: Optional[BookImageExtractor] = None):
        self.image_extractor = image_extractor or BookImageExtractor()

    async def parse(
        self,
        file_path: str,
        filename: Optional[str] = None,
        mode: Optional[BookMode] = None,
        extract_images: bool = True,
        max_images: int = 100,
        **kwargs
    ) -> ParsedBook:
        """
        Executa a extração ponta a ponta do PDF.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Arquivo PDF não encontrado: {file_path}")

        fname = filename or os.path.basename(file_path)
        doc = fitz.open(file_path)
        total_pages = len(doc)

        # 1. Metadados básicos
        raw_title = doc.metadata.get("title") or os.path.splitext(fname)[0]
        clean_title = self._clean_title(raw_title)
        author = doc.metadata.get("author") or "Desconhecido"
        year = self._extract_year(doc.metadata.get("creationDate"))

        # 2. Detecção de Modo Operacional se não informado
        if mode is None:
            detected_mode, _ = BookModeDetector.detect_mode(file_path, fname)
            effective_mode = detected_mode
        else:
            effective_mode = mode

        logger.info(f"Processando '{clean_title}' no modo {effective_mode.value.upper()} ({total_pages} páginas).")

        # 3. Extração de Imagens e Eleição de Capa
        cover_image: Optional[ParsedImage] = None
        attachments: List[ParsedImage] = []

        if extract_images:
            try:
                cover_image, attachments = self.image_extractor.extract_images_from_pdf(
                    doc=doc,
                    book_title=clean_title,
                    max_images=max_images
                )
            except Exception as img_err:
                logger.warning(f"Aviso na extração de imagens de '{clean_title}': {img_err}")

        # Mapa de imagens por página para embed contextual nos capítulos
        page_images_map: Dict[int, List[ParsedImage]] = {}
        for img in attachments:
            if not img.is_cover:
                page_images_map.setdefault(img.page_number, []).append(img)

        # 4. Segmentação em Capítulos
        chapter_ranges = self._segment_chapters(doc, total_pages)

        chapters: List[ParsedChapter] = []
        for order, (chap_title, start_pg, end_pg) in enumerate(chapter_ranges, start=1):
            chap_content, chap_imgs = self._render_chapter(
                doc=doc,
                title=chap_title,
                start_page=start_pg,
                end_page=end_pg,
                mode=effective_mode,
                page_images_map=page_images_map
            )

            # Estimativa de tokens
            est_tokens = len(chap_content.split()) * 4 // 3

            chapters.append(ParsedChapter(
                title=chap_title,
                order=order,
                content_markdown=chap_content,
                start_page=start_pg,
                end_page=end_pg,
                images=chap_imgs,
                estimated_tokens=est_tokens
            ))

        doc.close()

        return ParsedBook(
            title=clean_title,
            author=author,
            year=year,
            mode=effective_mode,
            source_filename=fname,
            total_pages=total_pages,
            chapters=chapters,
            cover_image=cover_image,
            attachments=attachments,
            metadata={
                "producer": doc.metadata.get("producer", ""),
                "format": "PDF",
                "chapter_count": len(chapters)
            }
        )

    def _segment_chapters(self, doc: fitz.Document, total_pages: int, max_pages_per_chapter: int = 25) -> List[Tuple[str, int, int]]:
        """
        Determina os intervalos de páginas dos capítulos usando TOC ou fatiamento de páginas.
        Se um capítulo de nível 1 for extenso (> max_pages_per_chapter), verifica se há
        subtópicos de nível 2 para subdividir em sub-notas atômicas e navegáveis.
        """
        toc = doc.get_toc()
        level1_entries = [entry for entry in toc if entry[0] == 1 and entry[2] > 0]

        def _clean_chapter_str(raw: str) -> str:
            clean = re.sub(r'[\r\n\t]+', ' ', raw)
            clean = re.sub(r'[:/\\?*|"<>]', ' - ', clean)
            clean = re.sub(r'\s{2,}', ' ', clean).strip()
            if len(clean) > 80:
                clean = clean[:77] + "..."
            return clean

        if len(level1_entries) >= 2:
            ranges = []
            for i, entry in enumerate(level1_entries):
                title = entry[1].strip()
                start_pg = max(1, entry[2])
                if i + 1 < len(level1_entries):
                    next_pg = max(start_pg, level1_entries[i+1][2])
                    end_pg = max(start_pg, next_pg - 1)
                else:
                    end_pg = total_pages

                clean_base_title = _clean_chapter_str(title)
                page_span = end_pg - start_pg + 1

                # Subdivide capítulos extensos que possuem nível 2 no TOC
                if page_span > max_pages_per_chapter:
                    sub_entries = [e for e in toc if e[0] == 2 and start_pg <= e[2] <= end_pg]
                    if len(sub_entries) >= 2:
                        # Se houver páginas antes da primeira sub-entrada (ex: introdução ao capítulo)
                        if sub_entries[0][2] > start_pg:
                            first_end = sub_entries[0][2] - 1
                            ranges.append((_clean_chapter_str(f"{clean_base_title} - Introdução"), start_pg, first_end))

                        cluster_title = _clean_chapter_str(sub_entries[0][1])
                        cluster_start = max(start_pg, sub_entries[0][2])

                        for s_idx in range(len(sub_entries)):
                            cur_sub = sub_entries[s_idx]
                            s_start = max(start_pg, cur_sub[2])
                            s_end = (
                                max(s_start, sub_entries[s_idx + 1][2] - 1)
                                if s_idx + 1 < len(sub_entries)
                                else end_pg
                            )

                            is_last = (s_idx == len(sub_entries) - 1)
                            cur_span = s_end - cluster_start + 1

                            if is_last or cur_span >= 6:
                                full_title = _clean_chapter_str(f"{clean_base_title} - {cluster_title}")
                                ranges.append((full_title, cluster_start, s_end))
                                if not is_last:
                                    next_sub = sub_entries[s_idx + 1]
                                    cluster_title = _clean_chapter_str(next_sub[1])
                                    cluster_start = max(start_pg, next_sub[2])
                        continue

                    # Se não tem nível 2, divide em partes uniformes
                    part_num = 1
                    for chunk_start in range(start_pg, end_pg + 1, max_pages_per_chapter):
                        chunk_end = min(end_pg, chunk_start + max_pages_per_chapter - 1)
                        part_title = _clean_chapter_str(f"{clean_base_title} (Parte {part_num:02d})")
                        ranges.append((part_title, chunk_start, chunk_end))
                        part_num += 1
                    continue

                ranges.append((clean_base_title, start_pg, end_pg))
            return ranges

        # Fallback se não houver TOC estruturado: fatiamento de páginas
        chunk_size = max_pages_per_chapter
        ranges = []
        chap_num = 1
        for start_pg in range(1, total_pages + 1, chunk_size):
            end_pg = min(total_pages, start_pg + chunk_size - 1)
            title = f"Parte {chap_num:02d} (Páginas {start_pg} a {end_pg})"
            ranges.append((title, start_pg, end_pg))
            chap_num += 1

        return ranges

    def _render_chapter(
        self,
        doc: fitz.Document,
        title: str,
        start_page: int,
        end_page: int,
        mode: BookMode,
        page_images_map: Dict[int, List[ParsedImage]]
    ) -> Tuple[str, List[ParsedImage]]:
        """
        Renderiza o texto e imagens do capítulo em Markdown estruturado de acordo com o modo.
        """
        lines: List[str] = [f"# {title}\n"]
        chapter_images: List[ParsedImage] = []

        for p_num in range(start_page, end_page + 1):
            if p_num > len(doc):
                break
            page = doc[p_num - 1]

            if mode == BookMode.RPG:
                page_md = self._render_rpg_page(page)
            elif mode == BookMode.MATH:
                page_md = self._render_math_page(page)
            else:
                page_md = self._render_general_page(page)

            if page_md.strip():
                lines.append(page_md.strip())

            # Embed das imagens aprovadas desta página
            if p_num in page_images_map:
                for img in page_images_map[p_num]:
                    chapter_images.append(img)
                    lines.append(f"\n![[{img.rel_path}]]\n")

        full_content = "\n\n".join(lines).strip()
        return full_content, chapter_images

    def _render_rpg_page(self, page: fitz.Page) -> str:
        """
        Renderiza página de RPG preservando fluxo bicolunar e faixas horizontais de largura completa.
        Reconstrói a ordem de leitura geométrica para manter tabelas e títulos contíguos aos seus dados.
        """
        page_width = page.rect.width
        blocks = page.get_text("blocks")

        col1_blocks = []
        col2_blocks = []
        spanning_blocks = []

        for b in blocks:
            if len(b) >= 7 and b[6] == 0:  # Bloco de texto
                x0, y0, x1, y1, text = b[0], b[1], b[2], b[3], b[4].strip()
                if not text:
                    continue

                # Bloco que cruza a linha média ou banner largo (>60% da largura da página)
                if (x0 < page_width * 0.45 and x1 > page_width * 0.55) or ((x1 - x0) > page_width * 0.60):
                    spanning_blocks.append((y0, y1, text))
                elif x1 <= page_width * 0.55:
                    col1_blocks.append((y0, y1, text))
                else:
                    col2_blocks.append((y0, y1, text))

        spanning_blocks.sort(key=lambda s: s[0])
        col1_blocks.sort(key=lambda c: c[0])
        col2_blocks.sort(key=lambda c: c[0])

        if not spanning_blocks:
            all_texts = [c[2] for c in col1_blocks] + [c[2] for c in col2_blocks]
        else:
            all_texts = []
            current_y = 0.0
            for s_y0, s_y1, s_text in spanning_blocks:
                c1_band = [c[2] for c in col1_blocks if current_y <= c[0] < s_y0]
                c2_band = [c[2] for c in col2_blocks if current_y <= c[0] < s_y0]
                all_texts.extend(c1_band)
                all_texts.extend(c2_band)
                all_texts.append(s_text)
                current_y = max(current_y, s_y1)

            all_texts.extend([c[2] for c in col1_blocks if c[0] >= current_y])
            all_texts.extend([c[2] for c in col2_blocks if c[0] >= current_y])

        # Conversão de caixas de regras para callouts e limpeza
        formatted_blocks = []
        for block in all_texts:
            cleaned = self._clean_text(block)
            if cleaned.strip():
                clean_block = self._format_rpg_callout(cleaned)
                formatted_blocks.append(clean_block)

        return "\n\n".join(formatted_blocks)

    def _render_math_page(self, page: fitz.Page) -> str:
        """
        Renderiza página de matemática preservando teoremas e equações.
        """
        raw_text = self._clean_text(page.get_text("text"))
        # Converte padrões de teoremas e provas para callouts
        formatted = re.sub(
            r'^(Teorema\s+[\d\.]+:?.*?)$',
            r'> [!THEOREM] \1',
            raw_text,
            flags=re.MULTILINE | re.IGNORECASE
        )
        formatted = re.sub(
            r'^(Demonstração:?.*?)$',
            r'> [!PROOF] \1',
            formatted,
            flags=re.MULTILINE | re.IGNORECASE
        )
        formatted = re.sub(
            r'^(Definição\s+[\d\.]+:?.*?)$',
            r'> [!DEFINITION] \1',
            formatted,
            flags=re.MULTILINE | re.IGNORECASE
        )
        return formatted

    def _render_general_page(self, page: fitz.Page) -> str:
        """Renderiza página de literatura / negócios em fluxo mono-colunar limpo."""
        return self._clean_text(page.get_text("text"))

    def _clean_text(self, text: str) -> str:
        """Remove marcas d'água de compra digital (ex: nome e email do comprador)."""
        lines = []
        for line in text.splitlines():
            # Linha com email de comprador (ex: 'Erik Martins erik.stos.mts@gmail.com')
            if re.search(r'[\w\.-]+@[\w\.-]+\.\w+', line) and len(line.strip()) < 80:
                continue
            lines.append(line)
        return "\n".join(lines)

    def _format_rpg_callout(self, text: str) -> str:
        """Detecta avisos e caixas de regras de RPG e transforma em callouts do Obsidian."""
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines:
            return text
        first_line_lower = lines[0].lower()

        if any(first_line_lower.startswith(h) for h in ["dica do mestre", "dica de mestre"]):
            return f"> [!TIP] Dica do Mestre\n> " + text.replace("\n", "\n> ")
        elif any(first_line_lower.startswith(h) for h in ["regra opcional", "regra avançada"]):
            return f"> [!NOTE] Regra Opcional\n> " + text.replace("\n", "\n> ")
        elif any(first_line_lower.startswith(h) for h in ["presença perturbadora", "aviso:", "atenção:", "perigo:"]):
            return f"> [!DANGER] {lines[0].title()}\n> " + text.replace("\n", "\n> ")
        return text

    def _clean_title(self, raw_title: str) -> str:
        """Limpa hashes, extensões, versões e ruídos do título do livro."""
        clean = re.sub(r'\.pdf$', '', raw_title, flags=re.IGNORECASE)
        clean = re.sub(r'[-_][a-z0-9]{5,10}$', '', clean)  # remove hashes como -lyfxjj
        clean = re.sub(r'[-_]?v\d+([-_.]\d+)*$', '', clean, flags=re.IGNORECASE)  # remove versões como -v1-3, v1.3
        clean = re.sub(r'[\r\n\t]+', ' ', clean)
        clean = re.sub(r'[:/\\?*|"<>]', ' - ', clean)
        clean = clean.replace("-", " ").replace("_", " ").strip()
        words = clean.split()
        formatted = []
        for w in words:
            low = w.lower()
            if low in ["rpg", "rn", "imecc", "pdf", "d&d"]:
                formatted.append(low.upper())
            elif low in ["de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas", "e", "ao", "aos", "para"]:
                formatted.append(low)
            else:
                formatted.append(w.capitalize())
        if formatted:
            formatted[0] = formatted[0].capitalize()
        return " ".join(formatted)

    def _extract_year(self, date_str: Optional[str]) -> Optional[int]:
        """Extrai o ano da data de metadados do PDF."""
        if not date_str:
            return None
        match = re.search(r'\b(19\d\d|20\d\d)\b', date_str)
        return int(match.group(1)) if match else None
