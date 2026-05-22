import os
from datetime import datetime, timedelta
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from src.agent.state import AgentState
from src.services.vector_db import VectorDBService
from src.services.ticktick import TickTickService
from src.services.obsidian import ObsidianService

# --- Definição das Tools ---
ticktick = TickTickService()
obsidian = ObsidianService()

@tool
async def create_obsidian_note(title: str, content: str, folder: str = "Inbox"):
    """
    Cria uma nova nota no Vault do Obsidian.
    folder: Opcional. Pasta onde a nota será salva (ex: 'Projetos', 'Estudos'). Padrão é 'Inbox'.
    """
    filename = f"{title}.md" if not title.endswith(".md") else title
    relative_path = os.path.join(folder, filename)
    commit_msg = f"Maeve: Criou nota '{title}' em {folder}"
    await obsidian.write_note(relative_path, content, commit_message=commit_msg)
    return f"Nota '{title}' criada com sucesso na pasta '{folder}'."

@tool
async def list_obsidian_folders():
    """
    Lista as pastas principais disponíveis no Vault do Obsidian.
    Útil para saber onde salvar uma nova nota.
    """
    folders = await obsidian.list_folders()
    if not folders:
        return "Nenhuma pasta encontrada no Vault (apenas a raiz)."
    return "Pastas disponíveis:\n" + "\n".join([f"- {f}" for f in folders])

@tool
async def delete_obsidian_item(relative_path: str):
    """
    Remove um arquivo ou pasta do Vault do Obsidian.
    USE COM CAUTELA. relative_path deve incluir a pasta (ex: 'Inbox/NotaVelha.md').
    """
    commit_msg = f"Maeve: Removeu '{relative_path}'"
    success = await obsidian.delete_item(relative_path, commit_message=commit_msg)
    if success:
        return f"Item '{relative_path}' removido com sucesso."
    return f"Erro: O caminho '{relative_path}' não foi encontrado."

@tool
async def move_obsidian_item(old_path: str, new_path: str):
    """
    Move ou renomeia um arquivo ou pasta dentro do Vault.
    Útil para organizar notas (ex: mover de 'Inbox/Nota.md' para 'Projetos/Nota.md').
    """
    commit_msg = f"Maeve: Moveu '{old_path}' para '{new_path}'"
    success = await obsidian.move_item(old_path, new_path, commit_message=commit_msg)
    if success:
        return f"Item movido de '{old_path}' para '{new_path}' com sucesso."
    return f"Erro: O caminho de origem '{old_path}' não foi encontrado."

@tool
async def cleanup_empty_obsidian_folders():
    """
    Remove recursivamente todas as pastas vazias no Vault do Obsidian.
    Útil para limpar a estrutura após mover várias notas.
    """
    commit_msg = "Maeve: Limpeza de pastas vazias"
    removed = await obsidian.cleanup_empty_folders(commit_message=commit_msg)
    if not removed:
        return "Nenhuma pasta vazia encontrada para remoção."
    return "Pastas removidas:\n" + "\n".join([f"- {f}" for f in removed])

@tool
async def create_ticktick_task(title: str, content: str = "", due_date: str = None):
    """
    Cria uma nova tarefa no TickTick.
    due_date deve estar no formato ISO com fuso horário do Brasil: 'YYYY-MM-DDTHH:MM:SS-0300'
    Exemplo para hoje às 23h (se hoje for 18/05): '2026-05-18T23:00:00-0300'
    """
    return await ticktick.create_task(title, content, due_date)

@tool
async def get_ticktick_tasks(date_filter: str = None):
    """
    Lista as tarefas pendentes no TickTick.
    date_filter: Opcional. Filtra por uma data específica no formato 'YYYY-MM-DD'.
    Se não fornecido, retorna as tarefas em aberto.
    """
    tasks = await ticktick.get_tasks()
    if not tasks:
        return "Nenhuma tarefa pendente encontrada no TickTick."
    
    # Se houver filtro de data, tentamos bater a string da data
    if date_filter:
        # Nota: O TickTick pode retornar a data em UTC (dia seguinte se for tarde da noite no Brasil)
        # Por isso, procuramos pela data no texto bruto do dueDate
        filtered = [t for t in tasks if t.get('dueDate') and date_filter in t['dueDate']]
        if not filtered:
            # Fallback: Se não achou na data exata, mostra as próximas para o LLM não se perder
            upcoming = "\n".join([f"- {t['title']} (Vence: {t.get('dueDate')})" for t in tasks[:5]])
            return f"Nenhuma tarefa pendente encontrada para a data {date_filter}.\nPróximas tarefas:\n{upcoming}"
        tasks = filtered

    return "\n".join([f"- {t['title']} (Vence em: {t.get('dueDate', 'Sem data')})" for t in tasks])

tools = [create_ticktick_task, get_ticktick_tasks, create_obsidian_note, list_obsidian_folders, delete_obsidian_item, move_obsidian_item, cleanup_empty_obsidian_folders]
tool_node = ToolNode(tools)

class MaeveAgent:
    def __init__(self, model_name: str = "gpt-4o-mini"):
        self.vector_db = VectorDBService()
        self.llm = ChatOpenAI(model=model_name, temperature=0).bind_tools(tools)
        self._graph = self._build_graph()

    def _build_graph(self):
        """Define a estrutura interna do LangGraph com suporte a ferramentas."""
        workflow = StateGraph(AgentState)
        
        workflow.add_node("call_model", self._call_model_node)
        workflow.add_node("tools", tool_node)
        
        workflow.set_entry_point("call_model")
        
        # Lógica de roteamento: Se o modelo chamar ferramentas, vai para o nó de ferramentas
        def should_continue(state: AgentState):
            messages = state['messages']
            last_message = messages[-1]
            if last_message.tool_calls:
                return "tools"
            return END

        workflow.add_conditional_edges("call_model", should_continue)
        workflow.add_edge("tools", "call_model") # Volta para o modelo após executar a ferramenta
        
        return workflow.compile()

    async def _call_model_node(self, state: AgentState):
        """Lógica de processamento do nó com RAG e Tool Calling."""
        from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
        
        messages = state['messages']
        
        # 1. Recuperação de Contexto (RAG)
        last_user_query = ""
        for m in reversed(messages):
            if isinstance(m, HumanMessage) or (isinstance(m, tuple) and m[0] == "user"):
                last_user_query = m.content if hasattr(m, "content") else m[1]
                break
        
        context_str = ""
        if last_user_query:
            context_docs = await self.vector_db.search_context(last_user_query)
            context_str = "\n".join([f"- {doc}" for doc in context_docs])
        
        # 2. Construção das Mensagens para o LLM
        now = datetime.now()
        today_str = now.strftime('%Y-%m-%d')
        tomorrow_str = (now + timedelta(days=1)).strftime('%Y-%m-%d')
        current_date_info = now.strftime('%Y-%m-%d %H:%M:%S (Dia da semana: %A, Fuso: BRT/UTC-3)')
        
        system_content = (
            "Você é a Maeve, uma assistente pessoal inteligente, proativa e organizada.\n"
            f"Data/Hora local do usuário (Brasil): {current_date_info}\n"
            f"Hoje é: {today_str}\n"
            f"Amanhã é: {tomorrow_str}\n\n"
            "DIRETRIZES DE SEGUNDO CÉREBRO (OBSIDIAN & MÉTODO PARA):\n"
            "- Você organiza o conhecimento do usuário utilizando o método PARA:\n"
            "  1. Projects: Projetos ativos com data de término.\n"
            "  2. Areas: Responsabilidades contínuas (ex: Saúde, Finanças, Carreira).\n"
            "  3. Resources: Temas de interesse e materiais de referência.\n"
            "  4. Archives: Itens completados ou inativos.\n"
            "- Ao reorganizar o Vault, você deve ser EXAUSTIVA. Analise cada nota individualmente.\n"
            "- Mapeie estruturas legadas (ex: '03 - Recursos') para as pastas padrão do PARA.\n"
            "- SEMPRE apresente um plano completo detalhando o destino de cada nota antes de executar.\n"
            "- Use a pasta 'Inbox' para capturas rápidas se não souber onde classificar.\n"
            "- SEMPRE utilize links internos (Wikilinks): [[Nome da Nota]] para conectar conceitos.\n"
            f"- Contextos recuperados do Vault:\n{context_str}\n\n"
            "GESTÃO OPERACIONAL (TICKTICK):\n"
            "- Você é responsável por manter a produtividade do usuário em dia.\n"
            "- Ao criar tarefas, seja específico e use o fuso horário UTC-03:00.\n"
            "- Formato de data para hoje às 23h: 'YYYY-MM-DDT23:00:00-0300'.\n"
            "- Se o usuário perguntar pelas tarefas:\n"
            f"  * De hoje: use get_ticktick_tasks(date_filter='{today_str}').\n"
            f"  * De amanhã: use get_ticktick_tasks(date_filter='{tomorrow_str}').\n"
            "  * Geral: use get_ticktick_tasks() sem filtros.\n"
            "- Sempre que uma tarefa for criada, verifique se ela deve gerar uma nota de apoio no Obsidian."
        )
        
        # A SystemMessage DEVE vir sempre em primeiro lugar absoluta.
        input_messages = [SystemMessage(content=system_content)] + messages
        
        # 3. Geração / Decisão
        response = await self.llm.ainvoke(input_messages)
        return {"messages": [response]}

    async def run(self, user_input: str) -> str:
        """Interface pública para executar o agente."""
        initial_state = {
            "messages": [("user", user_input)],
            "current_intent": None
        }
        result = await self._graph.ainvoke(initial_state)
        # Retornamos a última mensagem que não seja uma chamada de ferramenta
        for m in reversed(result["messages"]):
            if hasattr(m, "content") and m.content:
                return m.content
        return "Tarefa processada com sucesso."
