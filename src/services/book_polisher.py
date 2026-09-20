import os
import re
import asyncio
import logging
from typing import Optional, List, Tuple

from src.services.book_parser.base import BookMode
from src.services.book_parser.text_sanitizer import TextSanitizer
from src.agent.engine import create_chat_model
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger("SurgicalBookPolisher")

SURGICAL_SYSTEM_PROMPT = """Você é um assistente cirúrgico de formatação de Markdown para o Obsidian Vault.
Sua missão é transformar o bloco de texto fornecido em Markdown elegante, profissional e bem estruturado:

1. TABELAS: Se houver dados tabulares (ex: listas de armas, estatísticas, perícias, valores numéricos em colunas), converta-os em tabelas GFM válidas (| Coluna 1 | Coluna 2 |).
2. CALLOUTS: Se houver avisos, regras especiais, dicas do mestre, exercícios práticos ou exemplos, formate-os usando a sintaxe de Callout do Obsidian (> [!NOTE], > [!TIP], > [!DANGER], > [!EXAMPLE]).
3. MATEMÁTICA: Se houver fórmulas científicas ou equações com notação LaTeX, envolva-as em MathJax ($...$ em linha ou $$...$$ em bloco).
4. REGRA MANDATÓRIA (LOSSLESS FORMATTING):
   - NUNCA resuma, NUNCA omita e NUNCA altere nenhuma palavra, número, nome ou regra.
   - NÃO adicione comentários, introduções ou explicações (ex: "Aqui está o markdown:").
   - Preserve integralmente todas as tags de imagens do Obsidian (ex: ![[attachments/...]]).

Retorne estritamente o bloco formatado em Markdown."""

class SurgicalBookPolisher:
    """
    Polidor cirúrgico de capítulos de livros:
    Aplica primeiro higienização 100% determinística em CPU ($0.00).
    Em seguida, detecta anomalias estruturais (tabelas desalinhadas, caixas de regras, fórmulas)
    e aciona o modelo Fast (GPT-5.6 Luna) cirurgicamente apenas nesses blocos (<10% do volume),
    garantindo altíssima qualidade visual com custo desprezível em centavos.
    """

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or os.getenv("MAEVE_FAST_MODEL", "gpt-5.6-luna")
        self._llm = None

    @property
    def llm(self):
        if self._llm is None:
            self._llm = create_chat_model(self.model_name, temperature=0, max_tokens=4096)
        return self._llm

    @staticmethod
    def should_polish_block(block: str) -> bool:
        """
        Detector determinístico de anomalia estrutural:
        Verifica se o bloco se beneficiaria de formatação avançada por LLM (tabelas, callouts, fórmulas).
        Se for apenas parágrafo de texto corrido, retorna False (economizando 100% de tokens).
        """
        text = block.strip()
        if len(text) < 40:
            return False

        # 1. Já está perfeitamente formatado como tabela ou callout?
        if text.startswith("> [!") or (text.startswith("|") and text.endswith("|")):
            return False

        # 2. Detecção de dados tabulares não formatados:
        # Linhas consecutivas com números/stats separados por múltiplos espaços
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if len(lines) >= 2:
            tab_like_lines = 0
            for l in lines:
                # Linha com palavras seguidas de múltiplos espaços e números/dados
                if re.search(r'[\w\s]{2,20}\s{2,}\d+', l) or "\t" in l:
                    tab_like_lines += 1
            if tab_like_lines >= 2 and tab_like_lines / len(lines) >= 0.4:
                return True

        # 3. Detecção de caixas de regras / exercícios / avisos soltos
        first_line_lower = lines[0].lower() if lines else ""
        if any(first_line_lower.startswith(k) for k in [
            "quadro", "exercício", "exercicio", "meditação", "meditacao",
            "dica do mestre", "dica de mestre", "regra opcional", "ameaça",
            "atenção", "atencao", "importante", "nota:", "observação:", "observacao:"
        ]):
            return True

        # 4. Detecção de blocos de atributos / fichas de RPG
        if re.search(r'\b(FOR|AGI|INT|VIG|PRE)\s+\d\b', text) and re.search(r'\b\d+d\d+\b', text):
            return True

        # 5. Detecção de LaTeX solto sem delimitadores $ ou $$
        if re.search(r'(?<!\$)\\(int|sum|frac|sqrt|partial|alpha|beta|sigma|mathbb|mathbf)(?!\$)', text):
            return True

        return False

    async def polish_block_with_llm(self, block: str, chapter_title: str) -> str:
        """Envia um bloco complexo específico para formatação cirúrgica pelo Luna."""
        try:
            prompt = (
                f"Contexto do Capítulo: {chapter_title}\n\n"
                f"Bloco de texto a ser formatado:\n"
                f"```text\n{block}\n```"
            )
            messages = [
                SystemMessage(content=SURGICAL_SYSTEM_PROMPT),
                HumanMessage(content=prompt)
            ]

            response = await self.llm.ainvoke(messages)
            content = response.content.strip()

            # Remove tags de código ```markdown ... ``` caso o modelo tenha envolvido
            if content.startswith("```"):
                content = re.sub(r'^```(?:markdown)?\n', '', content)
                content = re.sub(r'\n```$', '', content)
                content = content.strip()

            # Safeguard: se a resposta for vazia ou estranhamente truncada (<30% do original), preserva original
            if len(content) < len(block) * 0.3:
                logger.warning(f"Resposta da LLM suspeita de truncamento para bloco em '{chapter_title}'. Preservando original.")
                return block

            return content
        except Exception as e:
            logger.warning(f"Falha ao polir bloco via LLM em '{chapter_title}': {e}. Preservando original.")
            return block

    async def polish_chapter(
        self,
        chapter_text: str,
        chapter_title: str,
        mode: BookMode = BookMode.GENERAL
    ) -> Tuple[str, int]:
        """
        Executa o pipeline cirúrgico completo para um capítulo:
        1. Higienização determinística em CPU.
        2. Fatiamento em blocos lógicos.
        3. Identificação e polimento concorrente dos blocos anômalos.
        4. Recomposição lossless do capítulo.
        Retorna (texto_polido, total_blocos_llm_processados).
        """
        # 1. Limpeza de CPU
        sanitized = TextSanitizer.sanitize(chapter_text, mode)

        # 2. Fatiamento em blocos por quebra dupla de linha
        raw_blocks = sanitized.split("\n\n")
        polished_blocks: List[str] = list(raw_blocks)
        tasks = []
        indices_to_polish = []

        # 3. Detecta blocos anômalos para polimento cirúrgico
        for idx, b in enumerate(raw_blocks):
            if self.should_polish_block(b):
                indices_to_polish.append(idx)
                tasks.append(self.polish_block_with_llm(b, chapter_title))

        # 4. Executa em paralelo apenas os blocos identificados
        if tasks:
            logger.info(
                f"Polimento cirúrgico em '{chapter_title}': {len(tasks)} de {len(raw_blocks)} blocos "
                f"requerem LLM ({len(tasks)/len(raw_blocks)*100:.1f}% do capítulo)."
            )
            results = await asyncio.gather(*tasks)
            for idx, polished_text in zip(indices_to_polish, results):
                polished_blocks[idx] = polished_text

        final_text = "\n\n".join(polished_blocks).strip()
        return final_text, len(tasks)
