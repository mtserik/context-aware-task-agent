import os
import unittest
import asyncio
import tempfile
import fitz

from src.services.book_parser.base import BookMode
from src.services.book_parser.pdf_parser import PDFBookParser

class TestBookParsers(unittest.TestCase):
    """Testes unitários e de integração para PDFBookParser e renderizadores."""

    def setUp(self):
        self.parser = PDFBookParser()

    def test_clean_title(self):
        """Valida a sanitização de títulos com hashes e extensões."""
        title1 = self.parser._clean_title("ordem-paranormal-rpg-v1-3-lyfxjj.pdf")
        self.assertIn("Ordem Paranormal", title1)
        self.assertNotIn("lyfxjj", title1)

        title2 = self.parser._clean_title("analise_no_rn_elon_lages.pdf")
        self.assertIn("Analise no RN", title2)

    def test_parse_synthetic_math_pdf(self):
        """Valida a extração de PDF sintético com teoremas e callouts MathJax."""
        doc = fitz.open()
        for i in range(2):
            page = doc.new_page()
            page.insert_text((50, 50), f"# Capítulo {i+1}\n")
            page.insert_text((50, 100), "Teorema 1.2: Todo conjunto compacto em R^n é fechado e limitado.\n")
            page.insert_text((50, 130), "Demonstração: Suponha por contradição que não seja limitado.\n")

        doc.set_toc([
            [1, "Capítulo 1: Compacidade", 1],
            [1, "Capítulo 2: Conexidade", 2]
        ])

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
            temp_path = tf.name

        try:
            doc.save(temp_path)
            doc.close()

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            parsed_book = loop.run_until_complete(
                self.parser.parse(temp_path, mode=BookMode.MATH, extract_images=False)
            )
            loop.close()

            self.assertEqual(len(parsed_book.chapters), 2)
            self.assertEqual(parsed_book.mode, BookMode.MATH)
            self.assertIn("> [!THEOREM]", parsed_book.chapters[0].content_markdown)
            self.assertIn("> [!PROOF]", parsed_book.chapters[0].content_markdown)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_parse_ordem_paranormal_slice(self):
        """Valida a extração de um trecho real de 10 páginas do Ordem Paranormal RPG."""
        rpg_path = r"E:\mtserik\Documents\RPGs\Ordem Paranormal\ordem-paranormal-rpg-v1-3-lyfxjj.pdf"
        if not os.path.exists(rpg_path):
            self.skipTest("Arquivo Ordem Paranormal não encontrado.")

        # Cria sub-PDF temporário de 10 páginas para teste rápido
        doc = fitz.open(rpg_path)
        subdoc = fitz.open()
        subdoc.insert_pdf(doc, from_page=0, to_page=10)
        # Mantém TOC parcial
        subdoc.set_toc([
            [1, "Pré-textuais", 1],
            [1, "Prefácio", 5]
        ])

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
            temp_path = tf.name

        try:
            subdoc.save(temp_path)
            subdoc.close()
            doc.close()

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            parsed_book = loop.run_until_complete(
                self.parser.parse(temp_path, filename="ordem-paranormal-rpg-v1-3-lyfxjj.pdf", extract_images=True)
            )
            loop.close()

            self.assertEqual(parsed_book.mode, BookMode.RPG)
            self.assertGreater(len(parsed_book.chapters), 0)
            self.assertIsNotNone(parsed_book.cover_image)
            print(f"\n[PARSER RPG TESTE] Capítulos: {len(parsed_book.chapters)}, Capa: {parsed_book.cover_image.name if parsed_book.cover_image else 'None'}")
            print(f"Total de Anexos aprovados: {len(parsed_book.attachments)}")
            for ch in parsed_book.chapters:
                print(f" - {ch.title} (pág {ch.start_page}-{ch.end_page}, ~{ch.estimated_tokens} tokens)")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

if __name__ == "__main__":
    unittest.main()
