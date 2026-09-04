import os
import re
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage, BaseMessage
from dotenv import load_dotenv

try:
    from langchain_anthropic import ChatAnthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False

from src.agent.state import AgentState, IntentDomain
from src.agent.prompts import SYSTEM_PROMPT_TEMPLATE, get_system_prompt
from src.services.registry import get_vector_db_service
from src.domain.tasks import normalize_ticktick_date
from src.domain.temporal import resolve_temporal_context
from src.agent.tools import (
    ALL_TOOLS,
    TASK_TOOLS,
    KNOWLEDGE_TOOLS,
    REMINDER_TOOLS,
    SEARCH_TOOLS,
    get_tools_for_intent,
    # Re-export tools for backward compatibility
    create_ticktick_task,
    batch_update_ticktick_tasks,
    create_ticktick_project,
    get_ticktick_tasks,
    get_ticktick_item_details,
    delete_ticktick_item,
    list_ticktick_structure,
    verify_task_creation,
    get_ticktick_metrics_via_mcp,
    batch_create_ticktick_tasks,
    create_obsidian_note,
    list_obsidian_folders,
    delete_obsidian_item,
    move_obsidian_item,
    cleanup_empty_obsidian_folders,
    list_obsidian_notes,
    get_obsidian_note_details,
    get_obsidian_note_content,
    sync_obsidian_knowledge,
    set_reminder,
    list_active_reminders,
    web_search,
    deep_research,
)

load_dotenv()

logger = logging.getLogger("MaeveEngine")

# Alias para compatibilidade retroativa com suíte de testes
_normalize_ticktick_date = normalize_ticktick_date
tools = ALL_TOOLS
tool_node = ToolNode(ALL_TOOLS)

# --- Funções Utilitárias de Pipeline ---

def _sanitize_message_history(raw_messages: List[BaseMessage], limit: int = 20) -> List[BaseMessage]:
    """
    Sanitiza o histórico de mensagens:
    1. Trunca na janela desejada sem cortar sequências no meio de chamadas de ferramentas.
    2. Remove ToolMessages órfãs no início para evitar loops e erros 400.
    3. Cura AIMessages pendentes sem resposta de ferramenta correspondente.
    """
    if len(raw_messages) <= limit:
        subset = list(raw_messages)
    else:
        subset = list(raw_messages[-limit:])
        while subset and isinstance(subset[0], ToolMessage) and limit < len(raw_messages):
            limit += 1
            subset = list(raw_messages[-limit:])

    # Elimina ToolMessages órfãs na cabeça da lista
    while subset and isinstance(subset[0], ToolMessage):
        subset = subset[1:]

    # Remove chamada pendente no final se for o último elemento
    if subset and isinstance(subset[-1], AIMessage) and subset[-1].tool_calls:
        subset = subset[:-1]

    # Cura mensagens intermediárias sem ToolMessage
    final_messages: List[BaseMessage] = []
    i = 0
    while i < len(subset):
        msg = subset[i]
        if isinstance(msg, AIMessage) and msg.tool_calls:
            if i + 1 < len(subset) and isinstance(subset[i + 1], ToolMessage):
                final_messages.append(msg)
            else:
                final_messages.append(AIMessage(content=msg.content or "Processando...", tool_calls=[]))
        else:
            final_messages.append(msg)
        i += 1

    return final_messages

def extract_text_from_message(data: Any) -> str:
    """
    Extrai texto puro de forma determinística e resiliente a partir de qualquer estrutura:
    - str
    - list (blocos de texto [{'type': 'text', 'text': ...}], comum no Claude/Anthropic)
    - AIMessage / AIMessageChunk / HumanMessage / BaseMessage
    - ChatResult (.generations[0].message.content)
    - dict (ex: {'messages': [...]}, {'content': ...})
    """
    if not data:
        return ""
    if isinstance(data, str):
        return data
    if isinstance(data, list):
        parts = []
        for item in data:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
                elif "content" in item:
                    parts.append(extract_text_from_message(item["content"]))
            elif hasattr(item, "text"):
                parts.append(str(item.text))
            elif hasattr(item, "content"):
                parts.append(extract_text_from_message(item.content))
        return "".join(parts)
    if hasattr(data, "generations") and data.generations:
        first_gen = data.generations[0]
        if hasattr(first_gen, "message"):
            return extract_text_from_message(first_gen.message.content)
    if hasattr(data, "content"):
        return extract_text_from_message(data.content)
    if isinstance(data, dict):
        if "content" in data:
            return extract_text_from_message(data["content"])
        if "messages" in data and data["messages"]:
            return extract_text_from_message(data["messages"][-1])
    return str(data)

# Resolução temporal ciente de fuso horário (America/Sao_Paulo)
_resolve_temporal_context = resolve_temporal_context


def create_chat_model(
    model_name: str,
    temperature: Optional[float] = 0,
    max_tokens: Optional[int] = None,
) -> BaseChatModel:
    """
    Factory polimórfica para instanciação dinâmica de modelos de linguagem (LLMs).
    Suporta arquitetura híbrida multi-provedores (OpenAI, Anthropic Claude) seguindo o Open/Closed Principle (OCP).
    Em caso de chave ausente da Anthropic, realiza fallback gracioso para OpenAI.
    """
    model_name_clean = model_name.strip()
    if max_tokens is None:
        try:
            max_tokens = int(os.getenv("MAEVE_MAX_TOKENS", "4096"))
        except ValueError:
            max_tokens = 4096

    # 1. Provedor Anthropic Claude
    if model_name_clean.lower().startswith("claude"):
        anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if _ANTHROPIC_AVAILABLE and anthropic_api_key:
            logger.info("Inicializando ChatAnthropic com o modelo: %s", model_name_clean)
            # Modelos Claude recentes (Sonnet 5, etc.) depreciaram o parâmetro temperature na API /v1/messages.
            # Omitimos temperature passando None para evitar o erro 400 'temperature is deprecated for this model'.
            return ChatAnthropic(
                model=model_name_clean,
                temperature=None,
                max_tokens=max_tokens,
                api_key=anthropic_api_key,
                streaming=True,
            )
        else:
            fallback_model = os.getenv("MAEVE_SMART_FALLBACK_MODEL", "gpt-4o")
            logger.warning(
                "Modelo Anthropic '%s' configurado, mas ANTHROPIC_API_KEY não foi encontrada "
                "ou biblioteca indisponível. Realizando fallback gracioso para OpenAI (%s).",
                model_name_clean,
                fallback_model,
            )
            return ChatOpenAI(model=fallback_model, temperature=temperature or 0, max_tokens=max_tokens, streaming=True)

    # 2. Provedor OpenAI (GPT-5.6 Luna/Terra/Sol, o1, o3, GPT-4o, etc.)
    logger.info("Inicializando ChatOpenAI com o modelo: %s", model_name_clean)
    openai_kwargs: Dict[str, Any] = {
        "model": model_name_clean,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "streaming": True,
    }

    # Modelos com raciocínio (GPT-5.x, Luna, Terra, Sol, o1, o3):
    # No endpoint /v1/chat/completions, tools exigem explicitamente reasoning_effort='none'
    is_reasoning_model = (
        model_name_clean.lower().startswith(("gpt-5", "o1", "o3"))
        or any(k in model_name_clean.lower() for k in ["luna", "terra", "sol"])
        or os.getenv("MAEVE_FORCE_REASONING_EFFORT_NONE", "false").lower() == "true"
    )
    if is_reasoning_model:
        openai_kwargs["reasoning_effort"] = "none"

    return ChatOpenAI(**openai_kwargs)


class MaeveAgent:
    """
    Orquestrador Central da Maeve (LangGraph StateGraph).
    Responsabilidade Única: Gerenciar a máquina de estados, roteamento por intenção e execução do modelo.
    """
    def __init__(self, checkpointer=None):
        fast_model_name = os.getenv("MAEVE_FAST_MODEL", "gpt-4o-mini")
        smart_model_name = os.getenv("MAEVE_SMART_MODEL", "gpt-4o")

        # Modelos base multi-provedor (OpenAI / Anthropic)
        self.fast_model_base = create_chat_model(fast_model_name, temperature=0, max_tokens=2048)
        self.smart_model_base = create_chat_model(smart_model_name, temperature=0, max_tokens=4096)
        self.router_model = create_chat_model(fast_model_name, temperature=0, max_tokens=256)

        # Cache de modelos estáticos legados para compatibilidade
        self.fast_model = self.fast_model_base.bind_tools(ALL_TOOLS)
        self.smart_model = self.smart_model_base.bind_tools(ALL_TOOLS)

        self._vector_db = get_vector_db_service()
        self._graph = self._build_graph(checkpointer)

    def _build_graph(self, checkpointer):
        workflow = StateGraph(AgentState)

        workflow.add_node("router", self._router_node)
        workflow.add_node("call_model", self._call_model_node)
        workflow.add_node("tools", tool_node)

        workflow.set_entry_point("router")
        workflow.add_edge("router", "call_model")

        workflow.add_conditional_edges(
            "call_model",
            lambda x: "tools" if x['messages'][-1].tool_calls else END
        )
        workflow.add_edge("tools", "call_model")

        return workflow.compile(checkpointer=checkpointer)

    async def _router_node(self, state: AgentState) -> Dict[str, Any]:
        """
        Classifica a intenção (domínio) e complexidade do pedido.
        Preenche AgentState.current_intent e AgentState.routing_metadata.
        """
        last_msg = next((m for m in reversed(state['messages']) if isinstance(m, HumanMessage)), None)
        if not last_msg:
            return {
                "current_intent": "chat",
                "routing_metadata": {"model": "fast", "complexity": 1, "domain": "chat", "reason": "No human message"}
            }

        text_clean = str(last_msg.content).strip().lower()

        # Heurística Fast-Path: O(1) para saudações e mensagens triviais
        simple_patterns = r"^(oi|olá|ola|bom dia|boa tarde|boa noite|valeu|obrigado|ok|beleza|show|tchau|obg|sim|não|nao)[\.\!\?]*$"
        if len(text_clean) <= 20 or re.match(simple_patterns, text_clean):
            print(f"[Router Fast-Path]: Mensagem simples ('{text_clean[:30]}') -> Usando FAST sem chamar LLM.")
            return {
                "current_intent": "chat",
                "routing_metadata": {
                    "complexity": 1,
                    "model": "fast",
                    "domain": "chat",
                    "reason": "Heuristic fast-path: trivial query/greeting"
                }
            }

        routing_prompt = f"""
        Analise o pedido abaixo e responda APENAS em JSON no formato:
        {{
            "complexity": int (1 a 5),
            "model": "fast" | "smart",
            "domain": "tasks" | "knowledge" | "search" | "reminders" | "chat" | "general",
            "reason": "string curta"
        }}

        Diretrizes de Domínio:
        - tasks: TickTick, listas de afazeres, subtarefas, projetos, time-blocking, hábitos, conclusão.
        - knowledge: Obsidian, notas, Vault, pastas de notas, resumos de conhecimento pessoal.
        - search: Pesquisa na web, notícias, fatos em tempo real, deep research.
        - reminders: Lembretes temporais no Telegram ("me lembra amanhã às 10h").
        - chat: Conversas reflexivas, saudações, bate-papo sem necessidade de ferramentas.
        - general: Pedidos híbridos que misturam múltiplos domínios.

        Complexidade:
        1-2 (fast): Comandos diretos, criação simples, saudações, listagens.
        3-5 (smart): Planejamento, múltiplos passos, raciocínio profundo, consolidação.

        Pedido: {last_msg.content}
        """

        try:
            raw_decision = await self.router_model.ainvoke(routing_prompt, config={"tags": ["router_llm"]})
            content_str = str(raw_decision.content).strip()

            json_match = re.search(r"\{.*?\}", content_str, re.DOTALL)
            if json_match:
                decision = json.loads(json_match.group(0))
            else:
                clean_json = content_str.replace("```json", "").replace("```", "").strip()
                decision = json.loads(clean_json)

            if not isinstance(decision, dict) or "model" not in decision:
                decision = {"complexity": 1, "model": "fast", "domain": "general", "reason": "Formato não-padrão"}

            domain: IntentDomain = decision.get("domain", "general")
            print(f"[Router]: Complexidade {decision.get('complexity', 1)} | Domínio: {domain.upper()} -> {str(decision.get('model', 'fast')).upper()} ({decision.get('reason', '')})")

            return {
                "current_intent": domain,
                "routing_metadata": decision
            }
        except Exception as e:
            print(f"[Router Warning]: Erro no Router: {e}. Defaulting to Fast/General.")
            return {
                "current_intent": "general",
                "routing_metadata": {"model": "fast", "complexity": 1, "domain": "general", "reason": "Fallback due to error"}
            }

    async def _call_model_node(self, state: AgentState) -> Dict[str, Any]:
        """
        Executa a inferência aplicando Dynamic Tool Binding de acordo com o domínio ativo.
        """
        routing = state.get("routing_metadata") or {"model": "fast", "domain": "general"}
        current_intent = state.get("current_intent") or routing.get("domain", "general")

        # 1. Dynamic Tool Binding: Injeta apenas ferramentas do domínio ativo (elimina Tool Bleed)
        active_tools = get_tools_for_intent(current_intent)
        base_model = self.smart_model_base if routing.get("model") == "smart" else self.fast_model_base

        if active_tools:
            llm = base_model.bind_tools(active_tools)
        else:
            llm = base_model

        # 2. Sanitização do Histórico
        final_messages = _sanitize_message_history(state['messages'], limit=20)

        # 3. Extração de Contexto do Usuário
        user_msg = next((m for m in reversed(final_messages) if isinstance(m, HumanMessage)), None)
        user_id = user_msg.additional_kwargs.get("user_id", "unknown") if user_msg else "unknown"
        chat_id = user_msg.additional_kwargs.get("chat_id", "unknown") if user_msg else "unknown"
        last_query = user_msg.content if user_msg else ""

        # 4. Busca Seletiva no RAG (Qdrant)
        # Bypassa RAG se for conversa trivial ou se domínio for estritamente tasks/reminders sem busca
        should_search_rag = bool(last_query) and current_intent in ["knowledge", "general"]
        if should_search_rag and routing.get("complexity", 1) == 1:
            clean_q = str(last_query).strip().lower()
            if len(clean_q) < 4:
                should_search_rag = False

        context_docs = await self._vector_db.search_context(last_query, limit=3) if should_search_rag else []
        context_str = "\n".join([
            f"- {doc['metadata'].get('title', 'Nota')}: {doc['content'][:1000]}" for doc in context_docs
        ])

        # 5. Compilação de Contexto Temporal e System Prompt (Persona Dinâmica Assimétrica)
        temporal = _resolve_temporal_context()
        active_tier = routing.get("model", "fast")
        system_content = get_system_prompt(
            tier=active_tier,
            date=temporal["date"],
            time=temporal["time"],
            day_of_week=temporal["day_of_week"],
            period=temporal["period"],
            timezone=temporal.get("timezone", "America/Sao_Paulo"),
            user_id=user_id,
            chat_id=chat_id,
            obsidian_context=context_str,
        )

        # 6. Invocação com Fallback Resiliente
        history = [m for m in final_messages if not isinstance(m, SystemMessage)]
        prompt_messages = [SystemMessage(content=system_content)] + history

        try:
            response = await llm.ainvoke(prompt_messages)
            return {"messages": [response]}
        except Exception as e:
            err_msg = str(e)
            logger.error("❌ Erro na invocação LLM: %s", err_msg)

            # Recuperação adaptativa caso o modelo OpenAI rejeite reasoning_effort com tools
            if "reasoning_effort" in err_msg:
                logger.info("Detectada restrição de reasoning_effort com ferramentas. Reconfigurando para reasoning_effort='none'...")
                try:
                    if hasattr(base_model, "model_copy"):
                        retry_base = base_model.model_copy(update={"reasoning_effort": "none"})
                        retry_llm = retry_base.bind_tools(active_tools) if active_tools else retry_base
                        return {"messages": [await retry_llm.ainvoke(prompt_messages)]}
                except Exception as retry_err:
                    logger.warning("Falha na recuperação de reasoning_effort: %s", retry_err)

            # Recuperação adaptativa caso o provedor (ex: Anthropic) rejeite temperature
            if "temperature" in err_msg.lower():
                logger.info("Detectada restrição de temperature no modelo. Reconfigurando com temperature=None...")
                try:
                    if hasattr(base_model, "model_copy"):
                        retry_base = base_model.model_copy(update={"temperature": None})
                        retry_llm = retry_base.bind_tools(active_tools) if active_tools else retry_base
                        return {"messages": [await retry_llm.ainvoke(prompt_messages)]}
                except Exception as retry_err:
                    logger.warning("Falha na recuperação de temperature: %s", retry_err)

            if "400" in err_msg:
                last_human = next((m for m in reversed(history) if isinstance(m, HumanMessage)), None)
                fallback_history = [last_human] if last_human else []
                return {"messages": [await base_model.ainvoke([SystemMessage(content=system_content)] + fallback_history)]}
            raise e

    async def run_stream(self, user_input: Any, thread_id: str = "default-thread"):
        """Retorna stream de eventos para visualização e feedback no Telegram."""
        recursion_limit = int(os.getenv("MAEVE_RECURSION_LIMIT", "100"))
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": recursion_limit}
        input_msg = user_input if not isinstance(user_input, str) else ("user", user_input)

        async for event in self._graph.astream_events({"messages": [input_msg]}, config=config, version="v2"):
            yield event

    async def run(self, user_input: Any, thread_id: str = "default-thread") -> str:
        """Execução direta assíncrona retornando a resposta em texto."""
        recursion_limit = int(os.getenv("MAEVE_RECURSION_LIMIT", "100"))
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": recursion_limit}
        input_msg = user_input if not isinstance(user_input, str) else ("user", user_input)
        result = await self._graph.ainvoke({"messages": [input_msg]}, config=config)
        for m in reversed(result.get("messages", [])):
            txt = extract_text_from_message(m)
            if txt:
                return txt
        return "Processado."
