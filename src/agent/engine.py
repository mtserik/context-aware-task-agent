import os
from datetime import datetime, timedelta
import httpx
import yaml
import json
from typing import List, Dict, Any
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from src.agent.state import AgentState
from src.services.vector_db import VectorDBService
from src.services.ticktick import TickTickService
from src.services.obsidian import ObsidianService
from src.services.database import DatabaseService

# --- Inicialização dos Serviços ---
ticktick = TickTickService()
obsidian = ObsidianService()
vector_db = VectorDBService()
db_service = DatabaseService()

# --- Ferramentas Obsidian ---

@tool
async def create_obsidian_note(title: str, content: str, folder: str = "Inbox"):
    """Cria uma nova nota no Vault do Obsidian."""
    filename = f"{title}.md" if not title.endswith(".md") else title
    relative_path = os.path.join(folder, filename)
    commit_msg = f"Maeve: Criou nota '{title}' em {folder}"
    await obsidian.write_note(relative_path, content, commit_message=commit_msg)
    return f"Nota '{title}' criada com sucesso na pasta '{folder}'."

@tool
async def list_obsidian_folders():
    """Lista as pastas principais disponíveis no Vault do Obsidian."""
    folders = await obsidian.list_folders()
    return "Pastas disponíveis:\n" + "\n".join([f"- {f}" for f in folders]) if folders else "Nenhuma pasta encontrada."

@tool
async def delete_obsidian_item(relative_path: str):
    """Remove um arquivo ou pasta do Vault do Obsidian."""
    success = await obsidian.delete_item(relative_path, commit_message=f"Maeve: Removeu '{relative_path}'")
    return f"Item '{relative_path}' removido." if success else f"Erro: Caminho '{relative_path}' não encontrado."

@tool
async def move_obsidian_item(old_path: str, new_path: str):
    """Move ou renomeia um arquivo ou pasta dentro do Vault."""
    success = await obsidian.move_item(old_path, new_path, commit_message=f"Maeve: Moveu '{old_path}' para '{new_path}'")
    return f"Item movido para '{new_path}'." if success else f"Erro ao mover '{old_path}'."

@tool
async def cleanup_empty_obsidian_folders():
    """Remove pastas vazias no Vault."""
    removed = await obsidian.cleanup_empty_folders(commit_message="Maeve: Limpeza de pastas")
    return "Pastas removidas:\n" + "\n".join([f"- {f}" for f in removed]) if removed else "Nenhuma pasta vazia."

@tool
async def list_obsidian_notes():
    """Lista todas as notas no Vault."""
    notes = await obsidian.list_all_notes()
    return "Notas encontradas:\n" + "\n".join([f"- {n}" for n in notes]) if notes else "Nenhuma nota."

@tool
async def get_obsidian_note_details(relative_path: str):
    """Retorna metadados de uma nota (título, links, YAML)."""
    metadata = await obsidian.get_note_metadata(relative_path)
    if not metadata: return f"Erro: Nota '{relative_path}' não encontrada."
    fm_str = yaml.dump(metadata['frontmatter'], allow_unicode=True) if metadata['frontmatter'] else "Nenhum YAML"
    return f"Título: {metadata['title']}\nLinks: {', '.join(metadata['links'])}\nYAML:\n{fm_str}"

@tool
async def get_obsidian_note_content(relative_path: str):
    """Lê o conteúdo completo de uma nota."""
    full_path = os.path.join(obsidian.vault_path, relative_path)
    content = await obsidian.get_note_content(full_path)
    return content if content else f"Erro ao ler '{relative_path}'."

@tool
async def sync_obsidian_knowledge():
    """Sincroniza o Obsidian com o banco vetorial."""
    try:
        await obsidian.sync()
        notes = await obsidian.list_all_notes()
        texts, metadatas = [], []
        for note_path in notes:
            content = await obsidian.get_note_content(note_path)
            if content.strip():
                meta = await obsidian.get_note_metadata(note_path)
                texts.append(f"Título: {meta['title']}\nConteúdo: {content}")
                metadatas.append({"source": "obsidian", "path": meta['path'], "title": meta['title']})
        if texts: await vector_db.upsert_documents(texts=texts, metadatas=metadatas)
        return f"Sincronização concluída: {len(texts)} notas indexadas."
    except Exception as e: return f"Erro na sincronização: {str(e)}"

# --- Ferramentas TickTick ---

@tool
async def create_ticktick_task(
    title: str, 
    content: str = "", 
    due_date: str = None, 
    priority: int = 0,
    project_id: str = None,
    parent_id: str = None
):
    """
    Cria uma tarefa ou subtarefa no TickTick.
    IMPORTANTE: Se for criar subtarefas, você DEVE primeiro criar a tarefa pai, 
    receber o ID dela, e só então chamar esta ferramenta novamente para as filhas.
    """
    print(f"DEBUG [create_ticktick_task]: {title}, Priority={priority}, Parent={parent_id}")
    try:
        res = await ticktick.create_task(title, content, due_date, project_id, priority, parent_id)
        task_id = res.get('id')
        # Retorno curto e direto focado no ID para o LLM não se perder
        return f"ID_CRIADO: {task_id}"
    except Exception as e: return f"❌ Erro: {str(e)}"

@tool
async def update_ticktick_task(
    task_id: str,
    title: str = None,
    content: str = None,
    due_date: str = None,
    priority: int = None,
    status: int = None
):
    """
    Atualiza uma tarefa existente no TickTick.
    task_id: OBRIGATÓRIO. Busque usando get_ticktick_tasks antes.
    status: 0 (pendente), 2 (concluída).
    """
    print(f"DEBUG [update_ticktick_task]: ID={task_id}, Título={title}")
    kwargs = {}
    if title: kwargs["title"] = title
    if content: kwargs["content"] = content
    if due_date: kwargs["dueDate"] = due_date
    if priority is not None: kwargs["priority"] = priority
    if status is not None: kwargs["status"] = status
    
    try:
        await ticktick.update_task(task_id, **kwargs)
        return f"✅ Tarefa {task_id} atualizada com sucesso!"
    except Exception as e: return f"❌ Erro ao atualizar: {str(e)}"

@tool
async def create_ticktick_project(name: str, color: str = None, view_mode: str = "list"):
    """Cria um novo projeto (lista) no TickTick via API REST."""
    print(f"DEBUG [create_ticktick_project]: {name}")
    try:
        res = await ticktick.create_project(name, color, view_mode)
        return f"✅ Projeto criado! ID: {res.get('id')}"
    except Exception as e: return f"❌ Erro: {str(e)}"

@tool
async def get_ticktick_tasks(date_filter: str = None):
    """Lista tarefas pendentes. date_filter: 'YYYY-MM-DD'."""
    print(f"DEBUG [get_ticktick_tasks]: Filtro={date_filter}")
    tasks = await ticktick.get_tasks()
    if not tasks: return "Nenhuma tarefa pendente."
    if date_filter:
        tasks = [t for t in tasks if t.get('dueDate') and date_filter in t['dueDate']]
    return "\n".join([f"- {t['title']} (Vence: {t.get('dueDate', 'Sem data')}) [ID: {t['id']}]" for t in tasks])

@tool
async def get_ticktick_metrics_via_mcp(query_type: str, start_date: str = None):
    """Obtém métricas via MCP (habits, focus_records, tasks_completed)."""
    print(f"DEBUG [get_ticktick_metrics]: {query_type}")
    try:
        if query_type == "habits": content = await ticktick.get_habits()
        elif query_type == "focus_records": content = await ticktick.get_focus_records(start_date)
        else: content = await ticktick.get_completed_tasks_history(start_date)
        return f"Métricas via MCP:\n{content}"
    except Exception as e: return f"❌ Erro MCP: {str(e)}"

@tool
async def batch_ticktick_tasks(tasks_list: List[Dict[str, Any]]):
    """Cria múltiplas tarefas em lote via MCP."""
    try:
        result = await ticktick.call_mcp_tool("batch_add_tasks", {"tasks": tasks_list})
        return f"✅ {len(tasks_list)} tarefas criadas via lote."
    except Exception as e: return f"❌ Erro lote: {str(e)}"

tools = [
    create_obsidian_note, list_obsidian_folders, delete_obsidian_item, 
    move_obsidian_item, cleanup_empty_obsidian_folders, list_obsidian_notes,
    get_obsidian_note_details, get_obsidian_note_content, sync_obsidian_knowledge,
    create_ticktick_task, 
    update_ticktick_task,
    create_ticktick_project, 
    get_ticktick_tasks,
    get_ticktick_metrics_via_mcp, 
    batch_ticktick_tasks
]
tool_node = ToolNode(tools)

class MaeveAgent:
    def __init__(self, checkpointer=None, model_name: str = "gpt-4o-mini"):
        self.llm = ChatOpenAI(model=model_name, temperature=0).bind_tools(tools)
        self._graph = self._build_graph(checkpointer)

    def _build_graph(self, checkpointer):
        workflow = StateGraph(AgentState)
        workflow.add_node("call_model", self._call_model_node)
        workflow.add_node("tools", tool_node)
        workflow.set_entry_point("call_model")
        workflow.add_conditional_edges("call_model", lambda x: "tools" if x['messages'][-1].tool_calls else END)
        workflow.add_edge("tools", "call_model")
        return workflow.compile(checkpointer=checkpointer)

    async def _call_model_node(self, state: AgentState):
        from langchain_core.messages import SystemMessage, HumanMessage
        last_query = next((m.content for m in reversed(state['messages']) if isinstance(m, HumanMessage)), "")
        context_docs = await vector_db.search_context(last_query) if last_query else []
        context_str = "\n".join([f"- {doc['metadata'].get('title')}: {doc['content'][:200]}" for doc in context_docs])
        
        now = datetime.now()
        system_content = (
            f"Você é a Maeve. Data/Hora atual: {now.strftime('%Y-%m-%d %H:%M')}.\n"
            "REGRAS DE OURO:\n"
            "1. FORMATO DE DATA: Use SEMPRE 'YYYY-MM-DDTHH:MM:SS-0300'.\n"
            f"   - Exemplo (Amanhã às 09h): '{(now + timedelta(days=1)).strftime('%Y-%m-%d')}T09:00:00-0300'.\n"
            "2. SEQUENCIAMENTO: Para subtarefas, crie o PAI primeiro, pegue o ID, e em um novo turno crie as FILHAS.\n"
            "3. EDIÇÃO: Use `update_ticktick_task` com o ID obtido via `get_ticktick_tasks`.\n"
            "4. PRIORIDADES: 1=Baixa, 3=Média, 5=Alta.\n"
            f"Contexto:\n{context_str}"
        )
        return {"messages": [await self.llm.ainvoke([SystemMessage(content=system_content)] + state['messages'])]}

    async def run(self, user_input: str, thread_id: str = "default-thread") -> str:
        config = {"configurable": {"thread_id": thread_id}}
        result = await self._graph.ainvoke({"messages": [("user", user_input)]}, config=config)
        for m in reversed(result["messages"]):
            if hasattr(m, "content") and m.content: return m.content
        return "Processado."
