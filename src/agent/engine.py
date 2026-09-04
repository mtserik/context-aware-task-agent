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
from src.agent.prompts import SYSTEM_PROMPT_TEMPLATE, get_system_prompt, get_system_prompt_parts
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

def _sanitize_message_history(raw_messages: List[BaseMessage], limit: int = 30) -> List[BaseMessage]:
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


def _apply_anthropic_history_cache(history: List[BaseMessage]) -> List[BaseMessage]:
    """
    Adiciona breakpoint de cache (cache_control ephemeral) na penúltima mensagem do histórico
    (final do turno anterior) para que todo o histórico de conversas acumulado seja lido com 90% de desconto.
    """
    if len(history) < 2:
        return history

    new_history = list(history)
    target_idx = len(new_history) - 2
    target_msg = new_history[target_idx]

    text = extract_text_from_message(target_msg)
    if not text:
        return history

    cached_content = [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]

    if isinstance(target_msg, AIMessage):
        new_history[target_idx] = AIMessage(
            content=cached_content,
            tool_calls=getattr(target_msg, "tool_calls", []),
            id=getattr(target_msg, "id", None),
        )
    elif isinstance(target_msg, HumanMessage):
        new_history[target_idx] = HumanMessage(
            content=cached_content,
            additional_kwargs=getattr(target_msg, "additional_kwargs", {}),
            id=getattr(target_msg, "id", None),
        )
    elif isinstance(target_msg, ToolMessage):
        new_history[target_idx] = ToolMessage(
            content=cached_content,
            tool_call_id=getattr(target_msg, "tool_call_id", ""),
            id=getattr(target_msg, "id", None),
        )
    return new_history

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
        # Remove eventuais blocos de pensamento interno <think>...</think> caso presentes
        clean_text = re.sub(r"<think>.*?</think>", "", data, flags=re.DOTALL)
        return clean_text
    if isinstance(data, list):
        parts = []
        for item in data:
            if isinstance(item, str):
                parts.append(extract_text_from_message(item))
            elif isinstance(item, dict):
                # Ignora explicitamente blocos de pensamento interno (Anthropic extended thinking / reasoning)
                if item.get("type") in ["thinking", "reasoning"]:
                    continue
                if item.get("type") == "text":
                    parts.append(extract_text_from_message(item.get("text", "")))
                elif "content" in item:
                    parts.append(extract_text_from_message(item["content"]))
            elif hasattr(item, "text"):
                if getattr(item, "type", "") in ["thinking", "reasoning"]:
                    continue
                parts.append(str(item.text))
            elif hasattr(item, "content"):
                if getattr(item, "type", "") in ["thinking", "reasoning"]:
                    continue
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

        # Garante que SEMPRE exista um checkpointer ativo (evita que a máquina de estados fique sem memória)
        if checkpointer is None:
            from langgraph.checkpoint.memory import MemorySaver
            checkpointer = MemorySaver()
            logger.info("Nenhum checkpointer externo fornecido. Inicializando com MemorySaver volátil em memória.")

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
        Classifica a intenção (domínio) e complexidade do pedido considerando o contexto conversacional recente.
        Preenche AgentState.current_intent e AgentState.routing_metadata.
        """
        messages = state.get('messages', [])
        last_msg = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
        if not last_msg:
            return {
                "current_intent": "chat",
                "routing_metadata": {"model": "fast", "complexity": 1, "domain": "chat", "reason": "No human message"}
            }

        text_clean = str(last_msg.content).strip().lower()

        # Encontra a última mensagem da Maeve (assistente) antes da mensagem humana atual
        last_ai_msg = None
        for m in reversed(messages):
            if isinstance(m, AIMessage):
                last_ai_msg = m
                break

        ai_text = extract_text_from_message(last_ai_msg).lower() if last_ai_msg else ""

        # 1. Heurística Contextual de Confirmação:
        # Se a Maeve perguntou/propôs uma ação ("quer que eu salve no Obsidian?") e o usuário confirma ("sim", "pode criar", "faz isso")
        confirmation_patterns = r"^(sim|pode|pode criar|pode salvar|pode fazer|faz isso|cria|salva|bora|manda bala|manda ver|com certeza|claro|por favor|confirmo|positivo|ok|ok pode|vai em frente)[\.\!\?]*$"
        is_confirmation = bool(re.match(confirmation_patterns, text_clean)) or any(text_clean.startswith(p) for p in ["sim,", "pode ", "faz ", "cria ", "salva "])

        if is_confirmation and last_ai_msg:
            # Assistente acabou de propor criar nota ou documentar no Obsidian
            # O raciocínio conceitual já foi concebido pela Maeve no turno anterior.
            # A escrita da nota é puramente operacional -> FAST (Luna, 20x mais barato)
            if any(k in ai_text for k in ["obsidian", "vault", "segundo cérebro", "second brain", "nota", "salvar esse", "salvar isso", "documentar"]):
                logger.info("[Router Contextual]: Confirmação para ação de Obsidian detectada -> KNOWLEDGE / FAST (Luna)")
                return {
                    "current_intent": "knowledge",
                    "routing_metadata": {
                        "complexity": 1,
                        "model": "fast",
                        "domain": "knowledge",
                        "reason": "Escrita operacional de nota no Obsidian a partir de contexto prévio (Luna)"
                    }
                }
            # Assistente acabou de propor criar/atualizar tarefa no TickTick
            if any(k in ai_text for k in ["tarefa", "task", "ticktick", "agendar", "backlog", "time-blocking"]):
                logger.info("[Router Contextual]: Confirmação para ação de Tarefa detectada -> TASKS / FAST")
                return {
                    "current_intent": "tasks",
                    "routing_metadata": {
                        "complexity": 1,
                        "model": "fast",
                        "domain": "tasks",
                        "reason": "Confirmação contextual do usuário para tarefa no TickTick"
                    }
                }
            # Assistente acabou de propor agendar lembrete
            if any(k in ai_text for k in ["lembrete", "lembrar", "notificar"]):
                logger.info("[Router Contextual]: Confirmação para ação de Lembrete detectada -> REMINDERS / FAST")
                return {
                    "current_intent": "reminders",
                    "routing_metadata": {
                        "complexity": 1,
                        "model": "fast",
                        "domain": "reminders",
                        "reason": "Confirmação contextual do usuário para agendar lembrete"
                    }
                }

        # 2. Heurística Fast-Path: O(1) para saudações e acks isolados
        # NUNCA aplicar se houver pergunta pendente do assistente na conversa anterior
        greeting_patterns = r"^(oi|olá|ola|bom dia|boa tarde|boa noite|valeu|obrigado|tchau|até mais|falou|ok|show|beleza|blz)(\s+(maeve|tudo bem|td bem))?[\.\!\?]*$"
        has_pending_question = bool(last_ai_msg and "?" in ai_text)

        if not has_pending_question and re.match(greeting_patterns, text_clean):
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

        # 3. LLM Router com Injeção de Contexto Recente (resolve ambiguidades e pronomes "isso", "aquilo")
        recent_context = ""
        if last_ai_msg:
            ai_snippet = extract_text_from_message(last_ai_msg)[:350].strip()
            recent_context = f"\nContexto Recente - Última Mensagem da Maeve (Assistente):\n\"{ai_snippet}\"\n"

        routing_prompt = f"""
        Analise o pedido abaixo considerando o contexto recente da conversa e responda APENAS em JSON no formato:
        {{
            "complexity": int (1 a 5),
            "model": "fast" | "smart",
            "domain": "tasks" | "knowledge" | "search" | "reminders" | "chat" | "general",
            "reason": "string curta"
        }}

        Diretrizes de Domínio:
        - tasks: TickTick, listas de afazeres, subtarefas, projetos, time-blocking, hábitos, conclusão.
        - knowledge: Obsidian, notas, Vault, pastas de notas, resumos de conhecimento pessoal, criar ou mover notas.
        - search: Pesquisa na web, notícias, fatos em tempo real, deep research.
        - reminders: Lembretes temporais no Telegram ("me lembra amanhã às 10h").
        - chat: Conversas reflexivas, saudações, bate-papo sem necessidade de ferramentas.
        - general: Pedidos híbridos que misturam múltiplos domínios ou continuam ações anteriores.

        Diretrizes de Complexidade & Escolha de Modelo:
        - 1-2 (fast / Luna): Comandos diretos, escrita e criação operacional de notas no Obsidian (salvar ideias, notas rápidas, mover arquivos), gerenciamento de tarefas no TickTick, lembretes, saudações e listagens.
        - 3-5 (smart / Sonnet): Raciocínio conceitual profundo, debates teóricos de arquitetura/engenharia/ciência de dados, planejamento estratégico denso, análises estatísticas complexas e consolidação de múltiplos conceitos novos.
{recent_context}
        Pedido Atual do Usuário:
        "{last_msg.content}"
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
        Executa a inferência aplicando Dynamic Tool Binding e Anthropic Prompt Caching (90% desconto de tokens).
        """
        routing = state.get("routing_metadata") or {"model": "fast", "domain": "general"}
        current_intent = state.get("current_intent") or routing.get("domain", "general")

        base_model = self.smart_model_base if routing.get("model") == "smart" else self.fast_model_base
        is_anthropic = (
            (isinstance(base_model, ChatAnthropic) if _ANTHROPIC_AVAILABLE else False)
            or "claude" in getattr(base_model, "model_name", "").lower()
            or "claude" in getattr(base_model, "model", "").lower()
        )

        # 1. Dynamic Tool Binding com Anthropic Tool Caching
        active_tools = get_tools_for_intent(current_intent)
        if active_tools:
            if is_anthropic and _ANTHROPIC_AVAILABLE:
                from langchain_anthropic.chat_models import convert_to_anthropic_tool
                formatted_tools = [convert_to_anthropic_tool(t) for t in active_tools]
                # Breakpoint de Cache: marca a última ferramenta ativa com cache_control ephemeral
                formatted_tools[-1]["cache_control"] = {"type": "ephemeral"}
                llm = base_model.bind(tools=formatted_tools)
            else:
                llm = base_model.bind_tools(active_tools)
        else:
            llm = base_model

        # 2. Sanitização do Histórico (janela expandida para 30 mensagens sem penalidade de custo graças ao cache)
        final_messages = _sanitize_message_history(state['messages'], limit=30)

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

        # 5. Compilação de Contexto Temporal e System Prompt (Persona Dinâmica Assimétrica + Prompt Caching)
        temporal = _resolve_temporal_context()
        active_tier = routing.get("model", "fast")
        static_prompt, dynamic_prompt = get_system_prompt_parts(
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

        if is_anthropic:
            # Anthropic Prompt Caching: Estrutura o SystemMessage em blocos com cache_control no bloco estático (>1024 tokens)
            system_message = SystemMessage(
                content=[
                    {
                        "type": "text",
                        "text": static_prompt,
                        "cache_control": {"type": "ephemeral"}
                    },
                    {
                        "type": "text",
                        "text": dynamic_prompt
                    }
                ]
            )
        else:
            system_message = SystemMessage(content=f"{static_prompt}\n\n{dynamic_prompt}")

        # 6. Invocação com Fallback Resiliente e Cache de Histórico
        history = [m for m in final_messages if not isinstance(m, SystemMessage)]
        if is_anthropic and len(history) >= 2:
            history = _apply_anthropic_history_cache(history)

        prompt_messages = [system_message] + history

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
