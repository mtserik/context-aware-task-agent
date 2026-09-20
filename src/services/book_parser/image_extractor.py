import hashlib
import io
import logging
from typing import List, Dict, Tuple, Optional, Set
import fitz
from PIL import Image

from src.services.book_parser.base import ParsedImage

logger = logging.getLogger("BookImageExtractor")

class BookImageExtractor:
    """
    Extrator determinístico de imagens de livros com Filtro Anti-Ruído Visual (Smart Visual Filter).
    Elimina asset clutter (texturas de fundo, ícones de dados, cantoneiras decorativas)
    e seleciona automaticamente a capa da obra.
    """

    DEFAULT_MIN_WIDTH = 200
    DEFAULT_MIN_HEIGHT = 200
    DEFAULT_MIN_AREA = 40000  # 200x200
    DEFAULT_MAX_ASPECT_RATIO = 5.0  # descarta réguas horizontais/verticais (ex: 800x20)
    MAX_REPEATED_OCCURRENCES = 3    # se mesma textura/marca d'água aparece em >3 páginas, é decorativa

    def __init__(
        self,
        min_width: int = DEFAULT_MIN_WIDTH,
        min_height: int = DEFAULT_MIN_HEIGHT,
        min_area: int = DEFAULT_MIN_AREA,
        max_aspect_ratio: float = DEFAULT_MAX_ASPECT_RATIO,
        max_repeated_occurrences: int = MAX_REPEATED_OCCURRENCES
    ):
        self.min_width = min_width
        self.min_height = min_height
        self.min_area = min_area
        self.max_aspect_ratio = max_aspect_ratio
        self.max_repeated_occurrences = max_repeated_occurrences

    def extract_images_from_pdf(
        self,
        doc: fitz.Document,
        book_title: str,
        max_images: int = 150
    ) -> Tuple[Optional[ParsedImage], List[ParsedImage]]:
        """
        Varre o PDF, aplica os filtros heurísticos, deduplica texturas por hash MD5
        e elege a imagem de capa. Retorna (cover_image, list_of_approved_attachments).
        """
        # 1. Primeira passada: mapeamento de ocorrências por hash para detectar texturas repetidas
        hash_occurrences: Dict[str, Set[int]] = {}
        raw_images_map: Dict[str, Dict[str, Any]] = {}

        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images(full=True)

            for img_info in image_list:
                xref = img_info[0]
                try:
                    base_image = doc.extract_image(xref)
                    if not base_image:
                        continue

                    img_bytes = base_image.get("image")
                    img_ext = base_image.get("ext", "png").lower()
                    width = base_image.get("width", 0)
                    height = base_image.get("height", 0)

                    if width < self.min_width or height < self.min_height:
                        continue
                    if (width * height) < self.min_area:
                        continue

                    # Checagem de aspect ratio
                    ratio = max(width, height) / max(1, min(width, height))
                    if ratio > self.max_aspect_ratio:
                        continue

                    md5_hash = hashlib.md5(img_bytes).hexdigest()

                    if md5_hash not in hash_occurrences:
                        hash_occurrences[md5_hash] = set()
                        raw_images_map[md5_hash] = {
                            "xref": xref,
                            "bytes": img_bytes,
                            "ext": img_ext,
                            "width": width,
                            "height": height,
                            "first_page": page_num + 1
                        }

                    hash_occurrences[md5_hash].add(page_num + 1)

                except Exception as ex:
                    logger.debug(f"Erro ao analisar imagem xref={xref}: {ex}")
                    continue

        # 2. Filtragem de texturas repetitivas (fundo de página / marcas d'água)
        approved_images: List[ParsedImage] = []
        cover_candidates: List[ParsedImage] = []

        img_counter = 1
        for md5_hash, occurrences in hash_occurrences.items():
            # Se a mesma imagem se repete em mais páginas que o limiar, é ruído visual/fundo
            if len(occurrences) > self.max_repeated_occurrences:
                logger.debug(f"Imagem {md5_hash[:8]} descartada: repetida em {len(occurrences)} páginas.")
                continue

            info = raw_images_map[md5_hash]
            first_page = info["first_page"]
            ext = "png" if info["ext"] in ["png", "webp"] else "jpg"
            name = f"p{first_page:03d}_img{img_counter:02d}.{ext}"

            parsed = ParsedImage(
                name=name,
                page_number=first_page,
                image_bytes=info["bytes"],
                extension=ext,
                width=info["width"],
                height=info["height"],
                md5_hash=md5_hash,
                is_cover=False,
                rel_path=f"attachments/{name}"
            )

            approved_images.append(parsed)
            img_counter += 1

            # Candidato a capa: páginas iniciais (1 a 5) com alta resolução
            if first_page <= 5 and info["width"] >= 400 and info["height"] >= 600:
                cover_candidates.append(parsed)

            if len(approved_images) >= max_images:
                break

        # 3. Eleição de capa
        cover_image: Optional[ParsedImage] = None
        if cover_candidates:
            # Seleciona a imagem com maior área nas páginas iniciais
            cover_candidates.sort(key=lambda x: x.width * x.height, reverse=True)
            best_cover = cover_candidates[0]
            best_cover.is_cover = True
            best_cover.name = f"cover.{best_cover.extension}"
            best_cover.rel_path = f"attachments/{best_cover.name}"
            cover_image = best_cover
        elif approved_images:
            # Fallback: primeira imagem aprovada vira capa
            best_cover = approved_images[0]
            best_cover.is_cover = True
            best_cover.name = f"cover.{best_cover.extension}"
            best_cover.rel_path = f"attachments/{best_cover.name}"
            cover_image = best_cover

        logger.info(
            f"Extração de imagens concluída para '{book_title}': "
            f"{len(approved_images)} aprovadas de {len(hash_occurrences)} únicas analisadas. "
            f"Capa: {cover_image.name if cover_image else 'Nenhuma'}."
        )

        return cover_image, approved_images
