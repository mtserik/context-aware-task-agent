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
from src.services.registry import get_profile_service, get_journal_service

logger = logging.getLogger("MaeveMCP.tools.context")


def register_context_tools(mcp: FastMCP) -> None:
    """Registra as ferramentas de contexto pessoal, perfil do Erik e diário noturno."""

    @mcp.tool(
        name="get_personal_context",
        description=(
            "Retorna um bloco de contexto pessoal e operacional estruturado do Erik: "
            "data/hora oficial de Brasília (America/Sao_Paulo), momento circadiano do dia, "
            "tarefas prioritárias de hoje no TickTick, e o Modelo Mental de Perfil/Padrões "
            "do Erik (estilo cognitivo, focos de mestrado/carreira, preferências). "
            "Ideal para injetar no system prompt do host LLM para ancoragem contextual realista."
        ),
    )
    async def get_personal_context() -> str:
        """Agrega contexto temporal, operacional e comportamental do Erik."""
        try:
            temporal = resolve_temporal_context()
            today_iso = temporal["iso"][:10]

            # 1. Busca tarefas do dia no TickTick
            tasks_svc = TaskDomainService()
            tasks_result = await tasks_svc.get_tasks(date_filter=today_iso)
            tasks_block = tasks_result.message if tasks_result.success else "Indisponivel no momento."

            period_label = {
                "manha": "Manhã — energia alta, foco em Big Rocks e planejamento estratégico.",
                "tarde": "Tarde — tração e execução. Combater dispersão. Fechar o que foi iniciado.",
                "noite": "Noite — wrap-up, revisão do dia, descompressão reflexiva. Evitar novas tarefas pesadas.",
                "madrugada": "Madrugada — foco cirúrgico. Resolver o problema e descansar.",
            }.get(temporal["period"], temporal["period"])

            # 2. Busca perfil e padrões vivos do Erik
            profile_block = ""
            try:
                profile_svc = get_profile_service()
                profile_block = await profile_svc.get_active_profile_summary()
            except Exception as p_err:
                logger.warning("Aviso ao buscar perfil pessoal: %s", p_err)

            context = f"""# Contexto Pessoal & Operacional do Erik

## Dados Temporais
- **Data:** {temporal['date']} ({temporal['day_of_week']})
- **Hora:** {temporal['time']} ({temporal['timezone']}, UTC-3)
- **Periodo Circadiano:** {period_label}

## Backlog Operacional (TickTick — Hoje + Atrasadas)
{tasks_block}

{profile_block}
"""
            return context.strip()
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

    @mcp.tool(
        name="log_daily_journal",
        description=(
            "Registra o Diário Noturno do Erik no Obsidian Vault em 'Diário/YYYY-MM-DD.md'. "
            "Sintetiza as reflexões livres do dia, humor, nível de energia (1-10) e vitórias/destaques. "
            "Vetoriza no Qdrant para memória semântica e atualiza silenciosamente os insights de perfil do Erik."
        ),
    )
    async def log_daily_journal(
        thoughts: Annotated[str, "Reflexões pessoais, desabafo ou relato do Erik sobre como foi o dia"],
        mood: Annotated[str, "Humor / Estado de espírito do Erik (ex: 'Produtivo', 'Cansado mas realizado', 'Inspirado')"] = "Produtivo",
        energy: Annotated[int, "Nível de energia percibido de 1 a 10"] = 8,
        highlights: Annotated[str, "Destaques, conquistas, tarefas vencidas ou aprendizados centrais do dia"] = "",
    ) -> str:
        """Registra e versiona o Diário Noturno no Obsidian."""
        try:
            journal_svc = get_journal_service()
            result = await journal_svc.log_journal(
                thoughts=thoughts,
                mood=mood,
                energy=energy,
                highlights=highlights
            )
            if result.get("success"):
                return f"✅ {result.get('message')}\n📂 Arquivo: {result.get('path')}\n✨ Humor: {result.get('mood')} | Energia: {result.get('energy')}/10"
            return f"Erro ao registrar diário: {result.get('error')}"
        except Exception as e:
            logger.error("Erro em log_daily_journal: %s", e)
            return f"Erro ao registrar diário: {str(e)}"

    @mcp.tool(
        name="log_user_insight",
        description=(
            "Registra um novo aprendizado ou padrão comportamental/operacional sobre o Erik. "
            "Categorias válidas: 'foco_atual', 'estilo_cognitivo', 'carreira_stack', "
            "'preferencia_pessoal', 'cultura_gostos', 'ritmo_energia'. "
            "Persiste no Supabase, vetoriza no Qdrant e sincroniza a nota 'Perfil Pessoal e Padrões - Erik'."
        ),
    )
    async def log_user_insight(
        category: Annotated[str, "Categoria do insight: 'foco_atual', 'estilo_cognitivo', 'carreira_stack', 'preferencia_pessoal', 'cultura_gostos', 'ritmo_energia'"],
        insight: Annotated[str, "Descrição clara e concisa do padrão, preferência ou aprendizado observado"],
        source: Annotated[str, "Origem da observação (ex: 'diario_noturno', 'chat', 'feedback_mestrado')"] = "chat",
    ) -> str:
        """Registra insight no perfil vivo do Erik."""
        try:
            profile_svc = get_profile_service()
            result = await profile_svc.add_insight(
                category=category,
                insight=insight,
                source=source
            )
            return f"✅ Insight registrado em '{result.get('category')}': {result.get('insight')}"
        except Exception as e:
            logger.error("Erro em log_user_insight: %s", e)
            return f"Erro ao registrar insight: {str(e)}"