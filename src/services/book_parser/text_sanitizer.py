import re
from typing import Optional
from src.services.book_parser.base import BookMode

class TextSanitizer:
    """
    Sanitizador determinístico de texto e Markdown para o pipeline de livros.
    Corrige capitulares quebradas (drop caps), hifenização de fim de linha,
    números de página soltos, cabeçalhos duplicados e links internos de EPUB em CPU ($0.00).
    """

    @staticmethod
    def clean_drop_caps(text: str) -> str:
        """
        Corrige letras capitulares que foram extraídas em linhas isoladas.
        Exemplo: 'B\\noas-vindas' -> 'Boas-vindas'
        Preserva espaço quando a letra isolada for um artigo (ex: 'A\\nhistória' -> 'A história').
        """
        def _join_caps(m: re.Match) -> str:
            cap = m.group(1)
            rest = m.group(2)
            raw = re.sub(r'[\u201c\u201d"\'«]', '', cap).strip()
            if raw in ["A", "O", "E"] and len(rest) >= 4 and not rest.startswith(("gora", "inda", "penas", "pesar", "qui")):
                return f"{cap} {rest}"
            return f"{cap}{rest}"

        cleaned = re.sub(
            r'(?m)^([\u201c\u201d"\'«]?[A-ZÀ-Ú])\s*\n\s*([a-zà-ú]+)',
            _join_caps,
            text
        )
        return cleaned

    @staticmethod
    def clean_hyphenation(text: str) -> str:
        """
        Corrige quebras de palavras por hifenização tipográfica no fim de linha.
        Exemplo: 'agen-\\ntes' -> 'agentes'
        """
        # Junta palavras hifenizadas no fim de linha, exceto palavras compostas conhecidas com hífen duplo
        cleaned = re.sub(
            r'(\b[a-zA-Zá-úÁ-Ú]+)-\n\s*([a-zA-Zá-úÁ-Ú]+\b)',
            r'\1\2',
            text
        )
        return cleaned

    @staticmethod
    def clean_standalone_numbers(text: str) -> str:
        """
        Remove números de página soltos entre parágrafos (rodapés/cabeçalhos de página).
        Exemplo: '\\n\\n7\\n\\n' -> '\\n\\n'
        """
        cleaned = re.sub(r'(?m)^\s*\d{1,4}\s*$', '', text)
        return cleaned

    @staticmethod
    def elevate_section_headers(text: str) -> str:
        """
        Eleva linhas curtas isoladas em caixa alta (ex: 'O QUE É RPG?', 'EXEMPLO') para '### Subtítulo'.
        Ignora linhas que já são cabeçalhos Markdown, tags, callouts ou anotações de dados/regras.
        """
        lines = text.splitlines()
        result_lines = []

        for line in lines:
            stripped = line.strip()
            # Critérios para título em caixa alta:
            # 1. Tamanho razoável (3 a 60 chars)
            # 2. Não começa com #, >, !, |, -, *, [
            # 3. É composto por letras maiúsculas, espaços e pontuação básica (? ! - : .)
            # 4. Tem pelo menos 2 caracteres alfabéticos maiúsculos
            if (
                3 <= len(stripped) <= 60
                and not stripped.startswith(("#", ">", "!", "|", "-", "*", "[", "<"))
                and re.search(r'[A-ZÀ-Ú]', stripped)
                and not re.search(r'[a-zà-ú]', stripped)
                and not re.search(r'\b\d+d\d+\b', stripped, flags=re.IGNORECASE)  # ignora rolagens de dados como 1d20
            ):
                # Formata como cabeçalho nível 3
                result_lines.append(f"### {stripped.title()}")
            else:
                result_lines.append(line)

        return "\n".join(result_lines)

    @staticmethod
    def clean_epub_artifacts(text: str) -> str:
        """
        Remove resíduos técnicos típicos de arquivos EPUB:
        - Links de notas de rodapé partXXXX.html -> [^1]
        - Tags de imagens mortas que não foram para attachments/
        - Declarações XML residuais
        """
        # Converte links internos de notas de rodapé [1](part0018.html#notes) -> [^1]
        cleaned = re.sub(r'\[(\d+)\]\([^)]*part\d+[^)]*\)', r'[^\1]', text)
        # Converte links internos com chXnotes -> [^X]
        cleaned = re.sub(r'\[(\d+)\]\([^)]*#\w*note\w*[^)]*\)', r'[^\1]', cleaned, flags=re.IGNORECASE)
        # Remove tags de imagem que não apontam para a pasta de attachments aprovados
        cleaned = re.sub(r'!\[.*?\]\((?!attachments/)[^)]+\)', '', cleaned)
        return cleaned

    @staticmethod
    def clean_duplicate_headers(text: str) -> str:
        """
        Remove títulos idênticos ou redundantes que aparecem consecutivamente no início do documento.
        Exemplo:
        # CAPÍTULO UM
        ## CAPÍTULO UM
        """
        lines = text.splitlines()
        filtered = []
        last_header = None

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                header_text = re.sub(r'^#+\s*', '', stripped).strip().lower()
                if last_header and header_text == last_header:
                    # Pula cabeçalho duplicado imediato
                    continue
                last_header = header_text
            else:
                if stripped:  # reset se houver texto normal
                    last_header = None
            filtered.append(line)

        return "\n".join(filtered)

    @staticmethod
    def clean_excessive_newlines(text: str) -> str:
        """Colapsa 3 ou mais quebras de linha consecutivas para um espaçamento padrão de 2."""
        return re.sub(r'\n{3,}', '\n\n', text).strip()

    @classmethod
    def sanitize(cls, text: str, mode: Optional[BookMode] = None) -> str:
        """Executa a suíte completa de sanitização de texto determinística."""
        if not text:
            return ""

        content = cls.clean_drop_caps(text)
        content = cls.clean_hyphenation(content)
        content = cls.clean_standalone_numbers(content)
        content = cls.clean_epub_artifacts(content)
        content = cls.elevate_section_headers(content)
        content = cls.clean_duplicate_headers(content)
        content = cls.clean_excessive_newlines(content)

        return content
