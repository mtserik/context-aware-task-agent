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
from src.services.search import SearchService
from src.agent.prompts import SYSTEM_PROMPT_TEMPLATE

# --- Inicialização dos Serviços ---
ticktick = TickTickService()
obsidian = ObsidianService()
vector_db = VectorDBService()
db_service = DatabaseService()
search_service = SearchService()

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
async def batch_update_ticktick_tasks(tasks_to_update: List[Dict[str, Any]]):
    """
    ÚNICA ferramenta para atualizar tarefas no TickTick (seja 1 ou várias).
    Use para mudar datas, títulos, projetos ou concluir tarefas.
    Cada objeto DEVE ter: {"task_id": "...", "title": "...", "project_id": "..."}
    Campos suportados: "due_date" (Fim), "start_date" (Início), "status", "priority".
    DICA: Para Time Blocking (duração), envie datas de início e fim no mesmo dia com horários diferentes.
    """
    print(f"🔥 [BATCH_UPDATE] Iniciando com {len(tasks_to_update)} tarefas.")
    try:
        normalized = []
        for t in tasks_to_update:
            item = t.copy()
            if "project_id" in item: item["projectId"] = item.pop("project_id")
            
            # Normalização de Datas (Time Blocking Support)
            final_due = item.pop("due_date", None)
            final_start = item.pop("start_date", None)

            if final_due:
                # Garante fuso horário BR
                if "Z" not in final_due and "-" not in final_due[10:]: final_due += "-0300"
                item["dueDate"] = final_due
                
                # Se a IA não definiu um início, o início é igual ao fim (sem duração)
                if not final_start:
                    item["startDate"] = final_due
                else:
                    if "Z" not in final_start and "-" not in final_start[10:]: final_start += "-0300"
                    item["startDate"] = final_start

            normalized.append(item)
            
        results = await ticktick.batch_update_tasks(normalized)
        successes = [r for r in results if r.get("status") == 200]
        return f"✅ Processadas {len(results)} atualizações. Sucessos: {len(successes)}."
    except Exception as e:
        return f"❌ Erro no motor de lote: {str(e)}"

@tool
async def create_ticktick_project(name: str, color: str = None, view_mode: str = "list"):



    """Cria um novo projeto (lista) no TickTick via API REST."""
    print(f"DEBUG [create_ticktick_project]: {name}")
    try:
        res = await ticktick.create_project(name, color, view_mode)
        return f"✅ Projeto criado! ID: {res.get('id')}"
    except Exception as e: return f"❌ Erro: {str(e)}"

@tool
async def get_ticktick_tasks(date_filter: str = None, project_id: str = None):
    """
    Lista tarefas PENDENTES para ter uma visão geral.
    date_filter: 'YYYY-MM-DD'.
    Use esta ferramenta para LISTAR e IDENTIFICAR tarefas (pegar IDs).
    Para ler o conteúdo completo/notas, use 'get_ticktick_item_details'.
    """
    print(f"DEBUG [get_ticktick_tasks]: Filtro={date_filter}, Projeto={project_id}")
    try:
        tasks = await ticktick.get_tasks(project_id=project_id)
        if not tasks: return "Nenhuma tarefa pendente encontrada."
        
        # Filtro de data
        if date_filter:
            tasks = [t for t in tasks if t.get('dueDate') and date_filter in t['dueDate']]
        
        if not tasks: return f"Nenhuma tarefa pendente para a data {date_filter}."
        
        # Limita a 40 tarefas para não estourar contexto da IA
        display_tasks = tasks[:40]
        # Retornamos uma estrutura que a IA possa parsear facilmente
        result = "\n".join([
            f"- {t['title']} (Vence: {t.get('dueDate', 'Sem data')}) [ID: {t['id']}, Proj: {t['projectId']}, Kind: {t.get('kind', 'TASK')}]" 
            for t in display_tasks
        ])
        
        if len(tasks) > 40:
            result += f"\n\n... e mais {len(tasks) - 40} tarefas não listadas por brevidade."
            
        return result
    except Exception as e:
        return f"❌ Erro ao buscar tarefas: {str(e)}"

@tool
async def get_ticktick_item_details(item_id: str):
    """
    Obtém o conteúdo COMPLETO e detalhes de uma tarefa ou nota específica.
    Use para ler o que está escrito dentro de uma nota antes de replicar no Obsidian.
    """
    try:
        details = await ticktick.get_task_by_id(item_id)
        return json.dumps(details, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"❌ Erro ao buscar detalhes: {str(e)}"

@tool
async def delete_ticktick_item(project_id: str, item_id: str):
    """Remove definitivamente uma tarefa ou nota do TickTick."""
    try:
        success = await ticktick.delete_task(project_id, item_id)
        return "✅ Item removido com sucesso." if success else "❌ Falha ao remover item."
    except Exception as e:
        return f"❌ Erro ao deletar: {str(e)}"

@tool
async def list_ticktick_structure(include_groups: bool = True):
    """
    Lista a estrutura de pastas (Grupos) e Listas (Projetos) do TickTick.
    Use para se localizar e saber em qual lista criar ou buscar algo.
    """
    try:
        projects = await ticktick.list_projects()
        structure = "ESTRUTURA TICKTICK:\n"
        
        if include_groups:
            groups = await ticktick.list_project_groups()
            group_map = {g['id']: g['name'] for g in groups}
            # Organiza por grupo
            by_group = {}
            for p in projects:
                gid = p.get('groupId', 'no_group')
                if gid not in by_group: by_group[gid] = []
                by_group[gid].append(p)
            
            for gid, projs in by_group.items():
                gname = group_map.get(gid, "Sem Pasta")
                structure += f"\n📂 {gname}:\n"
                for p in projs:
                    structure += f"  - 📝 {p['name']} [ID: {p['id']}, Kind: {p.get('kind')}]\n"
        else:
            for p in projects:
                structure += f"- 📝 {p['name']} [ID: {p['id']}, Kind: {p.get('kind')}]\n"
                
        return structure
    except Exception as e:
        return f"❌ Erro ao listar estrutura: {str(e)}"

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
async def batch_create_ticktick_tasks(tasks_list: List[Dict[str, Any]]):
    """Cria múltiplas tarefas em lote no TickTick."""
    try:
        result = await ticktick.call_mcp_tool("batch_add_tasks", {"tasks": tasks_list})
        return f"✅ {len(tasks_list)} tarefas criadas."
    except Exception as e: return f"❌ Erro lote criação: {str(e)}"

# --- Ferramentas de Lembrete ---

@tool
async def set_reminder(content: str, reminder_at: str, user_id: str, chat_id: str):
    """
    Agenda um lembrete customizado.
    reminder_at: Formato ISO 'YYYY-MM-DDTHH:MM:SS-0300'.
    """
    try:
        reminder_id = await db_service.create_reminder(user_id, chat_id, content, reminder_at)
        return f"✅ Lembrete agendado com sucesso! [ID: {reminder_id}]"
    except Exception as e:
        return f"❌ Erro ao agendar lembrete: {str(e)}"

@tool
async def list_active_reminders(user_id: str):
    """Lista todos os lembretes pendentes do usuário."""
    try:
        reminders = await db_service.list_user_reminders(user_id)
        if not reminders: return "Você não tem lembretes ativos."
        return "Lembretes ativos:\n" + "\n".join([f"- {r[0]} em {r[1].strftime('%d/%m %H:%M')}" for r in reminders])
    except Exception as e:
        return f"❌ Erro ao listar lembretes: {str(e)}"

# --- Ferramentas Web Search ---

@tool
async def web_search(query: str):
    """
    Realiza uma busca rápida na internet para fatos atuais ou informações gerais.
    Ideal para perguntas como 'qual a previsão do tempo' ou 'quem venceu o jogo'.
    """
    # O logger aqui será capturado pelo TelegramService se quisermos feedback em tempo real
    print(f"WEB_SEARCH_START: {query}") 
    results = await search_service.search(query)
    if not results or "error" in results[0]:
        return f"Erro na pesquisa: {results[0].get('error') if results else 'Sem resultados'}"
    
    formatted = "\n".join([f"- {r['title']} ({r['url']}): {r['content'][:300]}..." for r in results])
    return f"Resultados da Pesquisa Web:\n{formatted}"

@tool
async def deep_research(query: str):
    """
    Realiza uma pesquisa aprofundada na web para tópicos complexos.
    Sintetiza informações de múltiplas fontes. Use quando o usuário pedir
    uma 'investigação', 'estudo detalhado' ou 'pesquisa profunda'.
    """
    print(f"DEEP_RESEARCH_START: {query}")
    synthesis = await search_service.deep_research(query)
    return f"Síntese da Pesquisa Aprofundada:\n{synthesis}"

tools = [
    create_obsidian_note, list_obsidian_folders, delete_obsidian_item, 
    move_obsidian_item, cleanup_empty_obsidian_folders, list_obsidian_notes,
    get_obsidian_note_details, get_obsidian_note_content, sync_obsidian_knowledge,
    create_ticktick_task, 
    create_ticktick_project, 
    get_ticktick_tasks,
    get_ticktick_item_details,
    delete_ticktick_item,
    list_ticktick_structure,
    get_ticktick_metrics_via_mcp, 
    batch_create_ticktick_tasks,
    batch_update_ticktick_tasks,
    set_reminder, list_active_reminders,
    web_search, deep_research
]
tool_node = ToolNode(tools)

class MaeveAgent:
    def __init__(self, checkpointer=None, model_name: str = "gpt-4o-mini"):
        self.llm = ChatOpenAI(model=model_name, temperature=0, max_tokens=2048).bind_tools(tools)
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
        # Extrair user_id e chat_id das mensagens (se disponíveis)
        user_msg = next((m for m in reversed(state['messages']) if isinstance(m, HumanMessage)), None)
        user_id = user_msg.additional_kwargs.get("user_id", "unknown") if user_msg else "unknown"
        chat_id = user_msg.additional_kwargs.get("chat_id", "unknown") if user_msg else "unknown"

        last_query = user_msg.content if user_msg else ""
        context_docs = await vector_db.search_context(last_query) if last_query else []
        context_str = "\n".join([f"- {doc['metadata'].get('title')}: {doc['content'][:200]}" for doc in context_docs])
        
        # --- Cálculo de Contexto Temporal ---
        now_dt = datetime.now()
        date_str = now_dt.strftime('%d/%m/%Y')
        time_str = now_dt.strftime('%H:%M')
        
        # Dia da semana em Português
        dias = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
        day_of_week = dias[now_dt.weekday()]
        
        # Período do dia
        hour = now_dt.hour
        if 5 <= hour < 12: period = "manhã"
        elif 12 <= hour < 18: period = "tarde"
        elif 18 <= hour < 24: period = "noite"
        else: period = "madrugada"

        # Usa o template centralizado de prompts
        system_content = SYSTEM_PROMPT_TEMPLATE.format(
            date=date_str,
            time=time_str,
            day_of_week=day_of_week,
            period=period,
            user_id=user_id,
            chat_id=chat_id,
            obsidian_context=context_str
        )
        
        return {"messages": [await self.llm.ainvoke([SystemMessage(content=system_content)] + state['messages'])]}

    async def run_stream(self, user_input: Any, thread_id: str = "default-thread"):
        """Versão que retorna o stream de eventos para detecção de ferramentas."""
        config = {"configurable": {"thread_id": thread_id}}
        input_msg = user_input if not isinstance(user_input, str) else ("user", user_input)
        
        async for event in self._graph.astream_events({"messages": [input_msg]}, config=config, version="v1"):
            yield event

    async def run(self, user_input: Any, thread_id: str = "default-thread") -> str:
        config = {"configurable": {"thread_id": thread_id}}
        # Aceita tanto string quanto BaseMessage (para passar additional_kwargs)
        input_msg = user_input if not isinstance(user_input, str) else ("user", user_input)
        result = await self._graph.ainvoke({"messages": [input_msg]}, config=config)
        for m in reversed(result["messages"]):
            if hasattr(m, "content") and m.content: return m.content
        return "Processado."
