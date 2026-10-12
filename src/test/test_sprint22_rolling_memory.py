import unittest
import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from src.agent.tools.pruning import prune_tool_output, prune_tool_messages, MAX_KNOWLEDGE_CHARS
from src.agent.memory.summarizer import RollingMemorySummarizer
from src.domain.session import SessionDomainService
from src.domain.models import TaskResult


class TestSprint22RollingMemory(unittest.IsolatedAsyncioTestCase):
    """
    Suíte de Testes Automatizados da Sprint 22:
    - Tool Output Pruning & Sanitizer
    - Hierarchical Rolling Memory Summarizer
    - Living Session Grounding com TTL Cache
    """

    # =========================================================================
    # 1. Testes de Poda e Sanitização de Ferramentas (pruning.py)
    # =========================================================================

    def test_prune_obsidian_note_content_large(self):
        """Valida que notas massivas do Obsidian são podadas no limite estipulado."""
        huge_content = "# Nota Gigante\n" + ("Conteúdo repetitivo detalhado. " * 200)
        self.assertGreater(len(huge_content), MAX_KNOWLEDGE_CHARS)

        pruned = prune_tool_output("get_obsidian_note_content", huge_content)
        self.assertIn("Conteúdo da nota podado pela Staff Maeve", pruned)
        self.assertLess(len(pruned), len(huge_content))

    def test_prune_obsidian_note_content_small(self):
        """Valida que notas curtas do Obsidian são mantidas 100% intactas."""
        short_content = "# Nota Curta\nEsta é uma nota enxuta de arquitetura."
        pruned = prune_tool_output("get_obsidian_note_content", short_content)
        self.assertEqual(pruned, short_content)

    def test_prune_ticktick_tasks_json_cleans_noise(self):
        """Valida que JSONs complexos do TickTick são higienizados mantendo só campos essenciais."""
        raw_tasks = [
            {
                "id": f"650a{i:020d}",
                "title": f"Tarefa {i}",
                "dueDate": "2026-10-12T21:00:00.000+0000",
                "priority": 3,
                "etag": "abc123xyz",
                "creator": 999999,
                "sortOrder": i * 100,
                "items": [{"check": True}],
                "projectId": "proj_123",
            }
            for i in range(25)
        ]
        raw_json = json.dumps(raw_tasks)
        pruned = prune_tool_output("get_ticktick_tasks", raw_json)

        # Deve reter no máximo 20 tarefas e omitir etag, creator, items
        self.assertIn("tarefas adicionais omitidas", pruned)
        self.assertNotIn("etag", pruned)
        self.assertNotIn("creator", pruned)
        self.assertIn("proj_123", pruned)

    def test_prune_tool_messages_in_history(self):
        """Valida que apenas ToolMessages são alteradas na lista de mensagens."""
        huge_note = "A" * 3000
        messages = [
            HumanMessage(content="Qual o conteúdo da nota?"),
            AIMessage(content="", tool_calls=[{"id": "call_1", "name": "get_obsidian_note_content", "args": {}}]),
            ToolMessage(content=huge_note, tool_call_id="call_1", name="get_obsidian_note_content"),
            AIMessage(content="Aqui está o resumo da nota."),
        ]

        pruned = prune_tool_messages(messages)
        self.assertEqual(len(pruned), 4)
        self.assertIsInstance(pruned[2], ToolMessage)
        self.assertLess(len(pruned[2].content), 3000)
        self.assertIn("Conteúdo da nota podado", pruned[2].content)
        # Human e AI intactos
        self.assertEqual(pruned[0].content, "Qual o conteúdo da nota?")
        self.assertEqual(pruned[3].content, "Aqui está o resumo da nota.")

    # =========================================================================
    # 2. Testes do RollingMemorySummarizer (summarizer.py)
    # =========================================================================

    async def test_rolling_summarizer_short_history_no_compaction(self):
        """Valida que histórico curto (<= 16 mensagens) não é compactado desnecessariamente."""
        summarizer = RollingMemorySummarizer(max_messages_before_summary=16, messages_to_keep=6)
        messages = [
            HumanMessage(content="Oi"),
            AIMessage(content="Olá, Erik! Como posso ajudar?"),
            HumanMessage(content="Cria uma task no TickTick"),
            AIMessage(content="Criando tarefa..."),
        ]

        result = await summarizer.compact_history(messages)
        self.assertEqual(len(result), 4)
        self.assertEqual(result, messages)

    async def test_rolling_summarizer_long_history_compacts_older_messages(self):
        """Valida que histórico longo (> 16 mensagens) tem turnos antigos compactados em <resumo_sessao_consolidada>."""
        summarizer = RollingMemorySummarizer(max_messages_before_summary=10, messages_to_keep=4)

        # Monta histórico de 16 mensagens
        messages = []
        for i in range(8):
            messages.append(HumanMessage(content=f"Pergunta {i}: Analisar arquitetura do módulo {i}."))
            messages.append(AIMessage(content=f"Resposta {i}: Módulo {i} revisado e aprovado com sucesso."))

        result = await summarizer.compact_history(messages)

        # A primeira mensagem deve ser uma SystemMessage com o bloco de resumo
        self.assertIsInstance(result[0], SystemMessage)
        self.assertIn("<resumo_sessao_consolidada>", result[0].content)
        self.assertIn("Módulo", result[0].content)

        # As mensagens recentes mantidas devem ser as últimas 4
        self.assertGreaterEqual(len(result), 5)
        self.assertEqual(result[-1].content, "Resposta 7: Módulo 7 revisado e aprovado com sucesso.")

    async def test_rolling_summarizer_preserves_tool_call_integrity(self):
        """Valida que o ponto de corte nunca quebra o par AIMessage(tool_calls) e ToolMessage."""
        summarizer = RollingMemorySummarizer(max_messages_before_summary=6, messages_to_keep=2)

        messages = [
            HumanMessage(content="Msg 1"),
            AIMessage(content="Msg 2"),
            HumanMessage(content="Msg 3"),
            AIMessage(content="Msg 4"),
            HumanMessage(content="Msg 5"),
            AIMessage(content="", tool_calls=[{"id": "c1", "name": "t1", "args": {}}]),
            ToolMessage(content="Resultado Tool", tool_call_id="c1", name="t1"),
            AIMessage(content="Msg Final"),
        ]

        result = await summarizer.compact_history(messages)

        # Verifica se alguma ToolMessage ficou desacompanhada de AIMessage com tool_calls
        for i, m in enumerate(result):
            if isinstance(m, ToolMessage):
                self.assertGreater(i, 0)
                prev = result[i - 1]
                self.assertIsInstance(prev, AIMessage)
                self.assertTrue(bool(getattr(prev, "tool_calls", None)))

    async def test_rolling_summarizer_accumulates_existing_summary(self):
        """Valida que um resumo pré-existente é acumulado e não perdido na próxima compactação."""
        summarizer = RollingMemorySummarizer(max_messages_before_summary=4, messages_to_keep=2)

        prior_summary = SystemMessage(
            content="# RESUMO CONSOLIDADO DO HISTÓRICO ANTERIOR:\n<resumo_sessao_consolidada>\nDecisão antiga: Usar PostgreSQL no Supabase.\n</resumo_sessao_consolidada>"
        )
        messages = [
            prior_summary,
            HumanMessage(content="Nova pergunta sobre Qdrant"),
            AIMessage(content="Resposta sobre Qdrant"),
            HumanMessage(content="Mais uma pergunta sobre TickTick ID 650000000000000000000001"),
            AIMessage(content="TickTick atualizado"),
            HumanMessage(content="Pergunta final"),
        ]

        result = await summarizer.compact_history(messages)
        first_msg = result[0]
        self.assertIsInstance(first_msg, SystemMessage)
        self.assertIn("PostgreSQL", first_msg.content)
        self.assertIn("650000000000000000000001", first_msg.content)

    # =========================================================================
    # 3. Testes do Living Session Grounding (session.py)
    # =========================================================================

    async def test_living_session_grounding_ttl_cache(self):
        """Valida que get_living_session_context usa cache em chamadas subsequentes e respeita TTL."""
        mock_tasks = MagicMock()
        mock_tasks.get_tasks = AsyncMock(return_value=TaskResult(success=True, message="- [ ] Estudar Cálculo"))

        mock_db = MagicMock()
        mock_db.get_user_insights = AsyncMock(return_value=[{"category": "estudos", "insight": "Foco na P1"}])

        with patch("src.domain.session.get_database_service", return_value=mock_db):
            service = SessionDomainService(task_service=mock_tasks)

            # 1ª chamada: deve consultar tarefas e banco
            block1 = await service.get_living_session_context(user_id="test_user", max_age_seconds=180)
            self.assertIn("Estudar Cálculo", block1)
            self.assertIn("Foco na P1", block1)
            self.assertEqual(mock_tasks.get_tasks.call_count, 1)
            self.assertEqual(mock_db.get_user_insights.call_count, 1)

            # 2ª chamada imediata: deve vir do cache (call_count permanece 1)
            block2 = await service.get_living_session_context(user_id="test_user", max_age_seconds=180)
            self.assertEqual(block1, block2)
            self.assertEqual(mock_tasks.get_tasks.call_count, 1)

            # Invalidação forçada: deve reconstruir e incrementar chamadas
            service.invalidate_cache("test_user")
            block3 = await service.get_living_session_context(user_id="test_user", max_age_seconds=180)
            self.assertEqual(mock_tasks.get_tasks.call_count, 2)


if __name__ == "__main__":
    unittest.main()
