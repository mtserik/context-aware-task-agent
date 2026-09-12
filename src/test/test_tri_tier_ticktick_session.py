import sys
import unittest
import asyncio
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import MagicMock, AsyncMock, patch

# Configure mocks for optional/container-only external packages
for mod in [
    'httpx', 'psycopg_pool', 'qdrant_client', 'qdrant_client.models', 'qdrant_client.http',
    'dotenv', 'tavily', 'langchain_openai', 'langchain_core', 'langchain_core.messages',
    'langchain_core.tools', 'langchain_anthropic', 'langgraph', 'langgraph.graph',
    'langgraph.checkpoint', 'langgraph.checkpoint.postgres', 'langgraph.checkpoint.postgres.aio',
    'langgraph.checkpoint.memory', 'langgraph.prebuilt'
]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

from src.domain.tasks import TaskDomainService, normalize_ticktick_date
from src.domain.session import SessionDomainService
from src.domain.temporal import resolve_temporal_context
from src.services.database import DatabaseService


class TestSmartTaskResolution(unittest.IsolatedAsyncioTestCase):
    """Testes para o algoritmo de Smart Task Resolution do TaskDomainService."""

    def setUp(self):
        self.mock_ticktick = MagicMock()
        self.sample_tasks = [
            {"id": "66df10a9e4b0c20a11223344", "title": "Estudar Álgebra Linear e RAG", "projectId": "p1"},
            {"id": "66df20b0e4b0c20a55667788", "title": "Comprar ração pro gato", "projectId": "inbox"},
            {"id": "66df30c1e4b0c20a9900aabb", "title": "Deploy da Maeve na Railway", "projectId": "p2"},
            {"id": "66df40d2e4b0c20accbbddee", "title": "Almoço com a equipe", "projectId": "inbox"},
        ]
        self.mock_ticktick.get_tasks = AsyncMock(return_value=self.sample_tasks)
        self.mock_ticktick.get_task_by_id = AsyncMock(side_effect=lambda tid: next((t for t in self.sample_tasks if t["id"] == tid), None))
        self.service = TaskDomainService(ticktick_service=self.mock_ticktick)

    async def test_find_by_exact_hex_id(self):
        """Busca por ID hexadecimal exato de 24 caracteres do TickTick."""
        task = await self.service.find_task_by_identifier("66df20b0e4b0c20a55667788")
        self.assertIsNotNone(task)
        self.assertEqual(task["title"], "Comprar ração pro gato")

    async def test_find_by_exact_title_case_insensitive(self):
        """Busca por título exato com variação de maiúsculas/minúsculas."""
        task = await self.service.find_task_by_identifier("comprar ração pro gato")
        self.assertIsNotNone(task)
        self.assertEqual(task["id"], "66df20b0e4b0c20a55667788")

    async def test_find_by_partial_keyword(self):
        """Busca por termo chave / palavra-chave representativa."""
        task = await self.service.find_task_by_identifier("álgebra linear")
        self.assertIsNotNone(task)
        self.assertEqual(task["id"], "66df10a9e4b0c20a11223344")

        task2 = await self.service.find_task_by_identifier("railway")
        self.assertIsNotNone(task2)
        self.assertEqual(task2["id"], "66df30c1e4b0c20a9900aabb")

    async def test_find_returns_none_for_unknown_task(self):
        """Retorna None quando não encontra correspondência confiável."""
        task = await self.service.find_task_by_identifier("viajar para marte")
        self.assertIsNone(task)


class TestTickTickDateNormalization(unittest.TestCase):
    """Testes para o conversor estrito de datas para TickTick MCP."""

    def test_all_day_task_converts_to_sp_utc(self):
        """Data YYYY-MM-DD no fuso de São Paulo (UTC-3) vira 03:00 UTC."""
        utc_iso = normalize_ticktick_date("2026-09-15")
        self.assertEqual(utc_iso, "2026-09-15T03:00:00.000+0000")

    def test_preserves_valid_utc_iso(self):
        """Data já em formato ISO UTC com +0000 é preservada."""
        valid_iso = "2026-09-15T15:00:00.000+0000"
        self.assertEqual(normalize_ticktick_date(valid_iso), valid_iso)

    def test_converts_sp_offset_to_utc(self):
        """Data com offset -03:00 é convertida para UTC +0000."""
        input_date = "2026-09-15T10:00:00-03:00"
        res = normalize_ticktick_date(input_date)
        self.assertIn("+0000", res)
        self.assertIn("13:00:00", res)


class TestTaskDomainOperations(unittest.IsolatedAsyncioTestCase):
    """Testes para as operações de conclusão, deleção e reagendamento com Smart Resolution."""

    def setUp(self):
        self.mock_ticktick = MagicMock()
        self.service = TaskDomainService(ticktick_service=self.mock_ticktick)
        self.sample_tasks = [
            {"id": "66df10a9e4b0c20a11223344", "title": "Estudar Álgebra Linear e RAG", "projectId": "p1"},
            {"id": "66df20b0e4b0c20a55667788", "title": "Comprar ração pro gato", "projectId": "inbox"},
        ]
        self.mock_ticktick.get_tasks = AsyncMock(return_value=self.sample_tasks)
        self.mock_ticktick.complete_task = AsyncMock(return_value=True)
        self.mock_ticktick.delete_task = AsyncMock(return_value=True)
        self.mock_ticktick.update_task = AsyncMock(return_value={"id": "66df10a9e4b0c20a11223344", "dueDate": "2026-09-16T03:00:00.000+0000"})
        self.mock_ticktick.batch_update_tasks = AsyncMock(return_value=[{"task_id": "66df10a9e4b0c20a11223344", "status": 200}])

    async def test_complete_task_with_smart_resolution(self):
        """Conclui tarefa fornecendo apenas o nome em linguagem natural."""
        result = await self.service.complete_task("comprar ração")
        self.assertTrue(result.success)
        self.assertEqual(result.task_id, "66df20b0e4b0c20a55667788")
        self.assertIn("Comprar ração pro gato", result.message)
        self.mock_ticktick.complete_task.assert_called_once_with(project_id="inbox", task_id="66df20b0e4b0c20a55667788")

    async def test_delete_task_with_smart_resolution(self):
        """Deleta tarefa identificada pelo título."""
        result = await self.service.delete_task("álgebra linear")
        self.assertTrue(result.success)
        self.assertEqual(result.task_id, "66df10a9e4b0c20a11223344")
        self.mock_ticktick.delete_task.assert_called_once_with(project_id="p1", task_id="66df10a9e4b0c20a11223344")

    async def test_reschedule_task(self):
        """Reagenda tarefa com normalização automática da nova data."""
        result = await self.service.reschedule_task(task_identifier="álgebra linear", due_date="2026-09-16")
        self.assertTrue(result.success)
        self.mock_ticktick.update_task.assert_called_once()
        call_args = self.mock_ticktick.update_task.call_args[1]
        self.assertEqual(call_args["task_id"], "66df10a9e4b0c20a11223344")
        self.assertEqual(call_args["dueDate"], "2026-09-16T03:00:00.000+0000")

    async def test_batch_update_maps_task_id_to_id(self):
        """Garante que batch_update_tasks renomeia task_id para id conforme schema MCP."""
        updates = [{"task_id": "t1", "title": "Novo Titulo"}]
        result = await self.service.batch_update_tasks(tasks_to_update=updates)
        self.assertTrue(result.success)
        self.mock_ticktick.batch_update_tasks.assert_called_once()
        passed_updates = self.mock_ticktick.batch_update_tasks.call_args[0][0]
        self.assertIn("id", passed_updates[0])
        self.assertNotIn("task_id", passed_updates[0])
        self.assertEqual(passed_updates[0]["id"], "t1")


class TestSessionDomainService(unittest.IsolatedAsyncioTestCase):
    """Testes para o construtor de contexto de sessão operacional."""

    async def test_build_session_context_block(self):
        mock_tasks = MagicMock()
        mock_tasks.get_tasks = AsyncMock(return_value=MagicMock(
            success=True,
            message="1. [ID: 111 | Projeto: Inbox] Revisar PRs\n2. [ID: 222 | Projeto: Estudo] RAG Math"
        ))

        mock_db = MagicMock()
        mock_db.get_user_insights = AsyncMock(return_value=[
            {"category": "carreira", "insight": "Foco em Staff Software Engineer e IA generativa."},
            {"category": "rotina", "insight": "Treino na academia pela manhã."}
        ])

        with patch("src.domain.session.get_database_service", return_value=mock_db):
            service = SessionDomainService(task_service=mock_tasks)
            block = await service.build_session_context_block(user_id="erik_user")

            self.assertIn("# CONTEXTO OPERACIONAL ATIVO DA SESSÃO", block)
            self.assertIn("Revisar PRs", block)
            self.assertIn("RAG Math", block)
            self.assertIn("Staff Software Engineer", block)
            self.assertIn("Horário de Brasília", block)


class TestSessionBoundaryDetection(unittest.IsolatedAsyncioTestCase):
    """Testes para detecção de nova sessão conversacional no DatabaseService."""

    def setUp(self):
        self.db = DatabaseService.__new__(DatabaseService)
        self.sp_tz = ZoneInfo("America/Sao_Paulo")

    async def test_new_session_on_first_interaction(self):
        """Primeira interação do usuário sempre inicia nova sessão."""
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cur = AsyncMock()

        mock_cur.fetchone = AsyncMock(return_value=None)
        mock_cur.execute = AsyncMock()

        mock_conn.cursor.return_value.__aenter__ = AsyncMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__aexit__ = AsyncMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock()
        self.db.get_pool = AsyncMock(return_value=mock_pool)

        is_new = await self.db.check_and_update_session("u1", "c1", threshold_seconds=7200)
        self.assertTrue(is_new)

    async def test_same_session_within_inactivity_threshold(self):
        """Interação dentro do limite de inatividade (ex: 30 min) no mesmo dia civil mantém sessão ativa."""
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cur = AsyncMock()

        now_utc = datetime.now(timezone.utc)
        last_interaction = now_utc - timedelta(minutes=30)
        mock_cur.fetchone = AsyncMock(return_value=(last_interaction, 3))
        mock_cur.execute = AsyncMock()

        mock_conn.cursor.return_value.__aenter__ = AsyncMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__aexit__ = AsyncMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock()
        self.db.get_pool = AsyncMock(return_value=mock_pool)

        is_new = await self.db.check_and_update_session("u1", "c1", threshold_seconds=7200)
        self.assertFalse(is_new)

    async def test_new_session_after_inactivity_threshold(self):
        """Interação após mais de 2 horas (7200s) de inatividade dispara nova sessão."""
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cur = AsyncMock()

        now_utc = datetime.now(timezone.utc)
        last_interaction = now_utc - timedelta(hours=2, minutes=15)
        mock_cur.fetchone = AsyncMock(return_value=(last_interaction, 3))
        mock_cur.execute = AsyncMock()

        mock_conn.cursor.return_value.__aenter__ = AsyncMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__aexit__ = AsyncMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock()
        self.db.get_pool = AsyncMock(return_value=mock_pool)

        is_new = await self.db.check_and_update_session("u1", "c1", threshold_seconds=7200)
        self.assertTrue(is_new)


class TestTriTierCognitiveRouting(unittest.TestCase):
    """Testes para a determinação de Cérebro Cognitivo (Sonnet vs Terra vs None) no Tri-Tier."""

    def _determine_brain(self, domain: str, complexity: int, is_confirmation: bool) -> tuple[str, bool]:
        """Replicação exata da lógica determinística do _router_node do MaeveAgent."""
        if is_confirmation:
            brain = "none"
            plan_required = False
        elif domain == "knowledge" or complexity >= 4:
            brain = "sonnet"
            plan_required = True
        elif domain == "tasks" or complexity >= 2:
            brain = "terra"
            plan_required = True
        else:
            brain = "none"
            plan_required = False
        return brain, plan_required

    def test_frontier_brain_for_obsidian_knowledge(self):
        """Toda operação do Segundo Cérebro (Obsidian) deve engajar Claude Sonnet."""
        brain, plan = self._determine_brain(domain="knowledge", complexity=1, is_confirmation=False)
        self.assertEqual(brain, "sonnet")
        self.assertTrue(plan)

    def test_frontier_brain_for_high_complexity(self):
        """Tarefas de alta complexidade (>=4) acionam Claude Sonnet como Frontier Brain."""
        brain, plan = self._determine_brain(domain="tasks", complexity=4, is_confirmation=False)
        self.assertEqual(brain, "sonnet")
        self.assertTrue(plan)

        brain2, plan2 = self._determine_brain(domain="chat", complexity=5, is_confirmation=False)
        self.assertEqual(brain2, "sonnet")
        self.assertTrue(plan2)

    def test_operational_brain_for_daily_tasks(self):
        """Operações de tarefas do TickTick (complexidade 1 a 3) acionam GPT-5.6 Terra como Brain."""
        brain, plan = self._determine_brain(domain="tasks", complexity=1, is_confirmation=False)
        self.assertEqual(brain, "terra")
        self.assertTrue(plan)

        brain2, plan2 = self._determine_brain(domain="tasks", complexity=3, is_confirmation=False)
        self.assertEqual(brain2, "terra")
        self.assertTrue(plan2)

    def test_fast_path_for_short_confirmation(self):
        """Confirmação de turno anterior ('sim', 'ok', 'pode fazer') pula o Brain (none) e vai direto pra Luna."""
        brain, plan = self._determine_brain(domain="tasks", complexity=1, is_confirmation=True)
        self.assertEqual(brain, "none")
        self.assertFalse(plan)


if __name__ == "__main__":
    unittest.main()
