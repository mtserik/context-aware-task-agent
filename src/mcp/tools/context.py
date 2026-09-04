"""
MCP Context Tools — get_personal_context e set_reminder.

Zero-Token Principle: agregacao pura de dados REST + DB. Nenhum LLM envolvido.
"""
import logging
import os
from typing import Annotated, Optional

from mcp.server.fastmcp import FastMCP

from src.domain.tasks import TaskDomainService
from src.domain.reminders import ReminderDomainService
from src.domain.temporal import resolve_temporal_context

logger = logging.getLogger("MaeveMCP.tools.context")


def register_context_tools(mcp: FastMCP) -> None:
    """Registra as ferramentas de contexto pessoal e lembretes."""

    @mcp.tool(
        name="get_personal_context",
        description=(
            "Retorna um bloco de contexto pessoal e operacional estruturado do Erik: "
            "data/hora oficial de Brasilia (America/Sao_Paulo), momento circadiano do dia, "
            "tarefas prioritarias de hoje no TickTick. Ideal para injetar no system prompt "
            "do host LLM para ancoragem temporal e operacional realista."
        ),
    )
    async def get_personal_context() -> str:
        """Agrega contexto temporal e operacional do Erik. Retorna texto estruturado Markdown."""
        try:
            temporal = resolve_temporal_context()
            today_iso = temporal["iso"][:10]

            # Busca tarefas do dia
            tasks_svc = TaskDomainService()
            tasks_result = await tasks_svc.get_tasks(date_filter=today_iso)
            tasks_block = tasks_result.message if tasks_result.success else "Indisponivel no momento."

            period_label = {
                "manha": "Manha — energia alta, foco em Big Rocks e planejamento estrategico.",
                "tarde": "Tarde — tracao e execucao. Combater dispersao. Fechar o que foi iniciado.",
                "noite": "Noite — wrap-up, revisao do dia, anti-burnout. Evitar novas tarefas pesadas.",
                "madrugada": "Madrugada — foco cirurgico. Resolver o problema e descansar.",
            }.get(temporal["period"], temporal["period"])

            context = f"""# Contexto Pessoal & Operacional do Erik

## Dados Temporais
- **Data:** {temporal['date']} ({temporal['day_of_week']})
- **Hora:** {temporal['time']} ({temporal['timezone']}, UTC-3)
- **Periodo Circadiano:** {period_label}

## Backlog Operacional (TickTick — Hoje + Atrasadas)
{tasks_block}
"""
            return context
        except Exception as e:
            logger.error("Erro em get_personal_context: %s", e)
            return f"Erro ao montar contexto pessoal: {str(e)}"

    @mcp.tool(
        name="set_reminder",
        description=(
            "Agenda um lembrete no Supabase que sera entregue proativamente ao Erik "
            "via Telegram pelo worker de background da Maeve no horario especificado. "
            "Data/hora em ISO 8601: 'YYYY-MM-DDTHH:MM:SS'."
        ),
    )
    async def set_reminder(
        content: Annotated[str, "Texto do lembrete que sera enviado ao Erik via Telegram"],
        reminder_at: Annotated[str, "Data e hora do lembrete em ISO 8601 (ex: '2026-09-05T09:00:00')"],
    ) -> str:
        """Agenda lembrete no Supabase para entrega proativa via Telegram."""
        try:
            user_id = os.getenv("TELEGRAM_ALLOWED_USER_ID", "mcp_user")
            svc = ReminderDomainService()
            result = await svc.set_reminder(
                content=content,
                reminder_at=reminder_at,
                user_id=user_id,
                chat_id=user_id,
            )
            return result.message
        except Exception as e:
            logger.error("Erro em set_reminder: %s", e)
            return f"Erro ao agendar lembrete: {str(e)}"