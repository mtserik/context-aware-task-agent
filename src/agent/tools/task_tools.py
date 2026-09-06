from typing import List, Dict, Any, Optional
from langchain_core.tools import tool
from src.domain.tasks import TaskDomainService, normalize_ticktick_date

_task_domain = TaskDomainService()

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
    
    DATAS: 'due_date' pode ser enviado no formato ISO UTC ('YYYY-MM-DDTHH:MM:SSZ') ou local de São Paulo ('YYYY-MM-DDTHH:MM:SS' / 'YYYY-MM-DD'). O sistema normaliza automaticamente para UTC para o backend do TickTick.
    PRIORIDADES: 0: Nenhuma, 1: Baixa, 3: MÉDIA, 5: ALTA.
    
    SEQUÊNCIA OBRIGATÓRIA PARA SUBTAREFAS:
    1. Primeiro, crie a TAREFA PAI (deixe parent_id como None).
    2. Pegue o ID retornado (ID_CRIADO: ...).
    3. Chame novamente para cada subtarefa, passando o ID do pai no campo 'parent_id'.
    """
    result = await _task_domain.create_task(
        title=title,
        content=content,
        due_date=due_date,
        priority=priority,
        project_id=project_id,
        parent_id=parent_id
    )
    return result.to_agent_message()

@tool
async def batch_update_ticktick_tasks(tasks_to_update: List[Dict[str, Any]]):
    """
    ÚNICA ferramenta para atualizar tarefas no TickTick (seja 1 ou várias).
    Use para mudar datas, títulos, projetos ou concluir tarefas.
    Cada objeto DEVE ter: {"task_id": "...", "title": "...", "project_id": "..."}
    Campos suportados: "due_date" (Fim), "start_date" (Início), "status", "priority".
    DICA: Para Time Blocking (duração), envie datas de início e fim no mesmo dia com horários diferentes.
    """
    result = await _task_domain.batch_update_tasks(tasks_to_update)
    return result.to_agent_message()

@tool
async def create_ticktick_project(name: str, color: str = None, view_mode: str = "list"):
    """Cria um novo projeto (lista) no TickTick. Prefere MCP com fallback para REST."""
    result = await _task_domain.create_project(name=name, color=color, view_mode=view_mode)
    return result.to_agent_message()

@tool
async def batch_create_ticktick_tasks(tasks: List[Dict[str, Any]]):
    """
    Cria múltiplas tarefas ou subtarefas no TickTick em lote via MCP em uma única chamada.
    Use sempre que precisar criar listas de tarefas, projetos com histórias/entregáveis ou planos de ação.
    Cada item na lista DEVE ser um dicionário: {"title": "...", "content": "...", "due_date": "...", "priority": 0, "project_id": "...", "parent_id": "..."}
    """
    result = await _task_domain.batch_create_tasks(tasks)
    return result.to_agent_message()

@tool
async def get_ticktick_tasks(date_filter: str = None, project_id: str = None):
    """
    Lista tarefas PENDENTES do Erik com lookback de 7 dias para atrasadas.
    date_filter: data no formato 'YYYY-MM-DD' (ex: '2026-09-04') ou 'today' / 'hoje'.
    A camada de domínio converte automaticamente os carimbos UTC do TickTick para o fuso de São Paulo (UTC-3),
    garantindo que tarefas agendadas para a noite ou o dia civil correto sejam exibidas com precisão.
    As datas de vencimento retornadas já estarão formatadas para São Paulo - Brasil (DD/MM/YYYY HH:mm).
    """
    result = await _task_domain.get_tasks(date_filter=date_filter, project_id=project_id)
    return result.to_agent_message()

@tool
async def get_ticktick_item_details(item_id: str):
    """
    Obtém o conteúdo COMPLETO e detalhes de uma tarefa ou nota específica.
    Use para ler o que está escrito dentro de uma nota antes de replicar no Obsidian.
    """
    result = await _task_domain.get_task_details(item_id=item_id)
    return result.to_agent_message()

@tool
async def delete_ticktick_item(project_id: str, item_id: str):
    """Remove definitivamente uma tarefa ou nota do TickTick."""
    result = await _task_domain.delete_task(project_id=project_id, item_id=item_id)
    return result.to_agent_message()

@tool
async def list_ticktick_structure(include_groups: bool = True):
    """
    Lista a estrutura de pastas (Grupos) e Listas (Projetos) do TickTick.
    Use para se localizar e saber em qual lista criar ou buscar algo.
    """
    result = await _task_domain.list_structure(include_groups=include_groups)
    return result.to_agent_message()

@tool
async def verify_task_creation(task_id: str):
    """
    Verifica se uma tarefa recém-criada realmente existe e em qual projeto ela caiu.
    """
    result = await _task_domain.verify_task(task_id=task_id)
    return result.to_agent_message()

@tool
async def get_ticktick_metrics_via_mcp(query_type: str, start_date: str = None):
    """Obtém métricas via MCP (habits, focus_records, tasks_completed)."""
    result = await _task_domain.get_metrics(query_type=query_type, start_date=start_date)
    return result.to_agent_message()

from src.agent.tools.mcp_bridge import mcp_bridge

_BASE_TASK_TOOLS = [
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
]

# Combina ferramentas de domínio com ferramentas dinâmicas nativas do TickTick MCP (ex: get_project_with_undone_tasks)
_seen_tool_names = set()
_all_task_tools = []

for tool in _BASE_TASK_TOOLS + mcp_bridge.get_tools():
    t_name = getattr(tool, "name", str(tool))
    if t_name not in _seen_tool_names:
        _seen_tool_names.add(t_name)
        _all_task_tools.append(tool)

TASK_TOOLS = _all_task_tools
