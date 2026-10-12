import unittest
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.tools import StructuredTool, BaseTool
from src.mcp.server import create_mcp_server, mcp
from src.agent.tools.mcp_bridge import (
    FastMCPToolBridge,
    fastmcp_tool_to_langchain_tool,
    fastmcp_bridge,
)
from src.agent.tools import get_canonical_mcp_tools, FASTMCP_TOOLS


class TestSprint24MCPParity(unittest.IsolatedAsyncioTestCase):
    """
    Suíte de Testes da Sprint 24:
    - FastMCP Canonical Server Registry Parity (18 tools)
    - Bidirectional Bridge FastMCP -> LangChain StructuredTool
    - Domain Partitioning Parity
    - Telegram Bot Transient Status Auto-Deletion
    """

    # =========================================================================
    # 1. Paridade de Catálogo do FastMCP Server
    # =========================================================================

    def test_fastmcp_server_has_all_canonical_tools(self):
        """Valida que o servidor FastMCP registra todas as 24 ferramentas canônicas."""
        server = create_mcp_server()
        tools_dict = getattr(server._tool_manager, "_tools", {})
        self.assertEqual(len(tools_dict), 24)

        expected_tool_names = {
            "memory_search",
            "memory_store",
            "append_session_note",
            "search_knowledge",
            "sync_knowledge",
            "list_today_tasks",
            "create_task",
            "create_focus_block",
            "get_personal_context",
            "set_reminder",
            "log_daily_journal",
            "log_user_insight",
            "log_decision",
            "batch_move_obsidian_notes",
            "log_cultural_review",
            "ingest_book",
            "web_search",
            "deep_research",
            "control_vacuum",
            "control_switch",
            "get_device_status",
            "launch_desktop_app",
            "open_browser_url",
            "control_media_player",
        }
        self.assertEqual(set(tools_dict.keys()), expected_tool_names)

    async def test_fastmcp_list_tools_schema_validity(self):
        """Valida que list_tools expõe esquemas válidos para clientes MCP externos (Antigravity CLI/IDE)."""
        server = create_mcp_server()
        tools = await server.list_tools()
        self.assertEqual(len(tools), 24)

        for t in tools:
            self.assertTrue(bool(t.name))
            self.assertTrue(bool(t.description))
            self.assertIsInstance(t.inputSchema, dict)
            self.assertEqual(t.inputSchema.get("type"), "object")

    # =========================================================================
    # 2. Conversão Bidirecional FastMCP -> LangChain StructuredTool
    # =========================================================================

    def test_fastmcp_tool_conversion_to_langchain(self):
        """Valida que uma FastMCP Tool é convertida em StructuredTool com schema e metadados preservados."""
        server = create_mcp_server()
        mcp_tool = server._tool_manager._tools["memory_search"]

        lc_tool = fastmcp_tool_to_langchain_tool(mcp_tool)
        self.assertIsInstance(lc_tool, StructuredTool)
        self.assertEqual(lc_tool.name, "memory_search")
        self.assertIn("Busca semantica", lc_tool.description)
        self.assertTrue(hasattr(lc_tool, "args_schema"))

        # Valida que os parâmetros da função foram convertidos para o schema Pydantic
        schema = lc_tool.args_schema.model_json_schema()
        self.assertIn("query", schema["properties"])
        self.assertIn("limit", schema["properties"])

    def test_fastmcp_tool_bridge_get_all_tools(self):
        """Valida que o FastMCPToolBridge converte todas as 24 ferramentas para LangChain."""
        bridge = FastMCPToolBridge(create_mcp_server())
        all_tools = bridge.get_all_tools()
        self.assertEqual(len(all_tools), 24)
        names = {t.name for t in all_tools}
        self.assertIn("web_search", names)
        self.assertIn("create_task", names)
        self.assertIn("memory_store", names)
        self.assertIn("control_vacuum", names)
        self.assertIn("launch_desktop_app", names)

    def test_get_canonical_mcp_tools_global(self):
        """Valida que get_canonical_mcp_tools disponibiliza todas as ferramentas canônicas."""
        canonical = get_canonical_mcp_tools()
        self.assertEqual(len(canonical), 24)
        self.assertEqual(len(FASTMCP_TOOLS), 24)

    # =========================================================================
    # 3. Particionamento por Domínio Semântico
    # =========================================================================

    def test_domain_partitioning_tasks(self):
        """Valida ferramentas do domínio 'tasks' no FastMCP bridge."""
        bridge = FastMCPToolBridge(create_mcp_server())
        tasks = bridge.get_tools_for_domain("tasks")
        names = {t.name for t in tasks}
        self.assertEqual(names, {"list_today_tasks", "create_task", "create_focus_block"})

    def test_domain_partitioning_search(self):
        """Valida ferramentas do domínio 'search' no FastMCP bridge."""
        bridge = FastMCPToolBridge(create_mcp_server())
        search = bridge.get_tools_for_domain("search")
        names = {t.name for t in search}
        self.assertEqual(names, {"web_search", "deep_research"})

    def test_domain_partitioning_knowledge(self):
        """Valida ferramentas do domínio 'knowledge' no FastMCP bridge."""
        bridge = FastMCPToolBridge(create_mcp_server())
        knowledge = bridge.get_tools_for_domain("knowledge")
        names = {t.name for t in knowledge}
        self.assertIn("memory_search", names)
        self.assertIn("memory_store", names)
        self.assertIn("append_session_note", names)
        self.assertIn("sync_knowledge", names)
        self.assertIn("log_decision", names)

    # =========================================================================
    # 4. Pipeline do Telegram Bot — Limpeza de Mensagens Transitórias
    # =========================================================================

    async def test_telegram_handle_voice_cleans_transient_status(self):
        """Valida que handle_voice deleta automaticamente a mensagem 'Ouvindo... 🎙️'."""
        from src.services.telegram_bot import TelegramBotService

        bot_service = TelegramBotService()
        bot_service.allowed_user_id = "12345"
        bot_service.openai_client = MagicMock()
        bot_service.openai_client.audio = MagicMock()
        bot_service.openai_client.audio.transcriptions = MagicMock()
        bot_service.openai_client.audio.transcriptions.create = AsyncMock(return_value="Teste de voz transcrito")

        mock_update = MagicMock()
        mock_update.effective_user.id = 12345
        mock_update.effective_chat.id = 67890
        mock_update.message.voice.file_id = "voice_file_abc"

        mock_status_msg = MagicMock()
        mock_status_msg.message_id = 999
        mock_update.message.reply_text = AsyncMock(return_value=mock_status_msg)

        mock_voice_file = MagicMock()
        mock_voice_file.download_to_drive = AsyncMock()

        mock_context = MagicMock()
        mock_context.bot.get_file = AsyncMock(return_value=mock_voice_file)
        mock_context.bot.delete_message = AsyncMock()

        with patch.object(bot_service, "_process_text", new_callable=AsyncMock) as mock_process:
            await bot_service.handle_voice(mock_update, mock_context)

            # Verifica se delete_message foi acionado para remover 'Ouvindo... 🎙️'
            mock_context.bot.delete_message.assert_called_once_with(
                chat_id="67890", message_id=999
            )
            # Verifica se _process_text foi chamado com o texto transcrito
            mock_process.assert_called_once()
            self.assertEqual(mock_process.call_args[0][0], "Teste de voz transcrito")


if __name__ == "__main__":
    unittest.main()
