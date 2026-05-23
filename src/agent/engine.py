import os
from datetime import datetime, timedelta
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

# --- Definição das Tools ---
ticktick = TickTickService()
obsidian = ObsidianService()
vector_db = VectorDBService()
db_service = DatabaseService()

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
    old_path: Caminho relativo atual (ex: 'Inbox/Nota.md').
    new_path: Novo caminho relativo (ex: 'Resources/Nota.md').
    IMPORTANTE: Se for mover várias notas, chame esta ferramenta uma vez para cada nota. 
    Não tente mover pastas de sistema como 'Inbox', 'Projects', etc, apenas o conteúdo delas.
    """
    # Proteção simples contra mover pastas raiz do PARA
    protected = ["Inbox", "Projects", "Areas", "Resources", "Archives", "00 - Inbox"]
    if old_path.strip("/") in protected and not old_path.endswith(".md"):
        return f"Erro: Você tentou mover a pasta raiz '{old_path}'. Mova apenas os arquivos dentro dela."

    commit_msg = f"Maeve: Moveu '{old_path}' para '{new_path}'"
    success = await obsidian.move_item(old_path, new_path, commit_message=commit_msg)
    if success:
        return f"Item movido de '{old_path}' para '{new_path}' com sucesso."
    return f"Erro: O caminho de origem '{old_path}' não foi encontrado ou é inválido."

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

@tool
async def list_obsidian_notes():
    """
    Retorna a lista de todas as notas (caminhos relativos) no Vault.
    Útil para ter uma visão geral de todo o conhecimento disponível.
    """
    notes = await obsidian.list_all_notes()
    if not notes:
        return "Nenhuma nota encontrada no Vault."
    return "Notas encontradas:\n" + "\n".join([f"- {n}" for n in notes])

@tool
async def get_obsidian_note_details(relative_path: str):
    """
    Retorna metadados de uma nota específica (título, pasta, links, frontmatter).
    Útil para analisar a organização, conexões e metadados YAML de uma nota.
    """
    metadata = await obsidian.get_note_metadata(relative_path)
    if not metadata:
        return f"Erro: Nota '{relative_path}' não encontrada."
    
    links_str = ", ".join(metadata['links']) if metadata['links'] else "Nenhum link"
    fm_str = yaml.dump(metadata['frontmatter'], allow_unicode=True) if metadata['frontmatter'] else "Nenhum metadado YAML"
    
    return (
        f"Detalhes da nota:\n"
        f"- Título: {metadata['title']}\n"
        f"- Caminho: {metadata['path']}\n"
        f"- Pasta atual: {metadata['folder']}\n"
        f"- Links detectados: {links_str}\n"
        f"- Metadados (YAML):\n{fm_str}\n"
        f"- Tamanho: {metadata['char_count']} caracteres"
    )

@tool
async def get_obsidian_backlinks(note_title: str):
    """
    Retorna a lista de notas que citam (fazem link para) a nota especificada.
    Útil para entender o impacto de uma nota ou encontrar contextos relacionados.
    """
    backlinks = await obsidian.get_backlinks(note_title)
    if not backlinks:
        return f"Nenhuma nota cita [[{note_title}]] no momento."
    return f"Notas que citam [[{note_title}]]:\n" + "\n".join([f"- {b}" for b in backlinks])

@tool
async def create_obsidian_note_from_template(title: str, template_name: str, variables: Dict[str, str], folder: str = "Inbox"):
    """
    Cria uma nova nota baseada em um template pré-definido em .maeve/templates.
    variables: Dicionário com chave e valor para substituir no template (ex: {'date': '2024-05-23'}).
    folder: Pasta de destino. Padrão é 'Inbox'.
    """
    content = await obsidian.apply_template(template_name, variables)
    if content.startswith("Erro:"):
        return content
        
    filename = f"{title}.md" if not title.endswith(".md") else title
    relative_path = os.path.join(folder, filename)
    commit_msg = f"Maeve: Criou nota '{title}' usando template '{template_name}'"
    await obsidian.write_note(relative_path, content, commit_message=commit_msg)
    return f"Nota '{title}' criada com sucesso usando o template '{template_name}'."

@tool
async def get_obsidian_note_content(relative_path: str):
    """
    Lê o conteúdo completo de uma nota Markdown.
    """
    # ObsidianService.get_note_content espera caminho absoluto ou relativo?
    # No obsidian.py, ele checa se existe. Se passarmos relativo, ele pode falhar se não estiver no CWD.
    # Mas o ObsidianService.get_note_content atual usa file_path diretamente.
    # Vou ajustar o obsidian.py para aceitar relativo se necessário, ou aqui passamos o absoluto.
    full_path = os.path.join(obsidian.vault_path, relative_path)
    content = await obsidian.get_note_content(full_path)
    if not content:
        return f"Erro: Não foi possível ler a nota '{relative_path}'."
    return f"Conteúdo de '{relative_path}':\n\n{content}"

@tool
async def suggest_obsidian_links(relative_path: str):
    """
    Sugere links internos para uma nota baseado no conteúdo de outras notas no Vault.
    Analisa semanticamente o conteúdo para encontrar conexões relevantes.
    """
    full_path = os.path.join(obsidian.vault_path, relative_path)
    content = await obsidian.get_note_content(full_path)
    if not content:
        return f"Erro: Não foi possível ler a nota '{relative_path}'."
    
    # Busca notas relacionadas no Qdrant
    related = await vector_db.search_context(content, limit=5)
    
    # Filtra a própria nota e extrai títulos
    suggestions = []
    current_title = os.path.basename(relative_path).replace(".md", "")
    
    for doc in related:
        title = doc['metadata'].get('title')
        path = doc['metadata'].get('path')
        if title and title != current_title:
            suggestions.append(f"- [[{title}]] (em {path})")
            
    if not suggestions:
        return "Não foram encontradas sugestões de links relevantes no momento."
        
    return "Sugestões de links baseadas em similaridade semântica:\n" + "\n".join(suggestions)

@tool
async def suggest_note_folder(relative_path: str):
    """
    Analisa o conteúdo e metadados de uma nota para sugerir a melhor pasta no método PARA.
    Retorna a pasta sugerida e a justificativa.
    """
    metadata = await obsidian.get_note_metadata(relative_path)
    if not metadata:
        return f"Erro: Nota '{relative_path}' não encontrada."
    
    full_path = os.path.join(obsidian.vault_path, relative_path)
    content = await obsidian.get_note_content(full_path)
    
    # Aqui poderíamos usar uma chamada dedicada ao LLM ou apenas deixar o Agente decidir.
    # Como este é um 'tool', ele deve retornar uma sugestão.
    # Vou retornar um prompt para o próprio agente decidir se ele for o chamador, 
    # ou podemos fazer uma mini-inferência aqui se tivermos um prompt fixo.
    
    # Para simplificar e dar poder ao Agente, o tool retornará os dados organizados para análise.
    return (
        f"Análise de Classificação PARA para '{relative_path}':\n"
        f"Conteúdo resumido: {content[:500]}...\n"
        f"Pasta atual: {metadata['folder']}\n"
        "Por favor, decida se esta nota deve ser movida para: Projects, Areas, Resources ou Archives baseado no conteúdo."
    )

@tool
async def sync_obsidian_knowledge():
    """
    Sincroniza proativamente o conhecimento da Maeve com o Vault remoto.
    Realiza git pull, lê todas as notas e atualiza o banco vetorial Qdrant.
    Use esta ferramenta quando:
    1. O usuário pedir para atualizar ou sincronizar as notas.
    2. Você suspeitar que seu conhecimento local está desatualizado.
    3. Você for realizar uma tarefa de reorganização em massa (PARA).
    """
    try:
        # 1. Sincronizar com o Git (Pull)
        await obsidian.sync()
        
        # 2. Listar todos os arquivos .md
        notes = await obsidian.list_all_notes()
        if not notes:
            return "Sincronização concluída: Nenhuma nota encontrada no Vault."

        # 3. Processar e indexar cada nota
        texts = []
        metadatas = []
        
        for note_path in notes:
            content = await obsidian.get_note_content(note_path)
            if content.strip():
                metadata = await obsidian.get_note_metadata(note_path)
                full_text = f"Título: {metadata['title']}\nCaminho: {metadata['path']}\nConteúdo: {content}"
                
                texts.append(full_text)
                metadatas.append({
                    "source": "obsidian", 
                    "path": metadata['path'], 
                    "title": metadata['title'],
                    "folder": metadata['folder']
                })

        # 4. Upsert no Qdrant
        if texts:
            await vector_db.upsert_documents(texts=texts, metadatas=metadatas)

        return f"Sincronização proativa concluída com sucesso! {len(texts)} notas indexadas."
    except Exception as e:
        return f"Erro durante a sincronização proativa: {str(e)}"

tools = [
    create_ticktick_task, 
    get_ticktick_tasks, 
    create_obsidian_note, 
    list_obsidian_folders, 
    delete_obsidian_item, 
    move_obsidian_item, 
    cleanup_empty_obsidian_folders,
    list_obsidian_notes,
    get_obsidian_note_details,
    get_obsidian_note_content,
    suggest_obsidian_links,
    suggest_note_folder,
    sync_obsidian_knowledge,
    get_obsidian_backlinks,
    create_obsidian_note_from_template
]
tool_node = ToolNode(tools)

class MaeveAgent:
    def __init__(self, checkpointer=None, model_name: str = "gpt-4o-mini"):
        self.vector_db = vector_db
        self.llm = ChatOpenAI(model=model_name, temperature=0).bind_tools(tools)
        self._graph = self._build_graph(checkpointer)

    def _build_graph(self, checkpointer):
        """Define a estrutura interna do LangGraph com suporte a ferramentas e persistência."""
        workflow = StateGraph(AgentState)
        
        workflow.add_node("call_model", self._call_model_node)
        workflow.add_node("tools", tool_node)
        
        workflow.set_entry_point("call_model")
        
        # Lógica de roteamento
        def should_continue(state: AgentState):
            messages = state['messages']
            last_message = messages[-1]
            if last_message.tool_calls:
                return "tools"
            return END

        workflow.add_conditional_edges("call_model", should_continue)
        workflow.add_edge("tools", "call_model")
        
        return workflow.compile(checkpointer=checkpointer)

    async def _call_model_node(self, state: AgentState):
        """Lógica de processamento do nó com RAG e Tool Calling."""
        from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
        
        # 0. Saneamento de Histórico (Evita erro 400 da OpenAI)
        raw_messages = state['messages']
        clean_messages = []
        for i, m in enumerate(raw_messages):
            # Se for AIMessage com tool_calls, verifica se há ToolMessages correspondentes depois
            if isinstance(m, AIMessage) and m.tool_calls:
                has_response = False
                if i + 1 < len(raw_messages) and isinstance(raw_messages[i+1], ToolMessage):
                    has_response = True
                
                # Só mantém se tiver resposta ou se for a última mensagem do turno anterior 
                # (o LangGraph vai cuidar de chamar a tool se for o caso)
                if has_response:
                    clean_messages.append(m)
                else:
                    print(f"🧹 Removendo chamada de ferramenta órfã: {m.tool_calls[0]['name']}")
                    continue
            else:
                clean_messages.append(m)

        # 1. Recuperação de Contexto (RAG)
        last_user_query = ""
        for m in reversed(clean_messages):
            if isinstance(m, HumanMessage) or (isinstance(m, tuple) and m[0] == "user"):
                last_user_query = m.content if hasattr(m, "content") else m[1]
                break
        
        context_str = ""
        if last_user_query:
            context_docs = await self.vector_db.search_context(last_user_query)
            context_str = "\n".join([
                f"- [{doc['metadata'].get('title', 'Sem título')}]({doc['metadata'].get('path', 'sem-caminho')}):\n{doc['content'][:500]}..." 
                for doc in context_docs
            ])
        
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
            "DIRETRIZES DE EXECUÇÃO E INTELIGÊNCIA:\n"
            "- MEMÓRIA AUTOMÁTICA: Você possui memória persistente de conversa (via Supabase). Você NÃO precisa criar notas no Obsidian para lembrar de fatos simples ou preferências ditas no chat, a menos que o usuário peça explicitamente por uma nota.\n"
            "- INTEGRIDADE EM PRIMEIRO LUGAR: Sua prioridade é a realidade dos arquivos no disco, não a sua memória. Se uma ferramenta diz que o arquivo ainda está lá, ele ESTÁ lá.\n"
            "- VERIFICAÇÃO CONTÍNUA: Após cada ação de escrita, movimentação ou deleção, você DEVE usar `list_obsidian_notes` para confirmar o resultado. Não presuma sucesso.\n"
            "- RESILIÊNCIA A ERROS: Se o Git falhar, informe ao usuário o erro técnico real. Não tente mascarar falhas.\n"
            "- FIDELIDADE ESTRITA: Processe 100% dos itens aprovados em um plano. Se o plano tem 20 notas, mova as 20.\n"
            "- PENSAMENTO ALGORÍTMICO: Siga sempre o fluxo: LISTAR ATUAL -> ANALISAR -> PLANEJAR -> EXECUTAR -> VERIFICAR FINAL.\n\n"
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
        input_messages = [SystemMessage(content=system_content)] + clean_messages
        
        # 3. Geração / Decisão
        response = await self.llm.ainvoke(input_messages)
        return {"messages": [response]}

    async def run(self, user_input: str, thread_id: str = "default-thread") -> str:
        """Interface pública para executar o agente com persistência."""
        initial_state = {
            "messages": [("user", user_input)],
            "current_intent": None
        }
        config = {"configurable": {"thread_id": thread_id}}
        
        result = await self._graph.ainvoke(initial_state, config=config)
        
        # Retornamos a última mensagem que não seja uma chamada de ferramenta
        for m in reversed(result["messages"]):
            if hasattr(m, "content") and m.content:
                return m.content
        return "Tarefa processada com sucesso."
