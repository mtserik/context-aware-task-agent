import unittest
from src.services.book_parser.text_sanitizer import TextSanitizer

class TestTextSanitizer(unittest.TestCase):
    """Testes unitários para o sanitizador determinístico de texto em CPU."""

    def test_clean_drop_caps(self):
        """Valida que letras capitulares isoladas no início de parágrafos são unidas."""
        text = "B\noas-vindas a Ordem Paranormal RPG."
        cleaned = TextSanitizer.clean_drop_caps(text)
        self.assertEqual(cleaned, "Boas-vindas a Ordem Paranormal RPG.")

        # Teste com aspas/pontuação
        text_quote = "\u201cO\ns segredos do universo são profundos.\u201d"
        cleaned_quote = TextSanitizer.clean_drop_caps(text_quote)
        self.assertEqual(cleaned_quote, "\u201cOs segredos do universo são profundos.\u201d")

    def test_clean_hyphenation(self):
        """Valida a união de palavras partidas no final de linha com hífen."""
        text = "Os agen-\ntes da Ordem investigam rituais para-\nnormais."
        cleaned = TextSanitizer.clean_hyphenation(text)
        self.assertEqual(cleaned, "Os agentes da Ordem investigam rituais paranormais.")

    def test_clean_standalone_numbers(self):
        """Valida a eliminação de números de página soltos de rodapé."""
        text = "Primeiro parágrafo.\n\n7\n\nSegundo parágrafo."
        cleaned = TextSanitizer.clean_standalone_numbers(text)
        self.assertNotIn("\n7\n", cleaned)
        self.assertIn("Primeiro parágrafo.", cleaned)
        self.assertIn("Segundo parágrafo.", cleaned)

    def test_elevate_section_headers(self):
        """Valida promoção de linhas isoladas em caixa alta para cabeçalhos Markdown."""
        text = "Introdução ao sistema.\n\nO QUE É RPG?\n\nRPG é uma sigla.\n\n1d20\n\nEXEMPLO\n\nOutro texto."
        cleaned = TextSanitizer.elevate_section_headers(text)
        self.assertIn("### O Que É Rpg?", cleaned)
        self.assertIn("### Exemplo", cleaned)
        # 1d20 não deve virar cabeçalho
        self.assertNotIn("### 1D20", cleaned)

    def test_clean_epub_artifacts(self):
        """Valida conversão de notas de rodapé de EPUB e remoção de links mortos de imagens."""
        text = "Estudos mostram os benefícios.[1](part0018.html#ch01notes1)\n\n![logo](../images/00001.gif)\n\n![[attachments/cover.jpg]]"
        cleaned = TextSanitizer.clean_epub_artifacts(text)
        self.assertIn("[^1]", cleaned)
        self.assertNotIn("part0018.html", cleaned)
        self.assertNotIn("../images/00001.gif", cleaned)
        self.assertIn("![[attachments/cover.jpg]]", cleaned)

    def test_clean_duplicate_headers(self):
        """Valida deduplicação de cabeçalhos redundantes imediatos."""
        text = "# CAPÍTULO UM\n## CAPÍTULO UM\n\nTexto do capítulo."
        cleaned = TextSanitizer.clean_duplicate_headers(text)
        self.assertEqual(cleaned.count("CAPÍTULO UM"), 1)

if __name__ == "__main__":
    unittest.main()
