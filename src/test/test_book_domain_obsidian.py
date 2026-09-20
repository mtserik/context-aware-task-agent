import os
import unittest
import asyncio
import tempfile
import fitz

from src.services.obsidian import ObsidianService
from src.domain.books import BookDomainService
from src.services.book_parser.base import BookMode

class TestBookDomainObsidian(unittest.TestCase):
    """Testes unitários para BookDomainService e geração de MOC/Capítulos no Vault."""

    def setUp(self):
        self.temp_vault = tempfile.mkdtemp()
        self.obsidian = ObsidianService()
        self.obsidian.vault_path = self.temp_vault
        self.domain_service = BookDomainService(obsidian_service=self.obsidian)

    def tearDown(self):
        import shutil
        if os.path.exists(self.temp_vault):
            shutil.rmtree(self.temp_vault)

    def test_ingest_book_flow(self):
        """Valida a criação de pasta, MOC, capítulos e attachments no Vault."""
        # Cria um PDF sintético de teste
        doc = fitz.open()
        p1 = doc.new_page()
        p1.insert_text((50, 50), "Capítulo 1: Introdução ao Conhecimento")
        p1.insert_text((50, 80), "Este é o primeiro capítulo de estudo profundo.")

        p2 = doc.new_page()
        p2.insert_text((50, 50), "Capítulo 2: Teoremas Centrais")
        p2.insert_text((50, 80), "Teorema 2.1: Toda sequência limitada possui subsequência convergente.")

        doc.set_toc([
            [1, "Introdução ao Conhecimento", 1],
            [1, "Teoremas Centrais", 2]
        ])

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
            pdf_path = tf.name

        try:
            doc.save(pdf_path)
            doc.close()

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                self.domain_service.ingest_book(
                    file_path=pdf_path,
                    filename="livro-matematica-teste.pdf",
                    mode="math",
                    sync_git=False,
                    sync_vector_db=False
                )
            )
            loop.close()

            self.assertTrue(result["success"])
            self.assertEqual(result["chapter_count"], 2)
            self.assertEqual(result["mode"], "math")

            # Verifica se os arquivos foram criados no Vault
            book_folder = os.path.join(self.temp_vault, "Recursos", "Livros", result["title"])
            self.assertTrue(os.path.exists(book_folder))

            moc_file = os.path.join(book_folder, f"{result['title']}.md")
            self.assertTrue(os.path.exists(moc_file))

            with open(moc_file, "r", encoding="utf-8") as f:
                moc_text = f.read()
            self.assertIn("Ficha Técnica", moc_text)
            self.assertIn("Sumário & Capítulos", moc_text)
            self.assertIn("Introdução ao Conhecimento", moc_text)

            # Verifica o arquivo do primeiro capítulo
            chap1_file = os.path.join(book_folder, "01 - Introdução ao Conhecimento.md")
            self.assertTrue(os.path.exists(chap1_file))

            with open(chap1_file, "r", encoding="utf-8") as f:
                chap1_text = f.read()
            self.assertIn("livro:", chap1_text)
            self.assertIn("Índice do Livro", chap1_text)

        finally:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)

if __name__ == "__main__":
    unittest.main()
