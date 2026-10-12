import unittest
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from src.domain.query_expansion import ContextualQueryExpander
from src.domain.knowledge import KnowledgeDomainService
from src.domain.models import KnowledgeResult


class TestSprint23UnifiedBrainRAG(unittest.IsolatedAsyncioTestCase):
    """
    Suíte de Testes Automatizados da Sprint 23:
    - Contextual Query Expansion & Semantic Retrieval Enhancer (HyDE / RAG)
    - Single-Brain Unified ReAct Loop no LangGraph (Sonnet direto com ferramentas)
    - Integração de Query Expansion no KnowledgeDomainService e no MaeveAgent
    """

    # =========================================================================
    # 1. Testes Unitários de Query Expansion (ContextualQueryExpander)
    # =========================================================================

    def setUp(self):
        self.expander = ContextualQueryExpander()

    def test_is_contextual_query_anaphoric(self):
        """Valida que consultas com pronomes anafóricos ou elipses são identificadas como contextuais."""
        self.assertTrue(self.expander.is_contextual_query("E como ficou aquela decisão?"))
        self.assertTrue(self.expander.is_contextual_query("O que combinamos sobre isso?"))
        self.assertTrue(self.expander.is_contextual_query("Quais os requisitos do projeto?"))
        self.assertTrue(self.expander.is_contextual_query("como ficou?"))
        self.assertTrue(self.expander.is_contextual_query("E naquilo que falamos?"))

    def test_is_contextual_query_autonomous(self):
        """Valida que consultas ricas e autônomas não são marcadas incorretamente como contextuais."""
        self.assertFalse(self.expander.is_contextual_query(
            "Explique detalhadamente como funciona a decomposição em valores singulares SVD em Álgebra Linear"
        ))
        self.assertFalse(self.expander.is_contextual_query(
            "Qual a diferença entre arquitetura limpa hexagonal e arquitetura em camadas tradicional?"
        ))

    def test_extract_salient_terms_from_history(self):
        """Valida extração precisa de termos técnicos, crases inline, wikilinks e nomes próprios."""
        history = [
            HumanMessage(content="Estou configurando o `Databricks` SQL Warehouse com a API do [[AppScript]]."),
            AIMessage(content="Entendido, podemos usar o conector ODBC com autenticação OAuth2 no Databricks."),
        ]
        terms = self.expander.extract_salient_terms(history)
        self.assertIn("Databricks", terms)
        self.assertIn("AppScript", terms)
        self.assertIn("Warehouse", terms)
        self.assertNotIn("Maeve", terms)
        self.assertNotIn("Erik", terms)

    def test_expand_query_enriches_anaphoric(self):
        """Valida enriquecimento da consulta anafórica com os termos salientes da conversa."""
        history = [
            HumanMessage(content="Estamos desenhando o pipeline de dados usando Apache Spark e Delta Lake."),
            AIMessage(content="Excelente escolha de lakehouse para suportar ACID e time-travel."),
        ]
        short_query = "E como ficou aquela decisão?"
        expanded = self.expander.expand_query(short_query, history)

        self.assertNotEqual(short_query, expanded)
        self.assertTrue(expanded.startswith(short_query))
        self.assertTrue(any(term in expanded for term in ["Spark", "Apache", "Delta", "Lake", "lakehouse"]))

    def test_expand_query_preserves_autonomous(self):
        """Valida que consultas autônomas não sofrem poluição de termos."""
        history = [
            HumanMessage(content="Estamos desenhando o pipeline de dados usando Apache Spark."),
        ]
        autonomous_query = "Qual a definição formal de convergência quase certa de variáveis aleatórias?"
        expanded = self.expander.expand_query(autonomous_query, history)

        self.assertEqual(autonomous_query, expanded)

    # =========================================================================
    # 2. Testes de KnowledgeDomainService com Query Expansion
    # =========================================================================

    async def test_knowledge_domain_search_context_with_expansion(self):
        """Valida que search_knowledge_context utiliza o expander quando recebe histórico de mensagens."""
        mock_vdb = AsyncMock()
        mock_vdb.search_context.return_value = [{"metadata": {"title": "ADR-015"}, "content": "Conteúdo"}]
        mock_obs = AsyncMock()

        domain = KnowledgeDomainService(obsidian_service=mock_obs, vector_db_service=mock_vdb)

        history = [
            HumanMessage(content="Decidimos usar [[FastMCP]] para paridade de ferramentas na Maeve."),
        ]
        query = "O que decidimos sobre isso?"

        results = await domain.search_knowledge_context(
            query=query, limit=3, score_threshold=0.68, recent_messages=history
        )

        mock_vdb.search_context.assert_called_once()
        called_query = mock_vdb.search_context.call_args[0][0]
        self.assertIn("FastMCP", called_query)
        self.assertEqual(len(results), 1)

    # =========================================================================
    # 3. Testes do Single-Brain Unified ReAct Loop no MaeveAgent
    # =========================================================================

    @patch("src.agent.engine.create_chat_model")
    @patch("src.agent.engine.get_vector_db_service")
    async def test_router_single_brain_unified_knowledge(self, mock_vdb, mock_create_model):
        """
        Valida que em modo UNIFIED_BRAIN=true, pedidos do domínio 'knowledge' recebem
        brain='sonnet' E plan_required=False, roteando diretamente para call_model.
        """
        from src.agent.engine import MaeveAgent

        mock_llm = AsyncMock()
        mock_llm.model_name = "gpt-5.6-luna"
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)
        mock_llm.bind = MagicMock(return_value=mock_llm)
        mock_llm.ainvoke.return_value = AIMessage(
            content='{"complexity": 4, "model": "smart", "domain": "knowledge", "reason": "Vault", "plan_required": true}'
        )
        mock_create_model.return_value = mock_llm

        with patch.dict(os.environ, {"MAEVE_UNIFIED_BRAIN": "true"}):
            agent = MaeveAgent()
            state = {
                "messages": [HumanMessage(content="Cria uma nota sobre arquitetura do Qdrant no Obsidian")],
            }
            res = await agent._router_node(state)

            self.assertEqual(res["brain"], "sonnet")
            self.assertEqual(res["current_intent"], "knowledge")
            self.assertFalse(res["routing_metadata"]["plan_required"])

    @patch("src.agent.engine.create_chat_model")
    @patch("src.agent.engine.get_vector_db_service")
    async def test_router_tri_tier_legacy_when_unified_disabled(self, mock_vdb, mock_create_model):
        """
        Valida compatibilidade retroativa: se MAEVE_UNIFIED_BRAIN=false, pedidos de alta complexidade
        mantêm plan_required=True para passar pelo nó planner.
        """
        from src.agent.engine import MaeveAgent

        mock_llm = AsyncMock()
        mock_llm.model_name = "gpt-5.6-luna"
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)
        mock_llm.bind = MagicMock(return_value=mock_llm)
        mock_llm.ainvoke.return_value = AIMessage(
            content='{"complexity": 5, "model": "smart", "domain": "knowledge", "reason": "Vault", "plan_required": true}'
        )
        mock_create_model.return_value = mock_llm

        with patch.dict(os.environ, {"MAEVE_UNIFIED_BRAIN": "false"}):
            agent = MaeveAgent()
            state = {
                "messages": [HumanMessage(content="Cria uma nota conceitual no Obsidian")],
            }
            res = await agent._router_node(state)

            self.assertEqual(res["brain"], "sonnet")
            self.assertTrue(res["routing_metadata"]["plan_required"])

    @patch("src.agent.engine.create_chat_model")
    @patch("src.agent.engine.get_vector_db_service")
    async def test_call_model_selects_smart_brain_in_unified_mode(self, mock_vdb_getter, mock_create_model):
        """
        Valida que quando brain='sonnet' em modo unificado, _call_model_node utiliza
        smart_model_base como base_model com ferramentas ativas.
        """
        from src.agent.engine import MaeveAgent

        mock_vdb = AsyncMock()
        mock_vdb.search_context.return_value = []
        mock_vdb_getter.return_value = mock_vdb

        mock_smart = AsyncMock()
        mock_smart.model_name = "claude-3-5-sonnet"
        mock_smart.model = "claude-3-5-sonnet"
        mock_smart.bind_tools = MagicMock(return_value=mock_smart)
        mock_smart.bind = MagicMock(return_value=mock_smart)
        mock_smart.ainvoke.return_value = AIMessage(content="Aqui está a nota técnica criada.")

        mock_fast = AsyncMock()
        mock_fast.model_name = "gpt-5.6-luna"
        mock_fast.model = "gpt-5.6-luna"
        mock_fast.bind_tools = MagicMock(return_value=mock_fast)
        mock_fast.bind = MagicMock(return_value=mock_fast)
        mock_fast.ainvoke.return_value = AIMessage(content="Resposta da Luna")

        def side_effect(model_name, **kwargs):
            if "sonnet" in model_name:
                return mock_smart
            return mock_fast

        mock_create_model.side_effect = side_effect

        with patch.dict(os.environ, {"MAEVE_UNIFIED_BRAIN": "true"}):
            agent = MaeveAgent()
            agent.smart_model_base = mock_smart
            agent.fast_model_base = mock_fast

            state = {
                "messages": [HumanMessage(content="Cria uma nota sobre arquitetura")],
                "current_intent": "knowledge",
                "brain": "sonnet",
                "routing_metadata": {"brain": "sonnet", "domain": "knowledge", "model": "smart"},
                "session_context": "Contexto operacional de teste",
            }

            res = await agent._call_model_node(state)
            self.assertEqual(res["messages"][0].content, "Aqui está a nota técnica criada.")
            # Garante que o modelo inteligente (Sonnet) foi o invocado, e não a Luna
            mock_smart.ainvoke.assert_called_once()
            mock_fast.ainvoke.assert_not_called()


if __name__ == "__main__":
    unittest.main()
