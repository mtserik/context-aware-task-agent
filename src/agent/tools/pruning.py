"""
Tool Output Pruning & Anti-Noise Sanitizer (Sprint 22).

Intercepta e higieniza retornos massivos de ferramentas (ToolMessage) antes de serem
persistidos no histórico conversacional do LangGraph / Supabase Checkpointer.
Evita 'Tool Flooding' e protege a janela de atenção do transformador contra JSONs descartáveis.
"""

import json
import logging
from typing import Any, List, Dict
from langchain_core.messages import BaseMessage, ToolMessage

logger = logging.getLogger("ToolPruner")

# Limites calibrados para densidade de tokens (Sprint 22)
MAX_KNOWLEDGE_CHARS = 1800
MAX_SEARCH_CHARS = 2500
MAX_GENERAL_CHARS = 3000
MAX_TASKS_TO_RETAIN = 20


def prune_tool_output(tool_name: str, raw_content: Any) -> str:
    """
    Higieniza e poda o retorno de uma ferramenta específica de acordo com seu domínio semântico.
    """
    if raw_content is None:
        return ""

    content_str = str(raw_content).strip()
    if not content_str:
        return ""

    tool_lower = (tool_name or "").lower()

    # 1. Domínio de Conhecimento / Obsidian Vault
    if "obsidian" in tool_lower or "knowledge" in tool_lower:
        if len(content_str) > MAX_KNOWLEDGE_CHARS:
            truncated = content_str[:MAX_KNOWLEDGE_CHARS].rstrip()
            total_len = len(content_str)
            return (
                f"{truncated}\n\n"
                f"... [📌 Conteúdo da nota podado pela Staff Maeve para proteção de contexto. "
                f"Exibindo {MAX_KNOWLEDGE_CHARS} de {total_len} caracteres. Consulte seções específicas se necessário.]"
            )
        return content_str

    # 2. Domínio de Tarefas / TickTick
    if "ticktick" in tool_lower or "task" in tool_lower:
        # Tenta sanitizar JSON bruto caso a ferramenta devolva estrutura serializada
        try:
            parsed = json.loads(content_str)
            if isinstance(parsed, list):
                sanitized_list = []
                for item in parsed[:MAX_TASKS_TO_RETAIN]:
                    if isinstance(item, dict):
                        sanitized_list.append({
                            "id": item.get("id") or item.get("task_id"),
                            "title": item.get("title") or item.get("name"),
                            "due_date": item.get("dueDate") or item.get("due_date"),
                            "priority": item.get("priority", 0),
                            "project_id": item.get("projectId") or item.get("project_id"),
                            "status": item.get("status", 0),
                        })
                    else:
                        sanitized_list.append(item)
                trimmed_count = len(parsed) - len(sanitized_list)
                result_str = json.dumps(sanitized_list, ensure_ascii=False)
                if trimmed_count > 0:
                    result_str += f"\n... [📌 {trimmed_count} tarefas adicionais omitidas para concisão]"
                return result_str
        except Exception:
            pass

        # Fallback de texto puro para listagens longas
        if len(content_str) > MAX_GENERAL_CHARS:
            return content_str[:MAX_GENERAL_CHARS].rstrip() + "\n... [📌 Listagem extensa truncada]"
        return content_str

    # 3. Domínio de Pesquisa Web / Search
    if "search" in tool_lower or "tavily" in tool_lower or "research" in tool_lower:
        if len(content_str) > MAX_SEARCH_CHARS:
            return content_str[:MAX_SEARCH_CHARS].rstrip() + "\n... [📌 Resultados de busca podados para preservar contexto]"
        return content_str

    # 4. Domínio Geral
    if len(content_str) > MAX_GENERAL_CHARS:
        return content_str[:MAX_GENERAL_CHARS].rstrip() + "\n... [📌 Output podado]"

    return content_str


def prune_tool_messages(messages: List[BaseMessage]) -> List[BaseMessage]:
    """
    Percorre a lista de mensagens do histórico e aplica a poda cirúrgica
    exclusivamente nas instâncias de ToolMessage, preservando intactos
    HumanMessages, AIMessages e SystemMessages.
    """
    pruned_messages: List[BaseMessage] = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            tool_name = getattr(msg, "name", "") or getattr(msg, "tool_name", "")
            original_content = msg.content
            if isinstance(original_content, str):
                pruned_content = prune_tool_output(tool_name, original_content)
                if pruned_content != original_content:
                    # Cria cópia com conteúdo podado
                    pruned_msg = ToolMessage(
                        content=pruned_content,
                        tool_call_id=msg.tool_call_id,
                        name=msg.name,
                        id=msg.id,
                        additional_kwargs=getattr(msg, "additional_kwargs", {}),
                    )
                    pruned_messages.append(pruned_msg)
                    continue
        pruned_messages.append(msg)
    return pruned_messages
