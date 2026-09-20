import unittest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from src.services.book_polisher import SurgicalBookPolisher

class TestSurgicalBookPolisher(unittest.TestCase):
    """Testes unitários para o polidor cirúrgico híbrido de livros."""

    def setUp(self):
        self.polisher = SurgicalBookPolisher(model_name="gpt-5.6-luna")

    def test_should_polish_block_filtering(self):
        """Valida que blocos normais são ignorados (0 tokens) e anomalias são detectadas."""
        # 1. Parágrafo comum de narrativa -> False
        p_normal = (
            "A atenção plena é a capacidade humana básica de estar totalmente presente, "
            "consciente de onde estamos e do que estamos fazendo, e não excessivamente reativo."
        )
        self.assertFalse(self.polisher.should_polish_block(p_normal))

        # 2. Já formatado como Callout -> False
        p_callout = "> [!NOTE] Dica do Mestre\n> Sempre peça testes de Percepção."
        self.assertFalse(self.polisher.should_polish_block(p_callout))

        # 3. Tabela não formatada com múltiplas colunas e números -> True
        p_table = (
            "Espada Longa   1d8/1d10   19/x2   Marcial   Corte   R$ 15\n"
            "Adaga          1d4        19/x2   Simples   Perf    R$ 2\n"
            "Machado        1d8        x3      Marcial   Corte   R$ 20"
        )
        self.assertTrue(self.polisher.should_polish_block(p_table))

        # 4. Caixa de aviso / Exercício -> True
        p_box = "Quadro: Meditação da respiração\nSente-se com a coluna ereta e feche os olhos."
        self.assertTrue(self.polisher.should_polish_block(p_box))

        # 5. Ficha de RPG com atributos e dados -> True
        p_rpg = "Atributos: FOR 3, AGI 2, INT 1, VIG 2, PRE 1. Ataque: 2d20+5, Dano: 1d8+3."
        self.assertTrue(self.polisher.should_polish_block(p_rpg))

    def test_polish_chapter_selective_execution(self):
        """Valida que apenas blocos que necessitam de LLM são enviados para processamento."""
        chapter_md = (
            "# Capítulo 1: Fundamentos\n\n"
            "B\noas-vindas ao manual de regras.\n\n"
            "Espada Longa   1d8   19/x2   Marcial\n"
            "Adaga          1d4   19/x2   Simples\n\n"
            "Este é o texto final de encerramento."
        )

        mock_llm_response = MagicMock()
        mock_llm_response.content = "| Arma | Dano | Crítico | Tipo |\n|---|---|---|---|\n| Espada Longa | 1d8 | 19/x2 | Marcial |\n| Adaga | 1d4 | 19/x2 | Simples |"

        with patch.object(self.polisher, "polish_block_with_llm", new_callable=AsyncMock) as mock_polish_block:
            mock_polish_block.return_value = mock_llm_response.content

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            final_md, count = loop.run_until_complete(
                self.polisher.polish_chapter(chapter_md, chapter_title="Capítulo 1")
            )
            loop.close()

            # Apenas 1 bloco (a tabela de armas) deve ter acionado a LLM
            self.assertEqual(count, 1)
            mock_polish_block.assert_called_once()
            # O texto normal deve ter sido limpo via CPU (Drop cap 'Boas-vindas')
            self.assertIn("Boas-vindas ao manual de regras.", final_md)
            self.assertIn("| Espada Longa | 1d8 |", final_md)

if __name__ == "__main__":
    unittest.main()
