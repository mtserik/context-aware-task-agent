import logging
from typing import Optional, Dict, Any

from src.domain.temporal import resolve_temporal_context
from src.domain.tasks import TaskDomainService
from src.services.registry import get_database_service

logger = logging.getLogger("SessionDomainService")


class SessionDomainService:
    """
    Serviço de Domínio para montagem do Bloco de Contexto Operacional de Sessão.
    Garante que toda nova conversa iniciada no Telegram ou outras interfaces receba
    a mesma ancoragem de alta fidelidade que o Antigravity possui via get_personal_context.
    """

    def __init__(self, task_service: Optional[TaskDomainService] = None):
        self._tasks = task_service or TaskDomainService()
        self._db = get_database_service()

    async def build_session_context_block(self, user_id: str) -> str:
        """
        Monta um bloco estruturado contendo:
        1. Contexto Temporal estrito (Brasília / America/Sao_Paulo).
        2. Backlog Operacional completo do TickTick (Hoje + Atrasadas com IDs e Projetos).
        3. Metas e Modelo Mental ativo do Erik (Perfil / Supabase).
        """
        temporal = resolve_temporal_context()
        today_iso = temporal["date"]  # YYYY-MM-DD

        # 1. Backlog Operacional do TickTick (Hoje + Atrasadas)
        tasks_block = "Nenhuma tarefa pendente encontrada."
        try:
            task_res = await self._tasks.get_tasks(date_filter="today")
            if task_res.success and task_res.message:
                tasks_block = task_res.message
        except Exception as e:
            logger.warning("Falha ao carregar tarefas para contexto de sessão: %s", e)
            tasks_block = f"⚠️ Não foi possível consultar tarefas no momento ({e})."

        # 2. Insights e Metas do Perfil (Supabase)
        insights_block = ""
        try:
            insights = await self._db.get_user_insights(user_id=user_id, limit=6)
            if insights:
                insights_block = "\n".join([f"- [{i['category'].upper()}] {i['insight']}" for i in insights])
        except Exception as e:
            logger.warning("Falha ao carregar insights para contexto de sessão: %s", e)

        context_lines = [
            "# CONTEXTO OPERACIONAL ATIVO DA SESSÃO (NOVA CONVERSA)",
            f"- **Data Atual:** {temporal['date']} ({temporal['day_of_week']})",
            f"- **Hora Oficial:** {temporal['time']} (Horário de Brasília, UTC-3)",
            f"- **Momento Circadiano:** {temporal['period']}",
            "",
            "## 📋 Backlog Operacional no TickTick (Hoje + Atrasadas)",
            tasks_block,
        ]

        if insights_block:
            context_lines.extend([
                "",
                "## 👤 Metas & Padrões Ativos do Erik",
                insights_block,
            ])

        return "\n".join(context_lines)
