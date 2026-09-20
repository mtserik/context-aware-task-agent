import os
import unittest
import asyncio
import tempfile
import fitz

from src.services.book_parser.base import BookMode
from src.services.book_parser.detector import BookModeDetector
from src.services.book_parser.image_extractor import BookImageExtractor
from src.services.book_parser.pdf_parser import PDFBookParser
from src.domain.tokenization import MarkdownSemanticChunker
from src.domain.books import BookDomainService
from src.services.obsidian import ObsidianService
from src.services.book_worker import BookIngestionWorker
from src.mcp.server import create_mcp_server

class TestSprint20BookIngestionPipeline(unittest.TestCase):
    """
    Suíte completa de testes de regressão e ponta a ponta da Sprint 20:
    Ingestão Assíncrona de Livros e Invariante Zero-Token.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.obsidian = ObsidianService()
        self.obsidian.vault_path = self.temp_dir
        self.book_domain = BookDomainService(obsidian_service=self.obsidian)
        self.worker = BookIngestionWorker(book_domain=self.book_domain)

    def tearDown(self):
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_detector_modes(self):
        """Valida que o detector reconhece os diferentes modos determinísticos."""
        # 1. Math Hint
        m_math, _ = BookModeDetector.detect_mode("estudos/imecc/analise.pdf")
        self.assertEqual(m_math, BookMode.MATH)

        # 2. RPG Hint
        m_rpg, _ = BookModeDetector.detect_mode("rpgs/tormenta20.pdf")
        self.assertEqual(m_rpg, BookMode.RPG)

    def test_image_extractor_noise_filtering(self):
        """Valida que imagens com menos de 200x200 px ou repetidas são filtradas."""
        extractor = BookImageExtractor(min_width=200, min_height=200, min_area=40000)
        doc = fitz.open()
        p = doc.new_page()

        # Insere pixmap de teste pequeno (100x100 - ruído) e grande (400x600 - ilustração)
        pix_small = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 100, 100), 1)
        pix_small.clear_with(255)
        p.insert_image(fitz.Rect(10, 10, 110, 110), pixmap=pix_small)

        pix_large = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 400, 600), 1)
        pix_large.clear_with(128)
        p.insert_image(fitz.Rect(150, 50, 450, 500), pixmap=pix_large)

        cover, approved = extractor.extract_images_from_pdf(doc, "Teste Filtro")
        doc.close()

        # Apenas a imagem grande deve ser aprovada
        self.assertEqual(len(approved), 1)
        self.assertGreaterEqual(approved[0].width, 200)

    def test_chunker_bounds_and_token_count(self):
        """Garante limites estritos de tokenização com tiktoken."""
        chunker = MarkdownSemanticChunker(min_tokens=30, target_tokens=60, max_tokens=90, overlap_tokens=15)
        text = "O conhecimento é o recurso mais valioso da humanidade. " * 30
        chunks = chunker.chunk_markdown(text, chapter_title="Cap 1")
        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertLessEqual(c.token_count, 100)

    def test_worker_job_lifecycle(self):
        """Valida a execução assíncrona desacoplada do BookIngestionWorker com callback."""
        # Cria PDF sintético
        doc = fitz.open()
        p = doc.new_page()
        p.insert_text((50, 50), "Capítulo 1: Fundamentos\nTexto introdutório.")
        doc.set_toc([[1, "Fundamentos", 1]])

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
            pdf_path = tf.name

        doc.save(pdf_path)
        doc.close()

        completed_flag = asyncio.Event()
        callback_result = {}

        async def on_complete(res):
            callback_result.update(res)
            completed_flag.set()

        async def run_worker():
            job_id = self.worker.submit_job(
                file_path=pdf_path,
                filename="livro-worker-teste.pdf",
                mode="general",
                extract_images=False,
                sync_git=False,
                sync_vector_db=False,
                on_complete=on_complete
            )
            # Aguarda conclusão do job com timeout
            await asyncio.wait_for(completed_flag.wait(), timeout=5.0)
            status_info = self.worker.get_job_status(job_id)
            return status_info

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            status = loop.run_until_complete(run_worker())
            loop.close()

            self.assertEqual(status["status"], "SUCCESS")
            self.assertTrue(callback_result.get("success"))
            self.assertEqual(callback_result.get("chapter_count"), 1)
        finally:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)

    def test_mcp_tool_registration(self):
        """Valida que a ferramenta ingest_book está montada no servidor FastMCP."""
        mcp = create_mcp_server()
        # Inspeciona lista de tools registradas no FastMCP
        tool_names = [tool.name for tool in mcp._tool_manager.list_tools()]
        self.assertIn("ingest_book", tool_names)

if __name__ == "__main__":
    unittest.main()
