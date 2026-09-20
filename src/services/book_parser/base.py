from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional

class BookMode(str, Enum):
    """
    Modos operacionais de extração e formatação de livros:
    - MATH: Obras matemáticas e acadêmicas (preserva MathJax LaTeX, teoremas, demonstrações).
    - RPG: Livros de RPG e diagramações complexas (bicolunar, callouts de regras, filtro visual pesado).
    - NARRATIVE: Obras literárias, ficção e biografias (leitura contínua fluida, capítulos e citações).
    - GENERAL: Modo padrão resiliente para livros de negócios, artigos e tópicos gerais.
    """
    MATH = "math"
    RPG = "rpg"
    NARRATIVE = "narrative"
    GENERAL = "general"


@dataclass
class ParsedImage:
    """Representa uma imagem extraída do livro com metadados geométricos e hash."""
    name: str
    page_number: int
    image_bytes: bytes
    extension: str  # 'png', 'jpg', 'webp'
    width: int
    height: int
    md5_hash: str
    is_cover: bool = False
    rel_path: Optional[str] = None  # Caminho relativo no Vault (ex: 'attachments/cover.png')


@dataclass
class ParsedChapter:
    """Representa um capítulo atômico fatiado do livro."""
    title: str
    order: int
    content_markdown: str
    start_page: Optional[int] = None
    end_page: Optional[int] = None
    images: List[ParsedImage] = field(default_factory=list)
    estimated_tokens: int = 0


@dataclass
class ParsedBook:
    """Representa a obra integral processada e pronta para estruturação no Obsidian e Qdrant."""
    title: str
    author: str = "Desconhecido"
    year: Optional[int] = None
    mode: BookMode = BookMode.GENERAL
    source_filename: str = ""
    total_pages: int = 0
    chapters: List[ParsedChapter] = field(default_factory=list)
    cover_image: Optional[ParsedImage] = None
    attachments: List[ParsedImage] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseBookParser(ABC):
    """Interface abstrata para parsers especializados de livros (PDF, EPUB, etc.)."""

    @abstractmethod
    async def parse(
        self,
        file_path: str,
        filename: str,
        mode: Optional[BookMode] = None,
        **kwargs
    ) -> ParsedBook:
        """Extrai o livro deterministicamente respeitando o modo operacional."""
        pass
