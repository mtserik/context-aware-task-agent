import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import HumanMessage, AIMessage

from src.agent.state import AgentState
from src.agent.tools.mcp_bridge import DynamicMCPToolBridge, build_langchain_mcp_tool, OFFICIAL_TICKTICK_MCP_SCHEMAS
from src.agent.engine import MaeveAgent
from src.services.ticktick import TickTickService


class TestSprint18DynamicMCPBridge(unittest.TestCase):
    """Testes de unidade para a ponte dinâmica de ferramentas MCP (DynamicMCPToolBridge)."""

    def test_schema_conversion_to_structured_tool(self):
        """Verifica se os esquemas MCP oficiais são convertidos corretamente em StructuredTools com args_schema."""
        mock_service = MagicMock()
        mock_service.call_mcp_tool = AsyncMock(return_value={"project": {"id": "123", "name": "Notas"}, "tasks": []})

        schema_def = next(s for s in OFFICIAL_TICKTICK_MCP_SCHEMAS if s["name"] == "get_project_with_undone_tasks")
        tool = build_langchain_mcp_tool(schema_def, mock_service)

        self.assertEqual(tool.name, "get_project_with_undone_tasks")
        self.assertIn("projeto", tool.description.lower())
        self.assertIsNotNone(tool.args_schema)
        # Verifica se o campo 'project_id' existe no schema Pydantic gerado
        fields = tool.args_schema.model_fields
        self.assertIn("project_id", fields)

    def test_async_mcp_tool_execution(self):
        """Verifica a execução assíncrona da ferramenta chamando call_mcp_tool no serviço."""
        mock_service = MagicMock()
        mock_service.call_mcp_tool = AsyncMock(return_value={"id": "test_proj", "tasks": [{"title": "Nota 1"}]})

        schema_def = next(s for s in OFFICIAL_TICKTICK_MCP_SCHEMAS if s["name"] == "get_project_with_undone_tasks")
        tool = build_langchain_mcp_tool(schema_def, mock_service)

        async def run():
            result = await tool.ainvoke({"project_id": "test_proj"})
            mock_service.call_mcp_tool.assert_called_once_with("get_project_with_undone_tasks", {"project_id": "test_proj"})
            data = json.loads(result)
            self.assertEqual(data["id"], "test_proj")
            self.assertEqual(len(data["tasks"]), 1)

        asyncio.run(run())

    def test_bridge_discovery_and_fallback(self):
        """Verifica a descoberta e o fallback estrito do catálogo de referência."""
        mock_service = MagicMock()
        # Simula retorno vazio ou erro no tools/list
        mock_service.list_mcp_tools = AsyncMock(side_effect=Exception("Network error"))

        bridge = DynamicMCPToolBridge(ticktick_service=mock_service)
        tools = bridge.get_static_mcp_tools()
        self.assertGreaterEqual(len(tools), 5)
        tool_names = [t.name for t in tools]
        self.assertIn("get_project_with_undone_tasks", tool_names)
        self.assertIn("list_projects", tool_names)
        self.assertIn("search_task", tool_names)


class TestSprint18ContextualRouter(unittest.TestCase):
    """Testes para o Roteador Sensível a Contexto com Precedência de Entidades e Inércia."""

    def setUp(self):
        self.agent = MaeveAgent.__new__(MaeveAgent)
        self.agent.router_model = MagicMock()

    def test_explicit_ticktick_entity_precedence(self):
        """Menção explícita a 'TickTick' DEVE prevalecer e rotear para 'tasks', mesmo contendo 'notas'."""
        mock_response = MagicMock()
        # Mesmo se o LLM alucinasse 'knowledge' por ver a palavra 'notas'
        mock_response.content = json.dumps({
            "complexity": 1,
            "model": "fast",
            "domain": "knowledge",
            "reason": "Mencionou notas",
            "plan_required": False,
            "clarification_needed": False
        })
        self.agent.router_model.ainvoke = AsyncMock(return_value=mock_response)

        state: AgentState = {
            "messages": [HumanMessage(content="Usa o mcp do TickTick e me traz tudo que tem na Lista Notas")],
            "current_intent": None,
            "active_domain": None,
            "routing_metadata": None,
            "plan": None
        }

        async def run():
            decision = await self.agent._router_node(state)
            # A trava determinística de precedência deve sobrepor e forçar 'tasks'
            self.assertEqual(decision["current_intent"], "tasks")
            self.assertEqual(decision["active_domain"], "tasks")
            self.assertEqual(decision["routing_metadata"]["domain"], "tasks")

        asyncio.run(run())

    def test_explicit_obsidian_entity_precedence(self):
        """Menção explícita a 'Obsidian' DEVE prevalecer e rotear para 'knowledge'."""
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "complexity": 1,
            "model": "fast",
            "domain": "tasks",
            "reason": "Mencionou tarefas",
            "plan_required": False,
            "clarification_needed": False
        })
        self.agent.router_model.ainvoke = AsyncMock(return_value=mock_response)

        state: AgentState = {
            "messages": [HumanMessage(content="Salva essa lista de tarefas como uma nota no Obsidian Vault")],
            "current_intent": None,
            "active_domain": None,
            "routing_metadata": None,
            "plan": None
        }

        async def run():
            decision = await self.agent._router_node(state)
            self.assertEqual(decision["current_intent"], "knowledge")
            self.assertEqual(decision["active_domain"], "knowledge")

        asyncio.run(run())

    def test_conversational_inertia_multi_turn(self):
        """Se o turno anterior tratava de tarefas (active_domain='tasks'), 'lista notas' herda 'tasks'."""
        mock_response = MagicMock()
        # O LLM ciente da inércia responde tasks
        mock_response.content = json.dumps({
            "complexity": 1,
            "model": "fast",
            "domain": "tasks",
            "reason": "Inércia conversacional de tarefas/TickTick",
            "plan_required": False,
            "clarification_needed": False
        })
        self.agent.router_model.ainvoke = AsyncMock(return_value=mock_response)

        state: AgentState = {
            "messages": [
                HumanMessage(content="Quais tarefas eu tenho agendadas para amanhã?"),
                AIMessage(content="Você tem 3 tarefas agendadas no TickTick."),
                HumanMessage(content="E o que tem na lista notas?")
            ],
            "current_intent": "tasks",
            "active_domain": "tasks",
            "routing_metadata": None,
            "plan": None
        }

        async def run():
            decision = await self.agent._router_node(state)
            self.assertEqual(decision["current_intent"], "tasks")
            self.assertEqual(decision["active_domain"], "tasks")

        asyncio.run(run())

    def test_proactive_disambiguation(self):
        """Quando o router detecta ambiguidade inicial sem contexto, sinaliza clarification_needed."""
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "complexity": 1,
            "model": "fast",
            "domain": "chat",
            "reason": "Ambiguidade entre TickTick e Obsidian",
            "plan_required": False,
            "clarification_needed": True
        })
        self.agent.router_model.ainvoke = AsyncMock(return_value=mock_response)

        state: AgentState = {
            "messages": [HumanMessage(content="O que tem em notas?")],
            "current_intent": None,
            "active_domain": None,
            "routing_metadata": None,
            "plan": None
        }

        async def run():
            decision = await self.agent._router_node(state)
            self.assertEqual(decision["current_intent"], "chat")
            self.assertTrue(decision["routing_metadata"]["clarification_needed"])

        asyncio.run(run())

    def test_note_creation_command_not_hijacked_by_task_context(self):
        """Comando 'cria uma nota...' NÃO deve ser capturado como confirmação de tarefa nem aprisionado na inércia do TickTick."""
        mock_response = MagicMock()
        # Mesmo se o LLM equivocadamente respondesse 'tasks' pela inércia prévia
        mock_response.content = json.dumps({
            "complexity": 1,
            "model": "fast",
            "domain": "tasks",
            "reason": "Inércia",
            "plan_required": False,
            "clarification_needed": False
        })
        self.agent.router_model.ainvoke = AsyncMock(return_value=mock_response)

        state: AgentState = {
            "messages": [
                HumanMessage(content="me traz tudo que tem na Lista Notas do TickTick"),
                AIMessage(content="Aqui estão as tarefas da lista Notas no TickTick: 1. Comprar leite"),
                HumanMessage(content="cria uma nota sobre a reunião de arquitetura de software")
            ],
            "current_intent": "tasks",
            "active_domain": "tasks",
            "routing_metadata": None,
            "plan": None
        }

        async def run():
            decision = await self.agent._router_node(state)
            self.assertEqual(decision["current_intent"], "knowledge")
            self.assertEqual(decision["active_domain"], "knowledge")

        asyncio.run(run())

    def test_explicit_obsidian_with_prior_task_history(self):
        """Comando 'cria uma nota no Obsidian...' com histórico de tarefas prévio DEVE rotear para 'knowledge'."""
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "complexity": 1,
            "model": "fast",
            "domain": "tasks",
            "reason": "Inércia",
            "plan_required": False,
            "clarification_needed": False
        })
        self.agent.router_model.ainvoke = AsyncMock(return_value=mock_response)

        state: AgentState = {
            "messages": [
                HumanMessage(content="Quais tarefas eu tenho hoje?"),
                AIMessage(content="Você tem 2 tarefas agendadas no TickTick."),
                HumanMessage(content="cria uma nota no Obsidian sobre as metas de Q4")
            ],
            "current_intent": "tasks",
            "active_domain": "tasks",
            "routing_metadata": None,
            "plan": None
        }

        async def run():
            decision = await self.agent._router_node(state)
            self.assertEqual(decision["current_intent"], "knowledge")
            self.assertEqual(decision["active_domain"], "knowledge")

        asyncio.run(run())

    def test_confirmation_of_obsidian_proposal(self):
        """Confirmação curta para proposta de salvar no Vault/Obsidian roteia para 'knowledge'."""
        state: AgentState = {
            "messages": [
                HumanMessage(content="Acabei de ter um insight sobre a arquitetura do sistema"),
                AIMessage(content="Isso é ouro, Erik! Quer que eu documente essa decisão no seu Obsidian Vault?"),
                HumanMessage(content="pode criar")
            ],
            "current_intent": "knowledge",
            "active_domain": "knowledge",
            "routing_metadata": None,
            "plan": None
        }

        async def run():
            decision = await self.agent._router_node(state)
            self.assertEqual(decision["current_intent"], "knowledge")
            self.assertEqual(decision["active_domain"], "knowledge")

        asyncio.run(run())

    def test_confirmation_of_task_proposal(self):
        """Confirmação curta para proposta de agendar tarefa no TickTick roteia para 'tasks'."""
        state: AgentState = {
            "messages": [
                HumanMessage(content="Preciso revisar o PR #42 amanhã"),
                AIMessage(content="Quer que eu agende essa tarefa no seu TickTick para amanhã?"),
                HumanMessage(content="sim, pode agendar")
            ],
            "current_intent": "tasks",
            "active_domain": "tasks",
            "routing_metadata": None,
            "plan": None
        }

        async def run():
            decision = await self.agent._router_node(state)
            self.assertEqual(decision["current_intent"], "tasks")
            self.assertEqual(decision["active_domain"], "tasks")

        asyncio.run(run())


class TestSprint18TickTickServiceMCPFirst(unittest.TestCase):
    """Testa o comportamento MCP-First no TickTickService.get_tasks()."""

    def test_get_tasks_uses_mcp_when_project_id_provided(self):
        """Verifica se get_tasks() com project_id invoca get_project_with_undone_tasks no MCP."""
        service = TickTickService()
        service.mcp_token = "mock_mcp_token"
        service.call_mcp_tool = AsyncMock(return_value={
            "project": {"id": "proj_notes", "name": "Notas", "kind": "NOTE"},
            "tasks": [
                {"id": "note_1", "title": "Nota Geral", "kind": "NOTE"},
                {"id": "note_2", "title": "Nota RTM", "kind": "NOTE"}
            ]
        })

        async def run():
            tasks = await service.get_tasks(project_id="proj_notes")
            service.call_mcp_tool.assert_called_once_with("get_project_with_undone_tasks", {"project_id": "proj_notes"})
            self.assertEqual(len(tasks), 2)
            self.assertEqual(tasks[0]["title"], "Nota Geral")

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
