"""
MCP Task Tools — deterministic wrappers over TaskDomainService (TickTick).

Zero-Token Principle: nenhuma chamada a LLM. Toda logica e REST pura contra o TickTick.
"""
import logging
from typing import Annotated, Optional, List

from mcp.server.fastmcp import FastMCP

from src.domain.tasks import TaskDomainService
from src.domain.temporal import resolve_temporal_context

logger = logging.getLogger("MaeveMCP.tools.tasks")


def register_task_tools(mcp: FastMCP) -> None:
    """Registra as ferramentas de tarefas no servidor FastMCP."""

    @mcp.tool(
        name="list_today_tasks",
        description=(
            "Lista as tarefas pendentes do Erik para hoje no TickTick com prioridade, "
            "status, time-blocking e dados de projeto. Inclui automaticamente um lookback "
            "de 7 dias para capturar itens atrasados. Use sempre que precisar do contexto "
            "operacional do dia ou planejar o backlog."
        ),
    )
    async def list_today_tasks(
        project_id: Annotated[Optional[str], "ID de projeto especifico para filtrar (opcional)"] = None,
    ) -> str:
        """Lista tarefas do dia no TickTick com lookback de 7 dias para atrasadas."""
        try:
            temporal = resolve_temporal_context()
            today_iso = temporal["iso"][:10]  # YYYY-MM-DD

            svc = TaskDomainService()
            result = await svc.get_tasks(date_filter=today_iso, project_id=project_id)
            return result.message
        except Exception as e:
            logger.error("Erro em list_today_tasks: %s", e)
            return f"Erro ao buscar tarefas: {str(e)}"

    @mcp.tool(
        name="create_task",
        description=(
            "Cria uma nova tarefa no TickTick diretamente a partir do contexto de trabalho "
            "no Antigravity. Suporta time-blocking (start_date + due_date), prioridades "
            "(0=None, 1=Low, 3=Medium, 5=High) e associacao a projetos. "
            "Datas devem ser em ISO 8601: 'YYYY-MM-DDTHH:MM:SS'."
        ),
    )
    async def create_task(
        title: Annotated[str, "Titulo da tarefa"],
        content: Annotated[str, "Descricao detalhada ou checklist da tarefa (Markdown suportado)"] = "",
        due_date: Annotated[Optional[str], "Data/hora de vencimento ISO 8601 (ex: '2026-09-05T17:00:00')"] = None,
        priority: Annotated[int, "Prioridade: 0=None, 1=Low, 3=Medium, 5=High"] = 0,
        project_id: Annotated[Optional[str], "ID do projeto TickTick de destino (opcional)"] = None,
    ) -> str:
        """Cria tarefa no TickTick com normalizacao de datas para fuso de Brasilia."""
        try:
            svc = TaskDomainService()
            result = await svc.create_task(
                title=title,
                content=content,
                due_date=due_date,
                priority=priority,
                project_id=project_id,
            )
        except Exception as e:
            logger.error("Erro em create_task: %s", e)
            return f"Erro ao criar tarefa: {str(e)}"

    @mcp.tool(
        name="create_focus_block",
        description=(
            "Cria um Bloco de Foco consolidado (Princípio Anti-Bagunça / Chunking) no TickTick. "
            "Agrupa múltiplos itens em uma checklist interna dentro de UM único bloco de tempo (ex: 1h30, 2h), "
            "alocando automaticamente no projeto correto (Mestrado, Trabalho, etc.) e evitando poluição da agenda."
        ),
    )
    async def create_focus_block(
        title: Annotated[str, "Título do bloco de foco (ex: 'Resolução PM003: Questões 35 a 39')"],
        category: Annotated[str, "Categoria/Projeto do bloco: 'Mestrado', 'Trabalho', 'Pessoal'"] = "Mestrado",
        duration_minutes: Annotated[int, "Duração estimada do bloco em minutos (default: 120 = 2h)"] = 120,
        checklist: Annotated[Optional[List[str]], "Lista de itens ou questões específicas que compõem o bloco"] = None,
        due_date: Annotated[Optional[str], "Data de realização do bloco em ISO 8601 (ex: '2026-09-07T09:00:00')"] = None,
        priority: Annotated[int, "Prioridade: 0=None, 1=Low, 3=Medium, 5=High"] = 3,
    ) -> str:
        """Cria bloco de foco consolidado no TickTick."""
        try:
            svc = TaskDomainService()
            result = await svc.create_focus_block(
                title=title,
                category=category,
                duration_minutes=duration_minutes,
                checklist=checklist,
                due_date=due_date,
                priority=priority
            )
            return result.message
        except Exception as e:
            logger.error("Erro em create_focus_block: %s", e)
            return f"Erro ao criar bloco de foco: {str(e)}"