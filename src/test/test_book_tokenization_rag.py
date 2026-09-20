import unittest
from src.domain.tokenization import MarkdownSemanticChunker

class TestMarkdownSemanticChunker(unittest.TestCase):
    """Testes unitários para o segmentador semântico de Markdown para RAG."""

    def setUp(self):
        self.chunker = MarkdownSemanticChunker(
            min_tokens=50,
            target_tokens=100,
            max_tokens=150,
            overlap_tokens=20
        )

    def test_count_tokens(self):
        text = "Maeve é uma parceira executiva e assistente de alto nível."
        tokens = self.chunker.count_tokens(text)
        self.assertGreater(tokens, 5)

    def test_preserve_math_blocks(self):
        """Garante que equações em bloco $$ não sejam divididas no meio."""
        md = """# Análise Real

Seja f uma função contínua em um compacto K.

$$
\int_a^b f(x)dx = F(b) - F(a)
$$

Este é o Teorema Fundamental do Cálculo.
"""
        chunks = self.chunker.chunk_markdown(md, chapter_title="Capítulo 1")
        self.assertGreaterEqual(len(chunks), 1)
        # O bloco $$ deve estar íntegro em um dos chunks
        found_math = any(r"\int_a^b f(x)dx" in c.content for c in chunks)
        self.assertTrue(found_math)

    def test_overlap_and_indexing(self):
        """Verifica se os índices dos chunks são ordenados e têm contagem de tokens."""
        long_text = ("O Ordem Paranormal RPG é um sistema baseado em d20. "
                     "Os personagens investigam mistérios sobrenaturais e enfrentam o Outro Lado. " * 30)
        chunks = self.chunker.chunk_markdown(long_text, chapter_title="Introdução")
        self.assertGreater(len(chunks), 1)
        for i, c in enumerate(chunks, start=1):
            self.assertEqual(c.chunk_index, i)
            self.assertEqual(c.total_chunks, len(chunks))
            self.assertLessEqual(c.token_count, 160)

if __name__ == "__main__":
    unittest.main()
