import os
import unittest
import fitz
from src.services.book_parser.base import BookMode
from src.services.book_parser.detector import BookModeDetector

class TestBookModeDetector(unittest.TestCase):
    """Testes unitários e de integração para o classificador heurístico BookModeDetector."""

    def test_explicit_hint_override(self):
        """Testa se hint_mode sobrepõe qualquer classificação automática."""
        mode, diag = BookModeDetector.detect_mode("dummy/path/any_book.pdf", hint_mode="math")
        self.assertEqual(mode, BookMode.MATH)
        self.assertIn("explicitamente", diag["reason"])

        mode_rpg, _ = BookModeDetector.detect_mode("dummy/path/any_book.pdf", hint_mode="rpg")
        self.assertEqual(mode_rpg, BookMode.RPG)

        mode_narrative, _ = BookModeDetector.detect_mode("dummy/path/any_book.pdf", hint_mode="narrative")
        self.assertEqual(mode_narrative, BookMode.NARRATIVE)

    def test_real_rpg_pdf_ordem_paranormal(self):
        """Testa a classificação no arquivo real Ordem Paranormal RPG."""
        pdf_path = r"E:\mtserik\Documents\RPGs\Ordem Paranormal\ordem-paranormal-rpg-v1-3-lyfxjj.pdf"
        if not os.path.exists(pdf_path):
            self.skipTest("Arquivo do Ordem Paranormal não encontrado no disco E.")

        mode, diag = BookModeDetector.detect_mode(pdf_path)
        self.assertEqual(mode, BookMode.RPG)
        self.assertGreater(diag["final_scores"]["rpg"], 5.0)
        self.assertGreater(diag["layer1_toc_scores"]["rpg_matches"], 3)
        print(f"\n[DIAGNÓSTICO ORDEM PARANORMAL]: {diag['reason']}")
        print(f"Scores finais: {diag['final_scores']}")
        print(f"Layer 2 Physical: {diag['layer2_physical_scores']}")

    def test_synthetic_math_pdf_detection(self):
        """Cria um PDF sintético com TOC e termos matemáticos e valida a detecção de MATH."""
        import tempfile
        doc = fitz.open()
        # Adiciona 3 páginas com termos matemáticos
        for i in range(3):
            page = doc.new_page()
            page.insert_text((50, 50), f"Capítulo {i+1}: Espaços Métricos e Topologia")
            page.insert_text((50, 100), "Teorema 1.1: Seja E um espaço vetorial normado sobre R.")
            page.insert_text((50, 120), "Demonstração: Consideremos a sequência de Cauchy para todo epsilon > 0.")
            page.insert_text((50, 140), "Exercícios propostos: Mostre que f é contínua.")

        doc.set_toc([
            [1, "Capítulo 1: Espaços Métricos", 1],
            [1, "Capítulo 2: Teoremas de Ponto Fixo", 2],
            [1, "Capítulo 3: Cálculo Diferencial", 3]
        ])

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
            temp_path = tf.name

        try:
            doc.save(temp_path)
            doc.close()

            mode, diag = BookModeDetector.detect_mode(temp_path)
            self.assertEqual(mode, BookMode.MATH)
            self.assertGreater(diag["final_scores"]["math"], 3.0)
            self.assertGreater(diag["layer1_toc_scores"]["math_matches"], 1)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_synthetic_narrative_detection(self):
        """Cria um PDF mono-colunar sem imagens nem termos técnicos para validar NARRATIVE."""
        import tempfile
        doc = fitz.open()
        for i in range(3):
            page = doc.new_page()
            page.insert_text((50, 50), f"Capítulo {i+1}")
            # Gera parágrafos densos de prosa
            prose = ("Era uma tarde cinzenta e o vento sussurrava entre os galhos da velha macieira. "
                     "Ele caminhou devagar pela estrada de terra batida, pensando nas palavras do velho pescador. "
                     "Nada daquilo parecia fazer sentido agora, mas o tempo haveria de revelar a verdade oculta. " * 8)
            page.insert_textbox(fitz.Rect(50, 80, 500, 700), prose)

        doc.set_toc([
            [1, "Capítulo 1: A Partida", 1],
            [1, "Capítulo 2: O Retorno", 2],
            [1, "Capítulo 3: O Desfecho", 3]
        ])

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
            temp_path = tf.name

        try:
            doc.save(temp_path)
            doc.close()

            mode, diag = BookModeDetector.detect_mode(temp_path)
            self.assertEqual(mode, BookMode.NARRATIVE)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

if __name__ == "__main__":
    unittest.main()
