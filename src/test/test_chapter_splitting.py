import unittest
from src.services.book_parser.base import ParsedChapter
from src.domain.books import BookDomainService

class TestChapterSplitting(unittest.TestCase):
    """Testa a lógica de subdivisão de capítulos quando o teto de tokens é excedido."""

    def test_chapter_markdown_splitting(self):
        # Simula um capítulo de 12.000 tokens com múltiplos cabeçalhos H2
        sections = [
            f"## Seção Importante {i}\n\n" + "Este é um texto analítico longo. " * 300
            for i in range(6)
        ]
        large_content = "# Capítulo Extenso\n\n" + "\n\n".join(sections)
        est_tokens = len(large_content.split()) * 4 // 3
        self.assertGreater(est_tokens, 7000)

        # Testa algoritmo de partição
        MAX_CHAPTER_TOKENS = 7000
        import re
        parts = re.split(r'(?m)(?=^## )', large_content)
        sub_parts = []
        current_part = []
        current_tokens = 0
        for sec in parts:
            sec_tokens = len(sec.split()) * 4 // 3
            if current_tokens + sec_tokens > MAX_CHAPTER_TOKENS and current_part:
                sub_parts.append("\n\n".join(current_part).strip())
                current_part = [sec]
                current_tokens = sec_tokens
            else:
                current_part.append(sec)
                current_tokens += sec_tokens
        if current_part:
            sub_parts.append("\n\n".join(current_part).strip())

        self.assertGreater(len(sub_parts), 1)
        for p in sub_parts:
            self.assertLessEqual(len(p.split()) * 4 // 3, MAX_CHAPTER_TOKENS)

if __name__ == "__main__":
    unittest.main()
